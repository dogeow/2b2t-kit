"""Bounded top-down harvest of one witnessed 2x2 spruce through normal Kit inputs.

This does not depend on the server's soil tags. Only the certified trunk and
nonpersistent spruce leaves in its four core columns may be removed. It never
expands into neighboring trees or edits the soil.
"""
from pathlib import Path
from copy import deepcopy
import time
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from kit_runtime.journal import write_json


def trunk_certificate(root,logs):
    if (not isinstance(root,list)or len(root)!=3 or any(type(v)is not int for v in root)
            or not isinstance(logs,list)or not 4<=len(logs)<=140):raise ValueError('One exact grown two-by-two trunk required')
    positions=[]
    for row in logs:
        p=row.get('pos')
        if (not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)
                or not row.get('state','').startswith('Block{minecraft:spruce_log}')
                or p[0]not in (root[0],root[0]+1)or p[2]not in (root[2],root[2]+1)
                or not root[1]<=p[1]<=root[1]+33):raise ValueError('Trunk certificate contains an unrelated cell')
        positions.append(tuple(p))
    if len(set(positions))!=len(positions):raise ValueError('Duplicate trunk cell')
    for x in (root[0],root[0]+1):
        for z in (root[2],root[2]+1):
            heights=sorted(p[1]for p in positions if p[0]==x and p[2]==z)
            if not heights or heights!=list(range(root[1],heights[-1]+1)):raise ValueError('Four continuous soil-rooted trunk columns required')
    return {tuple(r['pos']):deepcopy(r)for r in logs}


def collect_core_drops(builder,root,total,book,save):
    """Reach observed log drops from the already cleared core; never remine."""
    attempted=set();deadline=time.monotonic()+20
    while inventory_counts(builder.check())['minecraft:spruce_log']<total:
        state=builder.check();remaining=total-inventory_counts(state)['minecraft:spruce_log']
        drops=[e for e in state.get('entities',[])if e.get('type')=='minecraft:item'
            and e.get('stack',{}).get('item')=='minecraft:spruce_log'and e.get('uuid')not in attempted
            and len(e.get('pos',[]))==3 and root[1]<=e['pos'][1]<=root[1]+34
            and all(root[i]-2<=e['pos'][i]<=root[i]+3 for i in (0,2))]
        if not drops:
            if time.monotonic()>=deadline:raise RuntimeError('Certified logs removed but pickup incomplete; never remine')
            time.sleep(.15);continue
        drop=drops[0];assert 0<drop['stack']['count']<=remaining,'Observed log drop exceeds this harvest remainder'
        _,rows=builder.scan(root,[root[0]+1,root[1]+35,root[2]+1]);assert not rows,'Core pickup route is no longer empty'
        pos=[min(max(drop['pos'][0],root[0]+.4),root[0]+1.6),drop['pos'][1]+.1,min(max(drop['pos'][2],root[2]+.4),root[2]+1.6)]
        book['pending_pickup']={'uuid':drop['uuid'],'count':drop['stack']['count'],'observed_pos':drop['pos'],'target':pos};save()
        builder.nav([root[0]+1.,pos[1],root[2]+1.]);builder.nav(pos);attempted.add(drop['uuid'])
        end=time.monotonic()+3;before=total-remaining
        while inventory_counts(builder.check())['minecraft:spruce_log']<before+drop['stack']['count']:
            if time.monotonic()>end:raise RuntimeError('Original observed log pickup remains unconfirmed; no mining replay')
            time.sleep(.1)
        book.setdefault('drop_pickups',[]).append(book.pop('pending_pickup'));save()


def harvest(builder,root,logs,path):
    expected=trunk_certificate(root,logs);path=Path(path)
    if path.exists():raise RuntimeError('Original harvest journal exists; never replay mining')
    book={'complete':False,'pending':None,'root':root,'certified_logs':logs,'mined':[],'cleared_core_leaves':[]}
    def save():write_json(path,book)
    def scan():return builder.scan([root[0],root[1]-1,root[2]],[root[0]+1,root[1]+35,root[2]+1])[1]
    def mine(p,row,leaf=False):
        if leaf:
            assert row['state'].startswith('Block{minecraft:spruce_leaves}')and'persistent=false'in row['state']
        else:assert p in expected and row['state']==expected[p]['state']
        assert not row.get('fluid')and not row.get('block_entity')
        book['pending']={'pos':list(p),'expected_state':row['state'],'kind':'clear_core_leaf'if leaf else'certified_log'};save()
        builder.n('select_item',item='minecraft:diamond_axe');reply=builder.n('mine_block',pos=list(p),face='up',expected_state=row['state'],seconds=15)
        assert reply.get('server_confirmed')and reply.get('native_sequence')==reply.get('server_ack_sequence'),'Native break was not confirmed; no replay'
        _,fresh=builder.scan(list(p),list(p));assert p not in fresh
        book['cleared_core_leaves'if leaf else'mined'].append({'pos':list(p),'request':reply['id']});book['pending']=None;save()
    try:
        s=builder.check();before=inventory_counts(s)['minecraft:spruce_log'];book.update(world_session=s['world_session'],logs_before=before);save()
        if room_for_item(s,'minecraft:spruce_log')<len(expected)+3*64:raise RuntimeError('Reserve log capacity and three spare inventory slots before harvesting')
        tools=[r for r in s['inventory']if r.get('item')=='minecraft:diamond_axe'and r.get('count')==1];assert len(tools)==1 and tools[0].get('durability',0)>=len(expected)+32
        rows=scan();actual={p:r for p,r in rows.items()if r['state'].startswith('Block{minecraft:spruce_log}')};assert set(actual)==set(expected)and all(actual[p]['state']==expected[p]['state']for p in expected)
        assert all(not r.get('fluid')and not r.get('block_entity')for r in rows.values())
        for p,r in rows.items():
            if p[1]>=root[1]and p not in expected:assert r['state'].startswith('Block{minecraft:spruce_leaves}')and'persistent=false'in r['state'],'Only this trunk and its natural core leaves may be touched'
        top=max(p[1]for p in rows if p[1]>=root[1]);center=[root[0]+1.,top+1.1,root[2]+1.];p=s['pos'];builder.nav([p[0],top+3.,p[2]]);builder.nav([center[0],top+3.,center[2]]);builder.nav(center)
        for y in range(max(p[1]for p in expected),root[1]-1,-1):
            rows=scan()
            for h in sorted({p[1]for p in rows if p[1]>=y+1},reverse=True):
                for x in (root[0],root[0]+1):
                    for z in (root[2],root[2]+1):
                        p=(x,h,z)
                        if p in rows:mine(p,rows[p],leaf=True)
                builder.nav([center[0],h+.1,center[2]])
            builder.nav([center[0],y+1.1,center[2]]);rows=scan()
            for p in sorted(q for q in expected if q[1]==y):
                assert p in rows;mine(p,rows[p])
            for p,row in rows.items():
                if p[1]==y and p not in expected:mine(p,row,leaf=True)
            builder.nav([center[0],y+.1,center[2]])
        remaining=scan();assert not any(r['state'].startswith('Block{minecraft:spruce_log}')for r in remaining.values())
        collect_core_drops(builder,root,before+len(expected),book,save)
        after=builder.check();book.update(complete=True,logs_held=inventory_counts(after)['minecraft:spruce_log'],log_gain=inventory_counts(after)['minecraft:spruce_log']-before,saplings_held=inventory_counts(after)['minecraft:spruce_sapling'],health=after['health'],soil_untouched=True);save();return book
    except Exception as error:book['error']=repr(error);save();raise
