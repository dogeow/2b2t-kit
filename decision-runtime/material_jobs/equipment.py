"""Borrow a suitable owned tool and temporarily store unsuitable pickaxes.

Never discard tools or borrow from an unapproved chest. Every exact variant is
returned during normal material cleanup; interruptions retain a location receipt.
"""
import json
import math
from pathlib import Path
import time

from container_access import open_grounded_chest
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json
from material_cleanup import register, complete
from material_plan import inventory_counts
from packed_supplies import open_box, matching_source, take_box
from .acquisition import ROCK_SOURCES, LOGS
from .snow_harvest import SNOW, SNOW_BLOCK, SNOWBALL
from .protocol import server_key


def identity(row):
    return (row.get('item'),row.get('durability'),
            tuple(sorted((v['id'],v['level']) for v in row.get('enchantments',[]))))


def is_silk(row):
    return row.get('count',0)>0 and row.get('item','').endswith('_pickaxe') and has_silk_touch(row)


def has_silk_touch(row):
    return any(isinstance(e,dict) and e.get('id')=='minecraft:silk_touch'
               and type(e.get('level')) is int and e['level']>0
               for e in row.get('enchantments',[]))


def needs_pickaxe_storage(row,minimum=0):
    return (row.get('count',0)>0 and row.get('item','').endswith('_pickaxe')
            and (is_silk(row) or row.get('durability',0)<minimum))


def wait(c,predicate):
    end=time.monotonic()+6
    while True:
        state=c.status()
        if predicate(state):
            return state
        if time.monotonic()>=end:
            raise RuntimeError('工具移动未得到确认；不重复点击')
        time.sleep(.15)


def restore(c,path):
    path=Path(path)
    journal=json.loads(path.read_text())
    if journal.get('world_session')!=c.world:
        raise RuntimeError('工具寄存记录属于另一世界会话，保留原位置')
    _restore_stored(c,path,journal)


def _stored_entries(journal,exact_slots=False):
    tools=journal.get('tools')
    if not isinstance(tools,list) or any(not isinstance(e,dict) or e.get('state') not in ('stored','returned') for e in tools):
        raise RuntimeError('工具寄存结果不确定，先核对仓库')
    if exact_slots and any(e['state']=='stored' and (
            type(e.get('chest_slot')) is not int or e['chest_slot']<0
            or not isinstance(e.get('pos'),list) or len(e['pos'])!=3
            or any(type(v) is not int for v in e['pos'])
            or not isinstance(e.get('tool'),dict) or e['tool'].get('count')!=1
            or not e['tool'].get('item','').endswith('_pickaxe')
            or type(e['tool'].get('durability')) is not int
            or not isinstance(e['tool'].get('enchantments'),list)) for e in tools):
        raise RuntimeError('工具寄存记录缺少准确仓库槽位或属性，不能跨会话恢复')
    return tools


def restore_after_reconnect(c,journal_path,previous_snapshot):
    """Recover the same player's stored variants after an explicit reconnect.

    The caller supplies a preserved native reply, not a newly invented scope.
    This entry never reconnects, clears a hold, or changes the journal's world.
    """
    path=Path(journal_path);journal=json.loads(path.read_text())
    if journal.get('world_session')==c.world:
        return restore(c,path)
    _stored_entries(journal,exact_slots=True)
    old=previous_snapshot
    if (not isinstance(old,dict) or old.get('connected') is not True
            or not isinstance(old.get('id'),str) or not old['id']
            or type(old.get('bridge_version')) is not int or old['bridge_version']<1
            or type(old.get('time')) is not int or old['time']<=0
            or type(old.get('control_revision')) is not int or old['control_revision']<0
            or not isinstance(old.get('inventory'),list)
            or not isinstance(old.get('menu'),dict) or not isinstance(old['menu'].get('slots'),list)
            or not isinstance(old['menu'].get('cursor'),dict)
            or not isinstance(old.get('world_session'),str) or not old['world_session']
            or old['world_session']!=journal.get('world_session')
            or any(not isinstance(old.get(k),str) or not old[k] for k in ('server','dimension','player_uuid'))):
        raise RuntimeError('缺少属于原寄存会话的完整原生回执，不能跨会话恢复')
    recovery_world=c.world

    def validate(state):
        if (not isinstance(state,dict) or state.get('connected') is not True
                or not isinstance(recovery_world,str) or not recovery_world or recovery_world==old['world_session']
                or c.world!=recovery_world or state.get('world_session')!=recovery_world
                or not isinstance(state.get('server'),str) or not state['server']
                or server_key(state['server'])!=server_key(old['server'])
                or state.get('dimension')!=old['dimension'] or state.get('player_uuid')!=old['player_uuid']):
            raise RuntimeError('恢复工具的玩家、服务器、维度或新会话不一致')
        health=state.get('health')
        hold=state.get('safety_hold')
        if (state.get('manual_movement') is not False or type(health) not in (int,float)
                or not math.isfinite(health) or health<18 or state.get('health_recovery_hold') is not False
                or not isinstance(hold,dict) or hold.get('active') is not False):
            raise RuntimeError('当前未确认健康、无手动接管且安全锁已解除，不能恢复工具')
        # Use the existing native + script interlock; it has no unlock API.
        if hasattr(c,'root'):
            from safety_interlock import require_unlocked
            require_unlocked(c.root,state)

    current=c.status();validate(current)
    if type(current.get('time')) is not int or current['time']<old['time']:
        raise RuntimeError('当前观察时间早于原寄存回执，不能恢复工具')
    evidence={'previous_world_session':old['world_session'],'world_session':recovery_world,
              'player_uuid':old['player_uuid'],'server':server_key(old['server']),'dimension':old['dimension'],
              'previous_snapshot_id':old['id'],'previous_observed_at':old['time'],
              'observed_at':current['time']}
    journal.setdefault('recoveries',[]).append(evidence);write_json(path,journal)
    _restore_stored(c,path,journal,validate=validate)


