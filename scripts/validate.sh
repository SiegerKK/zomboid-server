#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env || { echo "Create VPS-only .env from .env.example" >&2; exit 1; }
if grep -q CHANGE_ME_ .env; then echo "Set secrets in .env first" >&2; exit 1; fi
docker compose config --quiet
echo "Compose OK"
