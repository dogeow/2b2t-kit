"""Bounded Harness² strategy data. Models never install executable game code."""
from pathlib import Path
import ast,hashlib,json

CHOICES={
 'storage':('empty_spares','reserve_required'),
 'hover':('zero_velocity','owned_stationary_receipt'),
 'search':('biome_blind','land_only'),
 'water':('wait_for_capture','contained_sources_first'),
 'unknown':('hold',),
 'bootstrap':('validate_before_lease',),
}
BASELINE={k:v[0]for k,v in CHOICES.items()}
DEFAULT={k:v[-1]for k,v in CHOICES.items()}
RULES='''Harness strategy rules v2: edit only declarative POLICY values from the supplied choices.
Never operate Minecraft, acquire a game lease, run tools, change native safety checks, restart,
reconnect, read credentials or Notion, spawn agents, or replay unknown actions.
A selected strategy is a recommendation for the existing Kit sole controller. Native fresh
world, manual-control, inventory, health, collision and receipt gates remain mandatory.
Offline replay improvement is not proof of live speed improvement or iron production.
'''

def validate(policy):
 if not isinstance(policy,dict)or set(policy)!=set(CHOICES):raise ValueError('Exact strategy keys required')
 if any(type(v)is not str or v not in CHOICES[k]for k,v in policy.items()):raise ValueError('Unknown strategy choice')
 return dict(policy)

def validate_tree(files):
 if set(files)!={'AGENTS.md','scripts/policy.py'}or RULES not in files['AGENTS.md']:raise ValueError('Immutable strategy rules required')
 node=ast.parse(files['scripts/policy.py'])
 if(len(node.body)!=1 or not isinstance(node.body[0],ast.Assign)or len(node.body[0].targets)!=1
    or not isinstance(node.body[0].targets[0],ast.Name)or node.body[0].targets[0].id!='POLICY'):
  raise ValueError('Only one literal POLICY assignment is accepted')
 return validate(ast.literal_eval(node.body[0].value))

def digest(policy):return hashlib.sha256(json.dumps(validate(policy),sort_keys=True,separators=(',',':')).encode()).hexdigest()

def choose(policy,context):
 p=validate(policy);c=context
 if c.get('manual')or c.get('foreign_menu'):return {'action':'wait_for_player'}
 if c.get('unknown_native'):return {'action':'hold_unknown_action'}
 if c.get('health',20)!=20:return {'action':'hold_for_health'}
 if c.get('connected',True)is not True:return {'action':'await_connection'}
 stage=c.get('stage')
 if stage=='bootstrap':return {'action':'open_owner'if c.get('kernel_valid')else'repair_kernel_before_owner'}
 if stage=='space':
  need=max(0,c['required_slots']-c['free_slots'])
  if not need:return {'action':'proceed','deposit_beds':0}
  if not c.get('fresh_owned_storage'):return {'action':'observe_storage'}
  if p['storage']=='reserve_required':
   if c.get('empty_container_slots',0)<need or c.get('spare_beds',0)<need:return {'action':'use_other_storage'}
   return {'action':'deposit_beds','deposit_beds':need}
  return {'action':'deposit_beds','deposit_beds':c.get('spare_beds',0)}
 if stage=='hover':
  proof=all(c.get(k)is True for k in ('own_terminal','native_done','stationary','gravity_only'))
  return {'action':'proceed'if proof and p['hover']=='owned_stationary_receipt'else'wait_for_rest'}
 if stage=='search':
  if not c.get('effective_dark'):return {'action':'do_other_work'}
  if c.get('water_biome')and p['search']=='land_only':return {'action':'seek_land'}
  return {'action':'surface_scan'}
 if stage=='iron':
  if not c.get('water_protocol'):return {'action':'needs_host_update'}
  if c.get('source_count',0)<9:
   if p['water']=='contained_sources_first':return {'action':'prepare_contained_sources'}
   return {'action':'find_zombie'if not c.get('zombie_captured')else'prepare_contained_sources'}
  if not c.get('zombie_captured'):return {'action':'find_zombie'}
  if c.get('bait_open'):return {'action':'seal_bait_room'}
  if not c.get('water_released'):return {'action':'release_water'}
  return {'action':'verify_production'}
 raise ValueError('Unknown bounded strategy stage')

def evaluate(policy,cases):
 rows=[]
 for case in cases:
  planned=choose(policy,case['context']);ok=all(planned.get(k)==v for k,v in case['expected'].items())
  rows.append(dict(case=case['id'],planned=planned,expected=case['expected'],passed=ok))
 return dict(scope='offline_replay_not_live_time',passed=sum(r['passed']for r in rows),total=len(rows),cases=rows,live_actions_executed=0)

def load_selected(path):
 path=Path(path)
 if not path.exists():return dict(active=False,source='builtin_no_harness_adoption',policy=DEFAULT,policy_sha256=digest(DEFAULT),run_id=None)
 data=json.loads(path.read_text());policy=validate(data['policy'])
 if(data.get('schema')!=2 or data.get('model_iteration_verified')is not True
    or data.get('policy_sha256')!=digest(policy)or not data.get('run_id')
    or data.get('heldout',{}).get('passed')!=data.get('heldout',{}).get('total')
    or data.get('heldout',{}).get('total',0)<1):raise ValueError('Harness adoption has not passed the replay gate')
 return {**data,'active':True,'source':'harness2_verified_replay_strategy'}
