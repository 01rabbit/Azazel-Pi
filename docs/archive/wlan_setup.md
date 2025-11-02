# wlan0 を内部 AP として構成する手順

このドキュメントは、Raspberry Pi で `wlan0` を内部ネットワーク（172.16.0.0/24）のアクセスポイントにし、`wlan1` を通じてインターネットへ NAT するための手順をまとめたものです。

重要事項
- 内部ネットワーク: 172.16.0.0/24
- AP インターフェイス: `wlan0`（AP モードをサポートしていること）
- 外向きインターフェイス: `wlan1`（既に外部SSIDへ接続されていること）

同梱スクリプト
- `scripts/setup_wlan0_ap.sh` — システムを変更する実行スクリプト（sudo で実行）。実行前にスクリプト内の変数（SSID, PASSPHRASE, WLAN_AP, WLAN_UP 等）を確認してください。
- `scripts/templates/` — hostapd, dnsmasq, nftables のテンプレート。

使い方（簡易）

1. リポジトリの `scripts/setup_wlan0_ap.sh` を実機にコピー（または直接このリポジトリをクローン）します。
2. 必要ならスクリプトの先頭で SSID、パスフレーズ、インターフェイス名を編集します。
3. 実行:

```bash
sudo bash scripts/setup_wlan0_ap.sh
```

4. スクリプトは /etc/hostapd/hostapd.conf、/etc/dnsmasq.d/01-wlan0.conf、/etc/dhcpcd.conf に変更を加えます。原本は可能な限りバックアップされます。
5. 設定後、クライアントから SSID に接続して IP を受け取り、インターネット接続ができるか確認してください。

手動で行いたい場合はテンプレートを参照して以下の手順で実施します。

1) hostapd の設定（/etc/hostapd/hostapd.conf）

2) /etc/default/hostapd に DAEMON_CONF を設定

3) /etc/dhcpcd.conf に静的 IP (172.16.0.1/24) の追記と nohook wpa_supplicant

4) dnsmasq の設定 (/etc/dnsmasq.d/01-wlan0.conf)

5) カーネル IP フォワーディングを有効化

6) nftables を用いて wlan0 -> wlan1 のマスカレードを設定（テンプレート参照）

検証ポイント
- `ip addr show dev wlan0` で 172.16.0.1 が割り当てられていること
- クライアントが DHCP で 172.16.0.x を取得できること
- Pi から `ping -I wlan1 8.8.8.8` が通ること
- クライアントが外部へアクセスできること

Suricata の設定（wlan1 監視）

この構成では Suricata を `wlan1` で監視することを推奨します。リポジトリに設定支援スクリプトを用意しました:

```
sudo bash scripts/setup_suricata_wlan1.sh
```

スクリプトが行うこと:
- `/etc/suricata/suricata.yaml` の `HOME_NET` を `172.16.0.0/24` に書き換え（バックアップあり）
- `/etc/default/suricata` に起動引数 `-i wlan1 --af-packet` を設定して、Suricata を `wlan1` で起動するようにする
- Suricata サービスを再起動してログを確認します

手動で行いたい場合:
- `/etc/suricata/suricata.yaml` の `vars -> address-groups -> HOME_NET` を `"[172.16.0.0/24]"` に設定してください
- サービスを `-i wlan1` の引数で起動するか、`/etc/default/suricata` の `SURICATA_ARGS` を編集して `systemctl restart suricata` してください


トラブルシュート
- hostapd が起動しない: `journalctl -u hostapd -e`
- dnsmasq の問題: `journalctl -u dnsmasq -e` と `/var/log/syslog`
- NAT が効かない: `sysctl net.ipv4.ip_forward` と `sudo nft list ruleset`
