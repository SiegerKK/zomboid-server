#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
docker stats --no-stream zomboid-server || true
docker compose logs --tail=80 zomboid
