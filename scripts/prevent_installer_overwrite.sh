#!/usr/bin/env bash
# Lightweight guard to be sourced by install scripts to avoid overwriting
# configuration files that are symlinked to the repository.
is_symlinked() {
  local file="$1"
  if [[ -L "$file" ]]; then
    # Resolve link target and check if it lives under the repo
    local target
    target=$(readlink -f "$file")
    case "$target" in
      $(cd "$(dirname "$0")/.." && pwd)/*)
        return 0
        ;;
      *) return 1 ;;
    esac
  fi
  return 1
}

# Usage: prevent_overwrite /path/to/file
prevent_overwrite() {
  local file="$1"
  if is_symlinked "$file"; then
    echo "Detected that $file is symlinked to the repository; skipping overwrite." >&2
    return 0
  fi
  return 1
}

exit 0
