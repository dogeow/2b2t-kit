"""One observed adult coat, normal shears, then immediate identity-bound wool pickup."""
from pathlib import Path
from copy import deepcopy
import hashlib,json,math,time
from material_plan import inventory_counts
from kit_runtime.journal import write_json

PICKUP_HOST_SHA='9b06696ab98f0254b4019295733d241912e3a2914085e965e221e6765cbd9477'
def known_pickup_preflight(reply,request_id,world,host_sha):
    return(host_sha==PICKUP_HOST_SHA and reply.get('id')==request_id and reply.get('world_session')==world
        and reply.get('phase')=='error'and reply.get('detail')in('Drop is no longer loaded; observe again','Drop identity or stack changed'))

def drop_fingerprint(drops):
    return tuple(sorted((v['uuid'],v['stack']['count'])for v in drops))

def pickup_host_sha(c):
    import zipfile
    jars=list((Path(c.root).parents[2]/'mods').glob('twob2tkit-*.jar'))
    if len(jars)!=1:return ''
    with zipfile.ZipFile(jars[0])as z:return hashlib.sha256(z.read('dev/twob2tkit/automation/BuildSupplyTask.class')).hexdigest()

def eligible(entity,position):
    p=entity.get('pos');coat=entity.get('sheep')or{}
    return (entity.get('type')=='minecraft:sheep'and entity.get('alive')is True
        and entity.get('is_baby')is False and entity.get('has_custom_name')is False
        and entity.get('visible')is True and coat.get('ready_for_shearing')is True
        and coat.get('sheared')is False and isinstance(p,list)and len(p)==3
        and math.dist([position[0],position[1]+1.62,position[2]],[p[0],p[1]+.715,p[2]])<=2.7)

def shear_one(c,uuid,out,checkpoint):
    q=checkpoint();p=q['pos'];center=[math.floor(v)for v in p]
    low=[center[0]-4,center[1]-1,center[2]-4];high=[center[0]+4,center[1]+4,center[2]+4]
    def survey():
        s=checkpoint();r=c.checked('scan',min=low,max=high,details=True)
        return r,next((e for e in r.get('scan_entities',[])if e.get('uuid')==uuid),None)
    q,e=survey()
    if e is None or not eligible(e,q['pos']):raise RuntimeError('Current visible unshorn unnamed adult sheep is out of reach; no shearing sent')
    c.checked('select_item',item='minecraft:shears');q,e=survey()
    if e is None or not eligible(e,q['pos']):raise RuntimeError('Sheep moved or coat changed after selecting shears; no shearing sent')
    wool='minecraft:'+e['sheep']['color']+'_wool'
    scope=hashlib.sha256((c.server.lower().removesuffix(':25565')+'|'+uuid).encode()).hexdigest()[:24]
    directory=Path(c.root)/'sheep-tending'/scope;directory.mkdir(parents=True,exist_ok=True);pointer=directory/'active.json'
    if pointer.exists():
        old=json.loads(Path(json.loads(pointer.read_text())['journal']).read_text())
        if not old.get('complete')or old.get('pending'):raise RuntimeError('Original coat or wool recovery is unresolved; no repeated shearing')
    out=Path(out);out.mkdir(exist_ok=False);path=out/'shear-and-pickup.json';before=inventory_counts(q)[wool]
    old_drops={v['uuid']for v in q.get('entities',[])if v['type']=='minecraft:item'}
    book={'world_session':c.world,'uuid':uuid,'wool':wool,'before':before,'durability_before':q['hand']['durability'],
          'pre_drop_uuids':sorted(old_drops),'pending':None,'complete':False,'wool_gain':0,'shearing_sent':False,'receipts':[]}
    def save():write_json(path,book)
    def action(op,**params):
        book['pending']={'op':op,'params':params};save();previous=c.last
        try:reply=c.checked(op,**params)
        except RuntimeError:
            if op!='collect_item'or getattr(c,'unconfirmed_native_request',None)is not None:raise
            native=Path(c.root)/('reply-'+c.last+'.json')
            if not native.exists():raise
            rejected=json.loads(native.read_text())
            if not known_pickup_preflight(rejected,c.last,c.world,pickup_host_sha(c)):raise
            book.setdefault('preflight_rejected_pickups',[]).append(rejected)
            book['pending']['request_id']=c.last;save()
            return rejected
        finally:book['pending']['request_id']=c.last if c.last!=previous else None;save()
        book['receipts'].append(reply);save();return reply
    save();write_json(pointer,{'journal':str(path.resolve()),'world_session':c.world})
    action('interact_entity',entity_id=e['id'],expected_uuid=uuid,expected_hand='minecraft:shears')
    book['shearing_sent']=True;save();deadline=time.monotonic()+6
    while True:
        q,after=survey()
        if(after and(after.get('sheep')or{}).get('sheared')is True and q['hand'].get('durability')==book['durability_before']-1):break
        if time.monotonic()>deadline:raise RuntimeError('Original coat use lacks observed coat/durability confirmation; no replay')
        time.sleep(.1)
    book['pending']=None;book['coat_confirmed']=True;save()
    deadline=time.monotonic()+10;stable=None;stable_since=None;attempted=set()
    while inventory_counts(q)[wool]==before:
        drops=[v for v in q.get('entities',[])if v['type']=='minecraft:item'and v['uuid']not in old_drops
               and(v.get('stack')or{}).get('item')==wool and 1<=v['stack']['count']<=3 and math.dist(v['pos'],e['pos'])<=5]
        signature=drop_fingerprint(drops)
        if signature!=stable:stable=signature;stable_since=time.monotonic()
        if drops and time.monotonic()-stable_since>=.75:
            v=min(drops,key=lambda v:math.dist(v['pos'],q['pos']))
            identity=(v['uuid'],v['stack']['count'])
            if identity in attempted:raise RuntimeError('Original pickup identity already attempted; never replay it')
            if len(attempted)>=3:raise RuntimeError('Merged wool did not stabilize; retain original identities')
            attempted.add(identity);book['pickup_identities']=[list(v)for v in sorted(attempted)];save()
            action('collect_item',expected_uuid=v['uuid'],expected_item=wool,expected_count=v['stack']['count'],seconds=30)
            book['pending']=None;save();q=checkpoint()
            if inventory_counts(q)[wool]>before:break
            stable=None;stable_since=None
        if time.monotonic()>deadline:raise RuntimeError('Observed coat was shorn but wool is still uncollected; do not shear again')
        time.sleep(.1);q=checkpoint()
    gain=inventory_counts(q)[wool]-before
    if not 1<=gain<=3:raise RuntimeError('Wool conservation differs from this one observed coat')
    book.update(complete=True,pending=None,wool_gain=gain,after=inventory_counts(q)[wool],
                proof_scope='server_synced_sheared_flag_and_shears_debit_then_observed_drop_pickup_inventory_gain')
    save();return book
