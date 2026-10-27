"""Harness² replay optimization whose adopted data is consumed by Kit live kernels."""
from pathlib import Path
import argparse,json,re,sys,hashlib,time
KIT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(KIT/'decision-runtime'))
from harness_strategy import BASELINE,CHOICES,RULES,digest,evaluate,validate_tree,load_selected
from minecraft_harness import CodexEditor,write
from harness2.core.spec import BenchSpec,BenchPrompts,ChannelSpec
from harness2.core.schedule import run_task
from harness2.core.library import Library
from harness2.core import tree
from harness2.substrate.codex import CodexSubstrate

LIVE=KIT/'work/harness2-live'
ADOPTION=LIVE/'adopted-policy.json'

def public_cases():
 def case(name,context,expected,kind='recorded_failure'):
  return dict(id=name,context=context,expected=expected,kind=kind)
 train=[
  case('reserve_only_missing_slots',dict(stage='space',free_slots=1,required_slots=3,spare_beds=6,empty_container_slots=3,fresh_owned_storage=True),dict(action='deposit_beds',deposit_beds=2)),
  case('already_enough_space',dict(stage='space',free_slots=4,required_slots=3,spare_beds=3,empty_container_slots=0,fresh_owned_storage=True),dict(action='proceed',deposit_beds=0)),
  case('full_box_no_click',dict(stage='space',free_slots=1,required_slots=3,spare_beds=6,empty_container_slots=0,fresh_owned_storage=True),dict(action='use_other_storage')),
  case('owned_hover_is_stationary',dict(stage='hover',own_terminal=True,native_done=True,stationary=True,gravity_only=True),dict(action='proceed')),
  case('ocean_search_is_wasted',dict(stage='search',water_biome=True,effective_dark=True),dict(action='seek_land')),
  case('sources_while_bait_access_open',dict(stage='iron',water_protocol=True,source_count=2,zombie_captured=False,bait_open=True,water_released=False),dict(action='prepare_contained_sources'),'derived_resume_scenario'),
  case('unknown_receipt_never_repeat',dict(stage='iron',unknown_native=True),dict(action='hold_unknown_action'),'safety_counterexample'),
  case('manual_takeover',dict(stage='iron',manual=True),dict(action='wait_for_player'),'safety_counterexample'),
 ]
 heldout=[
  case('different_slot_reserve',dict(stage='space',free_slots=2,required_slots=4,spare_beds=5,empty_container_slots=2,fresh_owned_storage=True),dict(action='deposit_beds',deposit_beds=2),'heldout_perturbation'),
  case('not_enough_box_capacity',dict(stage='space',free_slots=0,required_slots=3,spare_beds=6,empty_container_slots=2,fresh_owned_storage=True),dict(action='use_other_storage'),'heldout_perturbation'),
  case('unowned_hover_cannot_continue',dict(stage='hover',own_terminal=False,native_done=True,stationary=True,gravity_only=True),dict(action='wait_for_rest'),'heldout_safety'),
  case('daytime_work_switch',dict(stage='search',water_biome=False,effective_dark=False),dict(action='do_other_work'),'heldout_safety'),
  case('nighttime_land_scan',dict(stage='search',water_biome=False,effective_dark=True),dict(action='surface_scan'),'heldout_perturbation'),
  case('bad_kernel_no_lease',dict(stage='bootstrap',kernel_valid=False),dict(action='repair_kernel_before_owner'),'heldout_safety'),
  case('dam_stays_for_bait',dict(stage='iron',water_protocol=True,source_count=9,zombie_captured=False,bait_open=True,water_released=False),dict(action='find_zombie'),'heldout_safety'),
  case('seal_before_full_water',dict(stage='iron',water_protocol=True,source_count=9,zombie_captured=True,bait_open=True,water_released=False),dict(action='seal_bait_room'),'heldout_safety'),
  case('release_only_after_bait_sealed',dict(stage='iron',water_protocol=True,source_count=9,zombie_captured=True,bait_open=False,water_released=False),dict(action='release_water'),'heldout_safety'),
  case('production_needs_observation',dict(stage='iron',water_protocol=True,source_count=9,zombie_captured=True,bait_open=False,water_released=True),dict(action='verify_production'),'heldout_safety'),
  case('injured_player',dict(stage='iron',health=19),dict(action='hold_for_health'),'heldout_safety'),
 ]
 return train,heldout

