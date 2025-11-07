# E-Paper ディスプレイ設定ガイド

このガイドでは、Azazel-PiでのWaveshare E-Paperディスプレイの設定、インストール、トラブルシューティングについて説明します。E-Paperディスプレイは、システム状態、防御モード、アラート情報を物理的に表示する機能を提供します。

## 概要

Azazel-PiのE-Paperディスプレイ機能：

- **リアルタイム状態表示**: 現在の防御モード、システム負荷、ネットワーク状態
- **アラート通知**: セキュリティインシデントやシステム異常の視覚化
- **起動アニメーション**: システム開始時のステータス表示
- **省電力運用**: 必要時のみ更新される電子ペーパー技術

## サポートされるハードウェア

### 推奨E-Paperディスプレイ

**Waveshare 2.13inch E-Ink Display HAT (V4)**
- 解像度: 250×122ピクセル
- インターフェース: SPI
- 色: 白黒2色
- 電源: 3.3V
- 部分更新対応

### 対応モデル一覧

| モデル | サイズ | 解像度 | 対応状況 | 備考 |
|--------|--------|---------|----------|------|
| 2.13inch V4 | 2.13" | 250×122 | ✅ 完全対応 | 推奨モデル |
| 2.13inch V3 | 2.13" | 250×122 | ✅ 対応 | 部分更新制限あり |
| 2.9inch | 2.9" | 296×128 | ⚠️ experimental | 要調整 |
| 4.2inch | 4.2" | 400×300 | ⚠️ experimental | 要調整 |

## ハードウェア設定

### GPIO接続

Waveshare 2.13inch E-Ink Display HATの標準接続：

```
E-Paper HAT    Raspberry Pi GPIO
VCC     →      3.3V (Pin 1 or 17)
GND     →      GND  (Pin 6, 9, 14, 20, 25, 30, 34, 39)
DIN     →      GPIO 10 (SPI0_MOSI, Pin 19)
CLK     →      GPIO 11 (SPI0_SCLK, Pin 23)
CS      →      GPIO 8  (SPI0_CE0, Pin 24)
DC      →      GPIO 25 (Pin 22)
RST     →      GPIO 17 (Pin 11)
BUSY    →      GPIO 24 (Pin 18)
```

### HATの使用

Waveshare E-Paper HATを使用する場合、上記のピン配置は自動的に設定されます：

```bash
# HATをRaspberry Piに直接装着
# 追加配線は不要
```

### カスタム配線

HATを使用しない場合の手動配線例：

```bash
# 配線確認スクリプト
gpio readall | grep -E "(10|11|8|25|17|24)"
```

## ソフトウェアインストール

### 統合インストール (推奨)

完全インストーラーにE-Paper統合が追加されました。ハードウェア未接続でもライブラリとサービスを準備できます。

```bash
# E-Paper統合を含む完全インストール
sudo scripts/install_azazel_complete.sh --enable-epd --start

# ハードウェア未接続でエミュレーションのみ行いたい場合
sudo scripts/install_azazel_complete.sh --enable-epd --epd-emulate --start
```

インストール後 `/etc/default/azazel-epd` に設定ファイルが配置され、EPD_OPTS=--emulate を指定することでサービスをエミュレーションモードで動作させられます。

```bash
sudo sed -i '/^EPD_OPTS=/d' /etc/default/azazel-epd
echo 'EPD_OPTS=--emulate' | sudo tee -a /etc/default/azazel-epd
sudo systemctl restart azazel-epd.service
```

### 旧スタンドアロンインストール (廃止)

`scripts/install_epd.sh` は統合により廃止されました。代わりに `--enable-epd` フラグを使用してください。

### 手動インストール

必要に応じて手動でインストール：

#### 1. システム依存関係

```bash
# Python関連パッケージをインストール
sudo apt update
sudo apt install -y \
  python3-pil \
  python3-numpy \
  python3-spidev \
  python3-rpi.gpio \
  libopenjp2-7 \
  libtiff5 \
  git
```

#### 2. SPIインターフェース有効化

