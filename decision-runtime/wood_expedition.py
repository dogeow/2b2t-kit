"""Explicitly started species/count expedition. Native Kit owns flight, combat and chopping.
Usage: wood_expedition.py --wood spruce --count 73 --out /path/to/evidence
"""
import argparse,json,math,time,collections
from pathlib import Path
from material_client import MaterialClient,Handoff,stocks
DEFAULT_ROOT=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation')
HOME=[761020.5,100,797854.5];DEPOT=[761012,66,797833]
def horizontal(a,b):return math.hypot(a[0]-b[0],a[2]-b[2])
def route(home,step=160):
 # A continuous transect reaches new biomes quickly; every segment is bounded and recorded for return.
 for i in range(1,21):yield [home[0],140,home[2]-i*step]
 for i in range(1,13):yield [home[0]+i*step,140,home[2]-20*step]
 for i in range(1,41):yield [home[0]+12*step,140,home[2]-20*step+i*step]
 for i in range(1,25):yield [home[0]+12*step-i*step,140,home[2]+20*step]
 for i in range(1,41):yield [home[0]-12*step,140,home[2]+20*step-i*step]
def landing(blocks,root):
 m={tuple(v['pos']):v for v in blocks};answer=[]
 for dx in range(-10,11):
  for dz in range(-10,11):
   d=math.hypot(dx,dz)
   if not 5<=d<=10:continue
   x,z=root[0]+dx,root[2]+dz
   for y in range(root[1]+3,root[1]-4,-1):
    below=m.get((x,y-1,z),{});name=below.get('state','')
    if not below.get('solid') or not any('minecraft:'+b+'}' in name for b in ('grass_block','dirt','podzol','coarse_dirt','rooted_dirt','stone','gravel','moss_block','snow_block')):continue
    if all(m.get((x,h,z),{}).get('passable',True) for h in range(y,root[1]+40)):
     answer.append(([x+.5,y+.15,z+.5],d));break
 return min(answer,key=lambda v:v[1])[0] if answer else None
def sky_path(blocks,pos):
 m={tuple(v['pos']):v for v in blocks};ox,oy,oz=map(math.floor,pos)
 def clear(x,y,z):return m.get((x,y,z),{}).get('passable',True)
 def safe(p):
  x,y,z=p;return abs(x-ox)<=11 and abs(z-oz)<=11 and oy-3<=y<=oy+6 and clear(x,y,z) and clear(x,y+1,z) and m.get((x,y-1,z),{}).get('solid',False)
 starts=[p for x in range(ox-1,ox+2) for z in range(oz-1,oz+2) for y in range(oy-1,oy+2) if safe(p:=(x,y,z))]
 if not starts:return None
 start=min(starts,key=lambda p:math.dist([p[0]+.5,p[1],p[2]+.5],pos));q=collections.deque([start]);parent={start:None}
 while q:
  p=q.popleft();x,y,z=p
  if all(clear(x,h,z) for h in range(y,oy+40)):
   path=[]
   while p is not None:path.append([p[0]+.5,p[1],p[2]+.5]);p=parent[p]
   return list(reversed(path))
  for dx,dz in [(1,0),(-1,0),(0,1),(0,-1)]:
   for dy in [0,1,-1]:
    n=(x+dx,y+dy,z+dz)
    if n not in parent and safe(n) and (dy<=0 or clear(x,y+2,z)):parent[n]=p;q.append(n)
 return None

