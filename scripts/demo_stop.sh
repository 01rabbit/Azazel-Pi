#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="azazel-demo"
LOG_DIR="$REPO_ROOT/runtime/logs"

which tmux >/dev/null 2>&1 && USE_TMUX=true || USE_TMUX=false

if $USE_TMUX; then
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Killing tmux session $SESSION"
    tmux kill-session -t "$SESSION"
  else
    echo "No tmux session named $SESSION found."
  fi
else
  echo "tmux not available; attempting to stop background demo processes by PID files."
  for f in serve eve_replay tui; do
    pidfile="$REPO_ROOT/runtime/${f}.pid"
    if [ -f "$pidfile" ]; then
      pid=$(cat "$pidfile" 2>/dev/null || echo "")
      if [ -n "$pid" ]; then
        if kill -0 "$pid" 2>/dev/null; then
          echo "Killing $f (pid=$pid)"
          kill "$pid" || true
          sleep 0.2
        fi
      fi
      rm -f "$pidfile"
    fi
  done
fi

echo "Demo stopped. Logs are in: $LOG_DIR"
exit 0
