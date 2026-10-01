"""Real, bounded furnace/concrete adapters under an existing MaterialClient lease.

All counts are final backpack totals. Existing or uncertain work is journaled,
never overwritten or reloaded. No client is created, no model is consulted.
"""
import json
import math
from pathlib import Path
import time

from build_supervisor import stocks
from furnace_bank import inspect_bank
from furnace_batches import collect, distribution, snapshot, wait_loading_balance
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json
from projection_material_plan import ProcessingCatalog
from shore_concrete import convert, block_state, position_for_batch
from concrete_shelter import enter_station, exit_station, choose_hatch_item
from concrete_soil import resolve as resolve_support
from drop_collection import collect_drop
from .planning import COLORS
from .protocol import JobBlocked, JobCancelled, JobPaused
from smelting_fuel import FuelCatalog, policy as fuel_policy, select_fuels


class CheckpointClient:
    """Retain the real client and menu ownership while checking public operations.

    The backend's poll-aware client must additionally check inside a long native
    request. This wrapper does not monkey-patch raw() or steal its revision lock.
    """
    def __init__(self, client, checkpoint):
        object.__setattr__(self, '_client', client)
        object.__setattr__(self, '_checkpoint', checkpoint)

    def __getattr__(self, key):
        return getattr(self._client, key)

    def __setattr__(self, key, value):
        setattr(self._client, key, value)

    def status(self):
        self._checkpoint()
        return self._client.status()

    def request(self, op, **params):
        self._checkpoint()
        result = self._client.request(op, **params)
        self._checkpoint()
        return result

    def checked(self, op, **params):
        self._checkpoint()
        result = self._client.checked(op, **params)
        self._checkpoint()
        return result


def _positions(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 16
            or any(not isinstance(pos, list) or len(pos) != 3 or any(type(v) is not int for v in pos) for pos in value)
            or len({tuple(pos) for pos in value}) != len(value)):
        raise JobBlocked('请先配置允许使用的普通熔炉坐标（1–16 个，不重复）')
    return value


def _target(value):
    if type(value) is not int or not 1 <= value <= 100000:
        raise JobBlocked('加工目标必须是正整数背包总量')
    return value


def _recipe(recipe, profile):
    jar = profile.get('recipe_jar')
    if not jar:
        raise JobBlocked('缺少当前客户端配方文件，不能猜测熔炼配方')
    catalog = ProcessingCatalog(jar)
    key, source, output = recipe.get('recipe_id'), recipe.get('source'), recipe.get('output', recipe.get('item'))
    found = next((r for r in catalog.recipes.get(output, []) if r.id == key and key in catalog.smelting), None)
    if (found is None or found.count != 1 or len(found.cells) != 1 or source not in found.cells[0][1]
            or source == output):
        raise JobBlocked('配方不是当前游戏可验证的普通 1:1 熔炼配方')
    ticks = catalog.smelting[key]['cooking_ticks_per_recipe']
    if ticks > 102400:
        raise JobBlocked('单件熔炼时间超过当前燃料批次能力')
    return {'recipe_id': key, 'source': source, 'output': output, 'cooking_ticks': ticks}


def _manifest(c, out, specification, filename):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    if path.exists():
        job = json.loads(path.read_text())
        if (job.get('world_session') != c.world or any(job.get(key) != value for key, value in specification.items())):
            raise JobBlocked('旧加工账本的世界或目标不同，不能重用')
    else:
        job = {'schema': 1, 'world_session': c.world, **specification, 'complete': False, 'batches': []}
        write_json(path, job)
    return path, job


