#!/usr/bin/env bash
set -euo pipefail
# 手動実行用ラッパー: 統合監視を停止して `run_all` を root で起動
# 使い方: sudo ./scripts/manual_monitor.sh

REPO_ROOT="/home/azazel/Azazel-Edge"
PYTHONPATH_ENV="$REPO_ROOT"
MODULE="azazel_edge.monitor.run_all"

if [ "$(id -u)" -ne 0 ]; then
  echo "このスクリプトは root(または sudo) で実行してください。例: sudo $0"
  exit 1
fi

echo "[INFO] 停止: systemd サービス azctl-unified.service, mattermost.service を停止します"
systemctl stop azctl-unified.service || true
systemctl stop mattermost.service || true

echo "[INFO] Suricata は動作させたままにしてください（eve.json を監視するため）。"
echo "[INFO] PYTHONPATH を設定して監視を起動します: PYTHONPATH=$PYTHONPATH_ENV"
echo "--- ログは標準出力に出ます。別ターミナルで確認してください ---"

export PYTHONPATH="$PYTHONPATH_ENV"
exec python3 -u -m "$MODULE"
