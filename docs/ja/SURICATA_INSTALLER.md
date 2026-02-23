# Suricata インストーラー (Azazel-Edge)

このドキュメントでは、このリポジトリに含まれるインストーラー`scripts/install_suricata_env.sh`について説明します。このインストーラーは、Pi上で使用されるSuricataランタイム環境を再構築します。

## インストーラーの機能

### システム設定

1. **システムユーザー作成**: `suricata`ユーザーを作成
2. **ディレクトリ設定**: `/var/lib/suricata`と`/var/log/suricata`を作成し、`suricata`ユーザーの所有に設定
3. **systemdドロップイン作成**: 必要なケーパビリティ（CAP_NET_RAW、CAP_NET_ADMIN）を持つ`suricata`ユーザーでSuricataを実行
4. **更新ラッパー**: `/usr/local/bin/azazel-suricata-update.sh`に更新ラッパーをインストール
5. **自動更新**: 日次実行のsystemdサービス+タイマーをインストール
6. **障害処理**: 更新失敗をログ記録する障害ハンドラーをインストール
7. **ログローテーション**: 更新ログ用のlogrotateルールをインストール
8. **ルール配布**: `configs/suricata/local.rules`をランタイムルールディレクトリに配布

## 使用方法

### 基本インストール

ターゲットのRaspberry Pi上でrootとして実行：

```bash
sudo bash scripts/install_suricata_env.sh
```

### インストール後の検証

スクリプト完了後、Suricataが実行され、期待されるインターフェース（例：`wlan1`）を監視していることを確認：

```bash
# Suricataサービス状態を確認
systemctl status suricata

# Suricataログを確認
journalctl -u suricata -n 50 --no-pager

# アラートイベントを確認
cat /var/log/suricata/eve.json | jq 'select(.event_type=="alert")' | head -n 5

# 統計情報を確認
cat /var/log/suricata/eve.json | jq 'select(.event_type=="stats")' | tail -n 1
```

## 詳細なインストール手順

### 1. 前提条件の確認

```bash
# Suricataがインストールされていることを確認
suricata --version

# 必要なパッケージの確認
dpkg -l | grep -E "(jq|systemd|logrotate)"

# ネットワークインターフェースの確認
ip link show
```

### 2. 手動インストール手順

システム要件を満たさない場合の手動設定手順：

#### システムユーザー作成

```bash
# suricataユーザーを作成
sudo useradd -r -s /bin/false -d /var/lib/suricata suricata

# グループ確認
id suricata
```

#### ディレクトリ設定

```bash
# 必要なディレクトリを作成
sudo mkdir -p /var/lib/suricata
sudo mkdir -p /var/log/suricata
sudo mkdir -p /etc/suricata/rules

# 所有者を設定
sudo chown -R suricata:suricata /var/lib/suricata
sudo chown -R suricata:suricata /var/log/suricata
sudo chown -R suricata:root /etc/suricata
```

#### systemd設定

```bash
# systemdドロップインディレクトリを作成
sudo mkdir -p /etc/systemd/system/suricata.service.d

# ドロップイン設定を作成
sudo tee /etc/systemd/system/suricata.service.d/azazel.conf <<EOF
[Service]
User=suricata
Group=suricata
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN CAP_SYS_NICE
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN CAP_SYS_NICE
NoNewPrivileges=yes
EOF

# systemdを再読み込み
sudo systemctl daemon-reload
```

#### 更新スクリプト設定

```bash
# 更新スクリプトを作成
sudo tee /usr/local/bin/azazel-suricata-update.sh <<'EOF'
#!/bin/bash
# Azazel-Edge Suricata rule updater

set -euo pipefail

LOG_FILE="/var/log/suricata/update.log"
LOCK_FILE="/var/run/suricata-update.lock"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"
}

cleanup() {
    rm -f "$LOCK_FILE"
}

trap cleanup EXIT

# 排他制御
if [ -f "$LOCK_FILE" ]; then
    log "ERROR: Another update is running (lock file exists)"
    exit 1
fi

touch "$LOCK_FILE"

log "INFO: Starting Suricata rule update"

# suricata-updateの実行
if suricata-update --suricata /usr/bin/suricata --output /etc/suricata/rules/; then
    log "INFO: Rules updated successfully"
    
    # 設定テスト
    if suricata -T -c /etc/suricata/suricata.yaml; then
        log "INFO: Configuration test passed"
        
        # Suricataをリロード
        if systemctl reload suricata; then
            log "INFO: Suricata reloaded successfully"
        else
            log "ERROR: Failed to reload Suricata"
            exit 1
        fi
    else
        log "ERROR: Configuration test failed"
        exit 1
    fi
else
    log "ERROR: Rule update failed"
    exit 1
fi

log "INFO: Update completed successfully"
EOF

# 実行権限を設定
sudo chmod +x /usr/local/bin/azazel-suricata-update.sh
```

#### 自動更新タイマー設定

