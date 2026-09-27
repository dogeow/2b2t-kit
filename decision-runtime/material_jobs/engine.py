"""Bounded local fetch/produce/build state machine with an injected game backend."""
from collections import Counter
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_plan import quantities, inventory_counts
from .planning import plan
from .protocol import JobBlocked, JobCancelled, JobPaused, fingerprint, server_key, validate_request

STATES = {'queued', 'planning', 'fetching', 'gathering', 'crafting', 'smelting',
          'hardening', 'building', 'paused', 'completed', 'blocked', 'failed', 'cancelled'}
ACTIVE_FIELDS = ('borer_active', 'chopping', 'navigating', 'native_material_busy')


class MaterialJob:
    def __init__(self, request, out, backend=None, *, clock=time.time, max_steps=256, max_seconds=7200):
        self.request = validate_request(request)
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        saved = self.out / 'request.json'
        if saved.exists() and fingerprint(json.loads(saved.read_text())) != fingerprint(self.request):
            raise ValueError('The output directory belongs to a different material request')
        if not saved.exists():
            write_json(saved, self.request)
        self.backend, self.clock = backend, clock
        self.max_steps, self.max_seconds = max_steps, max_seconds
        self.started = clock()
        self.last_control = self.request['created_at'] - 1
        self.steps = 0
        self.fetch_tried, self.no_progress = {}, Counter()
        self.snapshot, self.held = {}, {}
        self.batch_item, self.batch_count = None, 0
        self.context = dict(self.request['context'])
        self.prerequisites = {}
        self.pending_ready_build = None
        self.resuming = False
        self.state = {'schema': 1, 'id': request['id'], 'state': 'queued', 'phase': '等待接管',
                      'detail': '', 'done': 0, 'total': sum(request['targets'].values()),
                      'updated_at': int(clock() * 1000), 'terminal': False, 'ai_calls': 0}
        prior = self.out / 'status.json'
        if prior.exists():
            previous = json.loads(prior.read_text())
            if previous.get('id') != request['id']:
                raise ValueError('Status belongs to another material job')
            self.last_control = max(self.last_control, previous.get('last_control_at', 0))
            self.steps = previous.get('steps', 0)
            self.state = previous
            self.resuming = True
            self.prerequisites = dict(quantities(previous.get('requirements', {})))
        resumed = self.out / 'resume-context.json'
        if resumed.exists():
            record = json.loads(resumed.read_text())
            if record.get('id') != self.request['id']:
                raise ValueError('Resume context belongs to another job')
            self.context = self._validate_resume_context(record.get('context'))
        self._write(detail=self.state.get('detail', ''))

    def _write(self, state=None, phase=None, detail='', **extra):
        if state is not None:
            if state not in STATES:
                raise ValueError('Invalid material job state')
            self.state['state'] = state
        if phase is not None:
            self.state['phase'] = phase
        self.state.update(detail=str(detail)[:500], updated_at=int(self.clock() * 1000),
                          last_control_at=self.last_control, steps=self.steps, **extra)
        native = self.snapshot.get('native_task_session')
        if native:
            self.state['native_task_session'] = native
        write_json(self.out / 'status.json', self.state)
        return self.state

    def _event(self, kind, **fields):
        row = {'kind': kind, 'time': int(self.clock() * 1000), **fields}
        with (self.out / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')

    def control(self):
        path = self.out / 'control.json'
        if not path.exists():
            return None
        try:
            command = json.loads(path.read_text())
        except (OSError, ValueError) as error:
            raise JobPaused('控制指令尚未完整写入，已暂停') from error
        if command.get('id') != self.request['id']:
            return None
        stamp = command.get('created_at')
        if type(stamp) is not int or stamp <= self.last_control:
            return None
        action = command.get('action')
        if action not in ('pause', 'resume', 'cancel'):
            raise JobPaused('未知控制指令，已暂停')
        self.last_control = stamp
        self._event('control', action=action)
        if action == 'resume':
            if self.state['state'] != 'paused':
                return None
            context = self._validate_resume_context(command.get('context'))
            write_json(self.out / 'resume-context.json', {'id': self.request['id'], 'created_at': stamp, 'context': context})
            self.context = context
        return action

    def _validate_resume_context(self, context):
        try:
            validated = validate_request({**self.request, 'context': context})['context']
        except (ValueError, TypeError, AttributeError) as error:
            raise JobPaused('继续指令缺少当前世界与控制状态，请从 Kit 再次继续') from error
        original = self.request['context']
        if (server_key(validated['server']) != server_key(original['server'])
                or validated['dimension'] != original['dimension']
                or validated['world_session'] != original['world_session']):
            raise JobBlocked('世界已变化，不能把旧任务静默重绑；请在当前世界新建任务')
        return validated

    def _scope(self, state, *, initial=False):
        context = self.context
        if not state.get('connected'):
            raise JobPaused('已离开世界；本任务不会自动重连')
        if (server_key(state.get('server')) != server_key(context['server'])
                or state.get('dimension') != context['dimension']
                or state.get('world_session') != context['world_session']):
            raise JobBlocked('服务器、维度或世界会话已改变；需要在当前世界重新创建任务')
        if state.get('safety_hold', {}).get('active') or state.get('material_health_hold', {}).get('active'):
            raise JobPaused('安全离线锁仍开启；不会自动解除或重连')
        if state.get('manual_movement'):
            raise JobPaused('玩家接管移动，已让出控制')
        if (type(state.get('health')) not in (int, float) or not math.isfinite(state['health'])
                or state['health'] < 18):
            raise JobPaused('生命值不足，交给原生防护处理后暂停任务')
        if initial:
            revision = state.get('initial_control_revision', state.get('control_revision'))
            if revision != context['expected_revision']:
                raise JobPaused('控制状态已变化，请重新确认任务接管')

    def checkpoint(self):
        action = self.control()
        if action == 'cancel':
            raise JobCancelled('用户取消任务')
        if action == 'pause':
            raise JobPaused('用户暂停任务')
        if self.clock() - self.started > self.max_seconds:
            raise JobBlocked('达到本轮运行时限，已保留进度')
        if self.backend is not None:
            self.snapshot = self.backend.observe()
            self._scope(self.snapshot)
            # Show items actually received during long batches. Completion
            # still requires the receipt, fresh audit and safe cleanup.
            if self.request['mode']=='item' and isinstance(self.snapshot.get('inventory'),list):
                live=inventory_counts(self.snapshot)
                self.state.update(done=sum(min(live.get(item,0),count) for item,count in self.request['targets'].items()),
                                  total=sum(self.request['targets'].values()))
            elif self.request['mode']=='projection':
                building=self.snapshot.get('build_job') or {};audit=self.snapshot.get('projection_audit') or {}
                matched,total=building.get('matched'),audit.get('total')
                if (building.get('active') and building.get('placement_key')==self.request['projection_key']
                        and type(matched) is int and type(total) is int and 0<=matched<=total):
                    self.state.update(done=matched,total=total)
        self._write(detail=self.state.get('detail', ''))

    def _observe(self, *, initial=False):
        self.checkpoint()
        self.snapshot = self.backend.observe()
        self._scope(self.snapshot, initial=initial)
        self.held = dict(quantities(self.backend.stock()))
        targets = self._targets()
        if self.request['mode'] == 'item':
            self._write(done=sum(min(self.held.get(item, 0), count) for item, count in targets.items()),
                        total=sum(targets.values()))
        else:
            audit = self.snapshot['projection_audit']
            self._write(done=audit['matched'], total=audit['total'])
        return targets

    def _targets(self):
        if self.request['mode'] == 'item':
            return self.request['targets']
        audit = self.snapshot.get('projection_audit', {})
        if (audit.get('placement_key') != self.request['projection_key']
                or audit.get('loaded_chunks_verified') is not True
                or not isinstance(audit.get('replacement_items'), dict)
                or type(audit.get('matched')) is not int or type(audit.get('total')) is not int
                or not 0 <= audit['matched'] <= audit['total'] or audit['total'] <= 0):
            raise JobBlocked('缺少当前投影的完整方块核验；不能按旧差料清单施工')
        return dict(quantities(audit['replacement_items']))

    def _complete(self, targets):
        if self.request['mode'] == 'item':
            return all(self.held.get(item, 0) >= count for item, count in targets.items())
        audit = self.snapshot['projection_audit']
        if not targets and audit['matched']==audit['total'] and audit.get('enclosed_air_conflicts'):
            raise JobBlocked('目标方块已齐，但投影内部仍有占位冲突；保留已有建筑，不宣告完成')
        return not targets and audit['matched'] == audit['total']

    def _capacity(self, item, convertible=()):
        rows = self.snapshot.get('inventory')
        if not isinstance(rows, list):
            return None
        rows = [row for row in rows if 0 <= row.get('slot', -1) < 36]
        if len(rows) != 36:
            return None
        size = self._stack_size(item)
        if size is None:
            return None
        capacity = 0
        for row in rows:
            if not row.get('count') or row.get('item') == item or row.get('item') in convertible:
                capacity += size
        return capacity

    def _stack_size(self, item):
        known = []
        for mapping in (self.request.get('target_stack_sizes', {}), self.snapshot.get('target_stack_sizes', {})):
            size = mapping.get(item)
            if size is not None:
                if type(size) is not int or not 1 <= size <= 99:
                    raise JobBlocked('物品堆叠上限无效：' + item)
                known.append(size)
        known += [row['max_stack'] for row in self.snapshot.get('inventory', [])
                  if row.get('item') == item and row.get('count') and type(row.get('max_stack')) is int]
        if not known:
            return None
        if len(set(known)) != 1 or not 1 <= known[0] <= 99:
            raise JobBlocked('物品堆叠上限记录冲突：' + item)
        return known[0]

    def _batch_limit(self, item):
        size = self._stack_size(item)
        if size is None:
            raise JobBlocked('缺少物品的实际堆叠上限：' + item)
        return min(256 if item.endswith('_concrete') else 128, size * 4)

    def _plan(self, targets):
        return plan(self.backend.catalog, targets, self.held, self.snapshot.get('warehouse_stock_hint'))

    def _peak_slots(self, planned):
        sizes = {}
        def slots(counts):
            total = 0
            for item, count in counts.items():
                if count > 0:
                    if item not in sizes:
                        sizes[item] = self._stack_size(item) or 1
                    total += math.ceil(count / sizes[item])
            return total
        counts = Counter(self.held)
        occupied = sum(row.get('count', 0) > 0 for row in self.snapshot.get('inventory', [])
                       if 0 <= row.get('slot', -1) < 36)
        fragmentation = max(0, occupied - slots(counts))
        peak = slots(counts) + fragmentation
        for step in planned['steps']:
            if step['kind'] == 'acquire':
                counts[step['item']] += step['count']
            elif step['kind'] != 'reserve':
                counts.subtract(step['ingredients'])
                counts[step['item']] += step['produced']
            peak = max(peak, slots(counts) + fragmentation)
        return peak

    def _fit_batch(self, item, final_count):
        amount = min(self._batch_limit(item), final_count - self.held.get(item, 0))
        direct_target = self.held.get(item, 0) + amount
        while amount > 0:
            count = self.held.get(item, 0) + amount
            planned = self._plan({item: count})
            workspace = any(step['kind'] in ('craft', 'smelt', 'harden') for step in planned['steps'])
            if self._peak_slots(planned) <= (35 if workspace else 36):
                return count
            amount //= 2
        # A ready-made depot output may still fit even when its raw recipe does
        # not. Allow one bounded fetch; the production check below then blocks.
        return direct_target

    def _item_batch(self, targets):
        # Finished output must fit simultaneously. Recipe inputs can be consumed
        # later; unrelated player equipment cannot be counted as empty space.
        total_slots = 0
        for item, count in targets.items():
            size = self._stack_size(item)
            if size is None:
                raise JobBlocked('目标物品堆叠上限尚未同步')
            total_slots += math.ceil(count / size)
        if total_slots > 36:
            limits='；'.join(f'{item}：目标 {count}，已持有 {self.held.get(item,0)}，空背包最多 {36*self._stack_size(item)}'
                            for item,count in targets.items())
            raise JobBlocked('单物品目标超过背包总容量（'+limits+'），请减少数量；未开始取料或移动')
        full = self._plan(targets)
        convertible = {item for step in full['steps'] for item in step.get('ingredients', {})}
        required_slots = 0
        for item, count in targets.items():
            size = self._stack_size(item)
            capacity = self._capacity(item, convertible)
            if size is None or capacity is None:
                raise JobBlocked('背包容量或目标物品堆叠上限尚未同步')
            if count > capacity:
                self._make_room(targets, full, f'{item}：目标 {count}，已持有 {self.held.get(item,0)}，当前背包最多可容纳 {capacity}；请减少数量或腾出位置')
                return None
            required_slots += math.ceil(count / size)
        occupied = sum(bool(row.get('count')) and row.get('item') not in targets and row.get('item') not in convertible
                       for row in self.snapshot.get('inventory', []) if 0 <= row.get('slot', -1) < 36)
        if required_slots + occupied > 36:
            self._make_room(targets, full, '目标成品无法同时放入当前背包，请减少数量或腾出位置')
            return None
        if self.batch_item not in targets or self.held.get(self.batch_item, 0) >= self.batch_count:
            self.batch_item = next(item for item, count in targets.items() if self.held.get(item, 0) < count)
            self.batch_count = self._fit_batch(self.batch_item, targets[self.batch_item])
        return {self.batch_item: min(self.batch_count, targets[self.batch_item])}

    def _make_room(self, targets, planned, fallback):
        if not callable(getattr(self.backend, 'make_room', None)):
            raise JobBlocked(fallback)
        keep = set(self.request['targets']) | set(targets) | set(self._targets())
        keep.update(item for step in planned['steps'] for item in step.get('ingredients', {}))
        if any(step['kind'] == 'smelt' for step in planned['steps']):
            keep.add('minecraft:coal')
        self._call('make_room', [dict(targets), sorted(keep)], 'fetching')

    def _nearly_full(self):
        rows = self.snapshot.get('inventory', [])
        rows = [row for row in rows if 0 <= row.get('slot', -1) < 36]
        return len(rows) == 36 and sum(not row.get('count') for row in rows) <= 1

    def _projection_batch(self, targets):
        ready = {item: count for item, count in targets.items() if self.held.get(item, 0)}
        if (ready and self._nearly_full()
                or any(self.held.get(item, 0) >= min(count, self._batch_limit(item))
                       for item, count in ready.items())
                or self.batch_item in ready and self.held[self.batch_item] >= min(self.batch_count, targets[self.batch_item])):
            self._build_batch()
            return None
        if self.batch_item not in targets:
            # Work on carried useful output first, then ordinary shell material.
            # Fixed batches keep several hundred sand/gravel ingredients from
            # becoming a single backpack request for the entire projection.
            self.batch_item = min(targets, key=lambda item: (
                not bool(self.held.get(item, 0)), not item.endswith('_concrete'), item))
            self.batch_count = self._fit_batch(self.batch_item, targets[self.batch_item])
        return {self.batch_item: min(self.batch_count, targets[self.batch_item])}

    def _build_batch(self):
        self._call('build', [self.request['projection_key']], 'building')
        self.batch_item, self.batch_count = None, 0
        self.fetch_tried.clear()

    def _record_ready_build(self, receipt, before):
        """Accept a depot hint only after newly received projection output is observed."""
        if self.request['mode'] != 'projection' or receipt.get('ready_for_build') is not True:
            return
        provided = receipt.get('provided_finished')
        if (not isinstance(provided, dict) or not provided or len(provided) > 256
                or receipt.get('projection_key', self.request['projection_key']) != self.request['projection_key']):
            return
        try:
            amounts = dict(quantities(provided))
        except (TypeError, ValueError):
            return
        if len(amounts) != len(provided):
            return
        actual = inventory_counts(self.snapshot)
        needed = self._targets()
        verified = {item: before['inventory'].get(item, 0) + count for item, count in amounts.items()
                    if item in needed and actual.get(item, 0) - before['inventory'].get(item, 0) >= count
                    and self.held.get(item, 0) >= before['inventory'].get(item, 0) + count}
        if verified:
            # One-shot, in-memory intent: a restarted worker must audit again,
            # never treat a stale depot receipt as carried construction stock.
            self.pending_ready_build = verified
            self._event('finished_materials_received', provided={item: amounts[item] for item in verified})

    def _consume_ready_build(self, targets):
        pending, self.pending_ready_build = self.pending_ready_build, None
        if self.request['mode'] != 'projection' or not pending:
            return False
        actual = inventory_counts(self.snapshot)
        if not any(item in targets and actual.get(item, 0) >= count and self.held.get(item, 0) >= count
                   for item, count in pending.items()):
            return False
        self.prerequisites.clear()
        self._write(requirements={})
        self._build_batch()
        return True

    def _recover(self):
        path = self.out / 'inflight.json'
        if not path.exists():
            return
        pending = json.loads(path.read_text())
        if pending.get('job_id') != self.request['id']:
            raise JobBlocked('未完成动作属于其他任务')
        self._write('planning', '核对中断动作')
        recover = getattr(self.backend, 'recover', None)
        if recover is not None:
            receipt = recover(pending)
            self._event('recovery_receipt', receipt=receipt)
            self.checkpoint()
            if receipt.get('phase') == 'done' and receipt.get('safe_to_replan') is True and not self._work_active():
                path.unlink()
                return
            if receipt.get('phase') == 'paused':
                raise JobPaused(receipt.get('detail','恢复核验已暂停'))
            raise JobBlocked(receipt.get('detail','后端尚未确认旧动作安全结束，保留在制品'))
        # In the absence of a reconciler, a fresh completed output target is the
        # only safe inference. Unseen furnace contents never become virtual stock.
        self._observe()
        output_targets = pending.get('output_targets', {})
        busy = self._work_active()
        if output_targets and not busy and all(self.held.get(i, 0) >= n for i, n in output_targets.items()):
            self._event('recovered_from_output', targets=output_targets)
            path.unlink()
            return
        raise JobBlocked('中断动作尚未完成现物核对；保留在制品，避免重复投料')

    def _work_active(self):
        return (any(self.snapshot.get(field) for field in ACTIVE_FIELDS)
                or self.snapshot.get('pending_material_work')
                or self.snapshot.get('build_job', {}).get('active'))

    def _call(self, operation, args, stage, output_targets=None):
        if self.steps >= self.max_steps:
            raise JobBlocked('达到本轮动作上限，已保留进度')
        self.checkpoint()
        self.steps += 1
        before = {'stock': dict(self.held), 'inventory': dict(inventory_counts(self.snapshot)),
                  'replacement_items': dict(self.snapshot.get('projection_audit', {}).get('replacement_items', {})),
                  'matched': self.snapshot.get('projection_audit', {}).get('matched'),
                  'free_slots':sum(not row.get('count') for row in self.snapshot.get('inventory',[])
                                   if 0<=row.get('slot',-1)<36)}
        pending = {'job_id': self.request['id'], 'sequence': self.steps, 'operation': operation,
                   'args': args, 'before': before, 'output_targets': output_targets or {}}
        write_json(self.out / 'inflight.json', pending)
        self._write(stage, {'fetch':'仓库补料', 'acquire':'采集材料', 'craft':'合成材料',
                           'smelt':'熔炼材料', 'harden':'固化混凝土', 'build':'继续投影建造',
                           'make_room':'存放本任务副产物'}[operation])
        self._event('action_started', **pending)
        method = getattr(self.backend, operation, None)
        if method is None:
            raise JobBlocked('后端尚未实现：' + operation)
        receipt = method(*args)
        if not isinstance(receipt, dict) or receipt.get('phase') not in ('done', 'waiting', 'blocked', 'paused'):
            raise JobBlocked('动作未返回有效回执；不能重复发送')
        receipts = self.out / 'receipts'
        receipts.mkdir(exist_ok=True)
        write_json(receipts / ('%06d.json' % self.steps), {**pending, 'receipt': receipt})
        self._event('action_receipt', sequence=self.steps, operation=operation, receipt=receipt)
        if receipt['phase'] == 'paused':
            raise JobPaused(receipt.get('detail', '后端暂停作业'))
        if receipt['phase'] == 'blocked':
            raise JobBlocked(receipt.get('detail', '缺少能力或作业前置条件'))
        if receipt.get('requirements'):
            requirements = dict(quantities(receipt['requirements']))
            if len(requirements) > 32:
                raise JobBlocked('加工前置材料数量异常')
            self.prerequisites.update(requirements)
            self._write(requirements=self.prerequisites)
        self._observe()
        if self._work_active():
            raise JobBlocked('动作仍有未收回的在制品；不能开始下一轮投料')
        (self.out / 'inflight.json').unlink()
        if operation == 'fetch':
            self._record_ready_build(receipt, before)
        progressed = (self.held != before['stock']
                      or self.snapshot.get('projection_audit', {}).get('matched') != before['matched']
                      or sum(not row.get('count') for row in self.snapshot.get('inventory',[])
                             if 0<=row.get('slot',-1)<36)>before['free_slots'])
        search=receipt.get('search_progress') or {}
        if (operation=='acquire' and receipt['phase']=='waiting' and search.get('has_more') is True
                and type(search.get('new_tiles')) is int and 0<search['new_tiles']<=32):
            # Search coverage is useful progress, never an item receipt.
            progressed=True
            self._write(search_progress=search)
        # New construction materials change the reachable build frontier. Only
        # repeating the same build with the same useful stock is a stuck loop.
        relevant={item:before['stock'].get(item,0) for item in before['replacement_items']}
        if operation == 'build':
            # Eating, moving a spare tool, or changing depot hints is not
            # construction progress and must not reset the stuck-build guard.
            progressed = self.snapshot.get('projection_audit', {}).get('matched', 0) > before['matched']
        key = fingerprint([operation, args,relevant]) if operation=='build' else fingerprint([operation,args])
        self.no_progress[key] = 0 if progressed else self.no_progress[key] + 1
        if operation != 'fetch' and self.no_progress[key] >= 2:
            raise JobBlocked('同一步骤两次没有实际进展，已停止重复动作')
        return receipt

    def _fetch(self, targets):
        # A replanned dependency dict may shrink after partial depot pickup.
        # Cache each attempted absolute count, not the whole dict, so that a
        # smaller missing subset cannot repeatedly trigger an empty depot tour.
        targets = {item: count for item, count in targets.items()
                   if count > self.held.get(item, 0) and count > self.fetch_tried.get(item, 0)}
        if not targets:
            return False
        self.fetch_tried.update(targets)
        self._call('fetch', [targets], 'fetching', targets)
        return True

    def _fetch_intermediates(self, targets, planned):
        # The plan is topologically flattened, but the warehouse must not fetch
        # every output in it at once. Bricks already replace their polished
        # stone inputs; smooth stone already replaces its unsmelted stone.
        produced = Counter()
        dependencies = {}
        for step in planned['steps']:
            if step['kind'] in ('craft', 'smelt', 'harden'):
                dependencies.setdefault(step['item'],set()).update(step['ingredients'])
                if step['item'] not in targets:
                    produced[step['item']] += step['produced']
        frontier,seen=set(targets),set(targets)
        while frontier:
            children={item for parent in frontier for item in dependencies.get(parent,())
                      if item in produced and item not in seen}
            if not children:
                return False
            # A real receipt ends this pass. The next step starts from fresh
            # backpack stock and replans before descending another level.
            if self._fetch({item:self.held.get(item,0)+produced[item] for item in sorted(children)}):
                return True
            seen.update(children)
            frontier=children
        return False

    def _step(self, targets):
        if self._consume_ready_build(targets):
            return
        self.prerequisites = {item: count for item, count in self.prerequisites.items()
                              if self.held.get(item, 0) < count}
        self._write(requirements=self.prerequisites)
        if self.prerequisites:
            item, count = next(iter(self.prerequisites.items()))
            targets = {item: self._fit_batch(item, count)}
        elif self.request['mode'] == 'projection':
            if not targets:
                raise JobBlocked('投影仍有未匹配方块，但差料为空，需要原生核验处理')
            targets = self._projection_batch(targets)
            if targets is None:
                return
        else:
            targets = self._item_batch(targets)
            if targets is None:
                return
        self._write('planning', '计算材料净缺口')
        planned = self._plan(targets)
        write_json(self.out / 'plan.json', planned)
        wanted = {item: count for item, count in targets.items() if self.held.get(item, 0) < count}
        # Once an item output has had a depot pass, a later batch can use a
        # complete craft-only plan from fresh backpack stock. Its larger
        # absolute target must not send us back through the same chests first.
        local_craft = (self.request['mode'] == 'item' and not self.prerequisites
                       and bool(wanted) and all(item in self.fetch_tried for item in wanted)
                       and not planned['missing_supplies']
                       and any(step['kind'] == 'craft' for step in planned['steps'])
                       and all(step['kind'] in ('craft', 'reserve') for step in planned['steps']))
        peak_slots = self._peak_slots(planned) if local_craft else None
        local_craft = local_craft and peak_slots <= 35
        if not local_craft:
            if self._fetch(wanted):
                return
            if self._fetch_intermediates(targets, planned):
                return
        workspace = any(step['kind'] in ('craft', 'smelt', 'harden') for step in planned['steps'])
        if peak_slots is None:
            peak_slots = self._peak_slots(planned)
        if peak_slots > (35 if workspace else 36):
            self._make_room(targets, planned, '最小加工批次仍缺少背包周转空间，请先腾出位置')
            return
        for step in planned['steps']:
            kind, item = step['kind'], step['item']
            if kind == 'reserve':
                continue
            if kind == 'acquire':
                count = self.held.get(item, 0) + step['count']
                if self._fetch({item: count}):
                    return
                receipt = self._call('acquire', [item, count], 'gathering', {item: count})
                if receipt.get('phase') == 'waiting' and receipt.get('code') == 'quarry_backpack_reserve':
                    # The adapter has confirmed the exact stopped native request
                    # and rescanned its remaining blocks. Finish that transaction
                    # before unloading byproducts; the next acquisition replans
                    # from actual blocks instead of replaying a mining request.
                    self._make_room(targets, planned, '采坑需要卸货，但当前没有安全的副产物存放方式')
                return
            count = self.held.get(item, 0) + step['produced']
            if any(self.held.get(source, 0) < n for source, n in step['ingredients'].items()):
                raise JobBlocked('配方原料尚未真实进入背包')
            if kind == 'harden':
                self._call('harden', [item, count], 'hardening', {item: count})
            elif kind == 'smelt':
                self._call('smelt', [step, count], 'smelting', {item: count})
            else:
                self._call('craft', [{item: count}], 'crafting', {item: count})
            return
        raise JobBlocked('未找到可执行的材料步骤；保留当前目标等待补全能力')

    def run(self):
        if self.backend is None:
            raise ValueError('A concrete backend must be attached before execution')
        try:
            self._write('planning','前往投影并核对缺料' if self.request['mode']=='projection' else '核对背包与材料')
            self._observe(initial=True)
            self._recover()
            while True:
                targets = self._observe()
                if self._complete(targets):
                    self._write('completed', '任务完成', terminal=True)
                    break
                self._step(targets)
        except JobCancelled as error:
            self._write('cancelled', '已取消', str(error), terminal=True)
        except JobPaused as error:
            self._write('paused', '等待继续', str(error), terminal=False)
        except JobBlocked as error:
            self._write('blocked', '需要处理', str(error), terminal=True)
        except Exception as error:
            self._event('failure', error_type=type(error).__name__, detail=str(error)[:500])
            self._write('failed', '执行失败', str(error), terminal=True)
        finally:
            try:
                self.backend.finish()
            except Exception as error:
                self._event('finish_failed', error_type=type(error).__name__, detail=str(error)[:500])
                prior_state,prior_detail=self.state['state'],self.state.get('detail','')
                self._write('blocked', '收尾尚未确认', str(error), terminal=True,
                            work_state_before_finish=prior_state,work_detail_before_finish=prior_detail)
        return dict(self.state)
