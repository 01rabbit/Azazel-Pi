#!/usr/bin/env bash
# bin/azazel-qos-menu.sh
# Interactive helper for managing privileged host CSV and invoking azazel-qos-apply.sh
# Notes:
# - This menu is intentionally minimal and defers interface selection to
#   the underlying apply script. To override the LAN interface globally,
#   set AZAZEL_LAN_IF (e.g. export AZAZEL_LAN_IF=${AZAZEL_LAN_IF:-wlan0}).
set -euo pipefail

CSV="configs/network/privileged.csv"
APPLY="bin/azazel-qos-apply.sh"
MODE_FILE="runtime/qos_mode"

mkdir -p runtime configs/network
[[ -f "$MODE_FILE" ]] || echo "verify" > "$MODE_FILE"
[[ -f "$CSV" ]] || echo "# ip,mac,note" > "$CSV"

list() { nl -ba "$CSV"; }
add() {
  read -rp "IP: " IP
  read -rp "MAC: " MAC
  read -rp "NOTE: " NOTE
  [[ -n "$IP" && -n "$MAC" ]] || { echo "入力不備"; return 1; }
  tmp=$(mktemp); grep -vE "^\s*${IP}\s*," "$CSV" > "$tmp" || true; mv "$tmp" "$CSV"
  echo "${IP},${MAC},${NOTE}" >> "$CSV"; echo "追加しました"
}
del() {
  read -rp "削除IP: " IP
  tmp=$(mktemp); grep -vE "^\s*${IP}\s*," "$CSV" > "$tmp" || true; mv "$tmp" "$CSV"
  echo "削除しました"
}
apply() {
  MODE=$(cat "$MODE_FILE")
  sudo MODE="$MODE" "$APPLY" "$CSV"
}
mode() {
  CUR=$(cat "$MODE_FILE"); echo "現在: $CUR"
  read -rp "新MODE(none|verify|lock): " NEW
  case "$NEW" in none|verify|lock) echo "$NEW" > "$MODE_FILE"; echo "切替";; *) echo "無効";; esac
}

while true; do
  echo "1) 一覧  2) 追加  3) 削除  4) 反映  5) モード  6) 終了"
  read -rp "選択: " k
  case "$k" in
    1) list ;;
    2) add ;;
    3) del ;;
    4) apply ;;
    5) mode ;;
    6) exit 0 ;;
    *) echo "無効" ;;
  esac
done
