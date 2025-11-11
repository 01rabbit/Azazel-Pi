#!/usr/bin/env bash
set -euo pipefail
# Start a demo tmux session that runs:
#  - azctl serve (monitor)
#  - eve_replay (inject events)
#  - azctl status --tui --watch (live view)

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="azazel-demo"
EVE_FILE="$REPO_ROOT/runtime/demo_eve.json"
DECISIONS_LOG="$REPO_ROOT/decisions.log"
LOG_DIR="$REPO_ROOT/runtime/logs"

mkdir -p "$LOG_DIR"

CMD_SERVE=(python3 -m azctl.cli serve --suricata-eve "$EVE_FILE" --decisions-log "$DECISIONS_LOG")
CMD_EVE=(python3 "$REPO_ROOT/scripts/eve_replay.py" --file "$EVE_FILE" --interval 5 --loop)
CMD_TUI=(python3 -m azctl.cli status --tui --watch)

which tmux >/dev/null 2>&1 && USE_TMUX=true || USE_TMUX=false

if $USE_TMUX; then
  # Create or reuse session
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session $SESSION already exists. Attaching..."
    tmux attach -t "$SESSION"
    exit 0
  fi

  echo "Creating tmux session: $SESSION"
  tmux new-session -d -s "$SESSION" -c "$REPO_ROOT"
  # Pane 0: serve
  tmux send-keys -t "$SESSION:0.0" "${CMD_SERVE[*]} 2> $LOG_DIR/serve.log" C-m
  # Split pane for eve_replay
  tmux split-window -v -t "$SESSION:0.0" -c "$REPO_ROOT"
  tmux send-keys -t "$SESSION:0.1" "${CMD_EVE[*]} 2> $LOG_DIR/eve_replay.log" C-m
  # Split the lower pane horizontally for TUI
  tmux split-window -h -t "$SESSION:0.1" -c "$REPO_ROOT"
  tmux send-keys -t "$SESSION:0.2" "${CMD_TUI[*]} 2> $LOG_DIR/tui.log" C-m
  tmux select-layout -t "$SESSION" tiled

  echo "Started demo in tmux session '$SESSION'. Attach with: tmux attach -t $SESSION"
  echo "Logs: $LOG_DIR"
else
  echo "tmux not found; falling back to background processes (nohup)."
  nohup "${CMD_SERVE[@]}" > "$LOG_DIR/serve.log" 2>&1 &
  echo $! > "$REPO_ROOT/runtime/serve.pid"
  nohup "${CMD_EVE[@]}" > "$LOG_DIR/eve_replay.log" 2>&1 &
  echo $! > "$REPO_ROOT/runtime/eve_replay.pid"
  nohup "${CMD_TUI[@]}" > "$LOG_DIR/tui.log" 2>&1 &
  echo $! > "$REPO_ROOT/runtime/tui.pid"

  echo "Started demo processes in background. Logs: $LOG_DIR"
fi

exit 0
