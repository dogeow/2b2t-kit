"""Restore only an offline Flight speed still equal to an owned durable temporary value.

Patch its original NBT double bytes, preserving every other module setting.
Never starts the client, clears a hold, or guesses a user's changed speed.
"""
from pathlib import Path
import copy,hashlib,json,math,struct,subprocess
from material_jobs.bobby_snow_cache import _NBTReader
from kit_runtime.journal import write_json

class _LocatedDouble(float):pass
class _Offsets(_NBTReader):
 def _payload(self,kind,depth):
  start=self.pos;value=super()._payload(kind,depth)
  if kind==6:
   value=_LocatedDouble(value);value.offset=start
  return value

def game_running():
 r=subprocess.run(['pgrep','-f','net.fabricmc.loader.impl.launch.knot.KnotClient|net.minecraft.client.main.Main'],capture_output=True,text=True)
 if r.returncode not in (0,1):raise RuntimeError('Cannot establish the absence of a game process')
 return r.returncode==0

def recover(game,out,*,running=game_running):
 if running():raise RuntimeError('Offline Flight recovery refuses a running game')
 game=Path(game);out=Path(out);out.mkdir(parents=True,exist_ok=False);path=game/'meteor-client/modules.nbt';raw=path.read_bytes()
 root=_Offsets(raw).root();flight=[v for v in root.get('modules',[])if v.get('name')=='flight']
 if len(flight)!=1:raise RuntimeError('Exact Flight module required')
 groups=[v for v in flight[0].get('settings',{}).get('groups',[])if v.get('name')=='General']
 settings=[v for group in groups for v in group.get('settings',[])if v.get('name')=='speed']
 if len(settings)!=1 or not isinstance(settings[0].get('value'),_LocatedDouble):raise RuntimeError('Exact General speed double required')
 current=float(settings[0]['value']);entries=[]
 for p in (game/'config/twob2tkit').glob('*flight*.bak'):
  if p.is_symlink():raise RuntimeError('Flight backup symlink refused')
  values=p.read_text().split()
  if len(values)!=3:raise RuntimeError('Unknown flight backup; original retained')
  original,previous,requested=map(float,values)
  if any(not math.isfinite(v)or v<0 for v in (original,previous,requested)):raise RuntimeError('Invalid persisted flight backup')
  entries.append({'path':str(p),'original':original,'previous':previous,'requested':requested,'modified_at':p.stat().st_mtime})
 claimed=[v for v in entries if current in (v['previous'],v['requested'])and current!=v['original']
          and path.stat().st_mtime-v['modified_at']<=120]
 originals={v['original']for v in entries if v['original']>0}
 before_hash=hashlib.sha256(raw).hexdigest()
 if not claimed:
  result={'changed':False,'current_speed':current,'reason':'current value is not an owned temporary speed','before_sha256':before_hash};write_json(out/'result.json',result);return result
 if len(originals)!=1:raise RuntimeError('Ambiguous original speed; no user setting changed')
 original=next(iter(originals));offset=settings[0]['value'].offset
 if original==current:
  result={'changed':False,'current_speed':current,'reason':'outer original speed already loaded','before_sha256':before_hash};write_json(out/'result.json',result);return result
 updated=raw[:offset]+struct.pack('>d',original)+raw[offset+8:]
 expected=copy.deepcopy(root);expected_flight=next(v for v in expected['modules']if v.get('name')=='flight')
 expected_speed=next(v for g in expected_flight['settings']['groups']if g.get('name')=='General'for v in g['settings']if v.get('name')=='speed');expected_speed['value']=original
 if _NBTReader(updated).root()!=expected or len(updated)!=len(raw):raise RuntimeError('NBT change exceeded the one owned double')
 if running()or path.read_bytes()!=raw:raise RuntimeError('Client or configuration changed before conditional recovery')
 (out/'modules.nbt.before').write_bytes(raw);temporary=path.with_name('modules.nbt.owned-recovery.tmp');temporary.write_bytes(updated);temporary.replace(path)
 result={'changed':True,'previous_speed':current,'restored_speed':original,'patched_bytes':8,'all_other_settings_identical':True,
         'before_sha256':before_hash,'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'owned_receipts':claimed}
 write_json(out/'result.json',result);return result