def _load_batch(c, positions, spec, amount, journal, fuel_plan=None):
    """Generalize the existing stone loader using its verified slot primitives."""
    if journal.exists():
        raise JobBlocked('已有装炉账本，不能重复投料')
    parts = distribution(amount, len(positions))
    if fuel_plan is None:
        fuel_plan={'ready':True,'entries':[{'fuel_item':'minecraft:coal','fuel':math.ceil(n*spec['cooking_ticks']/1600),
                   'burn_ticks_per_fuel':1600} if n else None for n in parts],
                   'retained_counts':{},'evidence':{'kind':'legacy_coal_only'}}
    if not fuel_plan.get('ready') or len(fuel_plan.get('entries',[]))!=len(parts):
        raise JobBlocked('整批实际燃料尚未准备，不装入部分炉子')
    entries = [{'pos': pos, 'amount': n, **choice, 'stage':'planned'}
               for pos,n,choice in zip(positions,parts,fuel_plan['entries']) if n]
    job = {'world_session': c.world, 'source': spec['source'], 'output': spec['output'],
           'amount': amount, 'recipe_id': spec['recipe_id'], 'cooking_ticks': spec['cooking_ticks'],
           'furnaces': entries, 'complete': False, 'fuel_plan':fuel_plan}
    write_json(journal, job)
    for entry in entries:
        state = snapshot(c, entry['pos'])
        if any(row['count'] for row in state['menu']['slots'][:3]) or state['menu']['cursor']['count']:
            raise JobBlocked('指定熔炉已有物品，不能当成空炉覆盖')
        session, menu = InventorySession(c), state['menu']['id']
        entry.update(stage='prepared', loaded_source=0, loaded_fuel=0)
        write_json(journal, job)
        for item, cell, total, key in ((spec['source'], 0, entry['amount'], 'loaded_source'),
                                       (entry['fuel_item'], 1, entry['fuel'], 'loaded_fuel')):
            while entry[key] < total:
                state = wait_loading_balance(c, c.status(), spec['source'], spec['output'],
                                             entry['loaded_source'], entry['loaded_fuel'], menu,entry['fuel_item'])
                source = max((r for r in state['menu']['slots'][3:] if r['item'] == item and r['count']),
                             key=lambda row: row['count'], default=None)
                if source is None:
                    raise JobBlocked('装炉期间材料不足，保留已装物品，不重发')
                count = min(total - entry[key], source['count'])
                before = stocks(state).get(item, 0)
                if cell==1:
                    kept=fuel_plan.get('retained_counts',{}).get(item,0)
                    remaining_input=amount-sum(e.get('loaded_source',0) for e in entries) if item==spec['source'] else 0
                    if item==spec['output'] or before-kept-remaining_input<count:
                        raise JobBlocked('实际余量触及保留材料；不继续装燃料')
                entry.update(stage='input_loading' if cell == 0 else 'fuel_loading',
                             pending={'item': item, 'count': count, 'inventory_before': before})
                write_json(journal, job)
                state = session.place_cell(state, source, cell, count, append=True)
                if stocks(state).get(item, 0) != before - count:
                    raise JobBlocked('装炉库存变化未确认，保留未完成回执')
                loaded_source = entry['loaded_source'] + (count if cell == 0 else 0)
                loaded_fuel = entry['loaded_fuel'] + (count if cell == 1 else 0)
                wait_loading_balance(c, state, spec['source'], spec['output'], loaded_source, loaded_fuel, menu,entry['fuel_item'])
                entry[key] += count
                entry['pending'] = None
                write_json(journal, job)
            entry['stage'] = 'input_loaded' if cell == 0 else 'loaded'
            write_json(journal, job)
        c.checked('close_menu')
    job['loaded_at'] = time.time()
    write_json(journal, job)
    return job


def _wait_collect(c, journal, spec, checkpoint):
    job = json.loads(journal.read_text())
    if (job.get('world_session') != c.world or job.get('source') != spec['source']
            or job.get('output') != spec['output'] or job.get('recipe_id') != spec['recipe_id']
            or not job.get('furnaces')
            or sum(e['amount'] for e in job['furnaces']) != job.get('amount')
            or any(e.get('stage') not in ('loaded', 'output_collected', 'collected') or e.get('pending') for e in job['furnaces'])):
        raise JobBlocked('装炉只完成一部分或含未知操作，先核对炉内现物，不能自动重投')
    deadline = time.monotonic() + max(120, max(e['amount'] for e in job['furnaces']) * spec['cooking_ticks'] / 20 + 120)
    next_poll = 0
    while True:
        checkpoint()
        if time.monotonic() >= deadline:
            raise JobBlocked('熔炼等待达到上限，保留已装炉批次')
        if time.monotonic() >= next_poll:
            if collect(c, journal):
                return json.loads(journal.read_text())
            next_poll = time.monotonic() + 10
        time.sleep(.25)