class Expedition:
 def __init__(self,args):
  self.a=args;self.item='minecraft:'+args.wood+'_log';self.c=MaterialClient(args.root,args.out,args.server)
  self.home=list(args.home);self.path=[];self.previous=[];self.seen=set();self.started=time.monotonic();self.result={};self.offhand_slot=None;self.out=Path(args.out)
  if args.resume:self.previous=json.loads(Path(args.resume).read_text())['path']
 def log(self,event,**data):
  record={'time':time.time(),'event':event,**data};print(json.dumps(record,ensure_ascii=False),flush=True)
  with (self.out/'expedition.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
 def reanchor(self):
  s=self.c.status()
  if horizontal(s['pos'],self.c.anchor)>480:raise Handoff('Unexpected displacement outside the current travel segment')
  self.c.anchor=list(s['pos']);self.c.checked('guard',pve_only=True)
 def move(self,target,record=True):
  c=self.c;s=c.status()
  if horizontal(s['pos'],target)>245:raise RuntimeError('A flight segment must be at most 245 blocks')
  if horizontal(target,self.home)>self.a.radius:raise RuntimeError('Expedition search radius reached')
  self.reanchor();r=c.request('navigate',target=target,arrival=1,seconds=150)
  if r.get('phase')!='done':raise RuntimeError('Flight stopped: '+str(r.get('detail')))
  if horizontal(c.status()['pos'],target)>3:raise RuntimeError('Flight endpoint not verified')
  if record:self.path.append(list(target));self.save()
  self.reanchor()
 def save(self):
  (self.out/'route.json').write_text(json.dumps({'home':self.home,'path':self.path,'species':self.item,'count':self.a.count},indent=2))
 def survey(self):
  deadline=time.monotonic()+60;tries=0;core_loaded=0
  while True:
   r=self.c.request('scan_trees',item=self.item,radius=96)
   if 'tree_survey' not in r:raise RuntimeError(r.get('detail','No tree survey'))
   t=r['tree_survey'];tries+=1
   if t['loaded_columns']>=31662:core_loaded=9409;break
   core=self.c.request('scan_trees',item=self.item,radius=48).get('tree_survey',{})
   core_loaded=core.get('loaded_columns',0)
   if core_loaded>=9000 and t['loaded_columns']>=14000:break
   if time.monotonic()>=deadline:raise RuntimeError('Terrain is still loading; do not interpret missing chunks as no trees')
   for _ in range(5):self.c.status();time.sleep(.2)
  self.log('survey',pos=r['pos'],roots=len(t['trees']),biomes=t['biomes'],loaded=t['loaded_columns'],highest=t['highest_surface'],load_attempts=tries,core_loaded=core_loaded)
  return t
 def gather(self,survey):
  c=self.c
  for tree in survey['trees']:
   root=tree['pos'];key=tuple(root)
   if key in self.seen or horizontal(root,self.home)<64:continue
   self.seen.add(key)
   if horizontal(root,c.status()['pos'])>140:continue
   r=c.request('scan',min=[root[0]-11,root[1]-5,root[2]-11],max=[root[0]+11,root[1]+39,root[2]+11],details=True)
   if 'blocks' not in r:continue
   # Avoid worked ground and buildings. Tree validation again happens inside native AutoChopper.
   if any(b.get('block_entity') or any(v in b['state'] for v in ('_planks','_bricks','glass','concrete','_door','_trapdoor')) for b in r['blocks']):
    self.log('skip_near_structure',root=root);continue
   land=landing(r['blocks'],root)
   if not land:self.log('skip_no_clear_landing',root=root);continue
   current=c.status();height=max(current['pos'][1],tree['top']+15,land[1]+40)
   if height>300:continue
   if horizontal(current['pos'],root)>20 or abs(current['pos'][1]-root[1])>8:
    self.sky_exit()
    self.move([land[0],height,land[2]])
    self.move(land)
   before=stocks(c.status()).get(self.item,0)
   self.log('chop_start',root=root,count=before,target=self.a.count)
   r=c.request('chop',item=self.item,target_count=self.a.count,tree_limit=4,seconds=240)
   s=c.status();after=stocks(s).get(self.item,0)
   self.log('chop_end',phase=r.get('phase'),detail=r.get('detail'),count=after,gain=after-before,health=s['health'],remaining=s['chopper_remaining'],platforms=s['chopper_platforms'])
   if r.get('phase') not in ('done','waiting') or s['chopper_platforms'] or s['chopper_remaining']:raise RuntimeError('Chopping did not finish cleanly; inspect recorded position')
   if after>=self.a.count:return True
   self.sky_exit()
  return False
 def inventory_room(self):
  c=self.c;s=c.status();inv=[v for v in s['inventory'] if v['slot']<36]
  count=stocks(s).get(self.item,0);room=sum(v['max_stack']-v['count'] for v in inv if v['item']==self.item)
  needed=math.ceil(max(0,self.a.count-count-room)/64)+(0 if stocks(s).get(self.item.replace('_log','_sapling'),0) else 1)+1
  free=sum(v['count']==0 for v in inv)
  if free<needed:
   menu=s['menu'];cell=next((v for v in menu['slots'][9:45] if v['item']=='minecraft:flint' and v['count']),None)
   if cell and menu['type']=='InventoryMenu' and menu['slots'][45]['count']==0:
    self.offhand_slot=cell['slot'];c.checked('slot_click',menu_id=menu['id'],slot=cell['slot'],expected_item=cell['item'],expected_count=cell['count'],kind='pickup')
    c.checked('slot_click',menu_id=menu['id'],slot=45,expected_item='minecraft:air',expected_count=0,kind='pickup');free+=1
  assert free>=needed,'Insufficient inventory room for the remaining wood target'
 def sky_exit(self):
  c=self.c;s=c.status();x,y,z=map(math.floor,s['pos'])
  r=c.request('scan',min=[x-12,y-4,z-12],max=[x+12,y+39,z+12],details=True)
  if 'blocks' not in r:raise RuntimeError('Cannot verify the takeoff area')
  occupied={tuple(v['pos']) for v in r['blocks'] if not v.get('passable',True)}
  xs=range(math.floor(s['pos'][0]-.31),math.floor(s['pos'][0]+.31)+1);zs=range(math.floor(s['pos'][2]-.31),math.floor(s['pos'][2]+.31)+1)
  if all((xx,yy,zz) not in occupied for xx in xs for zz in zs for yy in range(y,y+40)):
   self.move([s['pos'][0],max(140,s['pos'][1]),s['pos'][2]]);return
  path=sky_path(r['blocks'],s['pos'])
  if not path:raise RuntimeError('No observed collision-free path out of this canopy')
  for point in path:
   if horizontal(c.status()['pos'],point)<.25:continue
   c.checked('walk',target=point,arrival=.2,seconds=12)
  here=c.status()['pos'];self.move([here[0],max(140,here[1]),here[2]])
 def restore_offhand(self):
  if self.offhand_slot is None:return
  c=self.c;s=c.status();m=s['menu'];hand=m['slots'][45]
  if hand['item']!='minecraft:flint':return
  dest=m['slots'][self.offhand_slot] if m['slots'][self.offhand_slot]['count']==0 else next(v for v in m['slots'][9:45] if v['count']==0)
  c.checked('slot_click',menu_id=m['id'],slot=45,expected_item=hand['item'],expected_count=hand['count'],kind='pickup')
  c.checked('slot_click',menu_id=m['id'],slot=dest['slot'],expected_item='minecraft:air',expected_count=0,kind='pickup')
 def return_home(self):
  c=self.c;self.sky_exit();current=c.status()['pos'];height=max(140,current[1])
  # Follow the surveyed route, skipping duplicate local land/takeoff points.
  for p in reversed(self.path):
   if horizontal(c.status()['pos'],p)<8:continue
   self.move([p[0],max(height,p[1]),p[2]],False)
  self.move([self.home[0],height,self.home[2]],False)
  self.move([761019.3,64.15,797854.5],False)
  r=c.fetch(DEPOT,{'oak_log':1});assert r.get('phase')=='done',r.get('detail')
  c.open(DEPOT);before=stocks(c.status()).get(self.item,0)
  try:after=c.transfer(self.item,0,deposit=True)
  finally:
   (self.out/'depot-final.json').write_text(json.dumps(c.status(),ensure_ascii=False,indent=2));c.checked('close_menu')
  self.result.update(deposited=before-after,remaining_carried=after,depot=DEPOT);self.restore_offhand()
 def run(self):
  c=self.c
  try:
   s=c.status();(self.out/'departure.json').write_text(json.dumps(s,ensure_ascii=False,indent=2))
   assert s.get('tree_survey_protocol')==1 and s['kill_aura'] and s['guard_pve_only']
   self.inventory_room()
   axes=[v for v in s['inventory'] if v['item'].endswith('_axe') and v['count']]
   assert any(v.get('durability',0)>self.a.count+32 for v in axes),'Axe durability reserve is insufficient'
   assert stocks(s).get('minecraft:golden_carrot',0)>=5,'Need food reserve'
   self.path=self.previous+[list(s['pos'])];self.save();found=False
   if not self.a.resume:self.move([s['pos'][0],140,s['pos'][2]])
   for index,target in enumerate(route(self.home)):
    if index<self.a.start_step:continue
    survey=self.survey()
    if self.gather(survey):found=True;break
    if time.monotonic()-self.started>self.a.minutes*60:break
    target[1]=min(300,max(140,survey['highest_surface']+16))
    here=c.status()['pos']
    if abs(here[1]-target[1])>2:self.move([here[0],target[1],here[2]])
    self.move(target)
   self.result.update(target=self.a.count,collected=stocks(c.status()).get(self.item,0),species=self.item,met=found)
   self.return_home();s=c.status();self.result.update(health=s['health'],pos=s['pos'],kill_aura=s['kill_aura']);self.log('finished',**self.result)
  except Exception as e:
   self.result.update(error=str(e));self.log('stopped',error=str(e));raise
  finally:
   (self.out/'result.json').write_text(json.dumps(self.result,ensure_ascii=False,indent=2));c.finish()
def main():
 p=argparse.ArgumentParser();p.add_argument('--resume',type=Path);p.add_argument('--start-step',type=int,default=0);p.add_argument('--root',type=Path,default=DEFAULT_ROOT);p.add_argument('--out',type=Path,required=True);p.add_argument('--server',default='simpcraft.com:25565');p.add_argument('--wood',choices=['spruce','birch','oak','jungle','acacia','dark_oak','mangrove','cherry','pale_oak'],default='spruce');p.add_argument('--count',type=int,default=73);p.add_argument('--radius',type=int,default=4000);p.add_argument('--minutes',type=int,default=35);p.add_argument('--home',type=float,nargs=3,default=HOME);a=p.parse_args();assert 1<=a.count<=512 and 100<=a.radius<=10000 and 1<=a.minutes<=120;Expedition(a).run()
if __name__=='__main__':main()
