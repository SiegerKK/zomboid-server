#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose ps
docker stats --no-stream zomboid-server || true
# Upstream may log command arguments and secrets. Redact before displaying.
python3 - <<'PY'
from pathlib import Path
import subprocess
secrets = []
for line in Path('.env').read_text().splitlines():
    key, sep, value = line.partition('=')
    if sep and any(x in key.upper() for x in ('PASSWORD', 'TOKEN', 'SECRET')):
        value = value.strip().strip('\"').strip("'")
        if value:
            secrets.append(value)
p = subprocess.run(['docker', 'compose', 'logs', '--tail=80', 'zomboid'],
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
output = p.stdout
for value in sorted(secrets, key=len, reverse=True):
    output = output.replace(value, '[REDACTED]')
print(output, end='')
raise SystemExit(p.returncode)
PY
