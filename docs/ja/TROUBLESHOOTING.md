# Azazel-Pi トラブルシューティングガイド

この包括的なトラブルシューティングガイドでは、Azazel-Piシステムのインストール、設定、運用中に遭遇する一般的な問題について説明します。

## クイック診断

### システムヘルスチェック

組み込みのヘルスチェックスクリプトから開始します：

```bash
# 包括的システムチェックを実行
sudo /opt/azazel/sanity_check.sh

# サービス状態を確認
sudo systemctl status azctl-unified.service

# 最近のログを表示
sudo journalctl -u azctl-unified.service --since "10 minutes ago"
```

### サービス状態概要

```bash
# 全Azazel関連サービスを確認
sudo systemctl status azctl-unified.service mattermost nginx docker

# セキュリティサービスを確認
sudo systemctl status suricata vector
docker ps --filter name=azazel_opencanary

# E-Paperサービスを確認（インストール済みの場合）
sudo systemctl status azazel-epd.service
```

## インストール問題

### パッケージインストール失敗

#### 問題: APTパッケージインストールが失敗する

**症状:**
- `apt install`コマンドがエラーを返す
- 依存関係が解決できない
- パッケージ競合が報告される

**解決策:**

```bash
# パッケージキャッシュをクリアして更新
sudo apt clean
sudo apt autoremove
sudo apt update
sudo apt upgrade

# 壊れたパッケージを修復
sudo apt install -f
sudo dpkg --configure -a

# ディスク容量を確認
df -h /
sudo apt autoclean

# 詳細出力でインストールを再試行
sudo apt install -v <パッケージ名>
```

#### 問題: Dockerインストールが失敗する

**症状:**
- Dockerデーモンが開始しない
- 権限拒否エラー
- コンテナランタイムが見つからない

**解決策:**

```bash
# 古いDockerインストールを削除
sudo apt remove docker docker-engine docker.io containerd runc

# 公式リポジトリからDockerをインストール
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# ユーザーをdockerグループに追加
sudo usermod -aG docker $USER
newgrp docker

# Dockerサービスを開始
sudo systemctl enable --now docker

# Dockerインストールをテスト
docker run hello-world
```

### インストールスクリプト失敗

#### 問題: install_azazel.shが途中で失敗する

**症状:**
- スクリプトがエラーコードで終了する
- 部分的なインストールが完了
- サービスが適切に設定されない

**解決策:**

```bash
# インストールログを確認
sudo journalctl -xe

# 部分的なインストールをクリーンアップ
sudo /opt/azazel/rollback.sh 2>/dev/null || true
sudo rm -rf /opt/azazel /etc/azazel

# 詳細出力で再試行
sudo bash -x scripts/install_azazel.sh

# インストール内容を事前確認するドライラン
sudo scripts/install_azazel.sh --dry-run
```

#### 問題: Mattermostダウンロードが失敗する

**症状:**
- ダウンロード中のネットワークタイムアウト
- アーキテクチャ不一致エラー
- 破損したtarballエラー

**解決策:**

```bash
# ネットワーク接続を確認
ping -c 4 8.8.8.8
curl -I https://releases.mattermost.com

# 手動ダウンロードとインストール
ARCH=$(dpkg --print-architecture)
VERSION="9.7.1"
wget https://releases.mattermost.com/${VERSION}/mattermost-team-${VERSION}-linux-${ARCH}.tar.gz

# tarballの整合性を確認
tar -tzf mattermost-team-${VERSION}-linux-${ARCH}.tar.gz | head

# カスタムtarballパスを設定
export MATTERMOST_TARBALL="/path/to/mattermost-tarball.tar.gz"
sudo scripts/install_azazel.sh
```

## 設定問題

### ネットワーク設定問題

#### 問題: インターフェースが見つからない

**症状:**
- "Interface eth0 not found"エラー
- ネットワークサービスの開始失敗
- ネットワーク接続なし

**解決策:**

```bash
# 利用可能なインターフェースをリスト
ip link show

# インターフェース状態を確認
ip addr show

# 正しいインターフェース名で設定を更新
sudo nano /etc/azazel/azazel.yaml
# 'interface'フィールドを実際のインターフェース名で更新

# サービスを再起動
sudo systemctl restart azctl-unified.service
```

#### 問題: Wi-Fi APが動作しない

**症状:**
- hostapdの開始に失敗
- クライアントにSSIDが見えない
- クライアントが接続できない

**解決策:**