def smelt(c, recipe, target_count, profile, out, checkpoint):
    """Use existing empty ordinary furnaces and recover acknowledged batches."""
    client = c if isinstance(c, CheckpointClient) else CheckpointClient(c, checkpoint)
    try:
        target_count = _target(target_count)
        spec = _recipe(recipe, profile)
        positions = _positions(profile.get('furnace_positions'))
        path, job = _manifest(client, out, {'kind':'smelt', 'target':target_count, **spec,
                                          'positions':positions}, 'smelting.json')
        if profile.get('furnace_bank_journal'):
            inspect_bank(client, positions, profile['furnace_bank_journal'])
        while True:
            checkpoint()
            pending = next((b for b in job['batches'] if not b.get('complete')), None)
            if pending:
                journal = Path(out) / pending['journal']
                done = _wait_collect(client, journal, spec, checkpoint)
                pending.update(complete=True, receipt=done)
                write_json(path, job)
            held = stocks(client.status())
            if held.get(spec['output'], 0) >= target_count:
                job['complete'] = True
                job['verified_output_count'] = held.get(spec['output'], 0)
                consumption={}
                for batch in job['batches']:
                    for furnace in batch.get('receipt',{}).get('furnaces',[]):
                        item=furnace.get('fuel_item','minecraft:coal')
                        row=consumption.setdefault(item,{'loaded':0,'returned':0,'consumed':0,'known':True})
                        values=(furnace.get('loaded_fuel',furnace.get('fuel')),furnace.get('fuel_returned'),furnace.get('fuel_consumed'))
                        if any(type(n) is not int for n in values):
                            row['known']=False
                        else:
                            for key,n in zip(('loaded','returned','consumed'),values):row[key]+=n
                for row in consumption.values():
                    if not row['known']:row.update(loaded=None,returned=None,consumed=None)
                job['fuel_consumption']=consumption
                write_json(path, job)
                return {'phase':'done', 'item':spec['output'], 'count':held[spec['output']],
                        'fuel_consumption':consumption,'journal':str(path)}
            if job.get('complete'):
                raise JobBlocked('这份加工账本已经完成，成品随后已移动；不能重复生产同一回执')
            per_furnace = min(64, 102400 // spec['cooking_ticks'])
            amount = min(target_count - held.get(spec['output'], 0), len(positions) * per_furnace)
            parts = distribution(amount, len(positions))
            catalog=FuelCatalog(profile['recipe_jar'])
            keep,allowed=fuel_policy(catalog,profile,recipe,client)
            fuels=select_fuels(catalog,held,parts,spec['cooking_ticks'],spec['source'],spec['output'],keep,allowed)
            if not fuels['ready']:
                return {'phase':'waiting', 'detail':'先补齐本批实际原料与合法燃料',
                        'requirements':fuels['requirements'],'fuel_choices':fuels,'journal':str(path)}
            # Inspect every furnace before the first loading click.
            for pos in positions:
                observed = snapshot(client, pos)
                if any(row['count'] for row in observed['menu']['slots'][:3]) or observed['menu']['cursor']['count']:
                    raise JobBlocked('指定熔炉有未处理物品，请先收回或选择空炉')
                client.checked('close_menu')
            entry = {'journal':'batch-%04d.json' % (len(job['batches']) + 1), 'complete':False, 'amount':amount}
            job['batches'].append(entry)
            write_json(path, job)
            _load_batch(client, positions, spec, amount, Path(out) / entry['journal'],fuels)
    except (JobCancelled, JobPaused):
        raise
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        return {'phase':'blocked', 'detail':str(error), 'journal':str(Path(out)/'smelting.json')}


def harden(c, item, target_count, profile, out, checkpoint):
    """Convert carried powder in bounded, verified shoreline batches."""
    client = c if isinstance(c, CheckpointClient) else CheckpointClient(c, checkpoint)
    try:
        target_count = _target(target_count)
        if item not in {'minecraft:'+color+'_concrete' for color in COLORS}:
            raise JobBlocked('仅支持原版混凝土粉末固化')
        station = profile.get('concrete_station')
        if not isinstance(station, dict) or not station.get('expected_state'):
            raise JobBlocked('请先配置并核验混凝土固化工位')
        support = station.get('support')
        if not isinstance(support, list) or len(support) != 3 or any(type(v) is not int for v in support):
            raise JobBlocked('固化工位的支撑坐标无效')
        powder = item+'_powder'
        batch_size = station.get('batch_size', 8)
        if type(batch_size) is not int or not 1 <= batch_size <= 16:
            raise JobBlocked('固化小批数量需在1–16之间')
        shelter_path = str(Path(station['shelter_ledger']).resolve()) if station.get('shelter_ledger') else None
        path, job = _manifest(client, out, {'kind':'harden','item':item,'target':target_count,
                                          'support':support,'shelter_ledger':shelter_path}, 'hardening.json')
        entered = False
        shelter = None
        if shelter_path:
            shelter = json.loads(Path(shelter_path).read_text())
            layout = shelter.get('layout', {})
            if layout.get('cell') != [support[0], support[1]+1, support[2]]:
                raise JobBlocked('固化支撑位置与已核验围护工位不一致')
            if station.get('stand_block') != [layout['stand'][0], layout['stand'][1]-1, layout['stand'][2]]:
                raise JobBlocked('围护固化工位需要对应的干燥站立方块')
            if job.get('shelter', {}).get('phase') not in (None, 'outside'):
                client.material_job_shelter = dict(job['shelter'])
                client.material_job_shelter_ledger = dict(shelter, path=shelter_path)
        def save_shelter(phase):
            state = {'path':shelter_path,'world_session':client.world,'phase':phase}
            client.material_job_shelter = state
            job['shelter'] = state
            write_json(path, job)
        def enter():
            nonlocal entered, shelter
            if shelter_path and not entered:
                checkpoint()
                save_shelter('entering')
                shelter = enter_station(client, shelter_path)
                client.material_job_shelter_ledger = shelter
                entered = True
                save_shelter('inside')
        def leave():
            nonlocal entered
            if entered:
                checkpoint()
                save_shelter('exiting')
                exit_station(client, shelter)
                entered = False
                save_shelter('outside')
        if any(not b.get('complete') for b in job['batches']):
            raise JobBlocked('上批粉末固化的收取尚未确认，先核对现场，不重复放置')
        while True:
            checkpoint()
            before = stocks(client.status())
            if before.get(item, 0) >= target_count:
                leave()
                job['complete'] = True
                write_json(path, job)
                return {'phase':'done','item':item,'count':before[item],'journal':str(path)}
            if job.get('complete'):
                raise JobBlocked('已完成固化账本不能用于补做随后移走的成品')
            amount = min(64, target_count - before.get(item, 0))
            if before.get(powder, 0) < amount:
                leave()
                return {'phase':'waiting','detail':'先取得本批混凝土粉末','requirements':{powder:amount},'journal':str(path)}
            if shelter_path and not entered and choose_hatch_item(client.status()) is None:
                return {'phase':'waiting','detail':'固化工位需要一块临时封口材料，先自动补料',
                        'requirements':{'minecraft:cobblestone':1},'journal':str(path)}
            enter()
            before = stocks(client.status())
            amount = min(64, target_count - before.get(item, 0))
            if amount <= 0:
                continue
            if before.get(powder, 0) < amount:
                leave()
                return {'phase':'waiting','detail':'进入工位后粉末数量变化，先核对库存','requirements':{powder:amount},'journal':str(path)}
            entry = {'powder_before':before.get(powder,0),'solid_before':before.get(item,0),
                     'amount':amount,'complete':False,'observed_batches':[],
                     'before_drop_uuids':[e.get('uuid') for e in client.status().get('entities',[])
                                          if e.get('type')=='minecraft:item']}
            job['batches'].append(entry)
            write_json(path, job)
            def progress(count):
                fresh = stocks(client.status())
                entry['observed_batches'].append({'confirmed_step':count,'powder':fresh.get(powder,0),'solid':fresh.get(item,0)})
                write_json(path, job)
                checkpoint()
            receipt = convert(client, support, station['expected_state'], powder, item, amount,
                              batch_size=batch_size, out=Path(out)/('convert-%04d' % len(job['batches'])),
                              waypoint=station.get('waypoint'), staging=station.get('staging'),
                              stand_block=station.get('stand_block'), on_progress=progress)
            after = stocks(client.status())
            recovered = amount + receipt.get('residual_recovered', 0)
            if before.get(powder,0)-after.get(powder,0) != amount or after.get(item,0)-before.get(item,0) != recovered:
                raise JobBlocked('粉末消耗与新成品数量不守恒，不重复固化')
            entry.update(complete=True, receipt=receipt, powder_after=after.get(powder,0), solid_after=after.get(item,0))
            write_json(path, job)
    except (JobCancelled, JobPaused):
        raise
    except (RuntimeError, ValueError, KeyError, OSError) as error:
        return {'phase':'blocked','detail':str(error),'journal':str(Path(out)/'hardening.json')}


def _idle(c):
    state = c.status()
    if (state.get('phase') == 'running' or state.get('guard_busy')
            or any(state.get(key) for key in ('borer_active','chopping','navigating','native_material_busy'))
            or state.get('build_job',{}).get('active')):
        raise JobBlocked('原生动作尚未停稳，不能核销中断加工')
    return state


def _recover_hardening(c, item, count, profile, out, checkpoint):
    path = Path(out) / 'hardening.json'
    job = json.loads(path.read_text())
    station = profile.get('concrete_station', {})
    if (job.get('world_session') != c.world or job.get('item') != item or job.get('target') != count
            or job.get('support') != station.get('support')):
        raise JobBlocked('中断固化账本的世界、物品或工位不一致')
    powder, support = item+'_powder', job['support']
    cell = [support[0],support[1]+1,support[2]]
    unfinished = [entry for entry in job['batches'] if not entry.get('complete')]
    if len(unfinished) > 1:
        raise JobBlocked('存在多批未确认的固化，不猜测先后顺序')
    for entry in unfinished:
        recovery_shelter = None
        state = _idle(c)
        held = stocks(state)
        used = entry['powder_before']-held.get(powder,0)
        received = held.get(item,0)-entry['solid_before']
        verified = entry.get('observed_batches', [])
        residual_credit = (1 if verified and verified[0]['powder']==entry['powder_before']
                           and verified[0]['solid']==entry['solid_before']+1 else 0)
        if not 0 < used <= entry['amount'] or not 0 <= received <= used+residual_credit:
            raise JobBlocked('粉末消耗或成品净增无法证明；不重发未确认放置')
        rows = c.request('scan',min=list(support),max=cell,details=True)['blocks']
        expected = resolve_support(rows,support,station['expected_state'])
        current = block_state(rows,cell)
        if current == f'Block{{{item}}}':
            if received+1 > used+residual_credit:
                raise JobBlocked('工位现有混凝土不属于本批欠收数量')
            if station.get('shelter_ledger'):
                ledger = enter_station(c,station['shelter_ledger'])
                c.material_job_shelter_ledger = ledger
                c.material_job_shelter = {'path':str(Path(station['shelter_ledger']).resolve()),
                                         'world_session':c.world,'phase':'inside'}
                job['shelter'] = c.material_job_shelter
                write_json(path,job)
                recovery_shelter = ledger
            position_for_batch(c,support,expected,station.get('stand_block'))
            state = _idle(c);current_held=stocks(state)
            if (current_held.get(powder,0)!=entry['powder_before']-used
                    or current_held.get(item,0)-entry['solid_before']+1>used+residual_credit):
                raise JobBlocked('接近残余工作格时数量变化，停止恢复')
            picks = [row for row in state.get('inventory',[]) if row.get('slot',99)<36
                     and row.get('item') in ('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')
                     and row.get('durability',0)>8]
            if not picks:
                raise JobBlocked('缺少可用镐，保留工位的欠收混凝土')
            tool = max(picks,key=lambda row:row['durability'])
            entry['residual_recovery'] = {'stage':'mining','pos':cell,
                'before_drop_uuids':[e.get('uuid') for e in c.status().get('entities',[]) if e.get('type')=='minecraft:item']}
            write_json(path,job)
            c.checked('select_item',item=tool['item'],slot=tool['slot'])
            c.checked('mine_block',pos=cell,face='up',expected_state=current,seconds=15)
        elif current not in ('Block{minecraft:air}','Block{minecraft:cave_air}') and not current.startswith('Block{minecraft:water}'):
            raise JobBlocked('固化工作格存在未确认占用，不能继续')
        # Only this batch's new drops can close a proven powder/output deficit.
        for _ in range(4):
            state = _idle(c);held=stocks(state)
            deficit=used+residual_credit-(held.get(item,0)-entry['solid_before'])
            if deficit==0:
                break
            if deficit<0 or held.get(powder,0)!=entry['powder_before']-used:
                raise JobBlocked('恢复时物料数量又发生变化')
            prior_ids=entry.get('residual_recovery',{}).get('before_drop_uuids',entry.get('before_drop_uuids'))
            if not isinstance(prior_ids,list):
                raise JobBlocked('缺少加工前掉落物记录，不能猜测物品归属')
            prior=set(prior_ids)
            candidates=[e for e in state.get('entities',[]) if e.get('type')=='minecraft:item'
                        and e.get('uuid') not in prior and e.get('stack',{}).get('item')==item
                        and 0<e['stack'].get('count',0)<=deficit and len(e.get('pos',[]))==3
                        and sum((e['pos'][i]-cell[i]-.5)**2 for i in range(3))<=36]
            if len(candidates)!=1:
                raise JobBlocked('欠收固化物没有唯一、可验证的新掉落物')
            entry['pickup_recovery']={'uuid':candidates[0]['uuid'],'count':candidates[0]['stack']['count']}
            write_json(path,job)
            if not collect_drop(c,candidates[0],observation=state,seconds=15):
                raise JobBlocked('固化掉落物拾取未确认，不重放粉末')
        held=stocks(_idle(c))
        rows=c.request('scan',min=cell,max=cell)['blocks'];current=block_state(rows,cell)
        if (held.get(powder,0)!=entry['powder_before']-used
                or held.get(item,0)-entry['solid_before']!=used+residual_credit
                or current not in ('Block{minecraft:air}','Block{minecraft:cave_air}') and not current.startswith('Block{minecraft:water}')):
            raise JobBlocked('固化恢复未同时满足库存守恒与工作格清空')
        entry.update(complete=True,recovered=True,recovered_powder_used=used,
                     recovered_solid=used+residual_credit,unspent=entry['amount']-used)
        write_json(path,job)
        if recovery_shelter is not None:
            checkpoint()
            exit_station(c,recovery_shelter)
            c.material_job_shelter={**c.material_job_shelter,'phase':'outside'}
            job['shelter']=c.material_job_shelter
            write_json(path,job)
    # Only after the old powder balance has been closed may new powder be used.
    return harden(c,item,count,profile,out,checkpoint)


def recover(c, operation, args, profile, original_out, checkpoint):
    """Reconcile original receipts first; uncertain half-loading is never replayed."""
    client=c if isinstance(c,CheckpointClient) else CheckpointClient(c,checkpoint)
    try:
        _idle(client)
        if operation=='smelt':
            recipe,target=args
            manifest=json.loads((Path(original_out)/'smelting.json').read_text())
            if not manifest.get('batches'):
                raise JobBlocked('没有完整装炉回执，不能把未知动作当成已执行')
            for batch in manifest['batches']:
                ledger=json.loads((Path(original_out)/batch['journal']).read_text())
                if any(entry.get('stage') not in ('loaded','output_collected','collected') or entry.get('pending') for entry in ledger.get('furnaces',[])):
                    raise JobBlocked('存在半投料或未知点击，保留炉内物品，不重投')
            result=smelt(client,recipe,target,profile,original_out,checkpoint)
            item=recipe.get('output',recipe.get('item'))
        elif operation=='harden':
            item,target=args
            result=_recover_hardening(client,item,target,profile,original_out,checkpoint)
        else:
            raise JobBlocked('不是可恢复的材料加工操作')
        verified=stocks(_idle(client)).get(item,0)>=target
        return {**result,'safe_to_replan':result.get('phase')=='done' and verified}
    except (JobCancelled,JobPaused):
        raise
    except (RuntimeError,ValueError,KeyError,OSError,TypeError) as error:
        return {'phase':'blocked','detail':str(error),'safe_to_replan':False}