```bash
# 現在のSPI状態を確認
lsmod | grep spi

# SPIを有効化（Raspberry Pi OS）
sudo raspi-config nonint do_spi 0

# 手動で設定ファイルを編集
sudo nano /boot/config.txt
# 以下を追加:
# dtparam=spi=on

# Raspberry Pi 5の場合
sudo nano /boot/firmware/config.txt
# 同様にdtparam=spi=onを追加
```

#### 3. Waveshareライブラリ

```bash
# Waveshare E-Paperライブラリをダウンロード
sudo git clone --depth 1 https://github.com/waveshare/e-Paper.git /opt/waveshare-epd

# Pythonライブラリパスを確認
ls -la /opt/waveshare-epd/RaspberryPi_JetsonNano/python/

# システムPythonパスに追加
echo 'export PYTHONPATH="${PYTHONPATH}:/opt/waveshare-epd/RaspberryPi_JetsonNano/python"' | sudo tee -a /etc/environment
```

### インストール確認

```bash
# SPI デバイス確認
ls -l /dev/spidev0.0

# Python依存関係確認
python3 -c \"import PIL, numpy, spidev, RPi.GPIO; print('Dependencies OK')\"

# E-Paperライブラリ確認
python3 -c \"import sys; sys.path.append('/opt/waveshare-epd/RaspberryPi_JetsonNano/python'); import epd2in13_V4; print('EPD library OK')\"
```

## サービス設定

### E-Paperデーモンの設定

デフォルト設定ファイルを編集：

```bash
# 設定ファイルを編集
sudo nano /etc/default/azazel-epd
```

```bash
# Azazel Pi E-Paper Display Configuration

# 更新間隔（秒）- デフォルト: 10
UPDATE_INTERVAL=10

# イベントログファイルのパス
EVENTS_LOG=/var/log/azazel/events.json

# E-Paperドライバー名
# 使用しているハードウェアに応じて調整
EPD_DRIVER=epd2in13_V4

# デバッグログを有効化（デフォルト: 0）
# DEBUG=1

# ジェントル更新（部分更新でちらつき軽減）
GENTLE_UPDATES=1

# エミュレーションモード（物理ディスプレイ不要）
# EMULATE=1
```

### サービス有効化

```bash
# 完全インストーラーで --start を使った場合は自動有効化済み
# 手動で有効化する場合:
sudo systemctl enable azazel-epd.service
sudo systemctl start azazel-epd.service
sudo systemctl status azazel-epd.service
```

### ログ確認

```bash
# サービスログを確認
sudo journalctl -u azazel-epd.service -f

# 最新のログエントリ
sudo journalctl -u azazel-epd.service --since \"10 minutes ago\"
```

## 表示内容とレイアウト

### メイン画面レイアウト

```
┌─────────────────────────────────────────────────┐
│ Azazel-Pi              [Mode: PORTAL]   12:34  │
├─────────────────────────────────────────────────┤
│ CPU: ██████░░░░ 60%    Mem: ███████░░░ 70%     │
│ Net: ↑ 1.2MB/s ↓ 0.8MB/s                      │
│ Alerts: 3    Score: 15/100                     │
├─────────────────────────────────────────────────┤
│ Last Event: 13:45                              │
│ Suspicious TCP scan from 192.168.1.23          │
└─────────────────────────────────────────────────┘
```

### 防御モード表示

#### Portal モード
```
[Mode: PORTAL]
Status: Monitoring
Delay: 100ms
```

#### Shield モード
```
[Mode: SHIELD] 
Status: Enhanced
Delay: 200ms | Limit: 128kbps
```

#### Lockdown モード
```
[Mode: LOCKDOWN]
Status: Quarantine
Delay: 300ms | Limit: 64kbps
⚠️ Network Restricted
```

### アラート表示

高優先度アラート発生時：

```
┌─────────────────────────────────────────────────┐
│ ⚠️  SECURITY ALERT  ⚠️                         │
│                                                 │
│ Intrusion detected!                             │
│ Source: 192.168.1.45                           │
│ Type: Port scan                                 │
│ Time: 14:23:15                                  │
│                                                 │
│ Mode switched: PORTAL → SHIELD                  │
└─────────────────────────────────────────────────┘
```

## 手動操作

### テスト表示 (ハードウェア未接続時は --emulate)

