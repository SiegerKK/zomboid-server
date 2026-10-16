#!/usr/bin/env bash
set -euo pipefail
# Upstream's init script prints argv, including ADMIN_PASSWORD. Remove that
# exact log statement before starting. Fail closed if upstream changes it.
python3 - <<'PY'
from pathlib import Path
import os
import sqlite3
import re
# A restored configuration can contain an OLD RCON secret, different from this
# container's environment. Never let the configurator print old/new values.
config = Path('/scripts/config/server_manager.py')
config_source = config.read_text()
pattern = r'''logger\.info\(\s*"Updated variable '%s' from '%s' to '%s'",\s*key,\s*old_value,\s*new_value,\s*\)'''
replacement = 'logger.info("Updated configuration key: %s", key)'
config_source, count = re.subn(pattern, replacement, config_source)
if count != 1 and replacement not in config_source:
    raise SystemExit('Unexpected config logging; review before startup')
config.write_text(config_source)
p = Path('/scripts/init-server.sh')
source = p.read_text()
line = 'echo "Starting Project Zomboid server with arguments: ${ARGS[*]}"'
marker = '# bootstrap: secret-bearing argument log removed'
if source.count(line) == 1:
    source = source.replace(line, marker)
elif marker not in source:
    raise SystemExit('Unexpected upstream init script; review before startup')
# Once the administrator exists, use the saved account instead of putting its
# password in every subsequent JVM command line (readable through host /proc).
server = os.environ.get('SERVER_NAME', 'servertest').replace(' ', '-')
db = Path(os.environ.get('CACHE_DIR', '/root/Zomboid')) / 'db' / (server + '.db')
if db.is_file():
    with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True) as connection:
        initialized = connection.execute(
            'SELECT 1 FROM whitelist WHERE username=? AND length(password)>0 LIMIT 1',
            (os.environ.get('ADMIN_USERNAME', 'admin'),)).fetchone()
    password_arg = '[[ -n "${ADMIN_PASSWORD}" ]] && ARGS+=("-adminpassword" "${ADMIN_PASSWORD}")'
    password_marker = '# bootstrap: administrator already initialized; omit password argv'
    if initialized:
        if source.count(password_arg) == 1:
            source = source.replace(password_arg, password_marker)
        elif password_marker not in source:
            raise SystemExit('Unexpected admin argument; review before startup')
if os.environ.get('PZ_ZOMBIEBUDDY_AGENT') == '1':
    agent_marker = '# bootstrap: pinned ZombieBuddy agent for actual game JVM only'
    anchor = 'ARGS+=("--")'
    if agent_marker not in source:
        if source.count(anchor) != 1:
            raise SystemExit('Unexpected JVM argument boundary; review before startup')
        source = source.replace(anchor, agent_marker + '\n' +
            'ARGS+=("-javaagent:/bootstrap/ZombieBuddy.jar=policy=deny-new,frontend=console,verbosity=1")\n' + anchor)
p.write_text(source)
PY
exec python3 /bootstrap/run-redacted.py "$@"
