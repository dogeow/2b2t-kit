"""Keep one confirmed outer gate for a return trip, with the inner gate closed."""
import math,time
from library_airlock_route import Z,closed,require_empty_relay,require_path


def scope(builder):
    state=builder.check();lease=state.get('supervision_lease')or{};owner=builder.q.lease
    if(state.get('connected')is not True or state.get('health')!=20 or state.get('manual_movement')is not False
       or state.get('screen') or state.get('world_session')!=builder.q.world
       or any(lease.get(k)!=owner.get(k)for k in ('id','job_session','world_session'))):
        raise RuntimeError('Healthy current airlock owner required')
    return {k:owner[k]for k in ('id','job_session','world_session')}


def require_restored(book):
    records=list(book.get('held_return_gate_history')or[])
    if book.get('held_return_gate'):records.append(book['held_return_gate'])
    for row in records:
        if(not isinstance(row,dict)or row.get('phase')!='closed'or row.get('pending')is not False
           or row.get('both_doors_closed')is not True or row.get('lever_restored')is not True
           or not row.get('on_request')or not row.get('off_request')
           or (row.get('scope')or{}).get('world_session')!=book.get('world_session')):
            raise RuntimeError('Original held return gate is not restored')


def _scan(builder):
    return builder.scan([760987,63,797802],[761000,67,797813])


def _opened(rows,on):
    return(rows.get((760996,64,Z),{}).get('state')==on
           and all(rows.get((760997,y,Z),{}).get('state')==f'Block{{minecraft:iron_door}}[facing=west,half={half},hinge=left,open=true,powered=true]'for y,half in [(64,'lower'),(65,'upper')]))


def begin(builder):
    from projection_completion import block_state
    require_restored(builder.book);ownership=scope(builder)
    if any(r.get('pending')for r in builder.book.get('airlock_crossings',[])):raise RuntimeError('Previous crossing remains pending')
    scene,rows=_scan(builder);require_empty_relay(scene,760997)
    row=rows.get((760996,64,Z),{});off=row.get('state','Block{minecraft:air}');kind,props=block_state(off)
    if(not closed(rows,760993)or not closed(rows,760997)or kind!='minecraft:lever'
       or props.get('face')!='floor'or props.get('powered')!='false'or row.get('fluid')is not False):
        raise RuntimeError('Both doors closed and original relay lever off required')
    pos=builder.check()['pos']
    if abs(pos[1]-64)>.12 or math.hypot(pos[0]-760996.5,pos[2]-(Z+.5))>.4:raise RuntimeError('Expected relay-side approach')
    for x in (760996,760998):require_path(rows,[[x+.5,64.,Z+.5]]*2)
    record={'phase':'opening','pending':True,'scope':ownership,'lever':[760996,64,Z],
            'off_state':off,'on_state':off.replace('powered=false','powered=true'),'inner_door':[760993,64,Z]}
    builder.book['held_return_gate']=record;builder.book.setdefault('held_return_gate_history',[]).append(record);builder.save()
    if builder.check().get('hand',{}).get('item')!='minecraft:netherite_sword':builder.n('select_item',item='minecraft:netherite_sword')
    reply=builder.n('interact',pos=record['lever'],face='up',expected_state=off,expected_hand='minecraft:netherite_sword');record['on_request']=reply['id'];builder.save()
    deadline=time.monotonic()+4
    while True:
        scope(builder);_,rows=_scan(builder)
        if not closed(rows,760993):raise RuntimeError('Inner door changed; no outbound crossing')
        if _opened(rows,record['on_state']):break
        if time.monotonic()>=deadline:raise RuntimeError('Original held opening not confirmed; no second toggle')
        time.sleep(.1)
    record.update(phase='outbound_crossing',pending=True);builder.save()
    builder.n('walk',target=[760998.5,64.,Z+.5],arrival=.1,restore_flight=False,seconds=12)
    record.update(phase='held_for_return',pending=False,opening_confirmed=True);builder.save()
    return record


def return_through(builder,observation=None):
    record=builder.book.get('held_return_gate')or{}
    if(record.get('phase')!='held_for_return'or record.get('pending')is not False
       or record.get('opening_confirmed')is not True or not record.get('on_request')
       or record.get('scope')!=scope(builder)or record.get('lever')!=[760996,64,Z]):
        raise RuntimeError('No exact settled owned gate for return; never replay an opening')
    state=builder.check();position=state['pos'];floor=64 if position[0]<761015 else 65
    if not(760997<=position[0]<=761034 and abs(position[1]-floor)<1.2 and 797810<=position[2]<=797813):raise RuntimeError('Return source outside main gallery')
    scene,rows=_scan(builder)if observation is None else observation
    if observation is not None and(scene.get('world_session')!=builder.q.world or not 0<=state['time']-scene.get('time',-10000)<=1000):raise RuntimeError('Stale return observation')
    require_empty_relay(scene,760997)
    if not closed(rows,760993)or not _opened(rows,record['on_state']):raise RuntimeError('Owned return gate or closed inner door changed')
    for x in (760994,760995,760996,760998):require_path(rows,[[x+.5,64.,Z+.5]]*2)
    record.update(phase='returning',pending=True);builder.save()
    if math.hypot(position[0]-760994.5,position[2]-(Z+.5))>31:
        builder.n('walk',target=[761014.5,64.,Z+.5],arrival=.1,restore_flight=False,seconds=20)
    builder.n('walk',target=[760994.5,64.,Z+.5],arrival=.1,restore_flight=False,seconds=20)
    # The native exact-state precondition prevents a second toggle. Closing our
    # own control restores separation even if another door changed meanwhile.
    record.update(phase='closing',pending=True);builder.save();scope(builder)
    reply=builder.n('interact',pos=record['lever'],face='up',expected_state=record['on_state'],expected_hand='minecraft:netherite_sword');record['off_request']=reply['id'];builder.save()
    deadline=time.monotonic()+4
    while True:
        scope(builder);scene,rows=_scan(builder);require_empty_relay(scene)
        if(rows.get(tuple(record['lever']),{}).get('state')==record['off_state']and closed(rows,760993)and closed(rows,760997)):break
        if time.monotonic()>=deadline:raise RuntimeError('Original held close not confirmed; no second toggle')
        time.sleep(.1)
    record.update(phase='closed',pending=False,lever_restored=True,both_doors_closed=True);builder.save()
    return scene,rows