```bash
# systemdサービスを作成
sudo tee /etc/systemd/system/azazel-suricata-update.service <<EOF
[Unit]
Description=Azazel-Edge Suricata Rule Update
Documentation=https://github.com/01rabbit/Azazel-Edge
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
ExecStart=/usr/local/bin/azazel-suricata-update.sh
StandardOutput=journal
StandardError=journal
EOF

# systemdタイマーを作成
sudo tee /etc/systemd/system/azazel-suricata-update.timer <<EOF
[Unit]
Description=Daily Azazel-Edge Suricata Rule Update
Documentation=https://github.com/01rabbit/Azazel-Edge

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=3600

[Install]
WantedBy=timers.target
EOF

# タイマーを有効化
sudo systemctl daemon-reload
sudo systemctl enable --now azazel-suricata-update.timer
```

#### ログローテーション設定

```bash
# logrotateルールを作成
sudo tee /etc/logrotate.d/azazel-suricata <<EOF
/var/log/suricata/update.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}

/var/log/suricata/eve.json {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 suricata suricata
    postrotate
        /bin/systemctl reload suricata > /dev/null 2>&1 || true
    endscript
}

/var/log/suricata/fast.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 suricata suricata
    postrotate
        /bin/systemctl reload suricata > /dev/null 2>&1 || true
    endscript
}
EOF
```

### 3. カスタムルールの配布

```bash
# ローカルルールディレクトリを作成
sudo mkdir -p /etc/suricata/rules/local

# Azazel-Edge固有のルールを配布
sudo cp configs/suricata/local.rules /etc/suricata/rules/local/

# ルールファイルの権限設定
sudo chown root:suricata /etc/suricata/rules/local/local.rules
sudo chmod 644 /etc/suricata/rules/local/local.rules
```

## 設定とカスタマイズ

### Suricata設定の調整

#### インターフェース設定

```yaml
# /etc/suricata/suricata.yaml
af-packet:
  - interface: wlan1  # 監視対象インターフェース
    cluster-id: 99
    cluster-type: cluster_flow
    defrag: yes
    use-mmap: yes
    mmap-locked: yes
```

#### ログ設定

```yaml
# EVE JSON ログ設定
outputs:
  - eve-log:
      enabled: yes
      filetype: regular
      filename: /var/log/suricata/eve.json
      types:
        - alert:
            payload: yes
            payload-printable: yes
            packet: yes
            metadata: yes
        - http:
            extended: yes
        - dns:
            enabled: yes
        - tls:
            extended: yes
        - files:
            force-magic: yes
        - smtp:
            enabled: yes
        - stats:
            totals: yes
            threads: yes
            deltas: yes
```

### ルール管理

#### カスタムルールセット

```bash
# /etc/suricata/rules/local/local.rules
alert tcp any any -> $HOME_NET 22 (msg:"SSH Brute Force Attempt"; \
    flow:to_server,established; content:"SSH"; nocase; \
    threshold:type threshold, track by_src, count 5, seconds 60; \
    classtype:attempted-admin; sid:1000001; rev:1;)

alert http any any -> $HOME_NET any (msg:"Suspicious User Agent"; \
    flow:to_server,established; content:"User-Agent"; nocase; \
    content:"bot"; nocase; distance:0; within:50; \
    classtype:trojan-activity; sid:1000002; rev:1;)
```

#### ルール無効化

```bash
# 特定のルールを無効化
sudo nano /etc/suricata/disable.conf
# 内容例:
# 2013028  # GPLとET規則の競合を回避
# 2610001  # 偽陽性の多いルール
```

### パフォーマンス調整

#### メモリ設定

```yaml
# suricata.yaml内のメモリ設定
threading:
  set-cpu-affinity: no
  cpu-affinity:
    - management-cpu-set:
        cpu: [ 0 ]
    - receive-cpu-set:
        cpu: [ 0 ]
    - worker-cpu-set:
        cpu: [ 1 ]

# メモリ使用量制限
max-pending-packets: 1024
```

#### 検知エンジン調整

```yaml
# 検知エンジンのプロファイル
detect:
  profile: medium
  custom-values:
    toclient-groups: 200
    toserver-groups: 200

# 高速パターンマッチング
mpm-algo: hs
spm-algo: hs
```

## 監視とメンテナンス

### ログ監視

```bash
# リアルタイムアラート監視
sudo tail -f /var/log/suricata/eve.json | jq 'select(.event_type=="alert")'

# 統計情報の表示
sudo tail -f /var/log/suricata/eve.json | jq 'select(.event_type=="stats")'

# エラーログの確認
sudo journalctl -u suricata -f
```

### パフォーマンス監視

```bash
# Suricataプロセスの監視
ps aux | grep suricata

# メモリ使用量確認
sudo systemctl status suricata

# ネットワーク統計
cat /proc/net/dev | grep wlan1
```

### 更新状況の確認

