"""Verify reconnect data before allowing material mutations. Disconnect alone is not survival proof."""
from collections import Counter
from pathlib import Path
import json,time
FOOD={'minecraft:golden_carrot','minecraft:cooked_beef','minecraft:cooked_porkchop','minecraft:cooked_chicken','minecraft:cooked_mutton','minecraft:apple','minecraft:bread','minecraft:baked_potato','minecraft:rotten_flesh'}
def counts(s):
 c=Counter()
 for v in s.get('inventory',[]):
  if v.get('count',0)>0:c[v['item']]+=v['count']
 menu=s.get('menu',{})
 # A normal disconnect returns the cursor and personal crafting inputs to inventory.
 cursor=menu.get('cursor',{})
 if cursor.get('count',0)>0:c[cursor['item']]+=cursor['count']
 count=9 if menu.get('type')=='CraftingMenu' else 4 if menu.get('type')=='InventoryMenu' else 0
 for v in menu.get('slots',[])[1:count+1]:
  if v.get('count',0)>0:c[v['item']]+=v['count']
 return c
def lost_since(before,after):
 if before.get('player_uuid') and before['player_uuid']!=after.get('player_uuid'):return {'player_identity_changed':1}
 old,new=counts(before),counts(after)
 return {i:n-new[i] for i,n in old.items() if i not in FOOD and new[i]<n}
def await_ready(root,checkpoint=None,timeout=45):
 from safety_interlock import require_unlocked
 root=Path(root);require_unlocked(root);until=time.monotonic()+timeout;stable=None;since=time.monotonic();latest={}
 while time.monotonic()<until:
  try:s=json.loads((root/'status.json').read_text())
  except (OSError,ValueError):time.sleep(.25);continue
  require_unlocked(root,s if time.time()*1000-s.get('time',0)<3000 else None)
  latest=s
  ready=s.get('connected') and s.get('server','').lower().removesuffix(':25565')=='simpcraft.com' and s.get('dimension')=='minecraft:overworld' and not s.get('screen') and time.time()*1000-s.get('time',0)<3000
  if ready and counts(s):
   key=(s['world_session'],s.get('player_uuid'),tuple(round(v,1) for v in s['pos']))
   if key!=stable:stable=key;since=time.monotonic()
   elif time.monotonic()-since>=2:
    missing=lost_since(checkpoint,s) if checkpoint else {}
    if missing:raise RuntimeError('Inventory continuity failed: '+json.dumps(missing))
    return s
  else:stable=None
  time.sleep(.25)
 raise RuntimeError('Game data not ready: '+json.dumps({'connected':latest.get('connected'),'pos':latest.get('pos'),'items':sum(counts(latest).values()),'server_last_death':latest.get('server_last_death')}))
