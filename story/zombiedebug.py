#!/usr/bin/env python3
"""Owner-requested loaded-zombie snapshots, bounded recordings and private analysis.

Records are observations, not AI intentions. No gameplay writes or forced chunks.
"""
from __future__ import annotations
import argparse
from collections import Counter
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
import scanctl

REQUEST='SiegerAdminZombieDebugRequest.txt'
STATUS='SiegerAdminZombieDebugStatus.txt'
STOP='SiegerAdminZombieDebugStop.txt'
ID=re.compile(r'[0-9a-f]{32}\Z')
TRACK=re.compile(r'[0-9a-f]{32}:[1-9][0-9]{0,8}\Z')
TERMINAL={'complete','stopped','limited','error','interrupted'}
MAX_BYTES=256*1024*1024+65536
MAX_LINE=65536
MAX_ROWS=1000001
MAX_TRACKED=200000
KINDS={'start','sample','zombie','entity_error','lost','sample_end','coverage_limit','end'}

def fail(message):raise ValueError(message)

def folder(world):
    if world!='story_test':fail('Only story_test is authorized')
    return scanctl.lua_dir(world)

def private_read(path,limit=2048):
    if path.is_symlink():fail('Symlinked diagnostic file refused')
    if not path.exists():return None
    if not path.is_file()or path.stat().st_size>limit:fail('Unsafe diagnostic file')
    data=path.read_text('ascii')
    if not data.endswith('\n'):return None
    if len(data.splitlines())!=1:fail('Malformed diagnostic control file')
    return data.rstrip('\n').split('\t')

def request(world):
    values=private_read(folder(world)/REQUEST)
    if values is None:return None
    if len(values)!=12 or values[0]!='v1'or not ID.fullmatch(values[1])or values[2]!=world or values[3]not in('snapshot','record')or values[-1]!='end':fail('Malformed diagnostic request')
    for value in values[4:10]:
        if not re.fullmatch('[0-9]{1,13}',value):fail('Malformed numeric request field')
    seconds,interval,byte_limit,rows,zombies,expiry=map(int,values[4:10])
    if not 100<=interval<=60000 or not 65536<=byte_limit<=268435456 or not 100<=rows<=1000000 or not 1<=zombies<=100000 or not 1<=expiry<=9999999999999:fail('Request limit out of bounds')
    if(values[3]=='snapshot'and seconds!=0)or(values[3]=='record'and not 1<=seconds<=1800):fail('Invalid recording duration')
    if values[10]!='-'and not scanctl.USERNAME.fullmatch(values[10]):fail('Invalid anchor player')
    return dict(id=values[1],mode=values[3],seconds=seconds,interval_ms=interval,max_bytes=byte_limit,max_records=rows,max_zombies=zombies,expires_ms=expiry,player=values[10])

def status(world):
    current=request(world)
    if not current:return {'status':'none'}
    values=private_read(folder(world)/STATUS)
    if values is None or(len(values)>1 and values[1]!=current['id']):
        expired=int(time.time()*1000)>current['expires_ms']
        return {'status':'pending','request':current,'request_expired':expired}
    if len(values)!=10 or values[0]!='v1'or values[1]!=current['id']or values[2]!=world or values[3]not in(TERMINAL|{'running'})or not re.fullmatch('[a-z_]{2,60}',values[4]):fail('Malformed diagnostic status')
    if values[8]!='SiegerAdminZombieDebug-'+current['id']+'.txt':fail('Unexpected diagnostic log name')
    if any(not re.fullmatch('[0-9]{1,13}',v)for v in(*values[5:8],values[9])):fail('Invalid diagnostic counters')
    updated=int(values[9]);stale=values[3]=='running'and int(time.time()*1000)-updated>max(30000,current['interval_ms']*2+10000)
    return {'status':values[3],'reason':values[4],'request':current,'samples':int(values[5]),'rows':int(values[6]),'bytes':int(values[7]),'updated_ms':updated,'stale_heartbeat':stale,'warning':'A running recorder with stale heartbeat may be blocked or interrupted; never assume full coverage'if stale else None}

