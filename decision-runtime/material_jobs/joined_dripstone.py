"""Harvest an upward pillar joined to one retained ceiling root, top down."""
import hashlib,json,math
from pathlib import Path

from kit_runtime.journal import write_json
from projection_completion import block_state
from .acquisition import _scan,_safe,_tool,_choose_tool,block_id,carried
from .dripstone_growth import growth_column,actual_mining_face
from .dry_hover_harvest import pickup,rejected_without_mining
from .local_air_path import move_replanning_once
from .protocol import JobBlocked,server_key

ITEM='minecraft:pointed_dripstone'


def column(rows,root,minimum_y):
    if (not isinstance(root,list)or len(root)!=3 or any(type(v)is not int for v in root)
            or type(minimum_y)is not int or not 1<=root[1]-minimum_y<=16):
        raise ValueError('One bounded exact ceiling root required')
    down=growth_column(rows,root,minimum_y)
    if len(down['chain'])!=1 or block_state(down['chain'][0]['state'])[1].get('thickness')!='tip_merge':
        raise JobBlocked('Only one retained ceiling root joined to an upward pillar is supported')
    cells={tuple(r['pos']):r for r in rows};x,y,z=root;up=[]
    for height in range(y-1,minimum_y-1,-1):
        row=cells.get((x,height,z))
        if not row or block_id(row)!=ITEM:break
        props=block_state(row['state'])[1]
        if props.get('vertical_direction')!='up' or props.get('waterlogged')!='false':
            raise JobBlocked('Joined lower pillar is not wholly dry upward dripstone')
        up.append(row)
    if not up:raise JobBlocked('Joined upward pillar is missing')
    floor=cells.get((x,up[-1]['pos'][1]-1,z))
    if (not floor or floor.get('solid')is not True or floor.get('fluid')is not False
            or floor.get('block_entity')is not False):
        raise JobBlocked('The complete pillar floor is unconfirmed or protected')
    return {'root':root,'root_row':down['chain'][0],'support':down['support'],
            'water':down['water'],'floor':floor,'upward':up}


def retained(rows,plan):
    cells={tuple(r['pos']):r for r in rows};root=cells.get(tuple(plan['root']))
    if not root or block_id(root)!=ITEM:raise JobBlocked('Highest ceiling root changed')
    props=block_state(root['state'])[1]
    if props.get('vertical_direction')!='down' or props.get('waterlogged')!='false':
        raise JobBlocked('Highest ceiling root direction or water changed')
    for key in ('support','water','floor'):
        row=cells.get(tuple(plan[key]['pos']))
        if not row or row['state']!=plan[key]['state']:
            raise JobBlocked('Joined pillar support, source water or floor changed')
    return cells


