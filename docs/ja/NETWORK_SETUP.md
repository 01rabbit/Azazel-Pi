# ネットワーク設定ガイド

このガイドでは、Azazel-Piの展開におけるネットワーク設定について、インストーラーによる自動設定と高度な用途向けの手動設定手順を含めて説明します。

## 概要

Azazel-Piは複数のネットワークモードで動作できます：

1. **ゲートウェイモード**: インターネット共有機能付きのWi-Fiアクセスポイントとして動作
2. **モニターモード**: ルーティングを行わず、既存のネットワークトラフィックを監視
3. **ブリッジモード**: ネットワークセグメント間での透明なインライン監視

大部分の展開では、インストーラーが自動設定を提供し、特別な展開向けに手動オプションも用意されています。

## 自動ネットワーク設定

### インストール中の設定

`install_azazel.sh`スクリプトは、`azazel.yaml`設定に基づいてネットワークインターフェースを自動設定します。これは大部分の展開での**推奨アプローチ**です。

#### azazel.yamlによる設定

ネットワーク要件を指定するため、`/etc/azazel/azazel.yaml`を編集します：

```yaml
network:
  # プライマリ監視インターフェース
  interface: "eth0"
  
  # IDSルール用のホームネットワーク定義
  home_net: "192.168.1.0/24"
  
  # ゲートウェイモード設定（オプション）
  gateway_mode:
    enabled: true
    ap_interface: "wlan0"
    client_interface: "wlan1"  
    internal_network: "172.16.0.0/24"
    gateway_ip: "172.16.0.254"       # 内部ネットワークゲートウェイIP
    ap_ssid: "Azazel_Internal"       # 内部AP SSID
    ap_passphrase: "change-this-to-a-strong-pass"
    
  # 静的IP設定（オプション）
  static_ip:
    enabled: false
    address: "192.168.1.100/24"
    gateway: "192.168.1.1"
    dns: ["8.8.8.8", "1.1.1.1"]
```

#### ネットワーク設定の適用

設定編集後：

```bash
# ネットワーク変更を適用するためAzazelサービスを再起動
sudo systemctl restart azctl-unified.service

# インターフェース設定を確認
ip addr show
ip route show
```

## ゲートウェイモードの設定

Azazel-Piがインターネット共有機能付きのWi-Fiアクセスポイントとして動作する必要がある場合：

### 自動ゲートウェイ設定

1. **インターフェース設定**: `azazel.yaml`で`gateway_mode.enabled: true`を設定
2. **インターフェース指定**: 
   - `ap_interface`: アクセスポイントをホストするインターフェース（例：`wlan0`）
   - `client_interface`: インターネットに接続するインターフェース（例：`wlan1`または`eth0`）
3. **サービス再起動**: `sudo systemctl restart azctl-unified.service`

### 検証

```bash
# アクセスポイント状態を確認
sudo systemctl status hostapd

# DHCPサーバーを確認
sudo systemctl status dnsmasq

# インターネット接続をテスト
ping -I wlan1 8.8.8.8

# NATルールを確認
sudo nft list ruleset | grep -A5 -B5 masquerade
```

### クライアント接続テスト

クライアントデバイスから：
1. 設定されたSSID（例：「Azazel-GW」）に接続
2. DHCP IP割り当てを確認（設定された範囲のIPを受信する必要）
3. インターネット接続をテスト
4. Azazelウェブインターフェースへのアクセスを確認

## モニターモードの設定

ルーティングを行わず既存のネットワークトラフィックを監視する展開の場合：

### 設定

```yaml
network:
  interface: "eth0"
  mode: "monitor"
  home_net: "192.168.1.0/24"
  
  # パケットキャプチャのプロミスキャスモード
  promiscuous: true
  
  # Suricata監視設定
  suricata:
    interface: "eth0"
    capture_mode: "af-packet"
```

### Suricata統合

監視インターフェース用のSuricataを設定：

```bash
# Suricata設定を生成
sudo /opt/azazel/scripts/suricata_generate.py \
  /etc/azazel/azazel.yaml \
  /etc/azazel/suricata/suricata.yaml.tmpl \
  --output /etc/suricata/suricata.yaml

# Suricataを再起動
sudo systemctl restart suricata

# 監視を確認
sudo tail -f /var/log/suricata/eve.json
```

## 手動ネットワーク設定

カスタムネットワーク設定が必要な高度な展開の場合：

### 手動Wi-Fiアクセスポイント設定

自動設定がニーズに合わない場合、コンポーネントを手動で設定できます：

