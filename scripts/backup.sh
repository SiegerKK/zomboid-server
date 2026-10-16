#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cid="$(docker compose ps -q zomboid || true)"
if [[ -n "$cid" && "$(docker inspect -f '{{.State.Running}}' "$cid")" == "true" ]]; then
  echo "Stop server before cold backup" >&2
  exit 1
fi
mkdir -p /srv/zomboid/backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
docker run --rm -v /srv/zomboid/data:/source:ro -v /srv/zomboid/backups:/dest alpine:3.20   tar -czf "/dest/world-$stamp.tar.gz" -C /source .
echo "Backup created. Copy it off-server as well."
