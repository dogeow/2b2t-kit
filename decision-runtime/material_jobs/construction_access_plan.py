"""Conservative temporary construction access, using only a confirmed sparse scan.

No game actions or file IO. This is an offline route/phase proposal, not proof of
live native reach, collision shapes, support clicks or completed placement.
"""
from collections import Counter, deque
import math


class AccessPlanBlocked(ValueError):
    pass


DIRECTIONS=((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))
SIDES=((1,0,0,'east'),(-1,0,0,'west'),(0,0,1,'south'),(0,0,-1,'north'))
SAFE_SHELL=('minecraft:white_concrete','minecraft:light_gray_concrete','minecraft:gray_concrete',
            'minecraft:smooth_stone','minecraft:quartz_block',
            'minecraft:polished_andesite','minecraft:deepslate_tiles','minecraft:deepslate_bricks')
GRAVITY={'minecraft:sand','minecraft:red_sand','minecraft:gravel','minecraft:anvil',
         'minecraft:chipped_anvil','minecraft:damaged_anvil','minecraft:dragon_egg'}


def point(value):
    if not isinstance(value,(list,tuple)) or len(value)!=3 or any(type(v) is not int for v in value):
        raise AccessPlanBlocked('Expected three integer block coordinates')
    return tuple(value)


def state_text(row):
    value=row.get('expected',row.get('state'))
    if not isinstance(value,str) or not value.startswith('Block{') or '}' not in value:
        raise AccessPlanBlocked('Expected an exact Minecraft block-state string')
    return value


def item(state):return state[6:state.index('}')]
def add(p,d):return tuple(a+b for a,b in zip(p,d))
def feet(p):return [p[0]+.5,p[1]+.02,p[2]+.5]


def traversable(row):
    if row.get('passable') is not True or row.get('fluid') or row.get('block_entity'):
        return False
    value=row.get('state','')
    if not isinstance(value,str) or not value.startswith('Block{') or '}' not in value:
        return False
    return item(value) in {'minecraft:'+name for name in
        ('air','cave_air','void_air','short_grass','tall_grass','fern','large_fern',
         'torch','wall_torch','soul_torch','soul_wall_torch')}


class Space:
    def __init__(self,low,high,rows,max_cells):
        self.low,self.high=point(low),point(high)
        if any(a>b for a,b in zip(self.low,self.high)):
            raise AccessPlanBlocked('Invalid scan bounds')
        if math.prod(b-a+1 for a,b in zip(self.low,self.high))>max_cells:
            raise AccessPlanBlocked('Access scan exceeds bounded planning size')
        self.rows={}
        for row in rows:
            p=point(row.get('pos'))
            if p in self.rows or not self.contains(p):raise AccessPlanBlocked('Duplicate or outside scan block')
            self.rows[p]=row
        self.blocked={p for p,row in self.rows.items() if not traversable(row)}
        self.cells={(x,y,z) for x in range(self.low[0],self.high[0]+1)
                    for y in range(self.low[1],self.high[1]) for z in range(self.low[2],self.high[2]+1)}

    def contains(self,p):return all(a<=v<=b for a,v,b in zip(self.low,p,self.high))

    def free(self,blocked):
        return {p for p in self.cells if p not in blocked and add(p,(0,1,0)) not in blocked}

    def boundary(self,p):
        return p[0] in (self.low[0],self.high[0]) or p[2] in (self.low[2],self.high[2]) or p[1]==self.high[1]-1


def flood(free,start):
    if start not in free:return {}
    parent={start:None};queue=deque([start])
    while queue:
        p=queue.popleft()
        for d in DIRECTIONS:
            q=add(p,d)
            if q in free and q not in parent:parent[q]=p;queue.append(q)
    return parent


def components(free):
    unseen=set(free);result=[]
    while unseen:
        group=set(flood(unseen,min(unseen)))
        unseen.difference_update(group);result.append(group)
    return result


def route(parent,end):
    if end not in parent:raise AccessPlanBlocked('No observed two-block-high route')
    path=[]
    while end is not None:path.append(end);end=parent[end]
    path.reverse();turns=[]
    for i,p in enumerate(path):
        if i in (0,len(path)-1) or tuple(p[k]-path[i-1][k] for k in range(3))!=tuple(path[i+1][k]-p[k] for k in range(3)):
            turns.append(feet(p))
    return turns


