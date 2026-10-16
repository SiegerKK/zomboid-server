#!/usr/bin/env bash
set -euo pipefail
# Upstream's init script prints argv, including ADMIN_PASSWORD. Remove that
# exact log statement before starting. Fail closed if upstream changes it.
python3 - <<'PY'
from pathlib import Path
p = Path('/scripts/init-server.sh')
source = p.read_text()
line = 'echo "Starting Project Zomboid server with arguments: ${ARGS[*]}"'
marker = '# bootstrap: secret-bearing argument log removed'
if source.count(line) == 1:
    p.write_text(source.replace(line, marker))
elif marker not in source:
    raise SystemExit('Unexpected upstream init script; review before startup')
PY
exec /bin/bash /scripts/entrypoint.sh "$@"
