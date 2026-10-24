"""Open two service cells while an independently verified adult enclosure remains closed."""
from collections import Counter
import math,time
from village_adult_enclosure import audit
from material_plan import inventory_counts

TOOLS={'minecraft:cobblestone':'minecraft:diamond_pickaxe','minecraft:cobbled_deepslate':'minecraft:diamond_pickaxe','minecraft:oak_planks':'minecraft:diamond_axe'}

def shell_positions(guard):
 x,y,z=guard['front'];inward=guard['inward'];depth=guard['depth'];inside=[z+n*inward for n in range(1,depth+1)]
 return({(x,y-1,zz)for zz in [z,*inside]}|{(x,y+3,zz)for zz in inside}
  |{(xx,yy,zz)for xx,zz in [(x,z),(x,z+(depth+1)*inward)]+[(xx,zz)for zz in inside for xx in [x-1,x+1]]for yy in range(y,y+5)})

def require_guard(scene,guard):
 x,y,z=guard['front'];inside=[z+n*guard['inward']for n in range(1,guard['depth']+1)];rows={tuple(r['pos']):r for r in scene['blocks']};proof=audit(rows,front=guard['front'],floor=y,inward=guard['inward'],depth=guard['depth'])
 if not proof['verified']:raise ValueError('Retained adult enclosure is not closed')
 people=[]
 for actor in scene['scan_entities']:
  if actor.get('type')!='minecraft:villager':continue
  box=actor['bounds']
  if box['max'][0]>x and box['min'][0]<x+1 and box['max'][2]>min(inside)and box['min'][2]<max(inside)+1:people.append(actor)
 if len(people)!=1:raise ValueError('Exact single resident required inside retained enclosure')
 actor=people[0];box=actor['bounds'];lo=[x,y,min(inside)];hi=[x+1,y+3,max(inside)+1]
 if(actor.get('uuid')!=guard['uuid']or actor.get('alive')is not True or actor.get('health')!=20 or actor.get('is_baby')is not False
    or not all(lo[i]<=box['min'][i]<box['max'][i]<=hi[i]for i in range(3))):raise ValueError('Retained resident identity, health or body boundary differs')
 return proof

def recover_pair(builder,targets,guard,protected=(),*,pickup_steps=()):
 if(len(targets)!=2 or any(t.get('item')not in TOOLS for t in targets)
    or any(not isinstance(t.get('pos'),list)or len(t['pos'])!=3 or any(type(v)is not int for v in t['pos'])for t in targets)):
  raise ValueError('Two explicit plain service targets required')
 positions=[t['pos']for t in targets];x,y,z=guard['front'];ys=sorted(p[1]for p in positions)
 if(any(p[0]!=x for p in positions)or positions[0][2]!=positions[1][2]or ys!=[y,y+1]
    or any(tuple(p)in shell_positions(guard)or tuple(p)in {tuple(v)for v in protected}for p in positions)):
  raise ValueError('Service targets must preserve the separately retained shell and quarantines')
 if any(r.get('pending')for r in builder.book.get('service_openings',[])):raise RuntimeError('Original service opening remains pending')
 low=[x-1,y-1,min(z,z+(guard['depth']+1)*guard['inward'],positions[0][2])];high=[x+1,y+4,max(z,z+(guard['depth']+1)*guard['inward'],positions[0][2])]
 def scene():
  current,rows=builder.scan(low,high)
  if current['world_session']!=builder.q.world:raise RuntimeError('Service world changed')
  require_guard(current,guard);return current,rows
 before=inventory_counts(builder.check());expected=Counter(before)
 for t in targets:expected[t['item']]+=1
 record={'pending':True,'targets':targets,'guard':guard,'world_session':builder.q.world,'before':dict(before),'mines':[]};builder.book.setdefault('service_openings',[]).append(record);builder.save()
 current,rows=scene()
 for target in targets:
  row=rows.get(tuple(target['pos']),{});state='Block{'+target['item']+'}'
  if row.get('state')!=state or row.get('solid')is not True or row.get('fluid')is not False or row.get('block_entity')is not False:raise ValueError('Exact full plain service blocks required before mining')
 for target in targets:
  current,rows=scene();state='Block{'+target['item']+'}';assert rows.get(tuple(target['pos']),{}).get('state')==state
  tool=TOOLS[target['item']]
  if builder.check().get('hand',{}).get('item')!=tool:builder.n('select_item',item=tool)
  entry={'pos':target['pos'],'pending':True};record['mines'].append(entry);builder.save();reply=builder.n('mine_block',pos=target['pos'],face='south'if guard['inward']==-1 else'north',expected_state=state,seconds=12)
  if not(reply.get('server_confirmed')is True and type(reply.get('native_sequence'))is int and reply['native_sequence']>0 and reply.get('server_ack_sequence')==reply['native_sequence']):raise RuntimeError('Original service mine lacks native ACK; no next excavation')
  entry.update(pending=False,request=reply['id'],native_sequence=reply['native_sequence'],server_ack_sequence=reply['server_ack_sequence']);builder.save()
 current,rows=scene();assert all(tuple(p)not in rows for p in positions)
 def received():return all(inventory_counts(builder.check())[item]==expected[item]for item in {t['item']for t in targets})
 for step in pickup_steps:
  if received():break
  scene()
  if step['kind']=='walk':builder.n('walk',target=step['pos'],arrival=.1,restore_flight=False,seconds=20)
  elif step['kind']=='navigate':builder.nav(step['pos'])
  else:raise ValueError('Explicit normal pickup waypoint required')
  end=time.monotonic()+2
  while not received()and time.monotonic()<end:time.sleep(.1)
 if not received():raise RuntimeError('ACKed service blocks not all recovered; no mining replay')
 record.update(pending=False,material_received=True,after=dict(inventory_counts(builder.check())));builder.save();return record
