#!/usr/bin/env python3
"""Filter launcher/configurator output before Docker's log driver receives it."""
import os
import signal
import subprocess
import sys

secrets = sorted({os.environ.get(k, '') for k in
                  ('ADMIN_PASSWORD', 'RCON_PASSWORD', 'PASSWORD')} - {''}, key=len, reverse=True)
process = subprocess.Popen(['/bin/bash', '/scripts/entrypoint.sh', *sys.argv[1:]],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors='replace', bufsize=1, start_new_session=True)

def forward(signum, _frame):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass

signal.signal(signal.SIGTERM, forward)
signal.signal(signal.SIGINT, forward)
for line in process.stdout:
    for value in secrets:
        line = line.replace(value, '[REDACTED]')
    print(line, end='', flush=True)
raise SystemExit(process.wait())