#### 1. hostapd設定

```bash
# hostapd設定を作成
sudo tee /etc/hostapd/hostapd.conf <<EOF
interface=wlan0
driver=nl80211
ssid=Azazel-GW
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=SecurePassphrase123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
country_code=JP
EOF

# hostapd設定パスを設定
echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' | sudo tee -a /etc/default/hostapd

# hostapdを有効化・開始
sudo systemctl unmask hostapd
sudo systemctl enable --now hostapd
```

#### 2. DHCPサーバー設定

```bash
# DHCP用のdnsmasqを設定
sudo tee /etc/dnsmasq.d/01-azazel.conf <<EOF
interface=wlan0
dhcp-range=172.16.0.10,172.16.0.200,255.255.255.0,24h
dhcp-option=3,172.16.0.254  # ゲートウェイ（Azazel-Pi）
dhcp-option=6,8.8.8.8,8.8.4.4  # DNS
server=8.8.8.8
domain-needed
bogus-priv
listen-address=127.0.0.1,172.16.0.254
EOF

# dnsmasqを再起動
sudo systemctl restart dnsmasq
```

#### 3. 静的IP設定

```bash
# APインターフェース用の静的IPを設定
sudo tee -a /etc/dhcpcd.conf <<EOF

# Azazel-Pi AP設定（内部ゲートウェイ）
interface wlan0
static ip_address=172.16.0.254/24
nohook wpa_supplicant
EOF

# ネットワークサービスを再起動
sudo systemctl restart dhcpcd
```

#### 4. NATとIPフォワーディング

```bash
# IPフォワーディングを有効化
echo 'net.ipv4.ip_forward=1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# nftablesでNATを設定
sudo tee /etc/nftables.d/nat.nft <<EOF
table ip nat {
    chain prerouting {
        type nat hook prerouting priority -100;
    }
    
    chain postrouting {
        type nat hook postrouting priority 100;
        oifname "wlan1" masquerade
    }
}
EOF

# nftablesルールを適用
sudo nft -f /etc/nftables.d/nat.nft
sudo systemctl enable nftables
```

### 外部クライアント接続設定

外部Wi-Fiネットワークへの接続の場合：

#### wpa_supplicant設定

```bash
# 外部Wi-Fi接続を設定
sudo tee /etc/wpa_supplicant/wpa_supplicant-wlan1.conf <<EOF
country=JP
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="ExternalNetworkSSID"
    psk="ExternalNetworkPassword"
    key_mgmt=WPA-PSK
}
EOF

# 権限を設定
sudo chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan1.conf

# wpa_supplicantサービスを有効化
sudo systemctl enable wpa_supplicant@wlan1.service
sudo systemctl start wpa_supplicant@wlan1.service
```

## ネットワークトラブルシューティング

### インターフェース問題

```bash
# 全ネットワークインターフェースをリスト
ip link show

# インターフェース状態を確認
ip addr show <interface>

# インターフェースのアップ/ダウン
sudo ip link set <interface> up
sudo ip link set <interface> down

# ワイヤレス機能を確認
sudo iwlist scan | head -20
```

### DHCP問題

```bash
# DHCPサーバー状態を確認
sudo systemctl status dnsmasq

# DHCPリースを確認
sudo cat /var/lib/dhcp/dhcpcd.leases

# クライアントからDHCPをテスト
sudo dhclient -v <interface>
```

### アクセスポイント問題

```bash
# hostapd状態を確認
sudo systemctl status hostapd

# hostapdログを確認
sudo journalctl -u hostapd -f

# APビーコンをテスト
sudo iwlist <interface> scan | grep -A5 -B5 "Azazel"
```

### 接続性問題

```bash
# インターネット接続をテスト
ping -c 4 8.8.8.8

# ルーティングテーブルを確認
ip route show

# NAT機能をテスト
sudo tcpdump -i wlan1 -n icmp

# ファイアウォールルールを確認
sudo nft list ruleset
```

### パフォーマンス問題

```bash
# インターフェース統計を確認
cat /proc/net/dev

# ワイヤレス統計を監視
watch -n1 cat /proc/net/wireless

# 帯域幅をテスト
iperf3 -c <server> -t 30
```

## 高度なネットワーキング

### VLAN設定

VLANセグメンテーションが必要な展開の場合：

```bash
# VLANインターフェースを作成
sudo ip link add link eth0 name eth0.100 type vlan id 100
sudo ip link set dev eth0.100 up
sudo ip addr add 192.168.100.1/24 dev eth0.100

# VLAN用のSuricataを設定
# /etc/azazel/azazel.yamlをVLANインターフェースで更新
```