def candidate_portals(space,expected,component,exterior,targets,start,held):
    highest=max(p[1] for p in targets);result=[]
    for lower,row in space.rows.items():
        upper=add(lower,(0,1,0));upper_row=space.rows.get(upper)
        # Above-layer construction must leave an exit in the final upper room.
        if lower[1]<highest+1 or not upper_row:continue
        positions=(lower,upper)
        if any(p not in expected or state_text(space.rows[p])!=expected[p]
               or item(expected[p]) not in SAFE_SHELL or space.rows[p].get('solid') is not True
               or space.rows[p].get('fluid') or space.rows[p].get('block_entity') for p in positions):continue
        reserve=Counter(item(expected[p]) for p in positions)
        if any(held.get(name,0)<n for name,n in reserve.items()):continue
        support=space.rows.get(add(lower,(0,-1,0)),{})
        if support.get('solid') is not True or support.get('fluid') or support.get('block_entity'):continue
        unsafe=False
        for p in positions:
            for d in DIRECTIONS:
                neighbor=space.rows.get(add(p,d))
                if neighbor and (neighbor.get('fluid') or neighbor.get('block_entity')):unsafe=True
            above=space.rows.get(add(p,(0,1,0)))
            if above and (item(state_text(above)) in GRAVITY or item(state_text(above)).endswith('_concrete_powder')):unsafe=True
        if unsafe:continue
        for dx,_,dz,face in SIDES:
            outside=add(lower,(dx,0,dz));inside=add(lower,(-dx,0,-dz))
            if outside not in exterior or inside not in component:continue
            rank=(sum(SAFE_SHELL.index(item(expected[p])) for p in positions),lower[1]-(highest+1),
                  math.dist(feet(outside),start),lower,face)
            result.append((rank,{'lower':lower,'upper':upper,'outside':outside,'inside':inside,
                                 'outside_face':face,'restore_reserve':dict(reserve)}))
    return [candidate for _,candidate in sorted(result,key=lambda pair:pair[0])]