def queue(args):
    base=folder(args.world)
    seconds=0 if args.command=='snapshot'else args.seconds
    if args.command=='record'and not 1<=seconds<=1800:fail('Record 1..1800 real seconds')
    if not 100<=args.interval_ms<=60000:fail('Interval 100..60000 ms')
    if not 1<=args.max_mib<=256 or not 100<=args.max_records<=1000000 or not 1<=args.max_zombies<=100000:fail('Invalid explicit recording limits')
    if args.player and not scanctl.USERNAME.fullmatch(args.player):fail('Use exact simple player login')
    spec={'world':args.world,'mode':args.command,'seconds':seconds,'interval_ms':args.interval_ms,'max_mib':args.max_mib,'max_records':args.max_records,'max_zombies':args.max_zombies,'player':args.player,'scope':'ALL currently loaded server zombies per sample; no forced loading'}
    print(json.dumps(spec,indent=2))
    if not args.yes:
        print('PREVIEW ONLY. Add --yes; dense sampling can stall a game tick.');return
    scanctl.assert_module_ready(args.world,'SiegerAdminZombieDebug')
    old=status(args.world)
    if old['status']in('pending','running'):fail('A previous recorder is active/pending; inspect status or stop it first')
    if old['status']in('error','interrupted','limited')and not args.acknowledge_failed:fail('Previous capture incomplete; inspect report and use --acknowledge-failed for a NEW capture')
    rid=secrets.token_hex(16);expires=int(time.time()*1000)+30000
    packet='\t'.join(['v1',rid,args.world,args.command,str(seconds),str(args.interval_ms),str(args.max_mib*1024*1024),str(args.max_records),str(args.max_zombies),str(expires),args.player or'-','end'])+'\n'
    scanctl.atomic_request(base/REQUEST,packet)
    print('QUEUED',rid,'; poll: pz story zombies status',args.world)

def stop(args):
    current=status(args.world)
    if current['status']not in('running','pending'):fail('No active/pending recording')
    if not args.yes:
        print('PREVIEW stop capture',current['request']['id']);return
    scanctl.assert_module_ready(args.world,'SiegerAdminZombieDebug')
    scanctl.atomic_request(folder(args.world)/STOP,current['request']['id']+'\n')
    print('STOP REQUESTED; poll status, this does not stop the game')

def finite(value):return type(value)in(int,float)and math.isfinite(value)

def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:fail('Duplicate JSON key in trace')
        result[key]=value
    return result

def logpath(world,rid=None):
    base=folder(world)
    if rid is None:
        current=request(world)
        if not current:fail('No debug capture request')
        rid=current['id']
    if not ID.fullmatch(rid):fail('Invalid recording ID')
    path=base/('SiegerAdminZombieDebug-'+rid+'.txt')
    if path.is_symlink()or not path.is_file()or path.stat().st_size>MAX_BYTES:fail('Unsafe/missing/oversized recording')
    return path,rid

def records(path,rid):
    """Bounded immutable-prefix read; footer is mandatory for completed capture."""
    with path.open('rb')as stream:
        remaining=os.fstat(stream.fileno()).st_size
        if remaining>MAX_BYTES:fail('Recording exceeds hard read limit')
        count=0
        while remaining:
            line=stream.readline(min(MAX_LINE+1,remaining));remaining-=len(line)
            if len(line)>MAX_LINE:fail('Oversized recording row')
            if not line.endswith(b'\n'):break # writer may still be appending: explicitly incomplete
            count+=1
            if count>MAX_ROWS:fail('Too many recording rows')
            obj=json.loads(line,object_pairs_hook=unique,parse_constant=lambda _:fail('Nonfinite JSON value'))
            if not isinstance(obj,dict)or obj.get('kind')not in KINDS or obj.get('id')!=rid:fail('Invalid recording row or ID')
            yield obj,len(line)

