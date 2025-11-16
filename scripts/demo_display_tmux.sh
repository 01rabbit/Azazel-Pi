#!/usr/bin/env bash
set -euo pipefail

# Build a tmux dashboard for demo monitoring:
#   ┌───────────── top pane ─────────────┐
#   │ azctl status --tui --watch         │
#   └───────────── bottom panes ─────────┘
#   │  tail Suricata eve.json │ tail OpenCanary log │
#
# Environment overrides:
#   SESSION_NAME   - tmux session name (default: azazel-demo-display)
#   SURICATA_LOG   - path to Suricata eve.json (default: /var/log/suricata/eve.json)
#   OPENCANARY_LOG - path to OpenCanary log (default: /opt/azazel/logs/opencanary.log)
#   TUI_CMD        - command for the top pane (default: python3 -m azctl.cli status --tui --watch)
#   TAIL_LINES     - how many lines tail shows initially (default: 200)
#   SURICATA_CMD   - full command for the Suricata pane (overrides SURICATA_LOG/TAIL_LINES)
#   OPENCANARY_CMD - full command for the OpenCanary pane
# Usage: scripts/demo_display_tmux.sh [--session NAME] [--suricata-log PATH]
#                                      [--opencanary-log PATH] [--tail-lines N]
#                                      [--tui-cmd "command ..."]

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION_NAME="${SESSION_NAME:-azazel-demo-display}"
SURICATA_LOG_DEFAULT="/var/log/suricata/eve.json"
OPENCANARY_LOG_DEFAULT="/opt/azazel/logs/opencanary.log"
SURICATA_LOG="${SURICATA_LOG:-$SURICATA_LOG_DEFAULT}"
OPENCANARY_LOG="${OPENCANARY_LOG:-$OPENCANARY_LOG_DEFAULT}"
TUI_CMD="${TUI_CMD:-python3 -m azctl.cli status --tui --watch}"
TAIL_LINES="${TAIL_LINES:-200}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]
  --session NAME         tmux session name (default: $SESSION_NAME)
  --suricata-log PATH    Suricata eve.json path (default: $SURICATA_LOG)
  --opencanary-log PATH  OpenCanary log path (default: $OPENCANARY_LOG)
  --tail-lines N         Number of lines tail prints initially (default: $TAIL_LINES)
  --tui-cmd "CMD"        Command for the top (TUI) pane
  -h, --help             Show this help

Environment variables can override the same settings (see script header).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session)
      [[ $# -lt 2 ]] && { echo "Missing value for --session" >&2; exit 1; }
      SESSION_NAME="$2"
      shift 2
      ;;
    --suricata-log)
      [[ $# -lt 2 ]] && { echo "Missing value for --suricata-log" >&2; exit 1; }
      SURICATA_LOG="$2"
      shift 2
      ;;
    --opencanary-log)
      [[ $# -lt 2 ]] && { echo "Missing value for --opencanary-log" >&2; exit 1; }
      OPENCANARY_LOG="$2"
      shift 2
      ;;
    --tail-lines)
      [[ $# -lt 2 ]] && { echo "Missing value for --tail-lines" >&2; exit 1; }
      TAIL_LINES="$2"
      shift 2
      ;;
    --tui-cmd)
      [[ $# -lt 2 ]] && { echo "Missing value for --tui-cmd" >&2; exit 1; }
      TUI_CMD="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required but not installed. Please install tmux and retry." >&2
  exit 1
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "Session '$SESSION_NAME' already exists. Attaching..."
  exec tmux attach -t "$SESSION_NAME"
fi

warn_if_missing_log() {
  local label="$1"
  local path="$2"
  if [[ ! -e "$path" ]]; then
    echo "Warning: $label log '$path' not found yet. The pane will wait for it to appear." >&2
  fi
}

warn_if_missing_log "Suricata" "$SURICATA_LOG"
warn_if_missing_log "OpenCanary" "$OPENCANARY_LOG"

: "${SURICATA_CMD:=tail -n ${TAIL_LINES} -F ${SURICATA_LOG}}"
: "${OPENCANARY_CMD:=tail -n ${TAIL_LINES} -F ${OPENCANARY_LOG}}"

create_session() {
  tmux new-session -d -s "$SESSION_NAME" -c "$REPO_ROOT"
  tmux send-keys -t "$SESSION_NAME:0.0" "$TUI_CMD" C-m

  # Split horizontally: top TUI, bottom logs
  tmux split-window -v -t "$SESSION_NAME:0.0" -c "$REPO_ROOT"
  # Split bottom pane vertically into Suricata (left) and OpenCanary (right)
  tmux split-window -h -t "$SESSION_NAME:0.1" -c "$REPO_ROOT"

  tmux send-keys -t "$SESSION_NAME:0.1" "$SURICATA_CMD" C-m
  tmux send-keys -t "$SESSION_NAME:0.2" "$OPENCANARY_CMD" C-m

  tmux select-pane -t "$SESSION_NAME:0.0"
}

create_session
echo "Started tmux session '$SESSION_NAME'. Attaching..."
exec tmux attach -t "$SESSION_NAME"