def plan_access(actual_scan,expected_cells,selection,pending,held,*,start_position=None,max_cells=100000,max_candidates=64):
    """Return a journal-ready doorway and ascending target-layer plan.

    actual_scan requires complete=True, min/max, blocks, world_session and
    observed_at. expected_cells/pending use {pos:[x,y,z], state/expected:exact
    state}. All model coordinates are already world coordinates. held is real
    carried inventory. An unscanned initial approach is explicitly flagged.
    """
    if (actual_scan.get('complete') is not True or not actual_scan.get('world_session')
            or type(actual_scan.get('observed_at')) is not int):
        raise AccessPlanBlocked('A complete, scoped actual scan is required')
    space=Space(actual_scan.get('min'),actual_scan.get('max'),actual_scan.get('blocks',[]),max_cells)
    model_low,model_high=point(selection.get('min')),point(selection.get('max'))
    if not space.contains(model_low) or not space.contains(model_high):raise AccessPlanBlocked('Scan does not cover model bounds')
    expected={}
    for row in expected_cells:
        p=point(row.get('pos'));value=state_text(row)
        if p in expected or not all(model_low[i]<=p[i]<=model_high[i] for i in range(3)):
            raise AccessPlanBlocked('Expected model contains duplicate or outside coordinates')
        expected[p]=value
    target_rows={}
    for row in pending:
        p=point(row.get('pos'));value=state_text(row)
        if expected.get(p)!=value:raise AccessPlanBlocked('Pending target disagrees with the full expected model')
        if p in space.rows and space.rows[p].get('replaceable') is not True:continue
        if held.get(item(value),0)>0:target_rows[p]=value
    if not target_rows:raise AccessPlanBlocked('No carried material matches pending air targets')
    free=space.free(space.blocked);groups=components(free)
    exterior=set().union(*(g for g in groups if any(space.boundary(p) for p in g)))
    enclosed=[g for g in groups if not any(space.boundary(p) for p in g)]
    start=list(start_position if start_position is not None else actual_scan.get('player',[]))
    if len(start)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in start):
        raise AccessPlanBlocked('Finite observed player position is required')
    if not exterior:raise AccessPlanBlocked('No observed external approach space')
    anchor=min(exterior,key=lambda p:math.dist(feet(p),start))
    start_cell=tuple(math.floor(v) for v in start)
    if start_cell in space.cells and start_cell not in exterior:
        raise AccessPlanBlocked('Temporary shell access must start in the external component')
    external_paths=flood(exterior,anchor)
    choices=[]
    for component in enclosed:
        targets={p:state for p,state in target_rows.items() if p in component or add(p,(0,-1,0)) in component}
        if not targets:continue
        counts=Counter(item(state) for state in targets.values())
        if any(held.get(name,0)<amount for name,amount in counts.items()):continue
        portals=candidate_portals(space,expected,component,exterior,targets,start,held)
        for portal in portals[:max_candidates]:choices.append((-len(targets),portal,targets,len(component)))
    if not choices:raise AccessPlanBlocked('No restorable two-block shell portal covers available enclosed targets')
    choices.sort(key=lambda x:x[0]);failures=[]
    for _,portal,targets,size in choices[:max_candidates]:
        blocked=space.blocked-{portal['lower'],portal['upper']};current=portal['outside'];stages=[]
        support_cells={p for p,row in space.rows.items() if row.get('solid') is True
                       and not row.get('fluid') and not row.get('block_entity')}-{portal['lower'],portal['upper']}
        try:
            opening=flood(space.free(blocked),current)
            if portal['inside'] not in opening:raise AccessPlanBlocked('Opening does not connect the intended interior')
            for y in sorted({p[1] for p in targets}):
                layer=sorted(p for p in targets if p[1]==y)
                before_paths=flood(space.free(blocked),current)
                after_blocked=blocked|set(layer);after_free=space.free(after_blocked)
                options=[add(p,(0,1,0)) for p in layer if add(p,(0,1,0)) in before_paths and add(p,(0,1,0)) in after_free]
                if not options:raise AccessPlanBlocked('No above-layer station remains clear after filling this layer')
                station=min(options,key=lambda p:math.dist(feet(p),feet(current)))
                after_paths=flood(after_free,station)
                if portal['outside'] not in after_paths:raise AccessPlanBlocked('Layer completion would seal the actor away from the portal')
                if any(add(p,(0,1,0)) not in after_paths for p in layer):
                    raise AccessPlanBlocked('Some targets have no connected above-layer standing space')
                # Support grows inward from the existing rim. Require every
                # target to join that chain; do not invent floating placements.
                unfilled=set(layer);supported=set(support_cells)
                while unfilled:
                    attached={p for p in unfilled if any(add(p,d) in supported for d in DIRECTIONS)}
                    if not attached:raise AccessPlanBlocked('The layer has unsupported floating targets')
                    supported.update(attached);unfilled.difference_update(attached)
                stages.append({'layer_y':y,'targets':[{'pos':list(p),'expected':targets[p]} for p in layer],
                               'station':feet(station),'path':route(before_paths,station),
                               'exit_path_after_layer':route(after_paths,portal['outside']),
                               'reachable_target_count':len(layer),'side':'above','navigation_min_feet_y':y+1,
                               'exit_preserved':True})
                blocked,current=after_blocked,station
                support_cells.update(layer)
            final_paths=flood(space.free(blocked),current)
            exit_path=route(final_paths,portal['outside'])
            original=[{'pos':list(p),'expected':expected[p],'original_state':state_text(space.rows[p])}
                      for p in (portal['lower'],portal['upper'])]
            return {'schema':1,'kind':'temporary_construction_access','world_session':actual_scan['world_session'],
                    'observed_at':actual_scan['observed_at'],'projection_key':selection.get('key'),
                    'geometry_only':True,'requires_live_revalidation':True,
                    'portal':original,'outside_face':portal['outside_face'],
                    'outside_station':feet(portal['outside']),'inside_station':feet(portal['inside']),
                    'approach_anchor':feet(anchor),'approach_path':route(external_paths,portal['outside']),
                    'unscanned_approach_prefix':start_cell not in exterior,'observed_player':start,
                    'entry_path':route(opening,portal['inside']),
                    'excluded_until_exit':[list(p) for p in (portal['lower'],portal['upper'])],
                    'mine_order':[list(portal['upper']),list(portal['lower'])],
                    'restore_order':[list(portal['lower']),list(portal['upper'])],
                    'restore_reserve':portal['restore_reserve'],'expected_recovered_items':portal['restore_reserve'],
                    'enclosed_component_cells':size,'covered_pending_count':len(targets),
                    'stages':stages,'final_exit_path':exit_path,
                    'restoration_requires_player_outside':True,
                    'limits':['two-grid-cell body approximation','no native raytrace or block-face placement proof',
                              'recheck actual world and actor after every stage before following paths']}
        except AccessPlanBlocked as error:failures.append(str(error))
    raise AccessPlanBlocked('No candidate preserves all phase exits: '+(failures[-1] if failures else 'none'))