def verified(path,rid,allow_partial=False):
    """Validate envelope and every sample; never relabel missing coverage as complete."""
    header=None;footer=None;current=None;seq=0;counts=Counter();seen=set();slots=set();rows=0;source_bytes=0;closed=0;errors_total=0
    for obj,line_bytes in records(path,rid):
        rows+=1;kind=obj['kind']
        if footer:fail('Rows after terminal footer')
        if header is None:
            if kind!='start'or obj.get('schema')!=1 or obj.get('world')!='story_test'or obj.get('version')!='zdebug-v1':fail('Missing/unsupported capture header')
            header=obj
        elif kind=='start':fail('Duplicate capture header')
        elif kind=='sample':
            if current is not None:fail('Unclosed sample before next sample')
            seq+=1
            if obj.get('seq')!=seq or type(obj.get('expected_slots'))is not int or not 0<=obj['expected_slots']<=100000:fail('Invalid sample sequence/coverage')
            if not isinstance(obj.get('context'),dict)or not finite(obj['context'].get('timestamp_ms')):fail('Invalid sample timestamp')
            current=obj;counts=Counter();seen=set();slots=set()
        elif kind in('zombie','entity_error','lost'):
            if current is None or obj.get('sample')!=seq:fail('Entity row outside matching sample')
            if kind=='zombie':
                track=obj.get('tracking_id');slot=obj.get('slot')
                if not isinstance(track,str)or not TRACK.fullmatch(track)or not track.startswith(rid+':')or track in seen:fail('Invalid/duplicate tracking identity')
                if type(slot)is not int or not 0<=slot<current['expected_slots']or slot in slots:fail('Invalid/duplicate list slot')
                if not all(finite(obj.get(k))for k in('x','y','z'))or not isinstance(obj.get('type'),str):fail('Invalid zombie row')
                for field in ('alive','moving','inside','crawling','on_floor','useless'):
                    if obj.get(field)is not None and type(obj[field])is not bool:fail('Invalid observed boolean')
                if obj.get('health')is not None and not finite(obj['health']):fail('Invalid observed health')
                for field in ('path','target','building','room','hide_rule'):
                    if obj.get(field)is not None and not isinstance(obj[field],dict):fail('Invalid nested observed field')
                seen.add(track);slots.add(slot)
            elif kind=='entity_error':
                slot=obj.get('slot')
                if type(slot)is not int or not 0<=slot<current['expected_slots']or slot in slots:fail('Invalid error slot')
                slots.add(slot)
            elif not isinstance(obj.get('tracking_id'),str)or not TRACK.fullmatch(obj['tracking_id']):fail('Invalid lost identity')
            counts[kind]+=1
        elif kind=='sample_end':
            if current is None or obj.get('seq')!=seq:fail('Unexpected sample end')
            fields=('inspected','null_slots','errors')
            if any(type(obj.get(k))is not int or obj[k]<0 for k in fields):fail('Invalid coverage counters')
            if obj['inspected']!=counts['zombie']or obj['errors']!=counts['entity_error']or sum(obj[k]for k in fields)!=current['expected_slots']:fail('Coverage/count mismatch')
            complete=obj['errors']==0
            if obj.get('coverage_complete')is not complete:fail('False coverage claim')
            if not finite(obj.get('elapsed_ms'))or obj['elapsed_ms']<0:fail('Invalid sample duration')
            closed+=1;errors_total+=obj['errors'];current=None
        elif kind=='coverage_limit':
            if current is not None:fail('Limit inside sample')
        elif kind=='end':
            if obj.get('status')not in TERMINAL or obj.get('rows_before_end')!=rows-1:fail('Invalid terminal capture state/count')
            if obj.get('samples')!=seq:fail('Terminal sample count mismatch')
            if obj.get('bytes_before_end')!=source_bytes:fail('Terminal byte count mismatch')
            if obj['status']=='complete'and(current is not None or seq<1 or closed!=seq or obj.get('entity_errors')!=0 or errors_total!=0):fail('Incomplete capture falsely marked complete')
            footer=obj
        source_bytes+=line_bytes
        yield obj
    if header is None:fail('Recording is empty')
    if not allow_partial and(not footer or footer['status']!='complete'):fail('Capture is incomplete/stopped/limited; use --allow-partial to inspect explicitly')

