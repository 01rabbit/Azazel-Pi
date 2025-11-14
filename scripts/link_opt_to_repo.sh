#!/usr/bin/env bash
# Create safe symlinks from /opt/azazel/config to files in the repository
# Usage: sudo ./scripts/link_opt_to_repo.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAP=(
  "/opt/azazel/config/docker-compose.yml:$REPO_ROOT/deploy/docker-compose.yml"
  "/opt/azazel/config/opencanary.conf:$REPO_ROOT/deploy/opencanary.conf"
)

# Additionally link every regular file under deploy/ into /opt/azazel/config
# if a file with the same basename doesn't already have an explicit mapping.
for f in "$REPO_ROOT"/deploy/*; do
  [[ -f "$f" ]] || continue
  base=$(basename "$f")
  target="/opt/azazel/config/$base"
  # Skip if already in MAP
  skip=0
  for m in "${MAP[@]}"; do
    if [[ "${m#*:}" == "$f" ]]; then
      skip=1
      break
    fi
  done
  if [[ $skip -eq 0 ]]; then
    MAP+=("$target:$f")
  fi
done

timestamp() { date +%s; }

if [[ $(id -u) -ne 0 ]]; then
  echo "This script requires root. Run with sudo." >&2
  exit 2
fi

echo "Using repo root: $REPO_ROOT"

for entry in "${MAP[@]}"; do
  target_opt=${entry%%:*}
  source_repo=${entry#*:}

  if [[ ! -e "$source_repo" ]]; then
    echo "Skipping $target_opt -> $source_repo : source not found in repo"
    continue
  fi

  # Ensure directory exists
  dir=$(dirname "$target_opt")
  mkdir -p "$dir"

  # If already a symlink to the desired source, skip
  if [[ -L "$target_opt" && "$(readlink -f "$target_opt")" == "$(readlink -f "$source_repo")" ]]; then
    echo "OK: $target_opt already symlinked to repo"
    continue
  fi

  # Backup existing file if present
  if [[ -e "$target_opt" || -L "$target_opt" ]]; then
    bak="$target_opt.bak.$(timestamp)"
    echo "Backing up $target_opt -> $bak"
    mv -f "$target_opt" "$bak"
  fi

  # Create symlink
  echo "Linking $target_opt -> $source_repo"
  ln -s "$source_repo" "$target_opt"
  chmod 644 "$source_repo" || true
  chown root:root "$source_repo" || true
done

echo "Done. Review backups (*.bak.*) if you need to restore original files."
