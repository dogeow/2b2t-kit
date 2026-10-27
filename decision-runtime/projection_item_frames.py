"""Normal original frame placement, content insertion and observed one-step rotations."""
import math,time
from pathlib import Path
from material_plan import inventory_counts
from kit_runtime.journal import write_json
from projection_wood import cell_at
from work_access import approach_faces

FACES={2:('north',[0,0,-1]),3:('south',[0,0,1]),4:('west',[-1,0,0]),5:('east',[1,0,0])}

def geometry(e):
    face,d=FACES[e['facing']];p=e['pos'];cell=[math.floor(v)for v in p]
    return [a-b for a,b in zip(cell,d)],face,[p[0]+2*d[0],p[1]-1.2,p[2]+2*d[2]]

def matches(e,a):
    return(a.get('type')==e['type'] and math.dist(a.get('pos',[math.inf]*3),e['pos'])<.15
        and all(a.get(k)==e[k]for k in ('facing','invisible','item_rotation','item')))

def place(c,e,out,checkpoint):
    if(e.get('type')not in('minecraft:item_frame','minecraft:glow_item_frame')or e.get('invisible')
       or e.get('facing')not in FACES or type(e.get('item_rotation'))is not int or not 0<=e['item_rotation']<8
       or e.get('item',{}).get('count')not in(0,1)):
        raise ValueError('Original visible cardinal wall frame required')
    wanted=e['item']
    if wanted.get('id')not in('minecraft:air','minecraft:white_banner')or wanted.get('patterns',[])!=[]:
        raise ValueError('Only original empty or plain white banner content supported')
    if(wanted['id']=='minecraft:air')!=(wanted['count']==0)or wanted['id']=='minecraft:air'and e['item_rotation']!=0:
        raise ValueError('Empty frames have no content to rotate')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);q=checkpoint();key=q['projection_selection']['key']
    if not all(lo<=v<=hi+1 for lo,v,hi in zip(q['projection_selection']['min'],e['pos'],q['projection_selection']['max'])):
        raise ValueError('Frame outside original projection')
    anchor,face,pose=geometry(e);row=cell_at(c,anchor)
    if not row.get('solid')or row.get('fluid')or row.get('block_entity'):raise RuntimeError('Dry non-container original frame support required')
    # Buttons and hooks share these original cells. Let the native navigator
    # prove their real collision shapes and a visible wall-face hit instead of
    # treating every occupied voxel as a full block or removing the furniture.
    approach_faces(c,anchor,row['state'],(face,),seconds=45,stand_distance=2.8)
    def audit():
        checkpoint();a=c.request('projection_audit')['projection_audit']
        if a['placement_key']!=key or not a.get('loaded_chunks_verified'):raise RuntimeError('Original frame audit scope changed')
        return a
    a=audit();near=[v for v in a['decorations']if math.dist(v['pos'],e['pos'])<.25]
    if near:
        if len(near)==1 and matches(e,near[0]):return {'already_matched':True,'actual':near[0]}
        raise RuntimeError('Existing decoration at original frame position; never modify it')
    ids={v['uuid']for v in a['decorations']};before=dict(inventory_counts(checkpoint()))
    if before.get(e['type'],0)<1 or wanted['count'] and before.get(wanted['id'],0)<1:
        raise RuntimeError('Actual carried frame and original content required')
    book={'world_session':c.world,'placement_key':key,'expected':e,'inventory_before':before,'pending':None,'complete':False,'steps':[]}
    path=out/'frame.json'
    def save():write_json(path,book)
    def send(op,kind,**params):
        book['pending']={'kind':kind};save()
        try:r=c.checked(op,**params)
        finally:book['pending']['request_id']=c.last;save()
        write_json(out/('%02d-native.json'%len(book['steps'])),r)
    def confirm(uid,content,rotation,stock):
        end=time.monotonic()+6;stamps=[]
        while True:
            a=audit();actual=[v for v in a['decorations']if v['uuid']==uid]if uid else [v for v in a['decorations']if v['uuid']not in ids and math.dist(v['pos'],e['pos'])<.15]
            counts=inventory_counts(checkpoint())
            if len(actual)==1 and matches({**e,'item':content,'item_rotation':rotation},actual[0]) and all(counts[k]==v for k,v in stock.items()):
                if a['observed_at']not in stamps:stamps.append(a['observed_at'])
                if len(stamps)>=2:return actual[0]
            else:stamps=[]
            if time.monotonic()>end:raise RuntimeError('Original frame use unconfirmed; no repeat or next rotation')
            time.sleep(.1)
    c.checked('select_item',item=e['type'])
    send('interact','one_ordinary_frame_placement',pos=anchor,face=face,expected_state=row['state'],expected_hand=e['type'])
    stock={e['type']:before[e['type']]-1}
    actual=confirm(None,{'id':'minecraft:air','count':0},0,stock)
    uid=actual['uuid'];book.update(owned_uuid=uid,pending=None);book['steps'].append({'kind':'placed','actual':actual});save()
    def use_owned(kind):
        checkpoint();a=audit();current=next((v for v in a['decorations']if v['uuid']==uid),None)
        if current!=actual:raise RuntimeError('Newly owned frame changed; preserve external changes')
        q=checkpoint();live=next((v for v in q.get('entities',[])if v['uuid']==uid),None)
        if live is None:
            p=[math.floor(v)for v in e['pos']];r=c.request('scan',min=[v-2 for v in p],max=[v+2 for v in p],details=True)
            if r.get('phase')!='done':raise RuntimeError('Owned frame identity scan unconfirmed')
            live=next((v for v in r.get('scan_entities',[])if v['uuid']==uid),None)
        if live is None or live['type']!=e['type']or math.dist(live['pos'],e['pos'])>.15:raise RuntimeError('Owned frame ID changed')
        send('interact_entity',kind,entity_id=live['id'],expected_uuid=uid)
    if wanted['count']:
        c.checked('select_item',item=wanted['id']);use_owned('one_content_insertion')
        stock[wanted['id']]=before[wanted['id']]-1;actual=confirm(uid,wanted,0,stock)
        book['steps'].append({'kind':'content_inserted','actual':actual});book['pending']=None;save()
        for rotation in range(1,e['item_rotation']+1):
            use_owned('one_rotation_%d'%rotation);actual=confirm(uid,wanted,rotation,stock)
            book['steps'].append({'kind':'rotation','actual':actual});book['pending']=None;save()
    book.update(complete=True,actual=actual,inventory_after=dict(inventory_counts(checkpoint())));save()
    print('ORIGINAL_FRAME_MATCHED',e['pos'],e['type'],e['item_rotation'],flush=True);return book
