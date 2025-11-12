# Azazel-Pi インストールガイド

この包括的なガイドでは、Raspberry Piシステム上でのAzazel-Piのインストールと初期セットアップについて、メインシステムコンポーネント、E-Paperディスプレイ統合、トラブルシューティング手順を含めて説明します。

## 概要

Azazel-Piは、必要なすべてのコンポーネントを自動的にプロビジョニングする **単一スクリプトインストール** を提供します：
- **コアサービス**: Suricata IDS/IPS、OpenCanaryハニーポット、Vectorログ収集
- **制御プレーン**: azctlデーモンとステートマシン
- **コラボレーションプラットフォーム**: PostgreSQLデータベース付きMattermost
- **Webインターフェース**: Nginxリバースプロキシ
- **オプションハードウェア**: E-Paperステータスディスプレイ

## 前提条件

### ハードウェア要件
- **Raspberry Pi 5 Model B**（推奨）または互換性のあるARM64デバイス
- Raspberry Pi OS（64-bit Lite）を搭載した **8GB+のmicroSDカード**
- 初期セットアップ用の **イーサネット接続**
- **オプション**: ステータス表示用Waveshare 2.13" E-Paperディスプレイ

### ソフトウェア要件
- **Raspberry Pi OS（64-bit Lite）** またはDebianベースディストリビューション
- 依存関係インストール用の **インターネット接続**
- **管理者権限**（sudoアクセス）

### ネットワーク設定
- デバイスは **静的IP** または信頼できるDHCP予約を持つ必要があります
- Webインターフェース用に **ポート80/443** が利用可能
- Mattermost（内部）用に **ポート8065** が利用可能

## インストール

### 1. システム準備

Raspberry Piを最新のパッケージに更新します：

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

### 2. Azazel-Piのダウンロード

#### オプションA: GitHubからクローン（開発版）
```bash
git clone https://github.com/01rabbit/Azazel-Pi.git
cd Azazel-Pi
```

#### オプションB: リリースバンドルのダウンロード（本番環境）
```bash
# 特定のバージョンタグを使用（本番環境推奨）
TAG=v1.0.0
curl -fsSL https://github.com/01rabbit/Azazel-Pi/releases/download/${TAG}/azazel-installer-${TAG}.tar.gz \
  | tar xz -C /tmp
cd /tmp/azazel-installer
```

### 3. インストールスクリプトの実行

自動インストーラーをrootとして実行：

```bash
# 基本インストール
sudo scripts/install_azazel.sh

# インストール後にサービスを自動開始
sudo scripts/install_azazel.sh --start

# ドライラン（変更なしで何がインストールされるかを確認）
sudo scripts/install_azazel.sh --dry-run
```

#### インストーラーが行うこと

`install_azazel.sh`スクリプトは以下の作業を実行します：

1. **システム依存関係**: aptを介して必要なパッケージをインストール
   - コアツール: `curl`、`git`、`jq`、`python3`、`rsync`
   - セキュリティコンポーネント: `suricata`、`nftables`、`netfilter-persistent`
   - インフラストラクチャ: `docker.io`、`nginx`、`python3-venv`

2. **専用サービス**:
   - **Vector**: ログ収集エージェント（公式リポジトリまたはtarballフォールバック）
   - **OpenCanary**: 専用Python仮想環境のハニーポット
   - **Mattermost**: PostgreSQLデータベース付きコラボレーションプラットフォーム

3. **Azazelコンポーネント**:
   - コアPythonモジュールを `/opt/azazel/` に
   - 設定テンプレートを `/etc/azazel/` に
   - systemdサービスユニットとターゲット
   - ユーティリティスクリプトとロールバック機能

4. **ランタイム環境**:
   - 運用ログ用の `/var/log/azazel/` を作成
   - Mattermost用PostgreSQLコンテナを設定
   - Nginxリバースプロキシをセットアップ
   - `azctl-unified.service`を有効化（開始はしない）

### 4. 設定

