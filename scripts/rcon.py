#!/usr/bin/env python3
"""Use RCON only inside a selected container; never put its secret in argv."""
import re
import subprocess
import sys

name = sys.argv[1] if len(sys.argv) > 1 else 'zomboid-server'
command = sys.argv[2] if len(sys.argv) > 2 else 'players'
if command not in ('players', 'help', 'save', 'quit', 'stats help', 'stats') and not re.fullmatch(r'stats [A-Za-z0-9_.:-]+(?: [A-Za-z0-9_.:-]+)?', command):
    raise SystemExit('Allowed commands: players, help, save, quit, stats help, stats')
code = r'''
import os,socket,struct,sys
command=sys.argv[1]
s=socket.create_connection(('127.0.0.1',27015),timeout=10)
def send(i,t,text):
    b=struct.pack('<ii',i,t)+text.encode()+b'\0\0'
    s.sendall(struct.pack('<i',len(b))+b)
def readn(n):
    b=b''
    while len(b)<n:
        part=s.recv(n-len(b))
        if not part: raise EOFError()
        b+=part
    return b
def recv():
    n=struct.unpack('<i',readn(4))[0]
    if not 10<=n<=1048576: raise RuntimeError('Invalid RCON frame')
    b=readn(n)
    return (*struct.unpack('<ii',b[:8]),b[8:-2].decode(errors='replace'))
send(100,3,os.environ['RCON_PASSWORD'])
for _ in range(8):
    i,t,b=recv()
    if i==-1: raise RuntimeError('RCON authentication failed')
    if i==100 and t==2: break
else: raise RuntimeError('Missing RCON authentication response')
send(200,2,command)
responses=[]
for _ in range(64):
    try: i,t,b=recv()
    except socket.timeout:
        if responses: break
        raise
    except EOFError:
        if responses or command=='quit': break
        raise
    if i==200 and b:
        responses.append(b)
        s.settimeout(0.5)
if not responses and command!='quit': raise RuntimeError('Empty RCON response')
print(''.join(responses))
'''
result = subprocess.run(['docker', 'exec', name, 'python3', '-c', code, command],
                        stdin=subprocess.DEVNULL, capture_output=True, text=True)
if result.returncode:
    raise SystemExit('RCON command failed; no secret output displayed')
if command == 'players':
    count = re.search(r'Players connected\s*\((\d+)\)', result.stdout)
    if not count:
        raise SystemExit('Unrecognized player count; do not stop the game')
    print('Players connected (' + count.group(1) + '):')
else:
    print(result.stdout.strip())
