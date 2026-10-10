"""Bounded normal bone meal use on a complete registered wheat field."""
import json
from pathlib import Path
import time
import hashlib

from farm_reseed import registered
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from potato_farm import _properties
from potato_harvest import _lease
from material_jobs.protocol import JobBlocked


def accept_growth(before_age,after_age,before_count,after_count,reply,world):
    if (reply.get('phase')!='done' or reply.get('world_session')!=world
            or type(before_age)is not int or type(after_age)is not int
            or not 0<=before_age<after_age<=7 or before_count-after_count!=1):
        raise JobBlocked('Registered wheat growth or one bone meal consumption unproved')


def reconcile_pre_use_rejection(journal,state,host_class_sha256):
    """The pinned host rejects these exact messages before vanilla useItemOn."""
    if host_class_sha256!='ef5f1bbccaa2746e9aaff2782c4c58ec8ef15c9cb6a0cf5cf1088a2819c09688':
        raise JobBlocked('Unverified host pre-use contract; retain bone meal intent')
    journal=Path(journal);raw=journal.read_bytes();book=json.loads(raw);pending=book.get('pending')or{}
    reply=pending.get('receipt')or{};before=pending.get('before_bone_meal')
    if (reply.get('phase')!='error' or reply.get('world_session')!=book.get('world_session')
            or reply.get('kit_version')not in ('2026.10.10.2','2026.10.10.3')
            or reply.get('detail')not in ('Target block changed','Target interaction face is occluded or out of reach')
            or state.get('world_session')!=book.get('world_session')
            or inventory_counts(reply)['minecraft:bone_meal']!=before
            or inventory_counts(state)['minecraft:bone_meal']!=before):
        raise JobBlocked('Pre-use rejection and unchanged bone meal are not proven')
    archive=journal.parent/'rejections';archive.mkdir(exist_ok=True);digest=hashlib.sha256(raw).hexdigest()
    (archive/('before-'+digest[:16]+'.json')).write_bytes(raw)
    proof={'request_id':reply['id'],'pos':pending['pos'],'before_bone_meal':before,
           'outcome':'rejected_before_normal_use','host_class_sha256':host_class_sha256,
           'original_pending_sha256':digest,'new_bone_meal_use_sent':False}
    write_json(archive/'latest-proof.json',proof);book.setdefault('pre_use_rejections',[]).append(proof)
    book['pending']=None;write_json(journal,book);return proof


def run(c,registry,out,*,target_mature=16,max_uses=64,checkpoint=lambda:None):
    if type(target_mature)is not int or not 1<=target_mature<=24 or type(max_uses)is not int or not 1<=max_uses<=128:
        raise ValueError('Bounded registered wheat growth target required')
    original=json.loads(Path(registry).read_text());layout=original['scope']['layout']
    registered(c.root,registry,layout['cells'][:1],server=c.server)
    pointer=Path(registry).parent/'growth-active.json'
    if pointer.exists():
        previous=json.loads(Path(json.loads(pointer.read_text())['journal']).read_text())
        if previous.get('pending'):raise JobBlocked('Original bone meal use unknown; no new growth intent')
    out=Path(out);out.mkdir(exist_ok=False);path=out/'wheat-growth.json';hurt=c.status()['recent_hurt_at']
    book={'world_session':c.world,'registry':str(registry),'pending':None,'uses':[],'grain_inventory_credit':0}
    save=lambda:write_json(path,book)
    save();write_json(pointer,{'world_session':c.world,'journal':str(path.resolve())})
    def state():
        checkpoint();s=c.status();_lease(c,s,hurt);return s
    def age(pos):
        state();r=c.checked('scan',min=pos,max=pos,details=True)
        if r.get('world_session')!=c.world or r.get('scan_cells_read')!=r.get('scan_total_cells')or r.get('scan_cells_read')!=1:
            raise JobBlocked('Current crop scan incomplete')
        row=next((x for x in r['blocks']if x['pos']==pos),None);value=_properties(row or{},'wheat','age',7)
        if value is None:raise JobBlocked('Original registered crop changed; do not use bone meal')
        return value
    target=[layout['center'][0]+.5,layout['center'][1]+1.6,layout['center'][2]+.5]
    from material_jobs.navigation import lift_for_travel
    from material_jobs.acquisition import _travel
    lift_for_travel(c);pose=state()['pos'];trace=[]
    _travel(c,[target[0],max(pose[1],layout['center'][1]+24),target[2]],checkpoint,trace,keep_cruise=True)
    write_json(out/'registered-field-arrival.json',trace)
    c.checked('navigate',target=target,arrival=.15,air_only=True,seconds=30)
    mature=0;save()
    for floor in layout['cells']:
        pos=[floor[0],floor[1]+1,floor[2]];current=age(pos)
        if current<7:
            # Hover above this exact crop; never stand on farmland or shoot
            # through taller intervening wheat from the center water cell.
            c.checked('navigate',target=[floor[0]+.5,floor[1]+1.6,floor[2]+.5],arrival=.15,air_only=True,seconds=15)
            current=age(pos)
        while current<7 and len(book['uses'])<max_uses:
            before=inventory_counts(state())['minecraft:bone_meal']
            if before<1:
                book.update(complete=False,mature=mature);save()
                return {'phase':'waiting','code':'WAIT_BONE_MEAL','mature':mature,'uses':len(book['uses'])}
            c.checked('select_item',item='minecraft:bone_meal');current=age(pos)
            if current==7:break
            book['pending']={'pos':pos,'before_age':current,'before_bone_meal':before};save()
            reply=c.request('interact',pos=pos,face='up',expected_state='Block{minecraft:wheat}[age=%d]'%current,expected_hand='minecraft:bone_meal')
            book['pending']['receipt']=reply;save();end=time.monotonic()+6
            if reply.get('phase')!='done':raise JobBlocked('Original bone meal result unknown; no repeated use')
            while True:
                after=age(pos);remaining=inventory_counts(state())['minecraft:bone_meal']
                if after>current and before-remaining==1:break
                if time.monotonic()>=end:raise JobBlocked('Bone meal outcome unknown; no repeated use')
                time.sleep(.15)
            accept_growth(current,after,before,remaining,reply,c.world)
            book['uses'].append({'pos':pos,'before_age':current,'after_age':after,'request_id':reply.get('id')})
            book['pending']=None;save();current=after
        if current==7:mature+=1
        if mature>=target_mature:break
    book.update(complete=mature>=target_mature,mature=mature);save()
    return {'phase':'done'if book['complete']else'waiting','mature':mature,'uses':len(book['uses']),'journal':str(path),'grain_inventory_credit':0}
