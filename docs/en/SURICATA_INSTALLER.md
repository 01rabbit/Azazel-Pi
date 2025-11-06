# Suricata installer (Azazel-Pi)

This document describes the installer `scripts/install_suricata_env.sh` included in this repository. The installer recreates the Suricata runtime setup used on the Pi:

- creates system user `suricata`
- ensures `/var/lib/suricata` and `/var/log/suricata` exist and are owned by `suricata`
- creates a systemd drop-in to run Suricata as `suricata` with required capabilities (CAP_NET_RAW, CAP_NET_ADMIN)
- installs an update wrapper at `/usr/local/bin/azazel-suricata-update.sh`
- installs a systemd service+timer to run the update daily
- installs a failure handler to log update failures
- installs logrotate rules for update logs
- deploys `configs/suricata/local.rules` to runtime rules directory

Usage (on the target Raspberry Pi):

Run as root:

```bash
sudo bash scripts/install_suricata_env.sh
```

After the script finishes, verify Suricata is running and monitoring the expected interface (e.g. `wlan1`):

```bash
systemctl status suricata
journalctl -u suricata -n 50 --no-pager
cat /var/log/suricata/eve.json | jq 'select(.event_type=="alert")' | head -n 5
```

Notes and caveats:
- The installer writes systemd units and logrotate configs directly to `/etc`.
- This script is intended for offline/air-gapped environments where the repo is placed on the target device first.
- Review the script before running on production. Adjust `OnCalendar` for the timer or the update sources as needed.