```bash
# テストパターンを表示
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=test --emulate

# 起動アニメーションを表示
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=boot

# 単発更新
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=once

# エミュレーションモード（画像ファイル出力）
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=test --emulate
```

### デバッグモード

```bash
# デバッグ出力有効化
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --debug --mode=test

# 詳細ログ出力
sudo systemctl stop azazel-epd.service
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --debug --interval=5
```

### ディスプレイリセット

```bash
# ディスプレイをクリア
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=clear

# 完全リフレッシュ
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=refresh

# サービス再起動
sudo systemctl restart azazel-epd.service
```

## トラブルシューティング

### 一般的な問題

#### 問題: ディスプレイが更新されない

**症状:**
- 画面が変化しない
- サービスログにエラー
- 古い表示内容のまま

**診断手順:**

```bash
# SPI インターフェース確認
ls -l /dev/spidev0.0
lsmod | grep spi

# サービス状態確認
sudo systemctl status azazel-epd.service

# 手動テスト
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=test
```

**解決策:**

```bash
# SPI有効化
sudo raspi-config nonint do_spi 0
sudo reboot

# 権限確認
sudo usermod -a -G spi,gpio azazel

# サービス再起動
sudo systemctl restart azazel-epd.service
```

#### 問題: 表示にアーティファクトやゴーストが現れる

**症状:**
- 前の画像が残る
- 部分的な表示崩れ
- 文字が読めない

**解決策:**

```bash
# 完全リフレッシュを実行
sudo python3 /opt/azazel/azazel_pi/core/display/epd_daemon.py --mode=refresh

# ジェントル更新を無効化
sudo nano /etc/default/azazel-epd
# GENTLE_UPDATES=0

# 更新間隔を延長
# UPDATE_INTERVAL=30

# サービス再起動
sudo systemctl restart azazel-epd.service
```

#### 問題: Python import エラー

**症状:**
- ModuleNotFoundError
- ライブラリが見つからない
- PIL/numpy関連エラー

**解決策:**

```bash
# 依存関係を再インストール
sudo apt install -y python3-pil python3-numpy python3-spidev python3-rpi.gpio

# Waveshareライブラリを再インストール
sudo rm -rf /opt/waveshare-epd
sudo git clone --depth 1 https://github.com/waveshare/e-Paper.git /opt/waveshare-epd

# Python パス確認
python3 -c \"import sys; print('\\n'.join(sys.path))\"
```

### ハードウェア診断

#### GPIO接続テスト

```bash
# GPIO状態確認
gpio readall

# 特定ピンの状態確認
gpio -g mode 25 out    # DC pin
gpio -g write 25 1
gpio -g read 25

# SPI通信テスト
sudo python3 -c \"
import spidev
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4000000
print('SPI OK')
spi.close()
\"
```

#### 電源供給確認

```bash
# 電圧確認
vcgencmd measure_volts

# 温度確認
vcgencmd measure_temp

# 電力状態確認
vcgencmd get_throttled
```

### パフォーマンス調整

#### 更新頻度の最適化

```bash
# 低頻度更新（バッテリー節約）
sudo nano /etc/default/azazel-epd
# UPDATE_INTERVAL=60

# 高頻度更新（リアルタイム性重視）
# UPDATE_INTERVAL=5
```

#### 画像品質の調整

```bash
# 高品質モード（完全更新）
sudo nano /etc/default/azazel-epd
# GENTLE_UPDATES=0

# 高速モード（部分更新）
# GENTLE_UPDATES=1
```

## カスタマイズ

### 表示レイアウトの変更

表示内容をカスタマイズする場合、Pythonモジュールを編集：

```bash
# カスタムレンダラーファイル
sudo nano /opt/azazel/azazel_pi/core/display/renderer.py

# カスタムレイアウト関数を追加
# class EPaperRenderer:
#     def render_custom_layout(self, data):
#         # カスタム表示ロジック
```

### フォントの変更

```bash
# 日本語フォントを追加
sudo apt install fonts-noto-cjk

# フォントファイルの場所
ls /usr/share/fonts/truetype/noto/

# カスタムフォント設定
sudo nano /opt/azazel/azazel_pi/core/display/fonts.py
```

