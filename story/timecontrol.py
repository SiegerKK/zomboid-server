#!/usr/bin/env python3
"""Bounded online clock jumps through independent SiegerAdmin; no simulation fast-forward."""
import argparse
import datetime
import json
import re
import secrets
import time
import scanctl
REQ='SiegerAdminClockRequest.txt'
RESP='SiegerAdminClockResult.txt'
ID=re.compile(r'[0-9a-f]{32}\Z')
def paths(world):
    if world!='story_test':raise ValueError('Only story_test is authorized')
    folder=scanctl.lua_dir(world)
    return folder/REQ,folder/RESP

def read(path):
    if not path.exists():return None
    if path.is_symlink() or path.stat().st_size>1024:raise ValueError('Unsafe clock protocol file')
    raw=path.read_text('ascii')
    if not raw.endswith('\n'):return None
    return raw.rstrip('\n').split('\t')

def result(world,rid):
    fields=read(paths(world)[1])
    if fields is None:return {'status':'pending'}
    if len(fields)!=12 or fields[0]!='v1' or not ID.fullmatch(fields[1])or fields[2]!=world or fields[3]not in('show','set','advance')or fields[4]not in('complete','error')or fields[5]not in('game_clock_verified','review_server_logs'):
        raise ValueError('Malformed clock response')
    if fields[1]!=rid:return {'status':'pending'}
    data={'request_id':rid,'operation':fields[3],'status':fields[4],'reason':fields[5]}
    for prefix,day,hour,nights in [('before',fields[6],fields[7],fields[10]),('after',fields[8],fields[9],fields[11])]:
        if day=='-':continue
        datetime.date.fromisoformat(day)
        if not re.fullmatch(r'[0-9]{1,2}\.[0-9]{6}',hour)or not 0<=float(hour)<24 or not re.fullmatch(r'[0-9]{1,7}',nights):raise ValueError('Invalid clock snapshot')
        data[prefix]={'date':day,'time_hours':float(hour),'nights_survived':int(nights)}
    if fields[4]=='complete'and not all(k in data for k in('before','after')):raise ValueError('Incomplete clock verification')
    return data

def run(args):
    req,_=paths(args.world)
    old=read(req)
    if args.operation=='status':
        if not old or len(old)!=8 or not ID.fullmatch(old[1]):raise ValueError('No valid clock request')
        print(json.dumps(result(args.world,old[1]),indent=2));return
    minutes=0
    if args.operation=='set':
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',args.value):raise ValueError('Use HH:MM')
        h,m=map(int,args.value.split(':'));minutes=h*60+m
    elif args.operation=='advance':
        # Integer minutes avoid binary float ambiguity in operator requests.
        if not re.fullmatch(r'[0-9]{1,4}',args.value)or not 1<=int(args.value)<=1440:raise ValueError('Advance 1..1440 minutes only')
        minutes=int(args.value)
    if args.operation!='show'and not args.yes:
        print('PREVIEW',args.operation,args.world,minutes,'minutes; no simulation. Add --yes.');return
    scanctl.assert_module_ready(args.world,'SiegerAdminClock')
    if old:
        if len(old)!=8 or old[0]!='v1'or not ID.fullmatch(old[1])or old[2]!=args.world:raise ValueError('Malformed old clock request')
        prior=result(args.world,old[1])
        if prior['status']=='pending':raise ValueError('Prior clock request pending; inspect status')
        if prior['status']=='error'and not args.acknowledge_failed:raise ValueError('Prior clock operation failed; inspect logs and acknowledge explicitly')
    rid=secrets.token_hex(16)
    expires=int(time.time()*1000)+30000
    scanctl.atomic_request(req,'\t'.join(['v1',rid,args.world,args.operation,str(minutes),str(expires),'1'if args.allow_players else'0','end'])+'\n')
    print('QUEUED',rid,'; poll: pz story time status',args.world)

def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    for name in('show','set','advance','status'):
        cmd=sub.add_parser(name);cmd.add_argument('world')
        if name in('set','advance'):cmd.add_argument('value')
        cmd.add_argument('--yes',action='store_true');cmd.add_argument('--allow-players',action='store_true');cmd.add_argument('--acknowledge-failed',action='store_true')
    args=parser.parse_args()
    try:run(args)
    except(ValueError,OSError,UnicodeError)as error:parser.exit(2,'Story time: '+str(error)+'\n')
if __name__=='__main__':main()