def run(c,root,minimum_y,stand_column,air_bounds,out,checkpoint):
    if (not isinstance(stand_column,list)or len(stand_column)!=2 or any(type(v)is not int for v in stand_column)
            or abs(stand_column[0]-root[0])+abs(stand_column[1]-root[2])!=1):
        raise ValueError('One adjacent standing column required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);file=out/'joined-harvest.json'
    initial=c.status();key=initial['projection_selection']['key']
    def state():
        checkpoint();q=c.status();_safe(q);lease=q.get('supervision_lease')or{}
        if (q.get('world_session')!=c.world or q['projection_selection']['key']!=key
                or lease.get('kind')!='materials' or lease.get('job_session')!=c.task
                or lease.get('revision')!=q.get('control_revision')):
            raise JobBlocked('Joined pillar controller or world changed')
        return q
    x,y,z=root
    def observe():return _scan(c,[x,minimum_y,z],[x,y+2,z],state)
    plan=column(observe(),root,minimum_y);before=carried(state(),ITEM)
    directory=Path(c.root)/'dripstone-growth-intents';directory.mkdir(parents=True,exist_ok=True)
    for old_file in directory.glob('*.json'):
        if old_file.is_symlink()or old_file.stat().st_size>16384:raise JobBlocked('Unsafe growth intent')
        old=json.loads(old_file.read_text());scope=old.get('scope')or{};other=scope.get('root')
        if (old.get('pending')and server_key(scope.get('server'))==server_key(initial['server'])
                and scope.get('dimension')==initial['dimension']and isinstance(other,list)
                and(other[0],other[2])==(x,z)):
            raise JobBlocked('Original column action unresolved; no replay')
    scope={'world_session':c.world,'server':initial['server'],'dimension':initial['dimension'],'root':root}
    shared=directory/(hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()+'.json')
    book={'world_session':c.world,'root':root,'plan':plan,'before':before,'pending':None,
          'mining_receipts':[],'pickup_receipts':[],'complete':False,'resource_credit':0}
    def save():
        write_json(file,book);write_json(shared,{'scope':scope,'journal':str(file),'mode':'joined_upward','pending':book['pending']})
    old_ids={e['uuid']for e in state().get('entities',[])if e.get('type')=='minecraft:item'}
    save();c.start_progress('采收整柱：保留最高根部和地面',len(plan['upward']))
    for index,expected in enumerate(plan['upward']):
        cells=retained(observe(),plan)
        if any(tuple(r['pos'])in cells for r in book['mining_receipts']):
            book['deferred']='New growth appeared in an already cleared cell';save();break
        pos=expected['pos'];current=cells.get(tuple(pos))
        if (not current or block_id(current)!=ITEM or block_state(current['state'])[1].get('vertical_direction')!='up'
                or block_state(current['state'])[1].get('waterlogged')!='false'):
            raise JobBlocked('Original upward target changed; no mining sent')
        pose=[stand_column[0]+.5,max(plan['floor']['pos'][1]+1.2,pos[1]-.8),stand_column[1]+.5]
        move_replanning_once(c,pose,out/('access-%02d'%index),max_straight=8,foot_offset=.2,
                             max_horizontal=24,scan_bounds=air_bounds)
        _choose_tool(c,_tool(state(),'pickaxe',33),state)
        fresh=retained(observe(),plan).get(tuple(pos))
        if not fresh or fresh['state']!=current['state']:raise JobBlocked('Upward target changed before mining')
        actual_mining_face(c,fresh,None)
        around=_scan(c,[v-1 for v in pos],[v+1 for v in pos],state)
        if any(r.get('fluid')for r in around):raise JobBlocked('Fluid next to upward target; no mining sent')
        book['pending']={'kind':'mine','pos':pos,'expected_state':fresh['state']};save()
        try:reply=c.request('mine_block',pos=pos,expected_state=fresh['state'],seconds=20)
        finally:book['pending']['request_id']=c.last;save()
        if rejected_without_mining(reply,c.last,c.world,pos):
            book['deferred']='Native admission rejected before sending mining'
            book['known_rejected_request']=dict(book['pending']);book['pending']=None;save();break
        if (reply.get('id')!=c.last or reply.get('world_session')!=c.world or reply.get('phase')!='done'
                or reply.get('server_confirmed')is not True
                or reply.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
                or type(reply.get('native_sequence'))is not int or reply['native_sequence']<=0
                or reply.get('native_sequence')!=reply.get('server_ack_sequence')
                or _scan(c,pos,pos,state)):
            raise JobBlocked('Original upward mining unconfirmed; preserve intent without replay')
        book['mining_receipts'].append({**book['pending'],'server_confirmed':True})
        book['pending']=None;save();c.set_progress(done=len(book['mining_receipts']),phase='保留最高根部，逐段采收下方石笋')
        print('UPWARD_SEGMENT_REMOVED',len(book['mining_receipts']),pos,flush=True)
    cells=retained(observe(),plan);all_removed=len(book['mining_receipts'])==len(plan['upward'])
    if all_removed and any(tuple(r['pos'])in cells for r in plan['upward']):
        raise JobBlocked('Upward cells changed after confirmed removal')
    if book['mining_receipts']:
        point=[(x if all_removed else stand_column[0])+.5,plan['floor']['pos'][1]+1.2,
               (z if all_removed else stand_column[1])+.5]
        move_replanning_once(c,point,out/'collect-column',max_straight=8,foot_offset=.2,
                             max_horizontal=24,scan_bounds=air_bounds)
    for index in range(len(plan['upward'])+1):
        q=state()
        if carried(q,ITEM)-before>=len(book['mining_receipts']):break
        drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'and e.get('uuid')not in old_ids
               and e.get('stack',{}).get('item')==ITEM and math.dist(e['pos'],root)<12]
        if not drops:break
        drop=min(drops,key=lambda e:math.dist(e['pos'],q['pos']));have=carried(q,ITEM)
        book['pending']={'kind':'pickup','uuid':drop['uuid'],'before':have,'count':drop['stack']['count']};save()
        if not pickup(c,drop,have,out/('pickup-%02d'%index),state,item=ITEM,expected_count=drop['stack']['count'],
                      air_bounds=air_bounds,allow_cone_edges=True):
            raise JobBlocked('Original joined-column drop pickup unconfirmed')
        book['pickup_receipts'].append(dict(book['pending']));book['pending']=None;save()
    retained(observe(),plan);after=carried(state(),ITEM)
    if after<before:raise JobBlocked('Pointed inventory decreased during joined harvest')
    book.update(after=after,actual_backpack_gain=after-before,resource_credit=after-before,
                attribution_scope='actual_backpack_delta_only',mining_complete=all_removed,
                root_retained=True,support_preserved=True,water_preserved=True,floor_preserved=True,
                complete=all_removed and after-before>=len(book['mining_receipts']))
    save();return book