### アイコンの追加

```bash
# アイコン画像ディレクトリ
sudo mkdir -p /opt/azazel/assets/icons

# カスタムアイコンファイル（24x24 PNG推奨）
sudo cp custom-icon.png /opt/azazel/assets/icons/
```

## 製品別設定

### Waveshare 2.13inch V4 (推奨)

```bash
# /etc/default/azazel-epd
EPD_DRIVER=epd2in13_V4
UPDATE_INTERVAL=10
GENTLE_UPDATES=1
```

### Waveshare 2.13inch V3

```bash
# /etc/default/azazel-epd
EPD_DRIVER=epd2in13_V3
UPDATE_INTERVAL=15
GENTLE_UPDATES=0  # V3は部分更新制限あり
```

### Waveshare 2.9inch (実験的)

```bash
# /etc/default/azazel-epd
EPD_DRIVER=epd2in9
UPDATE_INTERVAL=20
# カスタムレイアウト調整が必要
```

## セキュリティ考慮事項

### 権限設定

```bash
# E-Paperサービス用ユーザー
sudo useradd -r -s /bin/false azazel-epd
sudo usermod -a -G spi,gpio azazel-epd

# systemd サービス設定
sudo nano /etc/systemd/system/azazel-epd.service
# User=azazel-epd
```

### ログ管理

```bash
# ログローテーション設定
sudo nano /etc/logrotate.d/azazel-epd

# 内容:
# /var/log/azazel/epd.log {
#     daily
#     rotate 7
#     compress
#     missingok
#     notifempty
# }
```

## 監視とアラート

### ヘルスチェック

```bash
# E-Paperサービス監視スクリプト
sudo nano /opt/azazel/scripts/epd_healthcheck.sh

#!/bin/bash
# E-Paper display health check
if ! systemctl is-active --quiet azazel-epd.service; then
    echo \"EPD service down\" | logger -t azazel-epd
    systemctl restart azazel-epd.service
fi

# Cronで定期実行
sudo crontab -e
# */5 * * * * /opt/azazel/scripts/epd_healthcheck.sh
```

### パフォーマンス監視

```bash
# 更新時間測定
sudo journalctl -u azazel-epd.service | grep \"Update completed\"

# メモリ使用量確認
ps aux | grep epd_daemon

# CPU使用率確認
top -p $(pgrep -f epd_daemon)
```

## 関連ドキュメント

- [`INSTALLATION_ja.md`](INSTALLATION_ja.md) - Azazel-Pi完全インストールガイド
- [`TROUBLESHOOTING_ja.md`](TROUBLESHOOTING_ja.md) - 包括的トラブルシューティング
- [`OPERATIONS_ja.md`](OPERATIONS_ja.md) - 日常運用とメンテナンス
- [Waveshare公式ドキュメント](https://www.waveshare.com/wiki/2.13inch_e-Paper_HAT) - ハードウェア仕様

## 技術仕様

### 対応E-Paperディスプレイ

| 仕様項目 | 値 |
|----------|-----|
| インターフェース | SPI (4線式) |
| 動作電圧 | 3.3V |
| 消費電力 | < 40mW (更新時), < 0.01mW (待機時) |
| 動作温度 | 0°C ~ 50°C |
| 表示色 | 白黒2色 |
| 視野角 | > 170° |

### GPIO 仕様

| 信号名 | GPIO番号 | 物理ピン | 機能 |
|--------|----------|----------|------|
| VCC | 3.3V | 1, 17 | 電源 |
| GND | GND | 6, 9, 14, 20, 25, 30, 34, 39 | グランド |
| DIN | GPIO 10 | 19 | SPI データ入力 |
| CLK | GPIO 11 | 23 | SPI クロック |
| CS | GPIO 8 | 24 | SPI チップセレクト |
| DC | GPIO 25 | 22 | データ/コマンド選択 |
| RST | GPIO 17 | 11 | リセット |
| BUSY | GPIO 24 | 18 | ビジー信号 |

---

*E-Paperディスプレイの詳細な設定については、[Azazel-Piリポジトリ](https://github.com/01rabbit/Azazel-Pi)とWaveshare公式ドキュメントを参照してください。*