```bash
# hostapd状態とログを確認
sudo systemctl status hostapd
sudo journalctl -u hostapd --no-pager

# Wi-FiインターフェースがAPモードをサポートするか確認
sudo iw list | grep -A 10 "Supported interface modes"

# 競合するサービスを確認
sudo systemctl status NetworkManager
sudo systemctl status wpa_supplicant

# 必要に応じて競合サービスを無効化
sudo systemctl disable --now NetworkManager
sudo systemctl mask wpa_supplicant

# hostapdを再起動
sudo systemctl restart hostapd
```

#### 問題: DHCPがアドレスを割り当てない

**症状:**
- クライアントは接続するがIPアドレスを取得しない
- dnsmasqサービスが失敗する
- DHCP範囲の競合

**解決策:**

```bash
# dnsmasq状態を確認
sudo systemctl status dnsmasq
sudo journalctl -u dnsmasq --no-pager

# DHCP設定を確認
sudo cat /etc/dnsmasq.d/01-azazel.conf

# ポート競合を確認
sudo netstat -tuln | grep :53
sudo netstat -tuln | grep :67

# 競合するサービスを停止
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved

# dnsmasqを再起動
sudo systemctl restart dnsmasq
```

### データベース設定問題

#### 問題: PostgreSQLコンテナが開始しない

**症状:**
- Dockerコンテナが即座に終了する
- Mattermostでデータベース接続エラー
- ポートが既に使用中エラー

**解決策:**

```bash
# Docker状態を確認
sudo systemctl status docker
docker ps -a

# コンテナログを確認
docker logs azazel-db-postgres-1

# ポート競合を確認
sudo netstat -tuln | grep :5432

# コンテナを削除して再作成
cd /opt/azazel/config
sudo docker-compose --project-name azazel-db down -v
sudo docker-compose --project-name azazel-db up -d

# データベースディレクトリの権限を確認
sudo ls -la /opt/azazel/data/postgres
sudo chown -R 999:999 /opt/azazel/data/postgres
```

#### 問題: Mattermostがデータベースに接続できない

**症状:**
- Mattermostサービスの開始に失敗
- データベース接続タイムアウトエラー
- 認証失敗

**解決策:**

```bash
# Mattermost設定を確認
sudo cat /opt/mattermost/config/config.json | jq '.SqlSettings'

# 手動でデータベース接続をテスト
docker exec -it azazel-db-postgres-1 psql -U mmuser -d mattermost

# データベース認証情報を更新
sudo nano /opt/azazel/config/.env
# MATTERMOST_DB_*変数を更新

# 新しい認証情報でコンテナを再作成
cd /opt/azazel/config
sudo docker-compose --project-name azazel-db down
sudo docker-compose --project-name azazel-db up -d

# Mattermostを再起動
sudo systemctl restart mattermost
```

## 実行時問題

### サービス管理問題

#### 問題: サービスの開始に失敗する

**症状:**
- systemctl startコマンドが失敗する
- サービスが即座に終了する
- 依存関係の失敗

**解決策:**

```bash
# サービス依存関係を確認
sudo systemctl list-dependencies azctl-unified.service

# サービスを個別に開始
sudo systemctl start suricata
sudo systemctl start vector
docker start azazel_opencanary
sudo systemctl start azctl-unified.service

# 設定エラーを確認
sudo systemctl status --full <サービス名>
sudo journalctl -u <サービス名> --no-pager

# 失敗したサービスをリセット
sudo systemctl reset-failed
sudo systemctl daemon-reload
```

#### 問題: 高CPU使用率

**症状:**
- システムが応答しなくなる
- 高い負荷平均
- サービスがタイムアウトする

**解決策:**

```bash
# CPU集約的なプロセスを特定
htop
sudo iotop

# ログローテーション問題を確認
sudo du -sh /var/log/*
sudo logrotate -f /etc/logrotate.conf

# E-Paper更新頻度を削減
sudo nano /etc/default/azazel-epd
# UPDATE_INTERVAL=30 に設定

# リソース集約的なサービスを再起動
sudo systemctl restart vector
sudo systemctl restart suricata
```

#### 問題: Vectorサービスが開始に失敗

**症状:**
- Vectorサービスのステータスが「failed」または「inactive」と表示
- エラーログにVRL構文エラーや設定問題が表示
- ログ処理パイプラインが停止

**解決方法:**

