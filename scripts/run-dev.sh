#!/usr/bin/env bash
# Kept for compatibility: runs backend + frontend in the foreground.
# Ctrl+C stops both. Prefer `scripts/rf-gateway start|stop|status`.
exec "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/rf-gateway" run "$@"