def analyze(path,rid,allow_partial=False,events_limit=5000):
    zombies={};events=[];event_count=0;sample=None;footer=None;header=None
    samples=0;complete_samples=0;entity_errors=0;max_capture_ms=0;collisions=0
    online_seen={};types=Counter();rules=Counter();phases={};max_late=0
    def event(kind,track,**data):
        nonlocal event_count
        event_count+=1
        if len(events)<events_limit:events.append(dict(kind=kind,tracking_id=track,**data))
    for obj in verified(path,rid,allow_partial):
        kind=obj['kind']
        if kind=='start':header=obj
        elif kind=='sample':
            sample=obj;samples+=1;online_seen={};max_late=max(max_late,obj.get('late_by_ms',0))
        elif kind=='sample_end':
            complete_samples+=bool(obj['coverage_complete']);entity_errors+=obj['errors'];max_capture_ms=max(max_capture_ms,obj.get('elapsed_ms',0))
        elif kind=='end':footer=obj
        elif kind=='entity_error':
            track=obj.get('tracking_id')
            if track in zombies:zombies[track]['last']=None;zombies[track]['stationary_path_ms']=0
        elif kind=='lost':
            track=obj['tracking_id']
            if track in zombies:
                zombies[track]['observation_losses']+=1;zombies[track]['last']=None;zombies[track]['stationary_path_ms']=0
            event('observation_lost',track,sample=obj['sample'],reason='not_a_death_claim')
        elif kind=='zombie':
            track=obj['tracking_id'];now=sample['context']['timestamp_ms'];seq=sample['seq']
            if track not in zombies:
                if len(zombies)>=MAX_TRACKED:fail('Analysis identity limit reached; raw trace retained')
                zombies[track]={'tracking_id':track,'type':obj['type'],'samples':0,'inside_samples':0,'outside_samples':0,'unknown_inside_samples':0,'target_samples':0,'moving_samples':0,'observation_losses':0,'distance_observed_tiles':0.0,'max_speed_tiles_per_real_second':0.0,'first_seen_ms':now,'last_seen_ms':now,'state_counts':Counter(),'stationary_path_ms':0,'max_stationary_path_ms':0,'last':None}
            z=zombies[track];old=z['last'];z['samples']+=1;z['last_seen_ms']=now;types[obj['type']]+=1
            inside=obj.get('inside')
            z['inside_samples'if inside is True else'outside_samples'if inside is False else'unknown_inside_samples']+=1
            z['target_samples']+=isinstance(obj.get('target'),dict);z['moving_samples']+=obj.get('moving')is True
            state=obj.get('state')or'unknown';z['state_counts'][state]+=1
            hide=obj.get('hide_rule')or{};rules[str(hide.get('eligibility','unknown'))]+=1
            phase=str(hide.get('branch','unknown'))
            group=phases.setdefault(obj['type'],{}).setdefault(phase,Counter())
            group['observations']+=1
            group['rule_bound']+=hide.get('bound')is True
            group['rule_not_bound']+=hide.get('bound')is False
            group['rule_binding_unknown']+=hide.get('bound')is None
            group['inside'if inside is True else'outside'if inside is False else'unknown_inside']+=1
            group['moving']+=obj.get('moving')is True
            group['with_target']+=isinstance(obj.get('target'),dict)
            group['outside_idle_candidate']+=hide.get('eligibility')=='outside_idle_candidate'
            online=obj.get('online_id')
            if online is not None and online!=-1:
                if online in online_seen and online_seen[online]!=track:collisions+=1
                online_seen[online]=track
            if old is not None and old['seq']==seq-1:
                prev=old['row'];elapsed=(now-old['time'])/1000
                if elapsed>0:
                    distance=math.hypot(obj['x']-prev['x'],obj['y']-prev['y'])
                    z['distance_observed_tiles']+=distance
                    z['max_speed_tiles_per_real_second']=max(z['max_speed_tiles_per_real_second'],distance/elapsed)
                    age=sample['context'].get('game',{}).get('world_age_hours')
                    old_age=old.get('age')
                    path=obj.get('path')or{}
                    path_candidate=path.get('cancelled')is False and(path.get('using')is True or 'path'in str(obj.get('state','')).lower())
                    simulated=finite(age)and finite(old_age)and age>old_age
                    previous_stall=z['stationary_path_ms']
                    z['stationary_path_ms']=previous_stall+elapsed*1000 if simulated and path_candidate and distance<0.1 else 0
                    z['max_stationary_path_ms']=max(z['max_stationary_path_ms'],z['stationary_path_ms'])
                    if previous_stall<10000<=z['stationary_path_ms']:event('stationary_path_candidate',track,sample=seq,warning='not_proof_of_blocked_path_or_AI_cause')
                if obj.get('state')!=prev.get('state'):event('state_changed',track,sample=seq,before=prev.get('state'),after=obj.get('state'))
                if inside is True and prev.get('inside')is False:event('entered_building',track,sample=seq,previous_hide_rule=prev.get('hide_rule'),previous_target_present=isinstance(prev.get('target'),dict))
                if inside is False and prev.get('inside')is True:event('left_building',track,sample=seq)
                def key(v):return v.get('key')if isinstance(v,dict)else None
                if key(obj.get('building'))!=key(prev.get('building')):event('building_changed',track,sample=seq,before=key(prev.get('building')),after=key(obj.get('building')))
                def target(v):return (v.get('kind'),v.get('online_id'),v.get('tracking_id'))if isinstance(v,dict)else None
                if target(obj.get('target'))!=target(prev.get('target')):event('target_changed',track,sample=seq)
                def pathkey(v):return tuple(v.get(k)for k in('x','y','z','using','cancelled'))if isinstance(v,dict)else None
                if pathkey(obj.get('path'))!=pathkey(prev.get('path')):event('path_changed',track,sample=seq)
                if prev.get('alive')is True and obj.get('alive')is False:event('observed_dead',track,sample=seq)
            z['last']={'seq':seq,'time':now,'row':obj,'age':sample['context'].get('game',{}).get('world_age_hours')}
    summary=[]
    for z in zombies.values():
        z.pop('last');z.pop('stationary_path_ms');z['state_counts']=dict(z['state_counts']);z['distance_observed_tiles']=round(z['distance_observed_tiles'],4);z['max_speed_tiles_per_real_second']=round(z['max_speed_tiles_per_real_second'],4);summary.append(z)
    return {'schema':1,'recording_id':rid,'header':header,'terminal':footer,'capture_complete':bool(footer and footer['status']=='complete'),'samples':samples,'complete_samples':complete_samples,'entity_errors':entity_errors,'max_sample_elapsed_ms':max_capture_ms,'max_late_by_ms':max_late,'unique_observed_objects':len(zombies),'same_sample_online_id_collisions':collisions,'zombie_observations_by_type':dict(types),'hide_rule_observations':dict(rules),'observations_by_type_and_phase':phases,'zombies':summary,'derived_events':events,'derived_event_count':event_count,'events_truncated':event_count>len(events),'warning':'Server observations and inferred reference rules do not prove AI intent. Object IDs last only this recording/object lifetime. Disappearance is not death. Inside counts are sample fractions, not exact dwell durations. No speed is bridged across lost/error samples.'}

