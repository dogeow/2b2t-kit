"""Bounded single-item brewing clicks in an owned, verified stand."""
import json
INGREDIENTS = {'minecraft:gunpowder', 'minecraft:nether_wart', 'minecraft:glistering_melon_slice'}
ALLOWED = {'minecraft:air', 'minecraft:potion', 'minecraft:splash_potion', 'minecraft:blaze_powder'} | INGREDIENTS
def signature(state,params,world,task):
 menu=state.get('menu')or{};rows=menu.get('slots')or[];cursor=menu.get('cursor')or{};lease=state.get('supervision_lease')or{}
 keys={'menu_id','slot','kind','button','expected_item','expected_count','expected_cursor','expected_cursor_count'}
 if (state.get('connected') is not True or state.get('world_session')!=world or state.get('health')!=20
  or state.get('manual_movement') is not False or state.get('guard_busy') or state.get('native_material_busy') or state.get('pending_scan')
  or (state.get('safety_hold')or{}).get('active') or state.get('health_recovery_hold')
  or lease.get('kind')!='materials' or lease.get('job_session')!=task or lease.get('world_session')!=world or lease.get('revision')!=state.get('control_revision')
  or menu.get('type')!='BrewingStandMenu' or state.get('screen')!='BrewingStandScreen' or len(rows)!=41
  or type(menu.get('id')) is not int or menu['id']<=0 or params.get('menu_id')!=menu['id'] or set(params)-keys
  or params.get('kind')!='pickup' or params.get('button',0)!=0 or type(params.get('slot')) is not int or not 0<=params['slot']<41
  or params.get('expected_item') not in ALLOWED or params.get('expected_cursor') not in ALLOWED
  or type(params.get('expected_count')) is not int or params['expected_count'] not in (0,1)
  or type(params.get('expected_cursor_count')) is not int or params['expected_cursor_count'] not in (0,1)):return None
 row=rows[params['slot']]
 if (row.get('item')!=params['expected_item'] or row.get('count')!=params['expected_count'] or cursor.get('item')!=params['expected_cursor'] or cursor.get('count')!=params['expected_cursor_count']):return None
 if (row['count'],cursor['count']) not in ((1,0),(0,1)):return None
 slot=params['slot'];item=row['item'] if row['count'] else cursor['item']
 if slot<3 and item not in ('minecraft:potion','minecraft:splash_potion'):return None
 if slot==3 and item not in INGREDIENTS:return None
 if slot==4 and item!='minecraft:blaze_powder':return None
 return(world,state['control_revision'],menu['id'],state.get('last_request'),json.dumps(params,sort_keys=True))