def _restore_stored(c,path,journal,validate=None):
    _stored_entries(journal)
    for entry in journal['tools']:
        if entry['state']=='returned':
            continue
        if validate:validate(c.status())
        state=open_grounded_chest(c,entry['pos'])
        if validate:validate(state)
        menu=state['menu']
        if menu.get('type')!='ChestMenu' or menu['cursor']['count']:
            raise RuntimeError('恢复工具需要原仓库和空光标，未移动物品')
        if (not any(0<=r.get('slot',-1)<36 and not r.get('count') for r in state['inventory'])
                or not any(not r['count'] for r in menu['slots'][-36:])):
            raise RuntimeError('背包没有空槽取回寄存工具，保持原仓库位置')
        sources=[r for r in state['menu']['slots'][:-36] if r.get('count') and identity(r)==identity(entry['tool'])
                 and (entry.get('chest_slot') is None or r['slot']==entry['chest_slot'])]
        if len(sources)!=1 or sources[0]['count']!=1:
            raise RuntimeError('寄存工具的原槽位或属性改变，不能猜测取走另一把')
        before=sum(r.get('count',0) for r in state['inventory'] if r.get('slot',99)<36 and identity(r)==identity(entry['tool']))
        source=sources[0]
        stored_before=sum(r.get('count',0) for r in menu['slots'][:-36] if identity(r)==identity(entry['tool']))
        entry['state']='returning';write_json(path,journal)
        InventorySession(c).click(state,source['slot'],'quick_move')
        def returned(s):
            if validate:validate(s)
            current=s['menu']
            return (current['id']==menu['id'] and current.get('type')=='ChestMenu'
                    and not current['cursor']['count'] and not current['slots'][source['slot']]['count']
                    and sum(r.get('count',0) for r in current['slots'][:-36] if identity(r)==identity(entry['tool']))==stored_before-1
                    and sum(r.get('count',0) for r in s['inventory'] if 0<=r.get('slot',99)<36 and identity(r)==identity(entry['tool']))==before+1)
        wait(c,returned)
        entry['state']='returned';write_json(path,journal)
        c.checked('close_menu')
    complete(c,str(path))