```bash
# Vector設定構文をチェック
vector validate --no-environment /etc/azazel/vector/vector.toml

# 詳細なエラーログを表示
sudo journalctl -u vector --since "10 minutes ago" --no-pager

# VRL構文エラーの一般的な修正:
# 1. Vector 0.39.0+用のmap()関数構文を更新
# 2. クロージャパラメータの型不一致を修正
# 3. 設定パスが正しいことを確認

# 設定を手動でテスト
sudo /usr/local/bin/vector --config /etc/azazel/vector/vector.toml --dry-run

# 修正後にサービスを再起動
sudo systemctl restart vector
```

#### 問題: メモリ不足

**症状:**
- メモリ不足エラー
- OOMキラーによるサービス終了
- システムが応答しなくなる

**解決策:**

```bash
# メモリ使用量を確認
free -h
sudo dmesg | grep -i "killed process"

# スワップ領域を増加
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# CONF_SWAPSIZE=1024 に設定
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# サービスメモリ使用量を最適化
sudo nano /etc/systemd/system/suricata.service
# 追加: MemoryLimit=512M

# サービスを再起動
sudo systemctl daemon-reload
sudo systemctl restart azctl-unified.service
```

### ネットワークとセキュリティ問題

#### 問題: Suricataがトラフィックを検知しない

**症状:**
- /var/log/suricata/eve.jsonが空
- アラートが生成されない
- トラフィックが監視されていない

**解決策:**

```bash
# Suricata状態を確認
sudo systemctl status suricata
sudo suricata --dump-config | grep interface

# インターフェースがトラフィックを受信していることを確認
sudo tcpdump -i <インターフェース> -c 10

# Suricata設定を確認
sudo suricata -T -c /etc/suricata/suricata.yaml

# ルールを更新
sudo suricata-update
sudo systemctl restart suricata

# EICAR文字列でテスト
curl -s http://eicar.org/download/eicar.com.txt
```

#### 問題: OpenCanaryハニーポットがログを記録しない

**症状:**
- ハニーポットログが生成されない
- プローブに対してサービスが応答しない
- OpenCanaryサービスが失敗する

**解決策:**

```bash
# OpenCanary状態を確認
docker ps --filter name=azazel_opencanary
docker logs --tail 100 azazel_opencanary

# 設定を確認
sudo cat /opt/azazel/config/opencanary.conf

# ハニーポットサービスをテスト
nmap -sS -O localhost

# ポート競合を確認
sudo netstat -tuln | grep -E ':(22|23|80|443|21)'

# OpenCanaryを再起動
docker restart azazel_opencanary
```

#### 問題: ファイアウォールが正当なトラフィックをブロックする

**症状:**
- ウェブインターフェースにアクセスできない
- ネットワークサービスが到達不能
- SSH接続が切断される

**解決策:**

```bash
# 現在のファイアウォールルールを確認
sudo nft list ruleset

# 一時的にファイアウォールを無効化
sudo systemctl stop nftables

# 問題が継続するか確認
# 接続をテスト

# 例外ルールを追加
sudo nano /etc/azazel/nftables/lockdown.nft
# 必要なサービス用の許可ルールを追加

# 更新されたルールを適用
sudo nft -f /etc/azazel/nftables/lockdown.nft

# ファイアウォールを再有効化
sudo systemctl start nftables
```

## ハードウェア固有問題

### E-Paperディスプレイ問題

#### 問題: E-Paperディスプレイが更新されない

**症状:**
- ディスプレイが古い情報を表示する
- azazel-epdサービスが失敗する
- SPI通信エラー

**解決策:**

```bash
# SPIインターフェースを確認
ls -l /dev/spidev0.0
lsmod | grep spi

# 無効化されている場合はSPIを有効化
echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
sudo reboot

# E-Paperサービスを確認
sudo systemctl status azazel-epd.service
sudo journalctl -u azazel-epd.service --no-pager

# 手動でディスプレイをテスト
sudo python3 -m azazel_pi.core.display.epd_daemon --mode test

# 配線接続を確認
# ピンが期待されるGPIO割り当てと一致することを確認
```

#### 問題: E-Paperにアーティファクトやゴーストが表示される

**症状:**
- ディスプレイに重複画像が表示される
- 部分更新でアーティファクトが残る
- テキストが破損して表示される

**解決策:**