@contextlib.contextmanager
def output_file(path):
    path=Path(path)
    if path.resolve().is_relative_to(scanctl.REPO)or path.is_symlink()or not path.parent.is_dir():fail('Private exports must be new files outside source repository')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8')as stream:yield stream
    except BaseException:
        path.unlink(missing_ok=True);raise

def report(args):
    path,rid=logpath(args.world,args.id)
    if args.command=='analyze':
        data=analyze(path,rid,args.allow_partial,args.events_limit)
        if args.output:
            with output_file(args.output)as stream:json.dump(data,stream,ensure_ascii=False,indent=2)
            print('Private analysis:',args.output)
        else:print(json.dumps(data,indent=2))
        return
    # Validate first: never create a destination for a malformed/unfinished capture.
    count=0;terminal=None;digest=hashlib.sha256();before=path.stat()
    for row in verified(path,rid,args.allow_partial):
        count+=1
        if row['kind']=='end':terminal=row['status']
    if args.output:
        with output_file(args.output)as stream:
            stream.write('{"schema":1,"recording_id":'+json.dumps(rid)+',"capture_complete":'+json.dumps(terminal=='complete')+',"terminal_status":'+json.dumps(terminal)+',"records":[')
            first=True
            for row in verified(path,rid,args.allow_partial):
                if not first:stream.write(',')
                json.dump(row,stream,separators=(',',':'));first=False
            stream.write(']}\n')
            after=path.stat()
            if(before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):fail('Recording changed during export; wait for stop/completion')
        print('Private full JSON:',args.output,'rows:',count)
    else:
        with path.open('rb')as source:
            while block:=source.read(1024*1024):digest.update(block)
        print(json.dumps({'recording_id':rid,'capture_complete':terminal=='complete','terminal_status':terminal,'rows':count,'bytes':before.st_size,'sha256':digest.hexdigest(),'source':'private JSONL .txt, no inventory','note':'Use --output NEW.json for all observations or analyze for transitions'},indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    for mode in('snapshot','record'):
        p=subs.add_parser(mode);p.add_argument('world')
        p.add_argument('--player');p.add_argument('--interval-ms',type=int,default=1000)
        p.add_argument('--max-mib',type=int,default=64);p.add_argument('--max-records',type=int,default=250000);p.add_argument('--max-zombies',type=int,default=10000)
        if mode=='record':p.add_argument('--seconds',required=True,type=int)
        p.add_argument('--yes',action='store_true');p.add_argument('--acknowledge-failed',action='store_true');p.set_defaults(handler=queue)
    p=subs.add_parser('status');p.add_argument('world');p.set_defaults(handler=lambda a:print(json.dumps(status(a.world),indent=2)))
    p=subs.add_parser('stop');p.add_argument('world');p.add_argument('--yes',action='store_true');p.set_defaults(handler=stop)
    for mode in('report','analyze'):
        p=subs.add_parser(mode);p.add_argument('world');p.add_argument('--id');p.add_argument('--output');p.add_argument('--allow-partial',action='store_true')
        p.add_argument('--events-limit',type=int,default=5000);p.set_defaults(handler=report)
    args=parser.parse_args()
    try:
        if hasattr(args,'events_limit')and not 0<=args.events_limit<=100000:fail('Events limit 0..100000')
        args.handler(args)
    except(ValueError,OSError,UnicodeError,json.JSONDecodeError)as error:parser.exit(2,'Zombie debug: '+str(error)+'\n')
if __name__=='__main__':main()