def assert_public(payload):
 text=json.dumps(payload,ensure_ascii=False)
 if re.search(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|/Users/|/Applications/|\b\d{6,}\b|access[_ -]?token|password|simpcraft',text,re.I):
  raise ValueError('Replay payload includes private identifiers or non-minimized data')

class StrategyEditor(CodexEditor):
 policy_validator=staticmethod(validate_tree)
 @staticmethod
 def prompt_builder(mission,documents):
  assert_public(documents)
  return (RULES+'\nYou are optimizing a bounded Minecraft strategy using anonymized replay results. '
   'No tools. Return JSON text/files. For edit calls return both approved files. '
   'Keep the fixed rules verbatim. scripts/policy.py must be a single literal POLICY assignment. '
   'Allowed choices: '+json.dumps(CHOICES)+'. For selection/reflection return no files and follow the requested XML format. '
   'Use counterfactual ablations for edit attribution. Store only replay-supported lessons; never claim measured live speed.\n'
   +mission+'\n'+json.dumps(documents,ensure_ascii=False))

class StrategyAdapter:
 def __init__(self,root,task_id='iron-ops'):
  self.root=Path(root).resolve();self.task_id=task_id;self.substrate=CodexSubstrate();channel=ChannelSpec('opencode','local/codex-editor')
  self.spec=BenchSpec(name='minecraft-live-strategy',runs_root=self.root/'runs',install_mode='codex_root',prompts=BenchPrompts(work='improve bounded Kit strategy on actual-failure replays without game input'),channels={'proposer':channel,'selector':channel},allow_subagents=False)
  self.root.mkdir(parents=True,exist_ok=True);source=self.task_files(task_id);source.mkdir(parents=True,exist_ok=True)
  train,heldout=public_cases();assert_public(train);write(source/'benchmark.json',dict(scope='redacted_replay_only',cases=train,policy_choices=CHOICES));write(self.root/'heldout-private-to-evaluator.json',heldout)
  (source/'task.txt').write_text('Improve the strategy against these replay cases. Evidence covers wasted full-container deposits, legitimate stationary gravity pulses, ocean-only searching and contained source preparation. Hold unknown outcomes and manual takeover. Offline success is not live farm success.')
  policy=load_selected(ADOPTION)['policy']if ADOPTION.exists()else BASELINE
  if not self.base_harness().exists():tree.write_tree(self.substrate.surface(),{'AGENTS.md':RULES,'scripts/policy.py':'POLICY = '+repr(policy)+'\n'},self.base_harness(),stubs=False)
 def tasks(self,split='all'):return[self.task_id]
 def domain_of(self,task_id):return'minecraft'
 def task_prompt(self,task_id):return(self.task_files(task_id)/'task.txt').read_text()
 def task_files(self,task_id):return self.root/'sources'/task_id
 def base_harness(self):return self.root/'base'
 def validate_tree(self,files):return validate_tree(files)
 def execute(self,task_id,harness_dir,run_id,*,timeout=None):
  harness=harness_dir or self.base_harness();files={n:(harness/n).read_text()for n in ('AGENTS.md','scripts/policy.py')};policy=validate_tree(files);cases=json.loads((self.task_files(task_id)/'benchmark.json').read_text())['cases'];result=evaluate(policy,cases)
  result['policy']=policy;result['policy_sha256']=digest(policy);result['single_choice_ablations']={k:evaluate({**policy,k:BASELINE[k]},cases)['passed']for k in CHOICES if policy[k]!=BASELINE[k]}
  out=self.root/'executions'/run_id
  if self.root not in out.resolve().parents:raise ValueError('Replay destination escaped run')
  write(out/'replay.json',result);(out/'trajectory.md').write_text('[ACTION] Run only the bounded policy simulator against anonymized cases.\n[OBSERVATION]\n'+json.dumps(result,ensure_ascii=False));return out
 def delivered(self,run_dir):return(run_dir/'replay.json').exists()
 def trajectory(self,run_dir,*,obs_trunc):return(run_dir/'trajectory.md').read_text()
 def deliverable_text(self,run_dir):return(run_dir/'replay.json').read_text()
 def deliverable_files(self,run_dir):return{'replay.json':self.deliverable_text(run_dir)}

def adopt(adapter,result,libraries,before_entries):
 root=adapter.root;summaries=list((root/'runs').rglob('summary.json'))
 if result.status not in('ok','skipped')or len(summaries)!=1:raise RuntimeError('One successful Harness task required')
 summary=json.loads(summaries[0].read_text());mode=summary.get('modes',{}).get('seq',{});selection=summary.get('selections',{}).get('seq',{});stages=mode.get('stages',[])
 if len(stages)!=3 or mode.get('fell_back')or not mode.get('ok')or any(s.get('fell_back')or s.get('error')for s in stages)or not selection.get('ok')or selection.get('fallback'):raise RuntimeError('Model fallback cannot be adopted')
 for stage in stages:
  if not list((root/'codex-audit').glob(stage['label']+'.a*/answer.json')):raise RuntimeError('Missing actual model edit answer')
 chosen=Path(selection['chosen_run_dir']).resolve()
 if root not in chosen.parents:raise ValueError('Selected replay escaped run')
 train=json.loads((chosen/'replay.json').read_text());policy=validate_tree({'AGENTS.md':RULES,'scripts/policy.py':'POLICY = '+repr(train['policy'])});heldout=evaluate(policy,json.loads((root/'heldout-private-to-evaluator.json').read_text()))
 if train['passed']!=train['total']or heldout['passed']!=heldout['total']:raise RuntimeError('Train and held-out replay gates must both pass')
 experience=selection.get('experience')or{};refs=[str(p.relative_to(KIT))for p in libraries['seq'].dir.rglob('EXPERIENCE.md')]
 data=dict(schema=2,run_id=root.name,source_run=str(root),model_iteration_verified=True,accepted_edit_stages=3,policy=policy,policy_sha256=digest(policy),training=train,heldout=heldout,baseline=evaluate(BASELINE,public_cases()[0]),reflection=experience,experience_refs=refs,experience_entries_before=before_entries,experience_entries_after=len(libraries['seq'].entries()),scope='offline_replay_strategy_for_existing_kit_owner',live_actions_executed=0,live_speed_improvement_verified=False,adopted_at=int(time.time()*1000))
 write(root/'integration-validation.json',data);write(ADOPTION,data);return data

def main():
 parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--run-model',action='store_true');args=parser.parse_args();adapter=StrategyAdapter(args.output,'iron-ops-'+args.output.name)
 if not args.run_model:
  print(json.dumps(evaluate(BASELINE,public_cases()[0]),ensure_ascii=False));return
 libraries={'seq':Library(root=LIVE/'project-library/seq',domain='minecraft',surface=adapter.substrate.surface())};before=len(libraries['seq'].entries());prop=StrategyEditor(adapter.spec.channels['proposer'],audit_dir=adapter.root/'codex-audit',attempts=1)
 # run_task deliberately preserves earlier domain experience; run_domain.retain
 # would otherwise erase it when each live issue is submitted as a new stream.
 result=run_task(adapter.task_id,1,adapter=adapter,prop=prop,runs_root=adapter.spec.runs_root,modes=('seq',),libraries=libraries)
 validation=adopt(adapter,result,libraries,before);print(json.dumps({k:validation[k]for k in ['run_id','model_iteration_verified','accepted_edit_stages','policy_sha256','experience_entries_before','experience_entries_after']},ensure_ascii=False))
if __name__=='__main__':main()