```bash
# 完全リフレッシュを強制
sudo python3 -m azazel_pi.core.display.epd_daemon --mode shutdown
sudo python3 -m azazel_pi.core.display.epd_daemon --mode test

# ジェントル更新を無効化
sudo nano /etc/default/azazel-epd
# 追加: GENTLE_UPDATES=0

# 更新間隔を増加
# UPDATE_INTERVAL=30 に設定

# E-Paperサービスを再起動
sudo systemctl restart azazel-epd.service
```

### Raspberry Pi固有問題

#### 問題: SDカード破損

**症状:**
- 読み取り専用ファイルシステムエラー
- サービスがランダムに失敗する
- 起動失敗

**解決策:**

```bash
# ファイルシステム状態を確認
sudo fsck /dev/mmcblk0p2

# 不良ブロックを確認
sudo badblocks -v /dev/mmcblk0

# 一時的に読み取り専用モードを有効化
sudo mount -o remount,ro /

# 重要データをバックアップ
sudo tar -czf /tmp/azazel-backup.tar.gz /etc/azazel /opt/azazel/config

# より高い耐久性を持つSDカードへの交換を検討
```

#### 問題: 電源供給不足

**症状:**
- ランダムな再起動
- USBデバイスの切断
- 電圧不足警告

**解決策:**

```bash
# 電源供給状態を確認
dmesg | grep -i voltage
vcgencmd get_throttled

# 公式Raspberry Pi電源アダプター使用（Pi 5の場合5V 3A）
# USB電力消費を確認
lsusb -v | grep -i power

# 不要なサービスを無効化
sudo systemctl disable bluetooth
sudo systemctl disable wifi-powersave-off

# 必要に応じてCPU周波数を削減
sudo nano /boot/config.txt
# 追加: arm_freq=1000
```

## パフォーマンス最適化

### システムパフォーマンス

```bash
# システムリソースを監視
htop
iostat 1
sudo iotop

# I/Oスケジューラを最適化
echo mq-deadline | sudo tee /sys/block/mmcblk0/queue/scheduler

# ログ詳細度を削減
sudo nano /etc/systemd/journald.conf
# 設定: MaxLevelStore=warning

# ディスク容量をクリーンアップ
sudo apt autoclean
sudo journalctl --vacuum-time=7d
sudo docker system prune -f
```

### ネットワークパフォーマンス

```bash
# ネットワークインターフェースを監視
sudo iftop
nload

# ネットワークバッファを最適化
echo 'net.core.rmem_max = 16777216' | sudo tee -a /etc/sysctl.conf
echo 'net.core.wmem_max = 16777216' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# パケットドロップを確認
cat /proc/net/dev
sudo netstat -i
```

## 復旧手順

### 緊急アクセス

#### 問題: SSHアクセスが失われる

**解決策:**

```bash
# HDMI/キーボード経由の物理コンソールアクセス
# ネットワーク設定を確認
ip addr show
ip route show

# ネットワークサービスを再起動
sudo systemctl restart networking
sudo systemctl restart NetworkManager

# ファイアウォールルールをリセット
sudo nft flush ruleset

# SSHを再有効化
sudo systemctl enable --now ssh
```

#### 問題: ウェブインターフェースにアクセスできない

**解決策:**

```bash
# nginx状態を確認
sudo systemctl status nginx

# Mattermost状態を確認
sudo systemctl status mattermost

# nginxを一時的にバイパス
# Mattermostに直接アクセス: http://ip:8065

# nginx設定をリセット
sudo cp /opt/azazel/config/nginx.conf /etc/nginx/nginx.conf
sudo nginx -t
sudo systemctl restart nginx
```

### 完全システム復旧

#### ファクトリーリセット

```bash
# 全サービスを停止
sudo systemctl stop azctl-unified.service

# 設定をバックアップ
sudo tar -czf /tmp/config-backup.tar.gz /etc/azazel

# インストールを削除
sudo /opt/azazel/rollback.sh

# Dockerリソースをクリーンアップ
sudo docker system prune -af
sudo docker volume prune -f

# 一から再インストール
sudo scripts/install_azazel.sh --start

# 設定を復元
sudo tar -xzf /tmp/config-backup.tar.gz -C /
sudo systemctl restart azctl-unified.service
```

#### 選択的サービスリセット

```bash
# 特定のサービスをリセット
sudo systemctl stop <サービス>
sudo systemctl reset-failed <サービス>

# デフォルト設定を復元
sudo cp /opt/azazel/configs/<サービス>/* /etc/azazel/<サービス>/

# サービスを再起動
sudo systemctl start <サービス>
```

## ログ分析

### 重要なログの場所

