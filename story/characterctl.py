#!/usr/bin/env python3
"""Root-issued fixed character profiles; client execution requires explicit acknowledgement."""
import argparse,json,re,secrets
import scanctl
PROFILES={"joel-arrival-v1"}
REQ="SiegerCharacterRequest.txt"
RES="SiegerCharacterResult.txt"
def read(world,name):
 p=scanctl.lua_dir(world)/name
 if not p.exists():return None
 if p.is_symlink() or p.stat().st_size>512:raise ValueError("Unsafe character protocol file")
 return p.read_text("ascii").strip().split("\t")
def status(world):
 req=read(world,REQ)
 if not req:return {"status":"none"}
 if len(req)!=5 or req[0]!="v1" or not re.fullmatch("[0-9a-f]{32}",req[1]) or req[2]!=world or req[4] not in PROFILES:raise ValueError("Malformed request")
 res=read(world,RES)
 if not res or res[:5]!=req:return {"status":"pending","request_id":req[1]}
 if len(res)!=7 or res[5] not in ("waiting","complete","error"):raise ValueError("Malformed receipt")
 return {"status":res[5],"request_id":res[1],"player":res[3],"profile":res[4],"reason":res[6],"scope":"client acknowledgement; verify in-game and server snapshot"}
def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
 a=sub.add_parser("apply");a.add_argument("world");a.add_argument("player");a.add_argument("--profile",choices=sorted(PROFILES),required=True);a.add_argument("--yes",action="store_true")
 a=sub.add_parser("status");a.add_argument("world")
 args=p.parse_args()
 try:
  if args.world!="story_test":raise ValueError("Character profiles currently approved only for story_test")
  if args.command=="status":print(json.dumps(status(args.world),indent=2));return
  if not scanctl.USERNAME.fullmatch(args.player):raise ValueError("Invalid exact login")
  print("PROFILE",args.profile,"PLAYER",args.player,"replaces non-kept inventory, sets skills/stats and two bandaged non-zombie scratches")
  if not args.yes:print("PREVIEW ONLY");return
  scanctl.assert_module_ready(args.world,"SiegerStoryCharacter")
  if status(args.world)["status"]!="none":raise ValueError("Existing profile request must be audited and privately archived; no automatic reapplication")
  packet="\t".join(["v1",secrets.token_hex(16),args.world,args.player,args.profile])+"\n"
  scanctl.atomic_request(scanctl.lua_dir(args.world)/REQ,packet)
  print("QUEUED; not yet applied. Poll: sudo pz story character status",args.world)
 except (ValueError,OSError,UnicodeError) as e:p.exit(2,str(e)+"\n")
if __name__=="__main__":main()
