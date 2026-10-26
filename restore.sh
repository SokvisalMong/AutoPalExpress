#!/usr/bin/env bash
set -euo pipefail
umask 077

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Restore requires Python 3.10+ on the host (no pip packages needed).\n' >&2
    exit 1
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$ROOT/scripts/server_restore.py" "$@"
