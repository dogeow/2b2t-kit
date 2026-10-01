"""Real, deterministic Kit material worker. It never calls a model or reconnects.

Game recipes come from the running version's JAR. Every mutation is performed
through the existing guarded client bridge; completion uses fresh inventories.
"""
from collections import Counter, deque
from contextlib import contextmanager
import json
import math
import re
from pathlib import Path
import time

from live_snapshot import read_fresh
from material_client import MaterialClient, Handoff, expected_native_revision
from material_plan import inventory_counts, quantities
from projection_material_plan import ProcessingCatalog
from projection_wood import POST_ITEM, POST_RAW, finish_beams, post_work
from recipe_catalog import RecipeCatalog
from safety_interlock import require_unlocked
from kit_runtime.journal import write_json
from material_jobs.protocol import (JobBlocked, JobCancelled, JobPaused, fingerprint,
                                    search_coverage, server_key)
from material_jobs.profile import load as load_profile
from material_jobs.navigation import leave_projection, leave_quarry, local_park, move, outside_station, settled_state
from material_jobs.projection_advice import audit_fingerprint
from material_jobs.projection_supply import direct_air_supply

KIT_SCREENS = {'KitFormScreen', 'KitCollectionScreen', 'KitWorkspaceScreen', 'ClickGuiScreen'}


def _entry_height(cells, x, z, preferred_y):
    """Only dry full-block floors, with an observed two-block body space."""
    for y in (preferred_y, preferred_y-1):
        support=cells.get((x,y-1,z),{})
        if (support.get('solid') is True and support.get('fluid') is False
                and support.get('block_entity') is False
                and all((x,head,z) not in cells for head in (y,y+1))):
            return y
    return None


def _entry_approach_path(rows, target, radius=4):
    """Find nearby open sky connected to the registered first door waypoint."""
    x,z=math.floor(target[0]),math.floor(target[2]);y=math.floor(target[1])
    cells={tuple(row['pos']):row for row in rows}
    heights={(cx,cz):_entry_height(cells,cx,cz,y)
             for cx in range(x-radius,x+radius+1) for cz in range(z-radius,z+radius+1)}
    if heights.get((x,z))!=y:
        raise JobBlocked('登记入口缺少可靠落脚点或身体净空，不能直接接近')
    parents={(x,z):None};queue=deque([(x,z)])
    while queue:
        cell=queue.popleft();height=heights[cell]
        if not any(pos[0]==cell[0] and pos[2]==cell[1] and pos[1]>=height for pos in cells):
            path=[]
            while cell is not None:
                path.append([cell[0]+.5,heights[cell],cell[1]+.5]);cell=parents[cell]
            return path
        for dx,dz in ((0,1),(1,0),(0,-1),(-1,0)):
            nxt=(cell[0]+dx,cell[1]+dz);next_height=heights.get(nxt)
            if nxt in parents or next_height is None or abs(next_height-height)>1:continue
            if next_height!=height and any((cx,max(height,next_height)+2,cz) in cells for cx,cz in (cell,nxt)):
                continue  # Preserve the head room needed for a one-block step.
            parents[nxt]=cell;queue.append(nxt)
    raise JobBlocked('登记入口附近没有经核验的露天接近点；不长距离步行或穿屋檐')


def launch_snapshot(root, request):
    """Wait for a post-click snapshot; starting a fast worker can beat the tick."""
    since=max(request['created_at'],request.get('_context_not_before',0))
    deadline=time.monotonic()+4
    while True:
        state=read_fresh(root)
        if state.get('time',0)>=since:
            return state
        if time.monotonic()>=deadline:
            raise JobPaused('游戏尚未发布本次启动后的状态，请稍后继续')
        time.sleep(.05)


