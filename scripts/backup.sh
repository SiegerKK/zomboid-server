#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec 9>/run/lock/pz-operation.lock
flock -n 9 || { echo "Another PZ operation is running" >&2; exit 1; }
docker compose config --quiet
cid="$(docker compose ps --all -q zomboid)"
if [[ -n "$cid" && "$(docker inspect -f '{{.State.Running}}' "$cid")" != "false" ]]; then
  echo "Stop server before cold backup" >&2
  exit 1
fi
umask 077
install -d -m 700 /srv/zomboid/backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="/srv/zomboid/backups/world-$stamp.tar.gz"
tar --acls --xattrs --numeric-owner -czf "$archive.partial" -C /srv/zomboid/data .
tar -tzf "$archive.partial" >/dev/null
mv "$archive.partial" "$archive"
sha256sum "$archive" > "$archive.sha256"
echo "Cold backup created and archive checked. Restore test and offsite copy still required."