def store_silk(c,profile,out,minimum=0):
    """Keep the existing journal/cleanup path; minimum=0 preserves legacy silk-only calls."""
    if type(minimum) is not int or minimum<0:raise ValueError('Tool reserve must be a nonnegative integer')
    state=c.status()
    tools=[r for r in state['inventory'] if needs_pickaxe_storage(r,minimum)]
    if not tools:
        return
    if any(r.get('slot',99)>=36 for r in tools):
        raise RuntimeError('副手不适合本次采集的镐需要先放入背包，再开始普通矿物采集')
    path=out/'silk-tools.json'
    journal=json.loads(path.read_text()) if path.exists() else {'world_session':c.world,'tools':[]}
    if journal.get('world_session')!=c.world:
        raise RuntimeError('工具寄存记录属于另一世界会话，保留原位置')
    if any(e['state'] not in ('stored','returned') for e in journal['tools']):
        raise RuntimeError('前次工具移动未确认，保留寄存记录')
    for tool in tools:
        stored=False
        for pos in profile.get('depots',[]):
            state=open_grounded_chest(c,pos)
            if not any(not r['count'] for r in state['menu']['slots'][:-36]):
                c.checked('close_menu');continue
            source=next((r for r in state['menu']['slots'][-36:] if r.get('count') and identity(r)==identity(tool)),None)
            if source is None:
                raise RuntimeError('准备寄存的工具已改变')
            before=sum(r.get('count',0) for r in state['menu']['slots'][:-36] if identity(r)==identity(tool))
            empty_before={r['slot'] for r in state['menu']['slots'][:-36] if not r['count']}
            entry={'pos':pos,'tool':tool,'state':'storing','minimum_durability':minimum,
                   'reason':'silk_touch' if is_silk(tool) else 'durability_below_minimum'}
            journal['tools'].append(entry);write_json(path,journal)
            register(c,str(path),lambda:restore(c,path))
            InventorySession(c).click(state,source['slot'],'quick_move')
            arrived=wait(c,lambda s: not s['menu']['cursor']['count'] and
                 sum(r.get('count',0) for r in s['menu']['slots'][:-36] if identity(r)==identity(tool))==before+1)
            added=[r['slot'] for r in arrived['menu']['slots'][:-36] if r['slot'] in empty_before
                   and r.get('count')==1 and identity(r)==identity(tool)]
            if len(added)!=1:
                raise RuntimeError('无法确认工具新增的准确仓库槽位，保留寄存记录')
            entry['chest_slot']=added[0]
            entry['state']='stored';write_json(path,journal)
            c.checked('close_menu');stored=True;break
        if not stored:
            raise RuntimeError('允许取料的仓库没有工具寄存空间')


def prepare(c,item,target,profile,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    kind='pickaxe' if item in ROCK_SOURCES else 'axe' if item in LOGS else 'shovel'
    minimum=700 if kind=='pickaxe' else min(512,max(96,target-inventory_counts(c.status()).get(item,0)+32))
    grass=item=='minecraft:grass_block'
    snow_silk=item in (SNOW,SNOW_BLOCK)
    snow_plain=item==SNOWBALL
    def eligible(rows):
        return [r for r in rows if 0<=r.get('slot',-1)<36 and r.get('count')
                and r.get('item') in ('minecraft:diamond_'+kind,'minecraft:netherite_'+kind)
                and r.get('durability',0)>=minimum and (kind!='pickaxe' or not is_silk(r))
                and (not grass and not snow_silk or has_silk_touch(r))
                and (not snow_plain or not has_silk_touch(r))]
    checkpoint()
    if not eligible(c.status()['inventory']):
        ender,pad=profile.get('ender_chest'),profile.get('shulker_pad')
        # Packed-supply selection can require an enchantment but cannot yet
        # express its absence.  Never withdraw an arbitrary Silk Touch shovel
        # while preparing the plain-shovel snowball route.
        if ender and pad and not snow_plain:
            state=open_box(c,ender,'ChestMenu')
            candidate=None
            for box in state['menu']['slots'][:-36]:
                if box.get('count')!=1 or not box.get('item','').endswith('shulker_box'):
                    continue
                for tool in box.get('contains',[]):
                    if (tool.get('item') in ('minecraft:diamond_'+kind,'minecraft:netherite_'+kind)
                            and tool.get('durability',0)>=minimum
                            and (kind!='pickaxe' or not is_silk(tool))
                            and (not grass and not snow_silk or has_silk_touch(tool))
                            and (not snow_plain or not has_silk_touch(tool))):
                        if kind=='pickaxe' and any(r.get('item')==tool['item'] and r.get('durability',0)>=minimum and is_silk(r)
                               for r in box.get('contains',[])):
                            continue
                        candidate=(box['slot'],tool['item']);break
                if candidate:
                    break
            c.checked('close_menu')
            if candidate:
                slot,tool=candidate
                take_box(c,ender,pad,slot,{tool:inventory_counts(c.status()).get(tool,0)+1},
                         minimum_durability={tool:minimum},
                         required_enchantments={tool:{'minecraft:silk_touch':1}}
                         if grass or snow_silk else None)
    if not eligible(c.status()['inventory']):
        return {'phase':'blocked','detail':f'需要剩余耐久至少 {minimum} 的钻石或下界合金{kind}'
                + ('并带精准采集' if grass or snow_silk else '且不带精准采集' if snow_plain else '')
                + '；仓库未找到符合条件的现有工具'}
    if kind=='pickaxe':
        # Native AREA and Meteor AutoTool may both reselect a quicker worn
        # pickaxe. Keep only qualified candidates in the actor's inventory;
        # neither module's global settings need to change.
        store_silk(c,profile,out,minimum=minimum)
        actual=c.status()['inventory']
        if not eligible(actual) or any(needs_pickaxe_storage(row,minimum) for row in actual):
            raise RuntimeError('工具寄存后没有确认仅保留合格镐，停止开始采集')
    return {'phase':'done','detail':'采集工具已核验'}