class JobClient(MaterialClient):
    """Add responsive job cancellation without changing other MaterialClients."""
    def __init__(self, owner, *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def raw(self):
        state = super().raw()
        self.owner.latest = state
        self.owner.poll_control()
        return state

    def status(self, *args, **kwargs):
        try:
            return super().status(*args, **kwargs)
        except Handoff as error:
            state = self.owner.latest
            if (self.owner.cleaning and state.get('screen') in KIT_SCREENS
                    and owns_material_state(self, state)):
                return state
            raise JobPaused(str(error)) from error

    def request(self, op, **params):
        # During a user-opened Kit page cleanup may observe and release its own
        # lease, but must not close the page, move, craft or collect anything.
        state = self.raw()
        if state.get('screen') in KIT_SCREENS and (not self.owner.cleaning or op != 'material_job_pause'):
            raise JobPaused('正在查看 Kit 页面，材料动作保持暂停')
        return super().request(op, **params)

    def advise(self, goal, candidates, scene=None, fallback='wait'):
        # Keep base finish/recovery deterministic. Projection supply choices
        # use Backend.advise_projection_supply's separate, audited boundary.
        if fallback not in candidates:
            fallback = next(iter(candidates))
        return {'choice': fallback, 'source': 'local_material_job', 'ai_calls': 0}

    def record_advice_outcome(self, *args, **kwargs):
        pass


def require_scope(state, context, initial=False):
    if not state.get('connected'):
        raise JobPaused('已离开世界，不会自动重连')
    if (server_key(state.get('server')) != server_key(context['server'])
            or state.get('dimension') != context['dimension']
            or state.get('world_session') != context['world_session']):
        raise JobBlocked('世界会话已改变，请在当前世界重新开始任务')
    if state.get('manual_movement'):
        raise JobPaused('玩家接管移动，已让出控制')
    if initial and state.get('control_revision') != context['expected_revision']:
        raise JobPaused('任务启动后控制权发生变化，请重新开始')


def owns_material_state(client, state):
    lease = state.get('supervision_lease') or {}
    if (not state.get('connected') or state.get('world_session') != client.world
            or state.get('manual_movement') or lease.get('kind') != 'materials'
            or lease.get('job_session') != client.task or lease.get('id') != client.heartbeat.id
            or lease.get('world_session') != client.world or lease.get('revision') != state.get('control_revision')):
        return False
    if state.get('control_revision') == client.rev:
        return True
    if state.get('phase') == 'running':
        inflight = getattr(client, 'native_inflight', None)
        if not isinstance(inflight, dict):
            return False
        base, expected = inflight.get('base_revision'), inflight.get('expected_revision')
        rid, op = inflight.get('request_id'), inflight.get('op')
        stop = state.get('control_stop') or {}
        return (state.get('connected') is True and state.get('manual_movement') is False
                and isinstance(stop, dict)
                and not (stop.get('kind') in ('manual', 'emergency') and stop.get('revision') == state.get('control_revision'))
                and type(base) is int and type(expected) is int and type(state.get('control_revision')) is int
                and type(lease.get('revision')) is int and type(inflight.get('request_revision')) is int
                and base == client.rev == inflight['request_revision'] and expected > base
                and isinstance(rid, str) and bool(rid) and rid == client.last == state.get('id') == state.get('last_request')
                and isinstance(op, str) and bool(op) and state.get('op') == op
                and expected == expected_native_revision(op, base) == state['control_revision']
                and inflight.get('world_session') == client.world == state.get('world_session')
                and inflight.get('task_session') == client.task == lease.get('job_session')
                and inflight.get('lease_id') == client.heartbeat.id == lease.get('id')
                and isinstance(inflight.get('server'), str) and bool(inflight['server'])
                and server_key(inflight['server']) == server_key(state.get('server'))
                and isinstance(inflight.get('dimension'), str) and bool(inflight['dimension'])
                and inflight['dimension'] == state.get('dimension'))
    return (client.last is not None and state.get('last_request') == client.last
            and state.get('id') == client.last and state.get('phase') in ('done', 'stopped', 'waiting', 'error'))


def observed_warehouse_stock(rows):
    result = Counter()
    for row in rows:
        count = row.get('count', 0)
        item = row.get('item', '')
        if type(count) is not int or count <= 0 or not item.startswith('minecraft:'):
            continue
        result[item] += count
        if count == 1 and item.endswith('shulker_box'):
            for child in row.get('contains', []):
                n, key = child.get('count', 0), child.get('item', '')
                if type(n) is int and n > 0 and key.startswith('minecraft:'):
                    result[key] += n
    return dict(result)


def observed_packed_stack_sizes(rows, registered):
    """Actual native sizes from Ender stacks and intact boxes, never guessed from counts."""
    if not isinstance(registered,dict):
        raise JobBlocked('登记堆叠上限格式无效')
    sizes=dict(registered)
    if any(type(value) is not int or not 1<=value<=99 for value in sizes.values()):
        raise JobBlocked('登记堆叠上限无效，不能计算末影箱取料容量')
    def observe(row):
        if not isinstance(row,dict) or type(row.get('count')) is not int or row['count']<0:
            raise JobBlocked('末影箱物品数量未确认')
        if not row['count']:return
        item=row.get('item');size=row.get('max_stack')
        if not isinstance(item,str) or not item or item=='minecraft:air':
            raise JobBlocked('末影箱物品身份未确认')
        if size is None:return  # Only an explicit registered size can cover old metadata.
        if type(size) is not int or not 1<=size<=99 or row['count']>size:
            raise JobBlocked('末影箱实际堆叠上限或数量无效')
        if item in sizes and sizes[item]!=size:
            raise JobBlocked('末影箱实际堆叠上限与登记/先前观测冲突：'+item)
        sizes[item]=size
    for row in rows:
        observe(row)
        if row.get('count')==1 and row.get('item','').endswith('shulker_box'):
            children=row.get('contains',[])
            if not isinstance(children,list) or len(children)>27:
                raise JobBlocked('潜影盒内容元数据未确认，不取盒')
            for child in children:observe(child)
    return sizes


def unavailable_registered_source(pos, error):
    """Keep a failed registered source distinct from a verified empty chest."""
    return {'pos': list(pos), 'phase': 'unavailable',
            'reason': 'registered_chest_changed', 'scan_evidence': error.evidence}


def next_sequence(out):
    values = []
    for path in Path(out).iterdir():
        match = re.match(r'^(?:control-)?(\d+)(?:-|$)', path.name)
        if path.is_dir() and match:
            values.append(int(match.group(1)))
    return max(values, default=0)


def split_post_supply(audit, state=None):
    """Keep finished stock for cells the in-place post worker cannot repair."""
    needed=dict(quantities(audit.get('replacement_items',{})))
    posts=None
    if state is not None and needed.get(POST_ITEM):
        posts=post_work(audit,state)
        if posts['eligible']>needed[POST_ITEM]:
            raise JobBlocked('木柱审计可修格数超过差料数；停止补料')
        remaining=needed[POST_ITEM]-posts['eligible']
        if remaining:
            needed[POST_ITEM]=remaining
        else:
            needed.pop(POST_ITEM)
    return needed,posts


def next_build_supply(audit, held, state=None, exclude_items=()):
    needed,posts=split_post_supply(audit,state)
    needed=direct_air_supply(audit,needed,posts)
    if posts and posts['raw_needed']:
        needed[POST_RAW]=needed.get(POST_RAW,0)+posts['raw_needed']
    excluded=set(exclude_items)
    missing=[(count-held.get(item,0),item,count) for item,count in needed.items()
             if item not in excluded and count>held.get(item,0)]
    if not missing:
        return {}
    _,item,count=max(missing)
    batch=(16 if item==POST_RAW and posts and posts['raw_needed']
           else 256 if item.endswith('_concrete') else 128)
    return {item:min(count,held.get(item,0)+batch)}


def clean_for_replan(state, client=None):
    if not state.get('connected') or state.get('manual_movement'):
        return False
    if state.get('phase') not in ('done','stopped','waiting','error'):
        return False
    if any(state.get(k) for k in ('borer_active','chopping','navigating','printing')):
        return False
    if any(state.get(k,{}).get('active') for k in ('gravel','concrete','build_job')):
        return False
    menu = state.get('menu') or {}
    if menu.get('cursor',{}).get('count') != 0:
        return False
    grid = 10 if menu.get('type')=='CraftingMenu' else 5 if menu.get('type')=='InventoryMenu' else 0
    if grid and any(row.get('count') for row in menu.get('slots',[])[1:grid]):
        return False
    if menu.get('type') != 'InventoryMenu' or len(menu.get('slots',[])) < 5:
        return False
    return not client or not getattr(client,'resource_cleanup',{})


class Backend:
    def __init__(self, request, automation, out, checkpoint):
        self.request, self.root, self.out = request, Path(automation), Path(out)
        self.checkpoint = checkpoint
        self.client, self.native_gravel_session = None, None
        self.checking = self.cleaning = self.busy = False
        self.ready, self.last_poll = False, 0
        self.audit, self.audit_dirty = None, True
        self.warehouse_hint = {}
        self.latest = launch_snapshot(self.root,request)
        require_unlocked(self.root, self.latest)
        require_scope(self.latest, request['context'], initial=True)
        if (self.latest.get('material_job_control_protocol',0)<1
                or self.latest.get('air_only_navigation_protocol',0)<2):
            raise JobBlocked('请更新 Kit 主包后再开始材料任务，需要稳定停靠接口')
        if self.latest.get('dimension')!='minecraft:overworld':
            raise JobBlocked('目前材料自动采集只在主世界执行，不会自行进入下界')
        if self.latest.get('screen'):
            raise JobPaused('请关闭物品或设置页面后开始材料任务')
        self.initial_revision = self.latest['control_revision']
        baseline=self.out/'starting-inventory.json'
        if not baseline.exists():
            write_json(baseline,{'world_session':self.latest['world_session'],'counts':dict(inventory_counts(self.latest))})
        saved=json.loads(baseline.read_text())
        if saved.get('world_session')!=self.latest['world_session']:
            raise JobBlocked('初始背包记录属于另一世界会话')
        self.baseline=saved['counts']
        if request.get('_resume'):
            # Manual inventory changes during a pause are the player's items,
            # never newly owned mining byproducts inferred from an old count.
            for item,count in inventory_counts(self.latest).items():
                self.baseline[item]=max(self.baseline.get(item,0),count)
            write_json(baseline,{'world_session':self.latest['world_session'],'counts':self.baseline})
        self.profile = load_profile(self.root, request['context'])
        self.projection_jev_enabled = self.profile['projection_jev_advice']
        self.catalog = ProcessingCatalog(self.profile['recipe_jar'])
        self.crafting_catalog = RecipeCatalog(self.profile['recipe_jar'])
        self.sequence = next_sequence(self.out)
        self.ready = True

    def poll_control(self):
        if not self.ready or self.checking or self.cleaning or time.monotonic()-self.last_poll < .4:
            return
        self.last_poll = time.monotonic()
        self.checking = True
        try:
            self.checkpoint()
            if self.latest.get('screen') in KIT_SCREENS:
                raise JobPaused('正在查看 Kit 页面，任务已暂停；点击继续后恢复')
        finally:
            self.checking = False

    def observe(self):
        state = read_fresh(self.root)
        require_unlocked(self.root, state)
        require_scope(state, self.request['context'])
        self.latest = state
        if (self.request['mode'] == 'projection' and (self.audit is None or self.audit_dirty)
                and not self.checking and not self.busy and not self.cleaning):
            # Travel calls checkpoint directly as well as through raw polling.
            # Suppress re-entry for the whole audit preparation, not just the
            # final scan, while continuing ordinary scope/health observations.
            self.busy=True
            try:
                c = self.ensure_client()
                selection = c.status().get('projection_selection', {})
                if selection.get('key') != self.request['projection_key']:
                    raise JobBlocked('已锁定的投影发生变化')
                if not selection.get('min') or not selection.get('max'):
                    raise JobBlocked('投影范围不可读')
                center = [(selection['min'][i]+selection['max'][i])/2 for i in range(3)]
                # An unloaded audit is never counted as an empty projection.
                if math.hypot(state['pos'][0]-center[0], state['pos'][2]-center[2]) > 96:
                    self.prepare_travel()
                    target = [selection['max'][0]+4.5,
                              max(c.status()['pos'][1], selection['max'][1]+4), center[2]+.5]
                    from material_jobs.acquisition import _travel
                    _travel(c,target,self.checkpoint,[])
                self.refresh_audit()
                state = read_fresh(self.root)
            finally:
                self.busy=False
        state = dict(state, initial_control_revision=self.initial_revision,
                     target_stack_sizes=self.request.get('target_stack_sizes', {}),
                     warehouse_stock_hint=dict(self.warehouse_hint))
        if self.audit is not None:
            state['projection_audit'] = self.audit
        if self.client is not None:
            state['native_task_session'] = self.client.task
        elif self.native_gravel_session:
            state['native_task_session'] = self.native_gravel_session
        self.latest = state
        return state

    def stock(self):
        state = read_fresh(self.root)
        require_scope(state, self.request['context'])
        return dict(inventory_counts(state))

    def experience_state(self):
        from experience_recording import state_for_backend
        return state_for_backend(self)

    def ensure_client(self):
        if self.client is not None:
            return self.client
        state = read_fresh(self.root)
        require_unlocked(self.root, state)
        require_scope(state, self.request['context'])
        self.sequence += 1
        directory = self.out / ('control-%03d' % self.sequence)
        # Choose a nearby high point only after reading the actual column. The
        # default disconnect finish is never used for ordinary completed work.
        park = self.profile.get('park_target')
        if park is None:
            park = [state['pos'][0], min(315, max(100, state['pos'][1]+24)), state['pos'][2]]
        previous = self.busy
        self.busy = True
        try:
            client = JobClient(self, self.root, directory, server=state['server'],
                               record_experience=True, experience_state=self.experience_state(),
                               remote_finish='guard', park_target=park)
            self.client = client
        finally:
            self.busy = previous
        return client

    @contextmanager
    def action(self, name):
        self.checkpoint()
        c = self.ensure_client()
        self.sequence += 1
        out = self.out / ('%04d-%s' % (self.sequence, name))
        out.mkdir(parents=True, exist_ok=True)
        pending=self.out/'inflight.json'
        if pending.exists():
            write_json(self.out/'active-operation.json',{'directory':str(out.resolve()),'name':name,
                       'operation_fingerprint':fingerprint(json.loads(pending.read_text()))})
        self.busy = True
        try:
            yield c, out
        except Handoff as error:
            raise JobPaused(str(error)) from error
        finally:
            self.busy = False

    def refresh_audit(self):
        c = self.ensure_client()
        previous = self.busy
        self.busy = True
        try:
            reply = c.request('projection_audit')
            audit = reply.get('projection_audit', {})
            if (audit.get('placement_key') != self.request['projection_key']
                    or not audit.get('loaded_chunks_verified') or audit.get('kinds', {}).get('unloaded')):
                raise JobBlocked('投影区域尚未完整加载，不能凭旧差料建造')
            self.audit = audit
            self.audit_dirty = False
            write_json(self.out / 'projection-latest.json', audit)
        finally:
            self.busy = previous
        return self.audit

    def advise_projection_supply(self, offer, expected_stock):
        """Rank prechecked material batches without giving Jev a game action.

        The native audit and inventory must agree both before and after the
        bounded model call. If either changes, the worker pauses and replans
        only after an explicit resume. No position or placement key is sent.
        """
        # This is an explicit per-world opt-in. A direct caller cannot bypass
        # the engine gate or spend a model call using a default profile.
        if self.profile.get('projection_jev_advice') is not True:
            return {'choice': offer['fallback'], 'source': 'local',
                    'reason': 'projection_jev_disabled', 'model_call_scheduled': False}
        from decision_advisor import Advisor, safe_to_consult

        c = self.ensure_client()
        key = self.request['projection_key']
        fingerprint_before = offer['audit_fingerprint']

        def current_fingerprint():
            audit = self.refresh_audit()
            observed = audit.get('observed_at')
            if (type(observed) is not int
                    or not -1000 <= time.time() * 1000 - observed <= 5000):
                raise JobPaused('投影审计不是当前现场，请重新规划')
            try:
                targets = dict(quantities(audit['replacement_items']))
            except (KeyError, TypeError, ValueError) as error:
                raise JobPaused('投影差料已改变，请重新规划') from error
            return audit_fingerprint(audit, key, targets)

        def current_state():
            state = read_fresh(self.root, wait_seconds=.25)
            require_unlocked(self.root, state)
            require_scope(state, self.request['context'])
            if (not owns_material_state(c, state)
                    or (state.get('projection_selection') or {}).get('key') != key):
                raise JobPaused('材料控制权或选定投影已改变，请重新规划')
            return state

        if current_fingerprint() != fingerprint_before:
            raise JobPaused('投影差料在建议前已改变，请重新规划')
        if dict(inventory_counts(current_state())) != expected_stock:
            raise JobPaused('背包在建议前已改变，请重新规划')
        if not hasattr(self, 'projection_advisor'):
            self.projection_advisor = Advisor(self.out)
        decision = self.projection_advisor.select(
            'Choose one useful next material batch for the selected projection; native planning and safety gates decide all execution.',
            offer['choices'], current_state, offer['scene'], offer['fallback'])
        fresh_fingerprint = current_fingerprint()
        fresh_state = current_state()
        if (fresh_fingerprint != fingerprint_before
                or dict(inventory_counts(fresh_state)) != expected_stock
                or not safe_to_consult(fresh_state)):
            self.projection_advisor.outcome(decision, 'discarded_changed_audit_or_stock',
                                            audit_fingerprint=fingerprint_before)
            raise JobPaused('投影或背包在建议期间已改变，请重新规划')
        self.projection_advisor.outcome(decision, 'selected_for_local_material_plan',
                                        audit_fingerprint=fingerprint_before)
        return decision

    def record_projection_advice_outcome(self, decision, result, **evidence):
        if hasattr(self, 'projection_advisor'):
            self.projection_advisor.outcome(decision, result, **evidence)

    def close_owned_menu(self):
        c = self.client
        if c is None:
            return
        from craft_recovery import clear_owned_workbench
        inventory_owned = getattr(c, 'owned_inventory_crafting', None)
        recovered = clear_owned_workbench(c)
        if inventory_owned and not recovered:
            if c.status().get('screen'):
                raise JobPaused('玩家物品界面已打开，保留背包合成现场并交还控制')
            raise RuntimeError('Owned inventory crafting recovery is unavailable; no movement permitted')
        state = c.status()
        menu = state.get('menu', {})
        if state.get('screen'):
            if menu.get('id') != c.owned_material_menu or menu.get('cursor', {}).get('count'):
                raise JobPaused('物品界面不属于当前任务，保留现场')
            c.checked('close_menu')

    def prepare_travel(self):
        self.close_owned_menu()
        c=self.ensure_client()
        from material_jobs.construction_access import recover_pending
        recover_pending(self)
        leave_quarry(c,self.out/'acquisition')
        leave_projection(c)

    def stage_near_base(self, positions):
        """Cruise back into local interaction range after a remote resource trip."""
        if not positions:
            return
        c=self.ensure_client();p=c.status()['pos']
        nearest=min(positions,key=lambda v:math.dist(p,v))
        if math.dist(p,nearest)<=48:
            return
        staging=self.profile.get('supply_staging') or self.profile.get('workbench_staging')
        if staging is None:
            raise JobBlocked('远程返回仓库或工位需要登记室外接近点')
        from material_jobs.acquisition import _travel
        _travel(c,staging,self.checkpoint,[])

    def fetch(self, targets):
        with self.action('fetch') as (c, out):
            if all(self.stock().get(i, 0) >= n for i, n in targets.items()):
                return {'phase': 'done', 'detail': '背包已有所需材料'}
            self.prepare_travel()
            self.stage_near_base(self.profile['depots'])
            ready=self.finished_supply_pass(c,out,targets) if self.request['mode']=='projection' else None
            if ready is not None and ready['ready_for_build']:
                # Useful finished output is now physically carried. Do not
                # continue to Ender/raw ingredient errands before using it.
                return ready
            visited = []
            unavailable = list(ready.get('unavailable_sources', [])) if ready is not None else []
            for pos in ([] if ready is not None else self.profile['depots']):
                from construction_materials import supply_targets
                from container_access import OutdoorChestChanged, open_grounded_chest, verify_opened_chest
                self.checkpoint()
                held = self.stock()
                missing = {i:n for i,n in targets.items() if held.get(i,0) < n}
                if not missing:
                    break
                # Verify the actual chest and clear landing column. A recorded
                # indoor/obstructed position cannot authorize a blind approach.
                try:
                    state = open_grounded_chest(c, list(pos), allow_empty=True)
                except OutdoorChestChanged as error:
                    entry = unavailable_registered_source(pos, error)
                    visited.append(entry)
                    unavailable.append(list(pos))
                    write_json(out/'sources.json', visited)
                    continue
                menu_id = (state.get('menu') or {}).get('id')
                if menu_id is None or menu_id != c.owned_material_menu:
                    raise JobBlocked('仓库取料的容器归属未确认，不发送取料动作')

                entry = {'pos':list(pos), 'requested':{}, 'provided':{}, 'phase':'waiting'}
                visited.append(entry)
                write_json(out/'sources.json', visited)

                def observed():
                    try:
                        verify_opened_chest(c, state.get('_verified_chest'))
                    except OutdoorChestChanged as error:
                        entry.update(phase='blocked', reason='opened_chest_changed',
                                     scan_evidence=error.evidence)
                        write_json(out/'sources.json', visited)
                        raise JobBlocked('仓库取料中登记箱已变化，停止取料') from error
                    fresh = c.status()
                    menu = fresh.get('menu') or {}
                    rows = menu.get('slots', [])
                    if (menu.get('id') != menu_id or menu.get('type') != 'ChestMenu'
                            or len(rows) not in (63, 90) or menu.get('cursor', {}).get('count') != 0
                            or menu_id != c.owned_material_menu):
                        raise JobBlocked('仓库取料中容器或光标已变化，不重复取料')
                    stored, sizes = Counter(), {}
                    registry = self.request.get('target_stack_sizes', {})
                    for row in rows[:-36]:
                        count, item = row.get('count'), row.get('item')
                        if type(count) is not int or count < 0 or not isinstance(item, str):
                            raise JobBlocked('仓库物品数量未确认')
                        if not count:
                            continue
                        stored[item] += count
                        size = row.get('max_stack', registry.get(item))
                        if type(size) is not int or not 1 <= size <= 99 or count > size:
                            if item in missing:
                                raise JobBlocked('仓库目标物品的堆叠上限未确认：' + item)
                            continue
                        if (item in sizes and sizes[item] != size
                                or item in registry and registry[item] != size):
                            raise JobBlocked('仓库目标物品的堆叠上限冲突：' + item)
                        sizes[item] = size
                    return fresh, stored, sizes

                initial, stored, sizes = observed()
                selected = supply_targets(initial, missing, stored, reserve_empty=1, stack_sizes=sizes)
                for item, planned_target in selected.items():
                    fresh, source, sizes = observed()
                    # Recheck capacity after each transfer in case another
                    # module changed inventory; never spend the work slot.
                    target = supply_targets(fresh, {item:planned_target}, source,
                                            reserve_empty=1, stack_sizes=sizes).get(item)
                    if target is None:
                        continue
                    held = inventory_counts(fresh).get(item, 0)
                    entry['requested'][item] = target
                    write_json(out/'sources.json', visited)
                    c.transfer(item, target)
                    after, remaining, _ = observed()
                    gain = inventory_counts(after).get(item, 0) - held
                    if gain != target - held or source.get(item, 0) - remaining.get(item, 0) != gain:
                        raise JobBlocked('仓库出箱数量与背包增量未确认，不重复取料')
                    entry['provided'][item] = gain
                    entry['phase'] = 'done'
                self.close_owned_menu()
                write_json(out/'sources.json', visited)
            packed_receipt=self.fetch_packed(targets)
            held = self.stock()
            missing = {i:n-held.get(i,0) for i,n in targets.items() if held.get(i,0)<n}
            if isinstance(packed_receipt,dict) and packed_receipt.get('phase')=='waiting':
                return {**packed_receipt,'missing':missing,'unavailable_sources':unavailable}
            all_unavailable = bool(unavailable) and len(unavailable) == len(self.profile['depots'])
            detail = ('登记仓库均已失效，现场扫描已记录' if all_unavailable else
                      '仓库现货已核对，部分登记箱失效' if unavailable else '仓库现货已核对')
            return {'phase':'waiting' if missing else 'done', 'detail':detail,
                    'missing':missing, 'unavailable_sources':unavailable}

    def finished_supply_pass(self,c,out,targets):
        """Once per observed projection deficit, fill with real finished stock.

        Recorded warehouse hints choose recipes only. This path opens approved
        outdoor depots and checks source loss and backpack gain before credit.
        """
        from construction_materials import supply_targets
        from container_access import OutdoorChestChanged, open_grounded_chest, verify_opened_chest
        audit=self.audit if self.audit is not None and not self.audit_dirty else self.refresh_audit()
        key=self.request['projection_key']
        if (audit.get('placement_key')!=key or not audit.get('loaded_chunks_verified')
                or audit.get('kinds',{}).get('unloaded')):
            raise JobBlocked('当前投影缺料尚未完整核验，不能按旧记录批量取料')
        # The in-place worker supplies only repairable vertical cells. Finished
        # stock remains useful for other axes and occupied cells.
        needed,posts=split_post_supply(audit,c.status())
        # Opportunistic stock may only occupy backpack slots when the fresh,
        # complete audit proves it can be placed into an empty dry cell now.
        # Occupied terrain and state-only repairs stay in their source chest.
        needed=direct_air_supply(audit,needed,posts)
        token=fingerprint({'world_session':c.world,'projection_key':key,'needed':needed})
        record_path=self.out/'finished-supply-pass.json'
        if record_path.is_file():
            previous=json.loads(record_path.read_text())
            if previous.get('token')==token and previous.get('complete') is True:
                return None
        before=dict(inventory_counts(c.status()));credited=Counter();visited=[];unavailable=[]
        record={'schema':1,'token':token,'world_session':c.world,'projection_key':key,
                'needed':needed,'before':before,'visited':visited,'complete':False}
        write_json(record_path,record)
        for pos in self.profile['depots']:
            self.checkpoint()
            try:
                state=open_grounded_chest(c,list(pos),allow_empty=True)
            except OutdoorChestChanged as error:
                visited.append(unavailable_registered_source(pos,error))
                unavailable.append(list(pos))
                write_json(record_path,record)
                continue
            menu=state.get('menu') or {}
            if (menu.get('type')!='ChestMenu' or len(menu.get('slots',[])) not in (63,90)
                    or menu.get('cursor',{}).get('count')!=0 or menu.get('id')!=c.owned_material_menu):
                raise JobBlocked('现货补料的箱子或光标状态未确认，不发送新的取料动作')
            menu_id=menu['id'];entry={'pos':list(pos),'provided_finished':{},'requested':{}}
            visited.append(entry);write_json(record_path,record)
            def observed():
                try:
                    verify_opened_chest(c, state.get('_verified_chest'))
                except OutdoorChestChanged as error:
                    entry.update(phase='blocked', reason='opened_chest_changed',
                                 scan_evidence=error.evidence)
                    write_json(record_path,record)
                    raise JobBlocked('现货补料中登记箱已变化，停止取料') from error
                fresh=c.status();current=fresh.get('menu') or {}
                if (current.get('id')!=menu_id or current.get('type')!='ChestMenu'
                        or current.get('cursor',{}).get('count')!=0):
                    raise JobBlocked('现货补料中容器已变化，停止取料')
                rows=current['slots'][:-36]
                stored=Counter()
                for row in rows:
                    if row.get('count',0)>0:stored[row['item']]+=row['count']
                sizes={row['item']:row['max_stack'] for row in rows
                       if row.get('count',0)>0 and type(row.get('max_stack')) is int}
                return fresh,stored,{**self.request.get('target_stack_sizes',{}),**sizes}
            # Finished building blocks are filled first. The helper accounts
            # for partial stacks and reserves one completely empty work slot.
            for requested,is_finished in ((needed,True),(targets,False)):
                fresh,stored,sizes=observed()
                selected=supply_targets(fresh,requested,stored,reserve_empty=1,stack_sizes=sizes)
                for item,target in selected.items():
                    initial,source,_=observed();held=inventory_counts(initial).get(item,0)
                    if target<=held:continue
                    entry['requested'][item]=target
                    c.transfer(item,target)
                    after,remaining,_=observed();gain=inventory_counts(after).get(item,0)-held
                    if gain<0 or gain>target-held or source.get(item,0)-remaining.get(item,0)!=gain:
                        raise JobBlocked('现货出箱数量与背包增量不一致，不重复取料')
                    if is_finished and gain:
                        credited[item]+=gain;entry['provided_finished'][item]=entry['provided_finished'].get(item,0)+gain
                if credited:
                    # A ready construction batch takes precedence over raw
                    # inputs for the previously selected material chain.
                    break
            self.close_owned_menu()
            entry['phase']='done';write_json(record_path,record)
        after=dict(inventory_counts(c.status()))
        provided={item:min(count,max(0,after.get(item,0)-before.get(item,0)))
                  for item,count in credited.items() if after.get(item,0)>before.get(item,0)}
        record.update(complete=not unavailable,after=after,provided_finished=provided,
                      unavailable_sources=unavailable)
        write_json(record_path,record);write_json(Path(out)/'finished-supply.json',record)
        missing={item:amount-after.get(item,0) for item,amount in targets.items() if after.get(item,0)<amount}
        all_unavailable=bool(unavailable) and len(unavailable)==len(self.profile['depots'])
        detail=('已核对本轮现货，优先施工' if provided else
                '登记仓库均已失效，现场扫描已记录' if all_unavailable else
                '本轮批准仓库现货已核对，部分登记箱失效' if unavailable else '本轮批准仓库现货已核对')
        return {'phase':'waiting' if missing else 'done','detail':detail,
                'missing':missing,'ready_for_build':bool(provided),'provided_finished':provided,
                'unavailable_sources':unavailable,'projection_key':key}

    def fetch_packed(self, targets):
        if not self.profile.get('ender_chest') or not self.profile.get('shulker_pad'):
            return
        from packed_supplies import (choose_box, open_box, take_box, REQUIRED_FREE_SLOTS,
                                     workspace_requirement, PackedWorkspaceRequired)
        from construction_materials import supply_targets
        c = self.ensure_client()
        for _ in range(27):
            held = self.stock()
            if all(held.get(i,0)>=n for i,n in targets.items()):
                return
            state = open_box(c, self.profile['ender_chest'], 'ChestMenu')
            self.warehouse_hint = observed_warehouse_stock(state['menu']['slots'][:-36])
            # Loose items are ordinary inventory transfers; intact shulkers use
            # the existing place/recover/return journal and exact conservation.
            loose=Counter()
            packed=Counter()
            sizes=observed_packed_stack_sizes(state['menu']['slots'][:-36],
                                              self.request.get('target_stack_sizes',{}))
            for row in state['menu']['slots'][:-36]:
                if row.get('count',0)>0:
                    loose[row['item']]+=row['count']
                    if row.get('count')==1 and row.get('item','').endswith('shulker_box'):
                        for child in row.get('contains',[]):
                            if child.get('count',0)>0:packed[child['item']]+=child['count']
            held=inventory_counts(state)
            needs_box=any(n>held.get(i,0)+loose.get(i,0) and packed.get(i,0)>0 for i,n in targets.items())
            # Loose stock must not spend the admission slots if this same
            # fetch still needs an observed portable box afterwards.
            reserve=REQUIRED_FREE_SLOTS if needs_box else 1
            for item,target in supply_targets(state,targets,loose,reserve_empty=reserve,stack_sizes=sizes).items():
                c.transfer(item,target)
            state = c.status()
            self.warehouse_hint = observed_warehouse_stock(state['menu']['slots'][:-36])
            packed=Counter()
            for box in state['menu']['slots'][:-36]:
                if box.get('count')==1 and box.get('item','').endswith('shulker_box'):
                    for row in box.get('contains',[]):
                        if row.get('count',0)>0:packed[row['item']]+=row['count']
            # First enforce take_box's actual admission requirement, including
            # targets that would otherwise fit into an existing partial stack.
            sizes=observed_packed_stack_sizes(state['menu']['slots'][:-36],sizes)
            unknown=sorted(item for item,count in targets.items()
                           if count>inventory_counts(state).get(item,0) and packed.get(item,0)>0 and item not in sizes)
            if unknown:
                c.checked('close_menu')
                return {'phase':'waiting','code':'packed_stack_metadata_unknown','items':unknown,
                        'detail':'潜影盒内目标物品堆叠上限尚未实际观测，不猜容量或取盒'}
            needed=choose_box(state['menu']['slots'][:-36],targets,inventory_counts(state))
            space=workspace_requirement(state) if needed is not None else None
            if space:
                c.checked('close_menu')
                return space
            # Placing the carried box frees one of the admission slots. Keep
            # the other two for recovery and workspace throughout withdrawal.
            safe_targets=supply_targets(state,targets,packed,reserve_empty=REQUIRED_FREE_SLOTS-1,stack_sizes=sizes)
            choice = choose_box(state['menu']['slots'][:-36], safe_targets, self.stock())
            c.checked('close_menu')
            if choice is None:
                return
            space=workspace_requirement(c.status())
            if space:
                return space
            before = self.stock()
            try:
                take_box(c,self.profile['ender_chest'],self.profile['shulker_pad'],choice[1],safe_targets)
            except PackedWorkspaceRequired as error:
                # This typed failure occurs before pickup/journal mutation.
                # Never translate a later ambiguous transfer into a retry.
                return error.receipt
            after = self.stock()
            for item, amount in after.items():
                withdrawn = max(0, amount-before.get(item,0))
                if withdrawn:
                    self.warehouse_hint[item] = max(0,self.warehouse_hint.get(item,0)-withdrawn)
            if after==before:
                return

    def craft(self, targets):
        with self.action('craft') as (c, out):
            from goal_workflow import open_workbench
            from material_manufacture import manufacture, inventory_plan
            current = c.status()
            if inventory_plan(self.crafting_catalog, targets, inventory_counts(current)) is not None:
                if current.get('screen') or current.get('menu', {}).get('type') != 'InventoryMenu':
                    raise JobPaused('背包合成等待当前物品界面由玩家关闭，不接管或关闭玩家界面')
                if current.get('inventory_cursor_precondition_protocol',0)<1:
                    raise JobPaused('背包合成需要支持光标前置核验的新主包；未发送物品点击')
                # Quarry drops can arrive after a native pickup and join its
                # cursor. Exit the proved shaft before binding the menu-0
                # crafting preflight, then re-plan from the fresh inventory.
                self.prepare_travel()
                current = c.status()
                if (current.get('screen') or current.get('menu', {}).get('type') != 'InventoryMenu'
                        or inventory_plan(self.crafting_catalog, targets,
                                          inventory_counts(current)) is None):
                    raise JobPaused('离开采坑后背包或合成物料已变化，请按新现物重新规划')
                result = manufacture(c, self.crafting_catalog, targets)
                write_json(out/'result.json', result)
                return {'phase':'done' if result['complete'] else 'waiting',
                        'detail':'2×2背包合成结果已核对，无需前往工作台', 'crafting_location':'inventory', **result}
            self.prepare_travel()
            pos = self.profile.get('workbench')
            if not pos:
                return {'phase':'blocked','detail':'需要在材料工位中登记工作台'}
            entry=next((step['target'] for step in self.profile.get('workbench_entry',[]) if step.get('kind')=='walk'),None)
            if entry and math.dist(c.status()['pos'],entry)>28:
                staging=self.profile.get('workbench_staging')
                if not staging:
                    raise JobBlocked('远程返回工作台需要登记室外接近点，不能直接发送超范围步行')
                from material_jobs.acquisition import _travel
                _travel(c,staging,self.checkpoint,[])
            self.route('workbench_entry')
            open_workbench(c,pos)
            result = manufacture(c,self.crafting_catalog,targets)
            self.close_owned_menu()
            # The crafted stock is already verified. Preserve its receipt even
            # if the subsequent door exit cannot be confirmed.
            write_json(out/'result.json',result)
            self.route('workbench_exit')
            return {'phase':'done' if result['complete'] else 'waiting', 'detail':'合成结果已核对', **result}

    def make_room(self, targets, keep_items):
        """Deposit only this job's newly acquired mining byproducts, never gear."""
        from material_depots import exchange
        safe={'minecraft:'+name for name in ('stone','cobblestone','cobbled_deepslate','deepslate',
            'dirt','coarse_dirt','rooted_dirt','gravel','sand','red_sand','flint','granite','andesite','diorite',
            'tuff','calcite','dripstone_block','raw_iron','raw_iron_block','raw_copper','raw_gold','coal','redstone','lapis_lazuli')}
        keep=set(keep_items)|set(targets)

        def preflight():
            # Reading stock must precede acquiring a controller/lease: an
            # impossible new item job must not travel and then log out while
            # trying to park underground during an unnecessary cleanup.
            state=read_fresh(self.root)
            require_unlocked(self.root,state);require_scope(state,self.request['context'])
            rows=[r for r in state.get('inventory',[]) if 0<=r.get('slot',-1)<36]
            if len(rows)!=36 or len({r['slot'] for r in rows})!=36:
                return {},{},{'phase':'blocked','code':'capacity_observation_incomplete',
                              'detail':'完整背包容量尚未确认，未开始卸货或移动'}
            before=dict(inventory_counts(state))
            deposit={item:self.baseline.get(item,0) for item,n in before.items()
                     if item in safe and item not in keep and n>self.baseline.get(item,0)}
            free=sum(not r.get('count') for r in rows)
            freed=0
            for item,baseline in deposit.items():
                occupied=[r for r in rows if r.get('item')==item and r.get('count')]
                sizes={r.get('max_stack') for r in occupied}
                if len(sizes)==1 and type(next(iter(sizes))) is int and 1<=next(iter(sizes))<=99:
                    freed+=max(0,len(occupied)-math.ceil(baseline/next(iter(sizes))))
            capacity={};after_deposit={}
            for item in targets:
                sizes={r.get('max_stack') for r in rows if r.get('item')==item and r.get('count')}
                registered=self.request.get('target_stack_sizes',{}).get(item)
                if registered is not None:sizes.add(registered)
                size=next(iter(sizes)) if len(sizes)==1 else None
                if type(size) is not int or not 1<=size<=99:
                    capacity[item]=None;after_deposit[item]=None;continue
                occupied=sum(bool(r.get('count')) and r.get('item')==item for r in rows)
                capacity[item]=(free+occupied)*size
                # Recipe inputs are kept in the backpack during unloading,
                # but may eventually be consumed into this target's output.
                convertible=sum(bool(r.get('count')) and r.get('item') in keep-set(targets) for r in rows)
                after_deposit[item]=min(36,free+occupied+freed+convertible)*size
            info={'held':{i:before.get(i,0) for i in targets},'capacity':capacity,
                  'capacity_after_owned_deposit':after_deposit,'free_slots':free,'targets':dict(targets)}
            detail='；'.join(f'{(i+"：") if len(targets)>1 else ""}目标 {n}，已持有 {before.get(i,0)}，当前可容纳 {capacity[i] if capacity[i] is not None else "未确认"}'
                            for i,n in targets.items())+f'（空槽 {free}）'
            if not deposit:
                return before,deposit,{'phase':'blocked','code':'no_owned_byproducts',**info,
                    'detail':detail+'；没有可自动存放的本任务副产物，原有物品、工具和配方原料会保留。请腾出位置或另开较小目标'}
            if self.request['mode']=='item' and any(after_deposit[i] is not None and n>after_deposit[i] for i,n in targets.items()):
                return before,deposit,{'phase':'blocked','code':'target_exceeds_safe_capacity',**info,
                    'detail':detail+'；即使卸下本任务副产物仍装不下目标，未开始卸货或移动。请腾出位置或另开较小目标'}
            return before,deposit,None

        _,_,blocked=preflight()
        if blocked:
            return blocked
        with self.action('make_room') as (c,out):
            self.prepare_travel()
            self.stage_near_base(self.profile['depots'])
            before,deposit,blocked=preflight()
            if blocked:
                return blocked
            result=exchange(c,self.profile['depots'],deposit=deposit)
            write_json(out/'stored-byproducts.json',result)
            after=self.stock()
            stored={i:before[i]-after.get(i,0) for i in deposit if before[i]>after.get(i,0)}
            return {'phase':'done' if stored else 'blocked',
                    'detail':'采集副产物已存入登记仓库' if stored else '仓库没有剩余空间',
                    'stored':stored}

    def approach_route_entry(self, target):
        """Fly only to nearby verified open sky, then walk short checked steps."""
        from material_jobs.navigation import _air_scan, _body_sweep
        from material_jobs.acquisition import _travel
        from material_jobs.profile import point
        if not point(target) or not -62<=target[1]<=315:
            raise JobBlocked('登记入口坐标无效')
        c=self.ensure_client();current=c.status()['pos']
        if math.dist(current,target)<=2:
            return
        if math.hypot(current[0]-target[0],current[2]-target[2])<=2.25 and abs(current[1]-target[1])<=1:
            # A nearby one-block doorstep needs an ordinary ground step, not
            # an air detour into the eaves. Check the entire swept footprint,
            # including intervening support and the extra jumping headroom.
            self.checkpoint()
            low,high=_body_sweep(current,target)
            low[1]=min(math.floor(current[1]+1e-6),math.floor(target[1]))-1
            high[1]=max(math.floor(current[1]+1e-6),math.floor(target[1]))+2
            observed=_air_scan(c,low,high);cells={tuple(row['pos']):row for row in observed}
            preferred=max(math.floor(current[1]+.25),math.floor(target[1]))
            heights={(x,z):_entry_height(cells,x,z,preferred)
                     for x in range(low[0],high[0]+1) for z in range(low[2],high[2]+1)}
            start_y=heights.get((math.floor(current[0]),math.floor(current[2])))
            target_y=heights.get((math.floor(target[0]),math.floor(target[2])))
            if (any(height is None for height in heights.values()) or start_y is None
                    or abs(current[1]-start_y)>.25 or target_y!=target[1]
                    or max(heights.values())-min(heights.values())>1):
                raise JobBlocked('近距离入口台阶缺少完整干燥支撑或两格净空，保持当前位置')
            walk_y=max(heights.values());ceiling=walk_y+(2 if min(heights.values())!=walk_y else 1)
            if any(walk_y<=row['pos'][1]<=ceiling for row in observed):
                raise JobBlocked('近距离入口台阶的身体扫掠或跳跃净空出现障碍，不改为空中绕行')
            self.checkpoint()
            if math.dist(c.status()['pos'],current)>.15:
                raise JobBlocked('入口台阶核验后实际位置已改变，未发送步行')
            c.checked('walk',target=target,arrival=.3,restore_flight=False,seconds=12)
            actual=c.status()['pos']
            if math.dist(actual,target)>.65 or abs(actual[1]-target[1])>.45:
                raise JobBlocked('近距离入口台阶实际到点未确认，不继续工位路线')
            return
        x,z=math.floor(target[0]),math.floor(target[2]);y=math.floor(target[1])
        self.checkpoint()
        rows=_air_scan(c,[x-4,y-2,z-4],[x+4,319,z+4])
        path=_entry_approach_path(rows,target)
        _travel(c,path[0],self.checkpoint,[])
        for waypoint in path[1:]:
            self.checkpoint();current=c.status()['pos']
            if math.dist(current,waypoint)>.15:
                if math.hypot(current[0]-waypoint[0],current[2]-waypoint[2])>1.8 or abs(current[1]-waypoint[1])>1.25:
                    raise JobBlocked('室外接近后的实际位置偏离短步行路径，停止入门')
                low,high=_body_sweep(current,waypoint);low[1]=min(math.floor(current[1]+1e-6),int(waypoint[1]))-1
                high[1]=max(math.floor(current[1]+1e-6),int(waypoint[1]))+2
                observed=_air_scan(c,low,high);cells={tuple(row['pos']):row for row in observed}
                sx,sz=math.floor(current[0]),math.floor(current[2]);tx,tz=math.floor(waypoint[0]),math.floor(waypoint[2])
                start_y=_entry_height(cells,sx,sz,math.floor(current[1]+.25))
                target_y=_entry_height(cells,tx,tz,int(waypoint[1]))
                if start_y is None or target_y!=waypoint[1] or abs(start_y-target_y)>1:
                    raise JobBlocked('入口短步行的地面或净空改变，保持当前位置')
                walk_y=max(start_y,target_y)
                ceiling=walk_y+(2 if start_y!=target_y else 1)
                if any(walk_y<=row['pos'][1]<=ceiling for row in observed):
                    raise JobBlocked('入口短步行身体通道出现障碍，保持当前位置')
                c.checked('walk',target=waypoint,arrival=.3,restore_flight=False,seconds=12)
                actual=c.status()['pos']
                if math.dist(actual,waypoint)>.65 or abs(actual[1]-waypoint[1])>.45:
                    raise JobBlocked('入口短步行实际位置未确认，不继续进入房屋')
        if math.dist(c.status()['pos'],target)>1:
            raise JobBlocked('尚未抵达登记门口，不启动室内工位路线')

    def route(self, name):
        """Optional verified door/waypoint route, stored as per-base data."""
        c = self.ensure_client()
        for index,step in enumerate(self.profile.get(name, [])):
            self.checkpoint()
            if step.get('kind')=='walk':
                if index==0 and name.endswith('_entry'):
                    self.approach_route_entry(step['target'])
                    if math.dist(c.status()['pos'],step['target'])<=.4:continue
                c.checked('walk',target=step['target'],arrival=.4,restore_flight=False,seconds=45)
            elif step.get('kind')=='door':
                self.route_door(c,step)
            else:
                raise JobBlocked('工位路线包含不支持的动作')

    def route_door(self, c, step):
        """Approach one registered door face before one state-checked toggle."""
        from door_access import WOOD_DOORS
        from projection_completion import block_state
        pos,face,item=step.get('pos'),step.get('face'),step.get('item')
        if (not isinstance(pos,list) or len(pos)!=3 or any(type(v) is not int for v in pos)
                or face not in ('north','south','east','west','up','down')
                or item not in WOOD_DOORS or type(step.get('open',True)) is not bool):
            raise JobBlocked('登记门的坐标、门面或状态无效')

        def observed():
            reply=c.request('scan',min=pos,max=pos,details=True)
            if (reply.get('phase') not in (None,'done') or reply.get('world_session')!=c.world
                    or not isinstance(reply.get('blocks'),list) or len(reply['blocks'])!=1
                    or reply['blocks'][0].get('pos')!=pos):
                raise JobBlocked('登记门的最新扫描未完整确认，保留现场')
            row=reply['blocks'][0]
            try:
                name,properties=block_state(row['state'])
            except (KeyError,TypeError,ValueError) as error:
                raise JobBlocked('登记门状态无法解析，保留现场') from error
            if (name!=item or properties.get('half')!='lower'
                    or properties.get('powered')!='false'
                    or properties.get('open') not in ('true','false') or row.get('fluid') is not False):
                raise JobBlocked('已登记的门改变了，保留现场')
            return row,properties

        row,properties=observed()
        wanted='true' if step.get('open',True) else 'false'
        if properties['open']==wanted:
            return
        current=c.status()['pos']
        if math.dist(current,[v+.5 for v in pos])>12:
            raise JobBlocked('登记门超出本地接近范围，停止门交互')
        # The native approach checks a visible face and a collision-free path.
        # A failed or uncertain approach never authorizes an interaction.
        c.checked('approach_block',pos=pos,face=face,expected_state=row['state'],
                  stand_distance=3,seconds=45)
        self.checkpoint()
        if math.dist(c.status()['pos'],[v+.5 for v in pos])>4.5:
            raise JobBlocked('登记门接近后的实际位置未确认，不发送门交互')
        fresh,_=observed()
        if fresh['state']!=row['state']:
            raise JobBlocked('接近时登记门状态改变，保留现场；不重复开关')
        c.checked('select_item',item='minecraft:diamond_sword')
        fresh,_=observed()
        if fresh['state']!=row['state']:
            raise JobBlocked('门交互前状态改变，保留现场；不重复开关')
        # The native interaction verifies reach and visibility again after
        # rotation. Its result may be ambiguous, so never resend this toggle.
        c.checked('interact',pos=pos,face=face,expected_state=fresh['state'],
                  expected_hand='minecraft:diamond_sword')
        deadline=time.monotonic()+2
        while True:
            after,after_properties=observed()
            if {key:value for key,value in after_properties.items() if key!='open'} != {
                    key:value for key,value in properties.items() if key!='open'}:
                raise JobBlocked('交互后登记门其他属性改变，保留现场；不重复开关')
            if after_properties['open']==wanted:
                return
            if after['state']!=row['state'] or time.monotonic()>=deadline:
                raise JobBlocked('门状态没有得到服务器确认；不重复开关')
            time.sleep(.1)

    def acquire(self, item, count):
        from material_jobs.snow_harvest import PRODUCTS as SNOW_PRODUCTS
        if item=='minecraft:raw_iron_block':
            state=read_fresh(self.root)
            require_unlocked(self.root,state)
            require_scope(state,self.request['context'])
            self.latest=state
            if (type(state.get('raw_iron_block_quarry_protocol')) is not int
                    or state['raw_iron_block_quarry_protocol']<1):
                return {'phase':'blocked',
                        'detail':'当前 Kit 主包缺少天然粗铁块采坑核验；未移动或整理装备，请先更新主包'}
        if item in SNOW_PRODUCTS:
            state=read_fresh(self.root)
            require_unlocked(self.root,state)
            require_scope(state,self.request['context'])
            self.latest=state
            if (type(state.get('snow_harvest_protocol')) is not int
                    or state['snow_harvest_protocol']<1):
                return {'phase':'blocked','detail':'当前 Kit 主包缺少雪地采集工具锁；请先更新主包'}
            if (type(state.get('snow_biome_survey_protocol')) is not int
                    or state['snow_biome_survey_protocol']<1):
                return {'phase':'blocked',
                        'detail':'当前 Kit 主包缺少雪地群系粗筛接口；未移动角色，请先更新主包'}
        if item=='minecraft:grass_block':
            # Reject an older main package before acquiring a client, traveling,
            # or withdrawing equipment. Its mine_block would ignore our tool gate.
            state=read_fresh(self.root)
            require_unlocked(self.root,state)
            require_scope(state,self.request['context'])
            self.latest=state
            if (type(state.get('grass_block_tool_protocol')) is not int
                    or state['grass_block_tool_protocol']<1):
                return {'phase':'blocked','detail':'当前 Kit 主包缺少草方块精准采集工具核验；请先更新主包'}
        if item=='minecraft:gravel':
            return self.acquire_gravel(count)
        from material_jobs.acquisition import acquire, held_resource_route, _bounds, Unavailable, ROCK_SOURCES, LOGS
        from material_jobs.discovery import discover
        known=self.out/'discovered-resources.json'
        known_regions=[]
        if known.exists():
            try:
                if known.stat().st_size>1_000_000:
                    raise ValueError('resource list exceeds the bounded read limit')
                loaded=json.loads(known.read_text())
                if not isinstance(loaded,list):
                    raise ValueError('discovered resources must be a list')
                for region in loaded:
                    if not isinstance(region,dict) or not isinstance(region.get('item'),str):
                        raise ValueError('discovered resource row is malformed')
                    _bounds(region)
                known_regions=loaded
            except (OSError,ValueError,TypeError,KeyError,Unavailable):
                return {'phase':'blocked','code':'route_uncertain',
                        'detail':'旧资源区域记录损坏；未移动或整理装备'}
        if (item in ROCK_SOURCES or item in LOGS
                or item in ('minecraft:sand','minecraft:dirt','minecraft:grass_block')
                or item in SNOW_PRODUCTS):
            # Inspect an old same-world combat/unknown hold before action()
            # acquires a lease, prepare_travel moves, or equipment opens a box.
            current=read_fresh(self.root)
            require_unlocked(self.root,current)
            require_scope(current,self.request['context'])
            combined=list(self.profile.get('resource_regions',[]))
            combined.extend(region for region in known_regions if region not in combined)
            checked_profile={**self.profile,'resource_regions':combined}
            held=held_resource_route(self.root,current['world_session'],item,checked_profile,
                                     self.out/'acquisition',current=current)
            if held:
                return {'phase':'waiting','code':held['code'],
                        'detail':'原资源区路线待核；不会移动、换区或整理装备'}
        with self.action('acquire') as (c,out):
            self.prepare_travel()
            if (item not in ROCK_SOURCES and item not in LOGS
                    and item not in ('minecraft:sand','minecraft:dirt','minecraft:grass_block')
                    and item not in SNOW_PRODUCTS):
                return {'phase':'blocked','detail':'此原料尚未提供自动采集方式：'+item}
            if item in ('minecraft:dirt','minecraft:grass_block') or item in SNOW_PRODUCTS:
                from material_jobs.dirt_harvest import _box
                protected=self.profile.get('protected_regions')
                if not isinstance(protected,list) or not protected or any(_box(box) is None for box in protected):
                    return {'phase':'blocked','detail':'表层土方采集需要先登记有效的建造保护区域'}
            from material_jobs.equipment import prepare
            prepared=prepare(c,item,count,self.profile,self.out/'equipment',self.checkpoint)
            if prepared.get('phase')!='done':
                return prepared
            directory=self.out/'acquisition'
            for region in known_regions:
                if region not in self.profile['resource_regions']:
                    self.profile['resource_regions'].append(region)
            if any(r.get('item')==item for r in self.profile['resource_regions']):
                receipt=acquire(c,item,count,self.profile,directory,self.checkpoint)
                if receipt.get('code')!='no_safe_candidate':
                    return receipt
            found=discover(c,item,self.profile,self.root.parent/'material-resource-ledger',self.checkpoint)
            if found is None:
                progress=getattr(c,'material_search_progress',{})
                if progress.get('coarse_fallback')=='host_protocol_unavailable':
                    return {'phase':'blocked',
                            'detail':'当前 Kit 主包缺少雪地群系粗筛接口；未移动角色，请更新主包后重试',
                            'search_progress':progress}
                if isinstance(progress.get('guard_hold'),dict):
                    code=progress['guard_hold'].get('code')
                    return {'phase':'waiting','code':code if code in ('guard_displaced','route_uncertain')
                            else 'route_uncertain',
                            'detail':'原资源区路线等待防护清怪或核对；不会换去其他矿区',
                            'search_progress':progress}
                if (search_coverage(progress)>0
                        and progress.get('has_more') is True):
                    return {'phase':'waiting','detail':'本批粗筛或详细区域无安全矿点，继续搜索尚未访问的区域',
                            'search_progress':progress}
                return {'phase':'blocked','detail':'本轮已扫描未访问的资源区，未找到安全矿点；记录已保存，下次从新区域继续'}
            self.profile['resource_regions'].append(found)
            write_json(known,[r for r in self.profile['resource_regions'] if r.get('source')=='natural_survey' or r==found])
            return acquire(c,item,count,self.profile,directory,self.checkpoint)

    def smelt(self, recipe, count):
        from material_jobs.processing import smelt
        with self.action('smelt') as (c,out):
            self.prepare_travel()
            self.stage_near_base(self.profile.get('furnace_positions',[]))
            return smelt(c,recipe,count,self.profile,out,self.checkpoint)

    def harden(self, item, count):
        from material_jobs.processing import harden
        with self.action('harden') as (c,out):
            self.prepare_travel()
            return harden(c,item,count,self.profile,out,self.checkpoint)

    def run_pipeline(self, item, target_count, out, *, target_scope, checkpoint=None):
        from material_jobs.pipeline_dispatch import run
        from material_jobs.pipeline_experience import record_outcome
        started = time.monotonic()
        try:
            result = run(self, item, target_count, out,
                         self.checkpoint if checkpoint is None else checkpoint, target_scope)
        except ValueError:
            raise  # An invalid contract is not an observed game failure.
        except Exception as error:
            record_outcome(self, item, target_count, target_scope, out, error=error,
                           duration_ms=(time.monotonic()-started)*1000)
            raise
        record_outcome(self, item, target_count, target_scope, out, result=result,
                       duration_ms=(time.monotonic()-started)*1000)
        return result

    def acquire_gravel(self, target):
        from kit_cli import make_request, send
        before = self.stock().get('minecraft:gravel',0)
        if before >= target:
            return {'phase':'done','detail':'沙砾数量已足够'}
        self.checkpoint()
        self.finish()
        self.ready = True
        self.checkpoint()
        state = read_fresh(self.root)
        require_unlocked(self.root,state)
        require_scope(state,self.request['context'])
        if state.get('supervision_lease',{}).get('kind') not in (None,'parking'):
            raise JobPaused('前一材料任务尚未交还控制，不能启动沙砾采集')
        previous = self.busy
        self.busy = True
        try:
            request = make_request(state,'gravel_start',radius=64,depth=32,limit=min(2304,target-before))
            reply = send(self.root,request)
            lease = reply.get('supervision_lease') or {}
            if (reply.get('phase') != 'done' or not reply.get('gravel',{}).get('active')
                    or lease.get('kind') != 'materials' or not lease.get('job_session')
                    or reply.get('world_session') != self.request['context']['world_session']):
                raise JobBlocked('沙砾启动回执没有确认本次任务；保留现场，不重复启动')
            self.native_gravel_session = lease['job_session']
            started = time.monotonic()
            try:
                while True:
                    self.checkpoint()
                    state = read_fresh(self.root)
                    require_unlocked(self.root,state)
                    require_scope(state,self.request['context'])
                    gravel = state.get('gravel') or {}
                    if not gravel.get('active'):
                        break
                    if (state.get('supervision_lease') or {}).get('job_session') != self.native_gravel_session:
                        raise JobPaused('沙砾控制权已交还，不再操作新的任务')
                    if time.monotonic()-started > 1800:
                        raise JobBlocked('本次沙砾采集达到时限，保留已采物品')
                    time.sleep(.5)
            finally:
                self.stop_owned_gravel()
        finally:
            self.busy = previous
        actual = self.stock().get('minecraft:gravel',0)
        return {'phase':'done' if actual>=target else 'waiting' if actual>before else 'blocked',
                'detail':'沙砾采集已核对实际背包','before':before,'after':actual,'target':target}

    def stop_owned_gravel(self):
        from kit_cli import make_request, send
        if not self.native_gravel_session:
            return
        owned = self.native_gravel_session
        try:
            state = read_fresh(self.root)
            require_unlocked(self.root,state)
            require_scope(state,self.request['context'])
            lease = state.get('supervision_lease') or {}
            if not state.get('gravel',{}).get('active'):
                self.native_gravel_session = None
                return
            if lease.get('job_session') != owned:
                return
            # Exactly one stop request. An unknown reply is never replayed.
            send(self.root,make_request(state,'gravel_stop'))
            end = time.monotonic()+60
            while True:
                state = read_fresh(self.root)
                require_unlocked(self.root,state)
                require_scope(state,self.request['context'])
                if not state.get('gravel',{}).get('active'):
                    self.native_gravel_session = None
                    return
                if (state.get('supervision_lease') or {}).get('job_session') != owned:
                    return
                if time.monotonic() >= end:
                    raise JobBlocked('沙砾任务仍在安全上浮，保留原生防护')
                time.sleep(.5)
        except (RuntimeError,OSError,ValueError) as error:
            write_json(self.out/'gravel-cleanup.json',{'native_task_session':owned,
                       'confirmed':False,'reason':str(error),'action':'yield_to_native_guard'})
            raise

    def build(self, projection_key):
        with self.action('build') as (c,out):
            from goal_workflow import build_phase
            self.prepare_travel()
            state=c.status()
            require_scope(state,self.request['context'])
            selection=state.get('projection_selection',{})
            if selection.get('key')!=projection_key:
                raise JobBlocked('投影已改变')
            from material_jobs.acquisition import _travel
            low,high=selection['min'],selection['max'];actual=c.status()['pos']
            staging=[high[0]+4.5,max(actual[1],high[1]+4),(low[2]+high[2]+1)/2]
            _travel(c,staging,self.checkpoint,[])
            outside_station(c,selection)
            before=self.refresh_audit()
            if before.get('replacement_items',{}).get(POST_ITEM):
                posts=post_work(before,c.status())
                if posts['eligible']:
                    beams=finish_beams(c,limit=16,expected_key=projection_key,
                                       expected_world=self.request['context']['world_session'],
                                       expected_server=self.request['context']['server'],
                                       expected_dimension=self.request['context']['dimension'],
                                       target_item=POST_ITEM,target_axis='y')
                    if beams['completed']:
                        after=self.refresh_audit()
                        post_work(after,c.status())  # validates live server, world, selection and complete coverage
                        remaining={tuple(row['pos']) for row in after['mismatches']}
                        if (type(after.get('observed_at')) is not int
                                or after['observed_at']<=before['observed_at']
                                or any(tuple(receipt['pos']) in remaining for receipt in beams['completed'])):
                            raise JobBlocked('木柱逐格回执与完整投影复核不一致；停止重复施工')
                        write_json(out/'stripped-posts.json',{'placement_key':projection_key,
                                   'world_session':c.world,'before_matched':before['matched'],
                                   'after_matched':after['matched'],'completed':beams['completed'],
                                   'deferred':beams['deferred']})
                        leave_projection(c)
                        return {'phase':'done','detail':'木柱原位剥皮并通过投影复核',
                                'placed':len(beams['completed']),'post_scan_receipts':beams['completed']}
            after=build_phase(c,projection_key,seconds=240,stall_seconds=45,background=True)
            self.audit,self.audit_dirty=after,False
            leave_projection(c)
            gained=after['matched']-before['matched']
            state=c.status().get('build_job',{})
            navigation=state.get('navigation') or {}
            route_budget=(state.get('outcome')=='needs_review' and navigation.get('budget_exhausted') is True)
            route_unreachable=(state.get('outcome')=='blocked'
                               and state.get('reason','').startswith('找不到可通行路线；')
                               and navigation.get('search_pending') is False
                               and navigation.get('path_length')==0 and navigation.get('goals',0)>0
                               and type(navigation.get('expanded')) is int and navigation['expanded']>0)
            # The native planner can finish without expanding a node when the
            # held items have live targets but none can generate a safe
            # placement station. This must not be confused with a pending or
            # incomplete search. Only a complete schema-2 audit may hand this
            # state to exact-row supply selection.
            no_placement_goals=(state.get('outcome')=='blocked'
                                and state.get('reason','').startswith('找不到可通行路线；')
                                and type(after.get('audit_schema')) is int
                                and after['audit_schema']==2
                                and navigation.get('search_pending') is False
                                and type(navigation.get('path_length')) is int
                                and navigation['path_length']==0
                                and type(navigation.get('targets')) is int
                                and navigation['targets']>0
                                and type(navigation.get('goals')) is int
                                and navigation['goals']==0
                                and type(navigation.get('expanded')) is int
                                and navigation['expanded']==0)
            fresh_missing=(after.get('placement_key')==projection_key
                           and after.get('loaded_chunks_verified') is True
                           and not after.get('kinds',{}).get('unloaded')
                           and type(after.get('observed_at')) is int
                           and after['observed_at']>before.get('observed_at',0)
                           and type(after.get('kinds',{}).get('missing')) is int
                           and after['kinds']['missing']>0)
            route_blocked=route_unreachable or no_placement_goals
            if gained==0 and route_blocked and fresh_missing:
                from material_jobs.construction_access import attempt
                access=attempt(self,after)
                if access is not None:
                    return access
            if gained==0 and (route_budget or route_blocked) and fresh_missing:
                held=self.stock()
                # A held item whose targets produced zero placement stations
                # cannot gain a station merely by adding more of that same
                # item. Only a distinct absent item may open a new frontier.
                exhausted_held={item for item,count in held.items() if count>0} if no_placement_goals else ()
                requirements=next_build_supply(after,held,c.status(),exhausted_held)
                if no_placement_goals:
                    detail=('当前背包材料没有生成可核验的施工站位；先补新的缺料批次，再核验施工'
                            if requirements else
                            '当前背包材料没有可核验的施工站位，且没有新的安全补料批次；保留现场待检查')
                else:
                    detail=('当前材料没有已确认可达施工点；先补新的缺料批次，再核验施工'
                            if requirements else '所需材料已在背包，需要检查入口或支撑')
                return {'phase':'waiting' if requirements else 'blocked',
                        'detail':detail,
                        'requirements':requirements,'placed':0,'route_budget_exhausted':route_budget,
                        'route_unreachable':route_unreachable,'no_placement_goals':no_placement_goals,
                        'navigation':navigation}
            if state.get('outcome')=='missing_materials':
                # The native builder has already searched the current frontier
                # with this inventory. Even if it placed some blocks first,
                # restarting it unchanged only repeats the travel and scan
                # before discovering the same missing-material stop.
                requirements=next_build_supply(after,self.stock(),c.status()) if fresh_missing else {}
                return {'phase':'waiting' if requirements else 'blocked',
                        'detail':'先补可推进施工的下一批材料' if requirements else '没有新鲜且可放的差料证据，或背包已有差料；保留现场待核对',
                        'requirements':requirements,'placed':max(0,gained)}
            return {'phase':'done' if gained>0 else 'blocked',
                    'detail':state.get('reason','施工差料已重新核对'), 'placed':gained,
                    **({'route_budget_exhausted':True,'navigation':navigation} if route_budget else {})}

    def recover(self, inflight):
        blocked = {'phase':'blocked','detail':'中断操作需先核对在制品；不会重新投料','safe_to_replan':False}
        if inflight.get('operation') in ('smelt','harden'):
            path=self.out/'active-operation.json'
            if not path.is_file():
                return blocked
            record=json.loads(path.read_text())
            directory=Path(record.get('directory','')).resolve()
            if (record.get('operation_fingerprint')!=fingerprint(inflight)
                    or directory.parent!=self.out.resolve() or record.get('name')!=inflight['operation']):
                return blocked
            from material_jobs.processing import recover
            c=self.ensure_client()
            self.busy=True
            try:
                receipt=recover(c,inflight['operation'],inflight['args'],self.profile,directory,self.checkpoint)
            finally:
                self.busy=False
            return receipt
        if inflight.get('operation') not in ('fetch','craft','acquire','build','make_room'):
            return blocked
        path = self.out/'finish-recovery.json'
        if not path.is_file():
            return blocked
        receipt = json.loads(path.read_text())
        if (receipt.get('operation_fingerprint') != fingerprint(inflight)
                or receipt.get('world_session') != self.request['context']['world_session']
                or not receipt.get('safe_to_replan')):
            return blocked
        state = read_fresh(self.root)
        require_unlocked(self.root,state)
        require_scope(state,self.request['context'])
        if not clean_for_replan(state,self.client):
            return blocked
        return {'phase':'done','detail':'上次动作已确认停稳且无在制物；按当前背包重新规划',
                'safe_to_replan':True,'original_sequence':inflight.get('sequence'),
                'original_operation':inflight['operation']}

    def record_recovery(self, client):
        pending = self.out/'inflight.json'
        if not pending.is_file():
            return
        operation = json.loads(pending.read_text())
        state = read_fresh(self.root)
        lease = state.get('supervision_lease') or {}
        safe = (state.get('world_session')==client.world and clean_for_replan(state,client)
                and (not lease or lease.get('id')==client.heartbeat.id))
        write_json(self.out/'finish-recovery.json',{'schema':1,'world_session':client.world,
                   'operation_fingerprint':fingerprint(operation),'original_sequence':operation.get('sequence'),
                   'observed_revision':state.get('control_revision'),'safe_to_replan':safe})

    def finish(self):
        c = self.client
        if c is None:
            return
        self.cleaning = True
        try:
            state = read_fresh(self.root)
            if not owns_material_state(c,state):
                c.heartbeat.close()
                write_json(self.out/'finish-scope.json',{'owned':False,'action':'yield_control'})
                return
            c.rev = state['control_revision']
            if state.get('safety_hold', {}).get('active'):
                return
            if state.get('health', 0) < 14:
                try:
                    c.request('safe_logout')
                finally:
                    from safety_interlock import record_material_health_exit
                    record_material_health_exit(self.root,state,'Low health during material job finish')
                return
            if state.get('screen') in KIT_SCREENS:
                c.checked('material_job_pause',release=True)
                c.heartbeat.close()
                self.record_recovery(c)
                return
            if state.get('phase') == 'running' or state.get('build_job',{}).get('active'):
                c.checked('material_job_pause',release=False)
            try:
                # Recover held crafting contents before movement, then leave
                # the actual pit before any callback can open a distant chest.
                self.close_owned_menu()
                leave_quarry(c,self.out/'acquisition')
                tools_path=self.out/'equipment'/'silk-tools.json'
                if tools_path.exists():
                    tools=json.loads(tools_path.read_text())
                    entries=tools.get('tools')
                    if (tools.get('world_session')!=c.world or not isinstance(entries,list)
                            or any(not isinstance(entry,dict) or entry.get('state') not in ('stored','returned') for entry in entries)):
                        raise JobBlocked('工具寄存结果尚未确认，保留记录，不重复取放')
                    stored=[entry for entry in entries if entry['state']=='stored']
                    if stored:
                        depots=self.profile.get('depots',[])
                        if not depots or any(entry.get('pos') not in depots for entry in stored):
                            raise JobBlocked('寄存工具的仓库未在当前批准范围内，保留原位')
                        self.stage_near_base(depots)
                # Shelter exits still precede the vertical parking check; a
                # roof must not be mistaken for an open upward flight column.
                from material_cleanup import run as cleanup_resources
                if cleanup_resources(c):
                    raise JobBlocked('临时箱子或工位收尾未确认，保留记录；不重复清理')
                self.close_owned_menu()
                point = local_park(c)
                if not c.status().get('flight'):
                    # Grounded crafting/storage intentionally disabled Flight.
                    # Take off through the already scanned clear column before
                    # registering a parked-flight destination with the host.
                    reply=c.request('navigate',target=point,arrival=.25,air_only=True,seconds=90)
                    if reply.get('phase')!='done':
                        raise JobBlocked('地面作业后的安全起飞没有完成')
                    actual=settled_state(c,point,.55)
                    point=[actual['pos'][0],actual['pos'][1]+1,actual['pos'][2]]
                c.checked('material_job_park',park_target=point)
                c.park_target = point
            except (JobPaused,Handoff):
                # A user interface/control handoff cannot become a new logout
                # request. The native lease watchdog keeps its safety role.
                c.heartbeat.close()
                raise
            except (RuntimeError,OSError,ValueError,KeyError,TypeError) as error:
                try:
                    fresh = read_fresh(self.root)
                except (OSError,RuntimeError,ValueError) as unavailable:
                    raise JobPaused('收尾失败且当前控制状态无法核验，交还原生防护') from unavailable
                if not owns_material_state(c,fresh):
                    c.heartbeat.close()
                    raise JobPaused('收尾控制权已变化，保留当前状态') from error
                if fresh.get('safety_hold',{}).get('active'):
                    raise JobPaused('原生安全锁已开启，不继续收尾或自动重连') from error
                # Only a matching lease and current/owned terminal revision
                # permits this one-shot logout. Never attempt to climb a roof.
                c.rev=fresh['control_revision']
                try:
                    write_json(self.out/'finish-fallback.json',{'reason':str(error),'action':'safe_logout'})
                except OSError:
                    print('Material finish fallback journal unavailable; requesting owned safety logout',flush=True)
                try:
                    c.request('safe_logout')
                finally:
                    if fresh.get('health',0)<14:
                        from safety_interlock import record_material_health_exit
                        record_material_health_exit(self.root,fresh,'Low health after material cleanup/exit failed: '+str(error))
                    c.heartbeat.close()
                raise JobBlocked('安全停靠未完成，已请求保护下线：'+str(error)) from error
            c.finish()
            fallback = c.out/'park-fallback.json'
            if fallback.exists():
                record = json.loads(fallback.read_text())
                raise JobBlocked('收尾已切换保护下线：'+str(record.get('reason','停靠未确认')))
            proof=c.out/'stock-safety.json'
            receipt=json.loads(proof.read_text()) if proof.is_file() else {}
            if receipt.get('lease')!=c.heartbeat.id or receipt.get('action')!='KEEP_PVE_GUARD':
                raise JobBlocked('安全收尾尚未得到原生确认，物品进度已保留')
            self.record_recovery(c)
        finally:
            c.heartbeat.close()
            self.client = None
            self.cleaning = False


def create_backend(request, automation, out, checkpoint):
    return Backend(request,automation,out,checkpoint)