```bash
# 最新の更新ログを確認
sudo tail -n 50 /var/log/suricata/update.log

# タイマー状況を確認
sudo systemctl status azazel-suricata-update.timer

# 手動更新実行
sudo systemctl start azazel-suricata-update.service
```

## トラブルシューティング

### 一般的な問題

#### 1. Suricataが起動しない

**症状:**
- systemctl status suricataでfailed状態
- ログにエラーメッセージ

**診断:**
```bash
# 設定テスト
sudo suricata -T -c /etc/suricata/suricata.yaml

# 詳細ログ確認
sudo journalctl -u suricata --no-pager -l
```

**解決策:**
```bash
# 設定ファイルの構文確認
sudo suricata -T -c /etc/suricata/suricata.yaml

# インターフェース名の確認
ip link show

# 権限確認
sudo ls -la /var/log/suricata/
sudo ls -la /var/lib/suricata/
```

#### 2. ルール更新に失敗する

**症状:**
- azazel-suricata-update.serviceが失敗
- 古いルールセットのまま

**診断:**
```bash
# 更新ログを確認
sudo cat /var/log/suricata/update.log

# 手動更新実行
sudo /usr/local/bin/azazel-suricata-update.sh
```

**解決策:**
```bash
# ネットワーク接続確認
ping -c 4 rules.emergingthreats.net

# suricata-updateの直接実行
sudo suricata-update list-sources
sudo suricata-update update-sources
```

#### 3. パフォーマンス問題

**症状:**
- 高CPU使用率
- パケットドロップ
- メモリ不足

**解決策:**
```bash
# CPUアフィニティ設定
sudo nano /etc/suricata/suricata.yaml
# threading設定を調整

# メモリ制限設定
sudo systemctl edit suricata
# [Service]
# MemoryLimit=512M

# 検知ルール削減
sudo nano /etc/suricata/disable.conf
# 使用しないルールを無効化
```

### パフォーマンス最適化

#### Raspberry Pi固有の調整

```bash
# GPU分割メモリの調整
sudo nano /boot/config.txt
# gpu_mem=16  # 最小限のGPUメモリ

# CPUガバナーの設定
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# I/Oスケジューラの最適化
echo mq-deadline | sudo tee /sys/block/mmcblk0/queue/scheduler
```

#### ルールセット最適化

```bash
# 使用しないカテゴリの無効化
sudo nano /etc/suricata/suricata.yaml
# classification-file: /etc/suricata/classification.config
# reference-config-file: /etc/suricata/reference.config

# ET Pro rules（商用）への切り替え検討
# sudo suricata-update add-source "et/pro" "https://rules.emergingthreats.net/your-oinkcode/suricata/rules/etpro.rules.tar.gz"
```

## セキュリティ考慮事項

### アクセス制御

```bash
# suricataユーザーの権限確認
sudo -u suricata id

# ファイル権限の確認
sudo find /etc/suricata -type f -exec ls -la {} \;
sudo find /var/log/suricata -type f -exec ls -la {} \;
```

### ログセキュリティ

```bash
# ログファイルの暗号化（オプション）
sudo nano /etc/logrotate.d/azazel-suricata
# postrotate
#     gpg --trust-model always --encrypt -r admin@example.com /var/log/suricata/eve.json.1
# endscript

# ログの完全性チェック
sudo sha256sum /var/log/suricata/eve.json > /var/log/suricata/eve.json.sha256
```

## 注意事項と制限

### 重要な注意事項

1. **直接編集**: インストーラーはsystemdユニットやlogrotate設定を`/etc`に直接書き込みます
2. **オフライン環境**: このスクリプトは、リポジトリが先にターゲットデバイスに配置されるオフライン/エアギャップ環境を想定しています
3. **本番環境**: 本番環境で実行する前にスクリプトを確認してください
4. **カスタマイズ**: 必要に応じてタイマーの`OnCalendar`や更新ソースを調整してください

### システム要件

- Raspberry Pi OS（Debian系）
- Suricata 6.0以降
- systemd
- インターネット接続（更新用）
- 最低1GB RAM推奨

### 既知の制限

- IPv6サポートは限定的
- 高トラフィック環境での性能制限
- SD カードI/O性能による制約

## 関連ドキュメント

- [`INSTALLATION_ja.md`](INSTALLATION_ja.md) - 完全なシステムインストール手順
- [`OPERATIONS_ja.md`](OPERATIONS_ja.md) - 日常運用とメンテナンス
- [`TROUBLESHOOTING_ja.md`](TROUBLESHOOTING_ja.md) - Suricata関連のトラブルシューティング
- [`NETWORK_SETUP_ja.md`](NETWORK_SETUP_ja.md) - ネットワーク設定とSuricata統合

---

*Suricataインストールの詳細については、[公式ドキュメント](https://suricata.readthedocs.io/)と[Azazel-Edgeリポジトリ](https://github.com/01rabbit/Azazel-Edge)を参照してください。*