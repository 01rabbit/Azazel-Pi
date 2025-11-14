# 運用ガイド

このドキュメントは、現場でのAzazelのステージング、運用、メンテナンスの手順をまとめています。ワークフローはRaspberry Pi OS上での展開を想定していますが、他のDebian派生版にも適用可能です。

初期インストールについては、包括的なセットアップ手順として[`INSTALLATION_ja.md`](INSTALLATION_ja.md)を参照してください。

## 1. リリースの取得

署名されたGitタグ（例：`v1.0.0`）を選択し、インストーラーバンドルをダウンロードします：

```bash
TAG=v1.0.0
curl -fsSL https://github.com/01rabbit/Azazel-Pi/releases/download/${TAG}/azazel-installer-${TAG}.tar.gz \
  | tar xz -C /tmp
```

アーカイブには設定テンプレート、スクリプト、systemdユニットが含まれています。

## 2. ノードのブートストラップ

ターゲットホスト上でインストーラーを実行します。gitチェックアウトから作業する場合は、`scripts/install_azazel.sh`を使用できます：

```bash
cd /tmp/azazel-installer
sudo bash scripts/install_azazel.sh
```

スクリプトはリポジトリペイロードを`/opt/azazel`にコピーし、設定を`/etc/azazel`に配置し、systemdユニットをインストールして、統合`azctl-unified.service`を有効化します。

## 3. サービスの設定

1. `/etc/azazel/azazel.yaml`を編集して、インターフェース名、QoSポリシー、アラート閾値を反映させます。
2. デフォルト以外のルールセットが必要な場合は、Suricata設定を再生成します：

   ```bash
   sudo /opt/azazel/scripts/suricata_generate.py \
     /etc/azazel/azazel.yaml \
     /etc/azazel/suricata/suricata.yaml.tmpl \
     --output /etc/suricata/suricata.yaml
   ```
3. サービスを再読み込み: `sudo systemctl restart azctl-unified.service`

### モードプリセット