```bash
# システムログ
sudo journalctl -u azctl-unified.service
sudo journalctl -u mattermost
sudo journalctl -u nginx

# アプリケーションログ  
tail -f /var/log/azazel/decisions.log
tail -f /var/log/suricata/eve.json
tail -f /opt/mattermost/logs/mattermost.log

# E-Paperログ
sudo journalctl -u azazel-epd.service
```

### ログ分析ツール

```bash
# エラーを検索
sudo journalctl --since "1 hour ago" | grep -i error

# リアルタイムログを監視
sudo journalctl -f

# 分析用にログをエクスポート
sudo journalctl --since "24 hours ago" --output=json > /tmp/system-logs.json

# Suricataアラートを分析
jq 'select(.event_type=="alert")' /var/log/suricata/eve.json | head -10
```

## ヘルプの取得

### 収集すべき情報

ヘルプを求める前に、以下の情報を収集してください：

```bash
# システム情報
uname -a
cat /etc/os-release
df -h
free -h

# Azazelのバージョンと設定
git log --oneline -n 5  # gitからインストールした場合
sudo cat /etc/azazel/azazel.yaml

# サービス状態
sudo systemctl status azctl-unified.service --no-pager
sudo /opt/azazel/sanity_check.sh

# 最近のログ
sudo journalctl --since "1 hour ago" > /tmp/recent-logs.txt
```

### サポートリソース

