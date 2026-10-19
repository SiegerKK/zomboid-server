#!/usr/bin/env python3
"""Root-issued read-only character audit and server-owned equipment reconciliation."""
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
 if len(req) not in (5,6,7) or (len(req)>=6 and req[5]not in ("audit","repair")) or (len(req)==7 and (req[5]!="repair" or not re.fullmatch(r"-|[A-Za-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+",req[6]))) or req[0]!="v1" or not re.fullmatch("[0-9a-f]{32}",req[1]) or req[2]!=world or req[4] not in PROFILES:raise ValueError("Malformed request")
 res=read(world,RES)
 if not res or res[:5]!=req[:5]:return {"status":"pending","request_id":req[1]}
 if len(res)!=7 or res[5] not in ("waiting","complete","error"):raise ValueError("Malformed receipt")
 result={"status":res[5],"request_id":res[1],"player":res[3],"profile":res[4],"reason":res[6],"scope":"selected equipment identity verified; native equip and relog still require acceptance" if res[6]=="server_inventory_verified"else"diagnostic or legacy receipt; inventory usability is not established"}
 audit=scanctl.lua_dir(world)/"SiegerCharacterAudit.txt"
 if audit.is_file() and not audit.is_symlink() and audit.stat().st_size<4096:
  lines=audit.read_text("ascii").splitlines()
  if lines and lines[0]==req[1]:result["client_report"]={k:v for k,v in (line.split("\t") for line in lines[1:])}
 return result
def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
 for command in ("apply","audit","repair"):
  a=sub.add_parser(command);a.add_argument("world");a.add_argument("player");a.add_argument("--profile",choices=sorted(PROFILES),required=True);a.add_argument("--yes",action="store_true")
  if command=="repair":a.add_argument("--item",default="-",help="One exact profile item type for first acceptance; omit for full equipment")
 a=sub.add_parser("status");a.add_argument("world")
 args=p.parse_args()
 try:
  if args.world!="story_test":raise ValueError("Character profiles currently approved only for story_test")
  if args.command=="status":print(json.dumps(status(args.world),indent=2));return
  if args.command=="apply":raise ValueError("Legacy client-only profile apply is disabled after failed game acceptance; use audit then repair")
  if not scanctl.USERNAME.fullmatch(args.player):raise ValueError("Invalid exact login")
  if args.command=="repair"and not re.fullmatch(r"-|[A-Za-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+",args.item):raise ValueError("Invalid item selector")
  print("PROFILE",args.profile,"PLAYER",args.player,"READ-ONLY" if args.command=="audit" else "reconciles selected profile equipment using server IDs; preserves skills, health and unrelated inventory")
  if not args.yes:print("PREVIEW ONLY");return
  scanctl.assert_module_ready(args.world,"SiegerStoryCharacter")
  if status(args.world)["status"]!="none":raise ValueError("Existing profile request must be audited and privately archived; no automatic reapplication")
  packet="\t".join(["v1",secrets.token_hex(16),args.world,args.player,args.profile])+ ("\taudit" if args.command=="audit" else "\trepair\t"+args.item)+"\n"
  scanctl.atomic_request(scanctl.lua_dir(args.world)/REQ,packet)
  print("QUEUED; not yet applied. Poll: sudo pz story character status",args.world)
 except (ValueError,OSError,UnicodeError) as e:p.exit(2,str(e)+"\n")
if __name__=="__main__":main()
