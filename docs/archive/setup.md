## 🧩 システム構成 / System Architecture

Azazelは以下のコンポーネントで構成されます：  
*Azazel is composed of the following components:*

- OpenCanary（ハニーポットサービス、ホスト上で稼働） / Honeypot service running on the host
- Vector（ログ収集と転送、ホスト上で稼働） / Log collection and forwarding on the host
- Mattermost（通知UI、ホスト上で稼働） / Notification and collaboration UI on the host
- Nginx（Mattermost向けリバースプロキシ） / Reverse proxy for Mattermost
- PostgreSQL（Mattermost用DB、Dockerコンテナとして稼働） / Mattermost database running in Docker

PostgreSQL のみ Docker コンテナで提供され、それ以外のサービスは systemd から直接管理されます。  
*Only PostgreSQL runs inside Docker; all other services are managed directly via systemd on the host.*

---

## ⚙️ 設定ファイルの説明 / Configuration Files

### `/opt/azazel/config/opencanary.conf`
- 各種疑似サービス（SSH, HTTPなど）の有効化・ログ出力設定  
  *Enables simulated services like SSH/HTTP and sets log output settings.*
- `device.node_id` は一意な識別子  
  *`device.node_id` must be unique for each instance.*

### `/opt/azazel/config/vector.toml`
- Vectorが収集するログソース（例：OpenCanaryログ、Suricataログ）  
  *Defines sources Vector will collect logs from (e.g., OpenCanary, Suricata).* 
- 出力先はコンソール、ファイル、もしくは将来的にSIEM連携  
  *Output can be console, file, or eventually a SIEM system.*

### `/opt/mattermost/config/config.json`
- `install_azazel.sh` により `SiteURL` や `DataSource` が自動設定される  
  *`install_azazel.sh` automatically configures `SiteURL` and `DataSource`.*
- 手動でSMTPやファイルストレージなど追加設定可能  
  *You can manually configure SMTP, file storage, etc.*

### `/opt/azazel/config/docker-compose.yml` & `.env`
- PostgreSQL コンテナの定義と資格情報を保持  
  *Defines the PostgreSQL container and stores credentials.*
- `.env` は `MATTERMOST_DB_*` 変数を提供し、Mattermost との整合性を維持します  
  *The `.env` file exposes the `MATTERMOST_DB_*` variables to keep Mattermost in sync.*

---

## 🚦 起動順と依存関係 / Startup Sequence and Dependencies

- PostgreSQL コンテナは `/opt/azazel/config/docker-compose.yml` を用いて起動 (`docker compose --project-name azazel-db up -d`)  
  *Bring up PostgreSQL with `docker compose --project-name azazel-db up -d` in `/opt/azazel/config`.*
- Mattermost は PostgreSQL が `Up` になってから systemd 経由で起動  
  *Mattermost requires PostgreSQL to be running before its own startup.*
- `config.json` 編集後は `chown/chmod` を適切に行わないと起動失敗します  
  *Ensure `config.json` has correct ownership and permissions after editing.*
- `install_azazel.sh` は `mattermost.service` と `nginx.service` を自動有効化します  
  *The installer enables both `mattermost.service` and `nginx.service` automatically.*

---

## 🛠️ カスタマイズ例 / Customization Examples

- `.env` の `MATTERMOST_DB_PASSWORD` を変更し、同値を `config.json` に反映  
  *Rotate `MATTERMOST_DB_PASSWORD` in `.env` and mirror the change into `config.json`.*
- Nginx のリッスンポートや TLS 設定を `/etc/nginx/nginx.conf` で調整  
  *Tune Nginx listen ports and TLS settings via `/etc/nginx/nginx.conf`.*
- OpenCanary のサービス追加（Telnet, SMBなど）  
  *Enable additional OpenCanary services (e.g., Telnet, SMB).* 
- Vector のログ出力形式を JSON → text に変更  
  *Change Vector log output format from JSON to plain text.*

---

## 🧪 トラブルシュート / Troubleshooting

| 問題 / Problem | 原因 / Cause | 解決策 / Solution |
|------|------|--------|
| OpenCanary が Restarting を繰り返す / OpenCanary keeps restarting | `/root/.opencanary.conf` がディレクトリ / It is a directory | `rm -rf` して再起動 / Remove and restart |
| Vector が `is a directory` エラー / Vector "is a directory" error | `/etc/vector/vector.toml` が誤ってディレクトリ / It is incorrectly a directory | 正しいファイルを再配置 / Replace with correct file |
| Mattermost 起動失敗 `exit-code` / Mattermost fails with exit-code | `config.json` のパーミッション or DB接続誤り / Permission or DB access error | `chown` と DSN (例: `127.0.0.1:5432`) を確認 / Fix ownership and the DSN (e.g., `127.0.0.1:5432`) |

---

## 🔁 メンテナンスと更新 / Maintenance

- Suricataルール更新：  
  *Update Suricata rules:*
```bash
sudo suricata-update
```

- PostgreSQL コンテナの再起動：  
  *Restart the PostgreSQL container:*
```bash
(cd /opt/azazel/config && sudo docker compose --project-name azazel-db down && sudo docker compose --project-name azazel-db up -d)
```

- Mattermostのログ確認：  
  *Check Mattermost logs:*
```bash
sudo journalctl -u mattermost -e
```

---

## 📘 その他 / Notes

- `.env` や `.local` 設定などを活用することで、構成をより柔軟にできます  
  *You can further customize the setup using `.env` or `.local` files.*
- Mattermostの管理者アカウント作成は初回ブラウザアクセス時に行います  
  *Create the Mattermost admin account via the browser on first access.*

For advanced use, consider adjusting `.env` or mounting your own configuration volume.