サービスを開始する前に、メイン設定を確認・カスタマイズします：

```bash
sudo nano /etc/azazel/azazel.yaml
```

調整すべき主要設定：

- **インターフェース名**: ネットワーク設定に合わせる（`wlan1` - 外部接続、`wlan0` - 内部AP）
- **内部ネットワーク**: 172.16.0.0/24 (ゲートウェイ: 172.16.0.254)
- **QoSプロファイル**: 各防御モードの帯域制限
- **防御閾値**: Shield/Lockdown遷移のスコア制限
- **Lockdown許可リスト**: アクセス可能な重要サービス
- **通知設定**: Mattermost Webhook (http://172.16.0.254:8065)

設定構造の例：
```yaml
network:
  interface: "eth0"
  home_net: "192.168.1.0/24"

modes:
  portal:
    delay_ms: 100
    enabled: true
  shield:
    delay_ms: 200
    shape_kbps: 128
    enabled: true
  lockdown:
    delay_ms: 300
    shape_kbps: 64
    block_enabled: true

scoring:
  shield_threshold: 50
  lockdown_threshold: 100
  window_size: 10
```

### 5. サービスの開始

Azazelシステムを有効化・開始：

```bash
# すべてのAzazelサービスを開始
sudo systemctl start azctl-unified.service

# サービス状態を確認
sudo systemctl status azctl-unified.service

# 個別サービスを確認
sudo systemctl status mattermost nginx docker
```

### 6. 確認

#### サービスヘルスチェック
```bash
# 内蔵ヘルスチェックを実行
sudo /opt/azazel/sanity_check.sh

# システムログを確認
sudo journalctl -u azctl-unified.service -f
```

#### Webインターフェースアクセス
- **Mattermost**: `http://your-pi-ip`（Nginxプロキシ経由）
- **直接Mattermost**: `http://your-pi-ip:8065`（Nginx利用不可時）

#### コマンドラインインターフェース
```bash
# 基本ステータス（アクティブな設定が必要）
python3 -m azctl.cli status --config /etc/azazel/azazel.yaml

# Richターミナルインターフェース
python3 -m azctl.cli status --tui --config /etc/azazel/azazel.yaml

# 自動化用JSON出力
python3 -m azctl.cli status --json --config /etc/azazel/azazel.yaml
```

#### インタラクティブTUIメニュー
```bash
# 包括的なモジュラーメニューシステム
python3 -m azctl.cli menu

# カスタムインターフェース指定
python3 -m azctl.cli menu --lan-if wlan0 --wan-if wlan1
```

**TUIメニューの特徴:**
- **モジュラー設計**: 機能別に分離された8つのモジュール
- **リアルタイム監視**: システム状態、サービス、ログの即座更新
- **安全な操作**: 危険な操作には確認ダイアログ
- **包括的管理**: システム全体を一つのインターフェースから制御
- **拡張可能**: 新機能を簡単に追加可能な構造

## E-Paperディスプレイセットアップ（オプション）

Waveshare E-Paperディスプレイをお持ちの場合、以下の追加手順を実行：

### 1. ハードウェア接続

標準SPIピン配置に従って、E-Paper HATをRaspberry Piに接続します。詳細な配線情報については、[`EPD_SETUP_ja.md`](EPD_SETUP_ja.md)を参照してください。

### 2. SPIインターフェースの有効化

```bash
# raspi-configを使用
sudo raspi-config
# 移動: Interface Options → SPI → Enable

# または手動で有効化
echo "dtparam=spi=on" | sudo tee -a /boot/config.txt
sudo reboot
```

### 3. E-Paper依存関係のインストール

```bash
# E-Paperライブラリと依存関係をインストール
sudo scripts/install_epd.sh

# ディスプレイをテスト
sudo python3 -m azazel_pi.core.display.epd_daemon --mode test
```

### 4. E-Paperサービスの有効化

```bash
# 自動E-Paper更新を有効化
sudo systemctl enable --now azazel-epd.service

# サービス状態を確認
sudo systemctl status azazel-epd.service

# 更新ログを表示
sudo journalctl -u azazel-epd.service -f
```

### 5. 設定

E-Paperサービス設定を編集：

```bash
sudo nano /etc/default/azazel-epd
```

主な設定：
```bash
# 更新間隔（秒）
UPDATE_INTERVAL=10

# イベントログのパス
EVENTS_LOG=/var/log/azazel/events.json

# デバッグ出力を有効化
DEBUG=0
```

## ネットワーク設定

AP（アクセスポイント）機能が必要な展開の場合：

### 自動ネットワークセットアップ

インストーラーはネットワークインターフェースを自動設定できます。`/etc/azazel/azazel.yaml`で指定：

```yaml
network:
  # 監視用プライマリインターフェース
  interface: "wlan1"
  
  # ゲートウェイとして動作時の内部ネットワーク
  internal_network: "172.16.0.0/24"
  
  # APインターフェース設定（必要に応じて）
  ap_interface: "wlan0"
  ap_ssid: "Azazel-GW"
  ap_passphrase: "SecurePassphrase123"
```

### 手動ネットワーク設定

高度なセットアップについては、アーカイブされたネットワーク設定ガイドを参照：
- 手動Wi-Fi APセットアップ: `docs/archive/wlan_setup.md`
- RaspAP統合: `docs/archive/RaspAP_config.md`

## トラブルシューティング

### インストール問題

#### パッケージインストール失敗
```bash
# aptキャッシュをクリアして再試行
sudo apt clean
sudo apt update
sudo apt install -f

# ディスク容量を確認
df -h /
```

#### サービス開始失敗
```bash
# サービス状態を確認
sudo systemctl status <service-name>

# 詳細ログを表示
sudo journalctl -u <service-name> --no-pager

# 失敗したサービスをリセット
sudo systemctl reset-failed
```

### ランタイム問題

#### データベース接続問題
```bash
# PostgreSQLコンテナを確認
sudo docker ps | grep postgres

# データベースコンテナを再起動
cd /opt/azazel/config
sudo docker-compose --project-name azazel-db restart

# Mattermostデータベース設定を確認
sudo cat /opt/mattermost/config/config.json | jq '.SqlSettings'
```

#### ネットワークインターフェース問題
```bash
# 利用可能なインターフェースをリスト
ip link show

# インターフェース状態を確認
ip addr show <interface-name>

# 正しいインターフェース名で設定を更新
sudo nano /etc/azazel/azazel.yaml
sudo systemctl restart azctl-unified.service
```

#### E-Paperディスプレイ問題
```bash
# SPIインターフェースを確認
ls -l /dev/spidev0.0

# ディスプレイを手動テスト
sudo python3 -m azazel_pi.core.display.epd_daemon --mode test

# ドライバ競合を確認
sudo journalctl -u azazel-epd.service | grep -i error
```

### パフォーマンス問題

#### 高CPU使用率
```bash
# リソース集約プロセスを特定
htop

# E-Paper更新頻度を削減
sudo nano /etc/default/azazel-epd
# UPDATE_INTERVAL=30に設定

# リソース集約サービスを再起動
sudo systemctl restart vector
sudo systemctl restart suricata
```

#### メモリ不足
```bash
# メモリ使用量を確認
free -h
sudo dmesg | grep -i "killed process"

# スワップ領域を増加
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# CONF_SWAPSIZE=1024に設定
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# サービスメモリ使用量を最適化
sudo nano /etc/systemd/system/suricata.service
# 追加: MemoryLimit=512M

# サービスを再起動
sudo systemctl daemon-reload
sudo systemctl restart azctl-unified.service
```

### 復旧手順

#### 完全システムリセット
```bash
# すべてのAzazelサービスを停止
sudo systemctl stop azctl-unified.service

# インストールを削除（ログは保持）
sudo /opt/azazel/rollback.sh

# クリーンな再インストール
sudo scripts/install_azazel.sh --start
```

#### 設定リセット
```bash
# 現在の設定をバックアップ
sudo cp -r /etc/azazel /etc/azazel.backup

# デフォルト設定を復元
sudo rsync -a configs/ /etc/azazel/

# カスタマイズして再起動
sudo nano /etc/azazel/azazel.yaml
sudo systemctl restart azctl-unified.service
```

#### データベースリセット
```bash
# データベースを使用するサービスを停止
sudo systemctl stop mattermost

# データベースコンテナとデータを削除
cd /opt/azazel/config
sudo docker-compose --project-name azazel-db down -v
sudo rm -rf /opt/azazel/data/postgres

# データベースを再作成
sudo docker-compose --project-name azazel-db up -d
sudo systemctl start mattermost
```

## 高度な設定

### カスタムSuricataルール

環境固有のIDS設定を生成：

```bash
# テンプレートからSuricata設定を生成
sudo /opt/azazel/scripts/suricata_generate.py \
  /etc/azazel/azazel.yaml \
  /etc/azazel/suricata/suricata.yaml.tmpl \
  --output /etc/suricata/suricata.yaml

# Suricataを再起動して変更を適用
sudo systemctl restart suricata
```

### カスタムQoSプロファイル

トラフィック制御設定を編集：

```bash
sudo nano /etc/azazel/tc/classes.htb
sudo systemctl restart azctl-unified.service
```

### 外部SIEMとの統合

Vectorログ転送を設定：

```bash
sudo nano /etc/azazel/vector/vector.toml
sudo systemctl restart vector
```

## メンテナンス

### 定期更新

```bash
# システムパッケージを更新
sudo apt update && sudo apt upgrade

# Suricataルールを更新
sudo suricata-update

# 更新後にサービスを再起動
sudo systemctl restart azctl-unified.service
```

### ログ管理

```bash
# ログサイズを確認
sudo du -sh /var/log/azazel/*

# 手動でログをローテート
sudo logrotate -f /etc/logrotate.d/azazel

# 古いDockerイメージをクリーンアップ
sudo docker system prune -f
```

### バックアップと復元

```bash
# 設定をバックアップ
sudo tar -czf azazel-backup-$(date +%Y%m%d).tar.gz \
  /etc/azazel /opt/azazel/config

# 設定を復元
sudo tar -xzf azazel-backup-YYYYMMDD.tar.gz -C /
sudo systemctl restart azctl-unified.service
```

## 次のステップ

インストール成功後：

1. **設定の確認**: すべての設定が環境に合致していることを確認
2. **内部ネットワーク設定**: wlan0インターフェースで172.16.0.254の内部APが動作することを確認
3. **Mattermost設定**: http://172.16.0.254:8065 でWebhookとチャンネル設定を完了
4. **防御モードのテスト**: 手動でモード遷移をトリガーして動作を確認
5. **通知の設定**: configs/notify.yaml でWebhook URLを設定
6. **パフォーマンス監視**: 内蔵ツールを使用してシステムヘルスを追跡
7. **メンテナンス計画**: 更新とバックアップのスケジュールを確立

## 関連ドキュメント

- [`OPERATIONS_ja.md`](OPERATIONS_ja.md) - 日常の運用手順
- [`ARCHITECTURE_ja.md`](ARCHITECTURE_ja.md) - システムアーキテクチャと設計
- [`EPD_SETUP_ja.md`](EPD_SETUP_ja.md) - E-Paperディスプレイ設定詳細
- [`API_REFERENCE_ja.md`](API_REFERENCE_ja.md) - PythonモジュールとHTTPエンドポイント
- [`TROUBLESHOOTING_ja.md`](TROUBLESHOOTING_ja.md) - 包括的トラブルシューティングガイド

---

*最新のインストール手順と更新については、常に公式[Azazel-Piリポジトリ](https://github.com/01rabbit/Azazel-Pi)を参照してください。*