コントローラーは3つの防御モードを維持します。各モードは`azazel.yaml`から取得した遅延、トラフィックシェーピング、ブロック動作のプリセットを適用します。インシデント対応時にこれらのプリセットを有効化するリモートオーバーライドについては、[APIリファレンス – `/v1/mode`](API_REFERENCE_ja.md#post-v1mode)セクションを参照してください。

| モード | 遅延 (ms) | シェーピング (kbps) | ブロック | 使用例 |
|--------|----------:|-----------------:|:--------:|---------|
| portal | 100 | – | なし | ユーザーをオンラインに保ちながら自動スキャンを遅らせるベースライン遅延パディング |
| shield | 200 | 128 | なし | 侵入スコアがT1を超えた時の強化応答；攻撃者を抑制しつつリモートワークを維持 |
| lockdown | 300 | 64 | あり | T2を超えた時の緊急封じ込め；アンロックタイマーが期限切れになるまでシェーピングとハードブロックを組み合わせ |

より厳格なモードへの遷移は、最近のスコアの移動平均が設定された閾値を超えた時に発生します。アンロックタイマーは、デーモンがより制限の少ないモードに降格する前のクールオフ期間を強制します。現場でロックダウンに入った場合、監督する`azctl/daemon`は生成された許可リストを更新した後、`nft -f configs/nftables/lockdown.nft`を適用する必要があります。

## 4. ヘルスチェック

`scripts/sanity_check.sh`を使用してSuricata、Vector、OpenCanaryが有効化され実行されていることを確認します。`azctl`サービスからのsystemdジャーナルエントリは、状態遷移とスコアリング決定を公開します。

## 5. ロールバック

ホストからAzazelを削除するには、`sudo /opt/azazel/rollback.sh`を実行します。スクリプトは`/opt/azazel`を削除し、`/etc/azazel`を削除して、`azctl-unified.service`を無効化します。

## 防御モードの詳細

### Portal モード（ポータルモード）
- **目的**: 最小限の影響でベースライン監視
- **特徴**: 
  - 軽微な遅延追加（100ms）
  - 正常なトラフィックフローを維持
  - イベントログとスコアリングは継続
- **適用シナリオ**: 日常運用、平常時の監視

### Shield モード（シールドモード）
- **目的**: 脅威検知時の強化監視と制御
- **特徴**:
  - 中程度の遅延（200ms）
  - 帯域制限（128kbps）
  - トラフィックシェーピング適用
  - 詳細ログ記録
- **適用シナリオ**: 疑わしい活動検知時、スコアが中程度閾値を超過時

### Lockdown モード（ロックダウンモード）
- **目的**: 高リスク状況での完全封じ込め
- **特徴**:
  - 高遅延（300ms）
  - 厳格な帯域制限（64kbps）
  - 許可リストベースの通信のみ
  - 医療・緊急FQDNへのアクセス維持
- **適用シナリオ**: 重大な脅威検知時、高スコア閾値超過時

## 日常運用タスク

### TUIメニューを使用した日常運用

**推奨**: 日常的なモニタリングと運用作業には統合TUIメニューを使用

```bash
# メインメニューを起動
python3 -m azctl.cli menu
```

**TUIでの日常タスク:**
1. **「システム情報」** → リソース使用率、温度、システム負荷の確認
2. **「サービス管理」** → 全サービスの状態確認とログ表示
3. **「防御制御」** → 現在のモード、スコア、決定履歴の確認
4. **「ログ監視」** → リアルタイムアラート監視
5. **「ネットワーク情報」** → インターフェース状態とトラフィック統計

### 定期メンテナンス

#### 日次タスク（TUI推奨）
```bash
# TUIメニューから以下を確認:
# - システム情報 → リソース使用率
# - サービス管理 → 全サービス状態
# - 防御制御 → 最近の決定履歴
# - ログ監視 → アラート要約

# コマンドライン（スクリプト用）
sudo systemctl status azctl-unified.service
sudo tail -f /var/log/azazel/decisions.log
sudo tail -f /var/log/suricata/fast.log
```

#### 週次タスク
```bash
# システム更新
sudo apt update && sudo apt upgrade

# Suricataルール更新
sudo suricata-update
sudo systemctl restart suricata

# ログローテーション確認
sudo journalctl --disk-usage
sudo journalctl --vacuum-time=7d
```

#### 月次タスク
```bash
# 包括的ヘルスチェック
sudo /opt/azazel/sanity_check.sh

# 設定バックアップ
sudo tar -czf /backup/azazel-$(date +%Y%m%d).tar.gz /etc/azazel /opt/azazel/config

# Dockerリソースクリーンアップ
sudo docker system prune -f

# サービス再起動（計画メンテナンス）
sudo systemctl restart azctl-unified.service
```

### 監視とアラート

#### 重要な監視項目
```bash
# CPU使用率
htop

# メモリ使用量
free -h

# ディスク容量
df -h

# ネットワークトラフィック
sudo iftop

# サービス稼働状況
sudo systemctl is-active azctl-unified.service mattermost nginx docker
```

#### アラート設定例
```bash
# Cronによる自動ヘルスチェック
sudo crontab -e
# 追加: */15 * * * * /opt/azazel/sanity_check.sh >> /var/log/azazel/health.log

# ディスク容量警告
sudo nano /etc/crontab
# 追加: 0 6 * * * root df -h | grep -E '(9[0-9]%|100%)' && echo "Disk space warning" | wall
```

## インシデント対応

### インタラクティブTUIメニューの使用

**推奨方法**: インタラクティブメニューシステムを使用した運用

```bash
# TUIメニューを起動
python3 -m azctl.cli menu

# 特定のネットワークインターフェースを指定
python3 -m azctl.cli menu --lan-if wlan0 --wan-if wlan1
```

**TUIメニューからのモード切り替え:**
1. メニューから「防御制御」を選択
2. 「手動モード切り替え」を選択
3. 目的のモード（Portal/Shield/Lockdown）を選択
4. 確認ダイアログで操作を承認

**TUIメニューの主要機能:**
- **リアルタイム状態監視**: 現在のモード、脅威スコア、ネットワーク状態
- **ワンクリック操作**: 複雑な操作を簡単なメニューから実行
- **安全な操作**: 危険な操作には確認ダイアログと権限チェック
- **包括的情報**: システム全体の状態を一画面で確認

### 手動モード切り替え（CLI）

緊急時やスクリプトからの手動モード変更：

```bash
# Shieldモードに切り替え
echo '{"mode": "shield"}' | sudo tee /tmp/mode.json
python3 -m azctl.cli events --config /tmp/mode.json

# Lockdownモードに切り替け
echo '{"mode": "lockdown"}' | sudo tee /tmp/mode.json
python3 -m azctl.cli events --config /tmp/mode.json

# Portalモードに復帰
echo '{"mode": "portal"}' | sudo tee /tmp/mode.json
python3 -m azctl.cli events --config /tmp/mode.json
```

### HTTP APIを使用したモード制御

```bash
# RESTful APIでのモード切り替え
curl -X POST http://localhost:8080/v1/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "shield"}'

# 現在のモード確認
curl http://localhost:8080/v1/health
```

### ログ分析

#### Suricataアラート分析
```bash
# アラートの種類別集計
jq 'select(.event_type=="alert") | .alert.signature' /var/log/suricata/eve.json | sort | uniq -c

# 攻撃元IP集計
jq 'select(.event_type=="alert") | .src_ip' /var/log/suricata/eve.json | sort | uniq -c | sort -nr

# 時系列アラート分析
jq 'select(.event_type=="alert") | [.timestamp, .alert.signature, .src_ip]' /var/log/suricata/eve.json
```

#### Azazel決定ログ分析
```bash
# モード遷移履歴
grep "mode transition" /var/log/azazel/decisions.log

# スコア変動分析
grep "score:" /var/log/azazel/decisions.log | tail -20

# 閾値超過イベント
grep "threshold exceeded" /var/log/azazel/decisions.log
```

## 設定管理

### 設定テンプレートの更新

```bash
# 新しい設定テンプレートを適用
sudo rsync -av /opt/azazel/configs/ /etc/azazel/

# 設定差分を確認
sudo diff -u /etc/azazel/azazel.yaml.backup /etc/azazel/azazel.yaml

# 設定変更を適用
sudo systemctl restart azctl-unified.service
```

### 環境別設定管理

```bash
# 開発環境設定
sudo cp /opt/azazel/configs/environments/development.yaml /etc/azazel/azazel.yaml

# 本番環境設定
sudo cp /opt/azazel/configs/environments/production.yaml /etc/azazel/azazel.yaml

# テスト環境設定
sudo cp /opt/azazel/configs/environments/testing.yaml /etc/azazel/azazel.yaml
```

## パフォーマンス最適化

### システムチューニング

```bash
# I/Oスケジューラの最適化
echo mq-deadline | sudo tee /sys/block/mmcblk0/queue/scheduler

# ネットワークバッファの最適化
echo 'net.core.rmem_max = 16777216' | sudo tee -a /etc/sysctl.conf
echo 'net.core.wmem_max = 16777216' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Suricataワーカースレッド調整
sudo nano /etc/suricata/suricata.yaml
# threading.cpu-affinity を調整
```

### リソース使用量の最適化

```bash
# ログレベルの調整
sudo nano /etc/azazel/vector/vector.toml
# log_level = "warn" に設定

# E-Paper更新頻度の調整
sudo nano /etc/default/azazel-epd
# UPDATE_INTERVAL=30 に設定

# OpenCanaryサービスの選択的有効化
sudo nano /opt/azazel/config/opencanary.conf
# 不要なサービスを無効化
```

## バックアップとリストア

### 設定バックアップ

```bash
# 完全バックアップ
sudo tar -czf azazel-full-backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  /etc/azazel \
  /opt/azazel/config \
  /var/log/azazel \
  /opt/mattermost/config

# 設定のみバックアップ
sudo tar -czf azazel-config-backup-$(date +%Y%m%d).tar.gz \
  /etc/azazel \
  /opt/azazel/config
```

### リストア手順

```bash
# サービス停止
sudo systemctl stop azctl-unified.service

# バックアップからリストア
sudo tar -xzf azazel-config-backup-YYYYMMDD.tar.gz -C /

# 権限修正
sudo chown -R root:root /etc/azazel
sudo chmod -R 644 /etc/azazel/*.yaml

# サービス再開
sudo systemctl start azctl-unified.service
```

## セキュリティベストプラクティス

### アクセス制御

```bash
# SSH鍵認証の設定
sudo nano /etc/ssh/sshd_config
# PasswordAuthentication no
# PubkeyAuthentication yes

# ファイアウォール設定
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### 監査ログ

```bash
# システム監査有効化
sudo apt install auditd
sudo systemctl enable --now auditd

# Azazel関連ファイルの監査
echo "-w /etc/azazel/ -p wa -k azazel-config" | sudo tee -a /etc/audit/rules.d/azazel.rules
echo "-w /opt/azazel/ -p wa -k azazel-runtime" | sudo tee -a /etc/audit/rules.d/azazel.rules
sudo systemctl restart auditd
```

## トラブルシューティング

一般的な問題と解決方法については、[`TROUBLESHOOTING_ja.md`](TROUBLESHOOTING_ja.md)を参照してください。

### クイック診断

```bash
# 包括的ヘルスチェック
sudo /opt/azazel/sanity_check.sh

# サービス状態確認
sudo systemctl status azctl-unified.service --no-pager

# 最近のエラーログ確認
sudo journalctl -u azctl-unified.service --since "1 hour ago" | grep -i error
```

## 関連ドキュメント

- [`INSTALLATION_ja.md`](INSTALLATION_ja.md) - 完全インストールガイド
- [`NETWORK_SETUP_ja.md`](NETWORK_SETUP_ja.md) - ネットワーク設定手順
- [`TROUBLESHOOTING_ja.md`](TROUBLESHOOTING_ja.md) - 包括的問題解決ガイド
- [`API_REFERENCE_ja.md`](API_REFERENCE_ja.md) - PythonモジュールとHTTPエンドポイント
- [`ARCHITECTURE_ja.md`](ARCHITECTURE_ja.md) - システムアーキテクチャと設計

---

*最新の運用ガイダンスについては、[Azazel-Piリポジトリ](https://github.com/01rabbit/Azazel-Pi)を参照し、企業展開については管理者に相談してください。*