- **GitHub Issues**: [Azazel-Pi Issues](https://github.com/01rabbit/Azazel-Pi/issues)
- **ドキュメント**: このトラブルシューティングガイドと関連ドキュメント
- **コミュニティ**: Mattermostチャンネル（利用可能な場合）
- **専門サポート**: 企業展開についてはメンテナーに連絡

## 予防保守

### 定期メンテナンスタスク

```bash
# 週次タスク
sudo apt update && sudo apt upgrade
sudo suricata-update
sudo journalctl --vacuum-time=7d

# 月次タスク
sudo docker system prune -f
sudo /opt/azazel/sanity_check.sh
sudo systemctl restart azctl-unified.service

# 設定をバックアップ
sudo tar -czf /backup/azazel-$(date +%Y%m%d).tar.gz /etc/azazel /opt/azazel/config
```

### 監視とアラート

```bash
# 監視スクリプトを設定
sudo crontab -e
# 追加: */5 * * * * /opt/azazel/sanity_check.sh >> /var/log/azazel/health.log

# ディスク容量を監視
sudo nano /etc/crontab
# 追加: 0 6 * * * root df -h | grep -E '(9[0-9]%|100%)' && echo "Disk space warning" | wall

# ログローテーションを設定
sudo nano /etc/logrotate.d/azazel
```

## TUIメニューシステム問題

Azazel-PiのメニューTUIは `azctl/menu` ではなく、`azctl/tui_zero.py` / `azctl/tui_zero_textual.py` を使用します。

### メニュー起動失敗

#### 問題: TUIメニューが起動しない

**症状:**
```bash
$ python3 -m azctl.cli menu
ModuleNotFoundError: No module named 'textual'
```

**解決策:**

```bash
# Textual依存を導入
pip3 install textual

# 新TUIモジュールの存在確認
ls -la azctl/tui_zero.py azctl/tui_zero_textual.py

# 構文確認
python3 -m py_compile azctl/tui_zero.py azctl/tui_zero_textual.py azctl/cli.py
```

### 表示・入力問題

**症状:**
- キー入力が反応しない
- 画面が乱れる

**解決策:**

```bash
# ターミナル環境を確認
echo $TERM
stty -a
python3 -c "import sys; print(sys.stdin.isatty())"

# SSH経由の場合
ssh -t user@host python3 -m azctl.cli menu

# 256色端末を明示
export TERM=xterm-256color
python3 -m azctl.cli menu
```

### WiFi管理機能問題

#### 問題: WiFiスキャンが失敗する

**症状:**
```
Error: No networks found or scan failed
```

**解決策:**

```bash
# 無線インターフェースの確認
sudo iw dev

# スキャン権限の確認
sudo iw wlan1 scan | head -20

# NetworkManagerとの競合解決
sudo systemctl stop NetworkManager
sudo systemctl disable NetworkManager
```

#### 問題: WiFi接続が失敗する

**症状:**
- パスワード入力後に接続に失敗
- wpa_supplicant エラー

**解決策:**

```bash
# wpa_supplicant状態を確認
sudo wpa_cli -i wlan1 status

# 設定ファイルの権限確認
ls -l /etc/wpa_supplicant/wpa_supplicant.conf

# 手動接続テスト
sudo wpa_cli -i wlan1 add_network
sudo wpa_cli -i wlan1 set_network 0 ssid '"YourSSID"'
sudo wpa_cli -i wlan1 set_network 0 psk '"YourPassword"'
sudo wpa_cli -i wlan1 enable_network 0
```

### サービス管理機能問題

#### 問題: サービス制御が失敗する

**症状:**
- サービスの開始/停止ができない
- 権限エラーが発生

**解決策:**

```bash
# sudoers設定を確認
sudo visudo
# 追加必要な場合:
# %azazel ALL=(ALL) NOPASSWD: /bin/systemctl

# サービス状態を手動確認
sudo systemctl status azctl-unified.service

# systemctl権限テスト
sudo -u azazel sudo systemctl status azctl-unified.service
```

### 緊急操作機能問題

#### 問題: 緊急ロックダウンが正しく動作しない

**症状:**
- ネットワークが遮断されない
- nftablesルールが適用されない

**解決策:**

```bash
# nftables状態を確認
sudo nft list ruleset

# 手動でロックダウンルールをテスト
sudo nft flush ruleset
sudo nft add table inet emergency
sudo nft add chain inet emergency input '{ type filter hook input priority 0; policy drop; }'

# ネットワークインターフェース状態を確認
ip link show
```

#### 問題: システムレポート生成が失敗する

**症状:**
- レポートファイルが作成されない
- 権限エラーが発生

**解決策:**

```bash
# /tmp書き込み権限を確認
ls -ld /tmp
touch /tmp/test && rm /tmp/test

# 手動でレポート生成をテスト
sudo python3 -c "
import subprocess
result = subprocess.run(['uname', '-a'], capture_output=True, text=True)
print(result.stdout)
"
```

### パフォーマンス問題

#### 問題: メニューの応答が遅い

**症状:**
- メニュー表示に時間がかかる
- キー入力の反応が遅い

**解決策:**

```bash
# システムリソースを確認
htop
free -h
df -h

# I/O待機を確認
iostat -x 1 5

# プロセス優先度を調整
sudo nice -n -10 python3 -m azctl.cli menu
```

### デバッグとログ

#### TUIメニューのデバッグモード

```bash
# デバッグログを有効化
export AZAZEL_DEBUG=1
python3 -m azctl.cli menu

# 詳細ログを有効化
python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from azctl.tui_zero import run_menu
run_menu(lan_if='wlan0', wan_if='wlan1', start_menu=True)
"
```

#### ログファイルの確認

```bash
# TUIメニュー関連ログ
sudo journalctl -u azctl-unified.service --since "1 hour ago" | grep -i menu

# Python エラーログ
sudo tail -f /var/log/syslog | grep python3

# 手動でログ出力
python3 -m azctl.cli menu 2>&1 | tee menu_debug.log
```

## 日本固有のトラブルシューティング

### 文字エンコーディング問題

```bash
# 日本語ロケールを確認
locale
sudo dpkg-reconfigure locales
# ja_JP.UTF-8を選択

# E-Paperでの日本語表示問題
sudo apt install fonts-noto-cjk
sudo fc-cache -fv

# TUIメニューでの日本語表示問題
python3 -c "
from rich.console import Console
console = Console()
console.print('日本語テスト: あいうえお')
"
```

### タイムゾーン設定

```bash
# タイムゾーンを日本標準時に設定
sudo timedatectl set-timezone Asia/Tokyo
timedatectl status

# NTPサーバーを日本のサーバーに設定
sudo nano /etc/systemd/timesyncd.conf
# NTP=ntp.nict.jp
sudo systemctl restart systemd-timesyncd
```

### 日本の法規制対応

```bash
# 電波法対応の確認
iw reg get
sudo iw reg set JP

# ログ保存期間の設定（個人情報保護法対応）
sudo nano /etc/systemd/journald.conf
# MaxRetentionSec=90days  # 90日で自動削除
```

---

*追加のトラブルシューティングヘルプについては、[`INSTALLATION_ja.md`](INSTALLATION_ja.md)、[`OPERATIONS_ja.md`](OPERATIONS_ja.md)、[`NETWORK_SETUP_ja.md`](NETWORK_SETUP_ja.md)ガイドを参照するか、[Azazel-Piリポジトリ](https://github.com/01rabbit/Azazel-Pi)でissueを報告してください。*
