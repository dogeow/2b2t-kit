"""Exact potion quick-move guarded by fresh component evidence."""
import json

def signature(state, evidence, params, world, task, potion):
 menu=state.get('menu')or{};rows=menu.get('slots')or[];lease=state.get('supervision_lease')or{};pi=evidence.get('potion_inventory')or{}
 if (state.get('connected') is not True or state.get('world_session')!=world or state.get('health')!=20
  or state.get('manual_movement') is not False or state.get('guard_busy') or state.get('native_material_busy') or state.get('pending_scan')
  or (state.get('safety_hold')or{}).get('active') or state.get('health_recovery_hold')
  or lease.get('kind')!='materials' or lease.get('job_session')!=task or lease.get('world_session')!=world or lease.get('revision')!=state.get('control_revision')
  or state.get('screen')!='ContainerScreen' or menu.get('type')!='ChestMenu' or len(rows) not in (63,90)
  or type(menu.get('id')) is not int or menu['id']<=0 or params.get('menu_id')!=menu['id']
  or set(params)!={'menu_id','slot','kind','expected_item','expected_count','expected_cursor','expected_cursor_count'}
  or params.get('kind')!='quick_move' or params.get('expected_item')!='minecraft:potion' or params.get('expected_count')!=1
  or params.get('expected_cursor')!='minecraft:air' or params.get('expected_cursor_count')!=0 or (menu.get('cursor')or{}).get('count')!=0
  or type(params.get('slot')) is not int or not 0<=params['slot']<len(rows)-36 or not any(not r.get('count')for r in rows[-36:])
  or evidence.get('world_session')!=world or evidence.get('runtime_generation')!=state.get('runtime_generation') or evidence.get('player_uuid')!=state.get('player_uuid')
  or pi.get('complete') is not True or pi.get('menu_id')!=menu['id'] or pi.get('menu_type')!='ChestMenu'
  or type(pi.get('observed_at')) is not int or not 0<=state.get('time',0)-pi['observed_at']<1000):return None
 row=rows[params['slot']];match=[x for x in pi.get('potions',[])if x.get('slot')==params['slot'] and x.get('nonempty_child_index')==-1]
 if row.get('item')!='minecraft:potion' or row.get('count')!=1 or len(match)!=1 or match[0].get('item')!='minecraft:potion' or match[0].get('potion_contents')!={'potion':potion}:return None
 return (world,state['control_revision'],menu['id'],state.get('last_request'),json.dumps(params,sort_keys=True),potion)