### ブリッジ設定

透明監視設定の場合：

```bash
# ブリッジを作成
sudo brctl addbr br0
sudo brctl addif br0 eth0
sudo brctl addif br0 eth1

# ブリッジを有効化
sudo ip link set dev br0 up

# ブリッジモード用のSuricataを設定
# suricata.yamlをブリッジ設定で更新
```

### トラフィックシェーピング

QoSとトラフィック制御を設定：

```bash
# トラフィック制御ルールを適用
sudo /opt/azazel/tc_reset.sh
sudo /opt/azazel/nft_apply.sh

# トラフィックシェーピングを監視
sudo tc -s qdisc show
sudo tc -s class show dev <interface>
```

## ネットワークセキュリティ

### ファイアウォール設定

```bash
# 現在のnftablesルールを確認
sudo nft list ruleset

# Azazelファイアウォールルールを適用
sudo nft -f /etc/azazel/nftables/lockdown.nft

# ルール統計を確認
sudo nft list ruleset -a
```

### 侵入検知

```bash
# Suricataアラートを確認
sudo tail -f /var/log/suricata/fast.log

# ネットワークトラフィックを監視
sudo tcpdump -i <interface> -n -c 100

# OpenCanaryハニーポットログを確認
docker logs -f azazel_opencanary
```

## レガシーネットワーク設定

参考として、以下のアーカイブされたドキュメントに追加の手動設定手順が含まれています：

- **wlan_setup.md**（アーカイブ済み）: 詳細な手動Wi-Fi AP設定手順
- **RaspAP_config.md**（アーカイブ済み）: RaspAP統合ガイド

これらは参考のため`docs/archive/`に保管されていますが、新しい展開では**推奨されません**。代わりに上記の自動設定方法を使用してください。

## 既存インフラとの統合

### 企業ネットワーク

既存の企業ネットワークでの展開の場合：

1. **静的IP割り当て**: DHCP競合を避けるため静的IPを設定
2. **VLAN統合**: ネットワークセグメンテーション用の適切なVLANタグを使用
3. **DNS設定**: 内部DNSサーバーを使用
4. **プロキシ設定**: 必要に応じて企業プロキシを設定
5. **認証局**: 必要に応じて企業CA証明書をインストール

### クラウド統合

クラウド接続展開の場合：

1. **VPN設定**: リモート管理用のサイト間VPNを設定
2. **ログ転送**: クラウドSIEMへのログ送信用のVectorを設定
3. **リモート監視**: ウェブインターフェースへの安全なリモートアクセスを有効化
4. **バックアップ接続**: フェイルオーバーネットワーク接続を設定

## 日本固有のネットワーク設定

### 技適対応

日本での無線設備使用に関する設定：

```bash
# 日本の電波法に準拠した設定
sudo tee -a /etc/hostapd/hostapd.conf <<EOF
country_code=JP
ieee80211d=1
ieee80211h=1
EOF

# Raspberry Pi用のregdomainを設定
echo 'REGDOMAIN=JP' | sudo tee -a /etc/default/crda
```

### ISP固有設定

日本の主要ISPでの設定例：

#### NTT フレッツ系

```bash
# PPPoE設定（必要に応じて）
sudo pppoeconf

# IPv6設定
echo 'net.ipv6.conf.all.forwarding=1' | sudo tee -a /etc/sysctl.conf
```

#### KDDI/au系

```bash
# IPv4 over IPv6 (DS-Lite) 設定
# ※ISPから提供される設定情報に基づいて設定
```

### 地域固有の周波数設定

```bash
# 2.4GHz帯の推奨チャネル（日本）
# チャネル1, 6, 11を使用することを推奨
sudo nano /etc/hostapd/hostapd.conf
# channel=1  # または6, 11
```

## 関連ドキュメント

- [`INSTALLATION_ja.md`](INSTALLATION_ja.md) - 完全インストールガイド
- [`OPERATIONS_ja.md`](OPERATIONS_ja.md) - 運用手順
- [`TROUBLESHOOTING_ja.md`](TROUBLESHOOTING_ja.md) - ネットワークトラブルシューティング
- [`docs/archive/wlan_setup.md`](archive/wlan_setup.md) - レガシー手動設定手順

---

*最新のネットワーキングガイダンスについては、[Azazel-Piリポジトリ](https://github.com/01rabbit/Azazel-Pi)を参照し、企業展開については管理者に相談してください。*
