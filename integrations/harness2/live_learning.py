"""Post-execution Harness reflection over minimized, verified Kit receipts."""
from pathlib import Path
from collections import Counter
import json,re,hashlib
from strategy_loop import KIT,LIVE,ADOPTION,StrategyEditor,assert_public
from harness_strategy import BASELINE,RULES,choose,validate_tree,digest
from minecraft_harness import write
from harness2.core.library import Library,has_experience
from harness2.core.spec import ChannelSpec
from harness2.substrate.codex import CodexSubstrate

def applied_summary(acceptance_path):
 path=Path(acceptance_path).resolve()
 if KIT/'work' not in path.parents:raise ValueError('Acceptance escaped local work')
 proof=json.loads(path.read_text());result=proof['stage'];bookpath=Path(result['source_proof']).resolve()
 if KIT/'work' not in bookpath.parents or bookpath.is_symlink():raise ValueError('Stage evidence escaped local work')
 book=json.loads(bookpath.read_text());adopted=json.loads(ADOPTION.read_text())
 if(not proof.get('complete')or proof.get('pending')is not None or not result.get('applied')
    or proof['policy_sha256']!=adopted['policy_sha256']or result['strategy']['policy_sha256']!=adopted['policy_sha256']
    or not book.get('complete')or book.get('pending')is not None or book.get('pending_inventory_ack')
    or len(book.get('removed',[]))!=4 or len(book.get('water_uses',[]))!=6
    or not all(r.get('recovered')for r in book['removed'])
    or not all(r.get('confirmed')and not r.get('unknown_outcome')and r.get('use_count')==1 for r in book['water_uses'])):raise ValueError('Only a fully verified application can produce experience')
 expected=Counter(book['inventory_before']);expected['minecraft:cobblestone']+=4
 if +expected!=Counter(book['inventory_after']):raise ValueError('Unaccounted stage materials')
 before={tuple(r['pos']):r for r in book['scene_before']['blocks']};after={tuple(r['pos']):r for r in book['scene_after']['blocks']}
 water='Block{minecraft:water}[level=0]';stone='Block{minecraft:cobblestone}'
 source_count=lambda rows:sum(rows.get((x,95,797805),{}).get('state')==water for x in range(761076,761085))
 if(source_count(before)!=2 or source_count(after)!=9 or book['scene_after']['health']!=20
    or not all(after.get((x,95,797806),{}).get('state')==stone for x in range(761076,761085))
    or any(before.get((x,93,z),{}).get('state')!=after.get((x,93,z),{}).get('state')for x in range(761079,761082)for z in range(797813,797816))):raise ValueError('Live final scene does not prove contained source preparation')
 owner=next(p for p in bookpath.parents if(p/'control/events.jsonl').exists());events=[json.loads(l)for l in(owner/'control/events.jsonl').read_text().splitlines()];plan=json.loads(Path(proof['plan']['plan_path']).read_text());start=next(i for i,e in enumerate(events)if e['request_id']==plan['fresh_scan_id']);end=next(i for i,e in enumerate(events)if e['request_id']==book['scene_after']['id']);segment=events[start+1:end+1]
 if not segment or any(e['world_session']!=book['world_session']or e['params'].get('task_session')!=book['task_session']or e['phase']!='done'for e in segment):raise ValueError('Application event chain is not fully terminal and owned')
 counts=Counter(e['op']for e in segment);context=plan['context'];policy=adopted['policy'];legacy_water={**policy,'water':BASELINE['water']}
 summary=dict(scope='one_verified_native_application_not_live_speed_comparison',selected_policy=policy,context_before=context,selected_decision=choose(policy,context),counterfactual_water_rule_only=choose(legacy_water,context),observed=dict(source_count_before=2,source_count_after=9,retainers_recovered=4,bucket_uses=6,player_health_after=20,outlet_dam_preserved=True,bait_access_preserved=True,all_inventory_conserved=True,elapsed_seconds=round(proof['measured_stage_wall_ms']/1000,3),native_operations=dict(counts),native_input_count=sum(n for op,n in counts.items()if op not in('scan','snapshot')),farm_operational_verified=False,live_speed_improvement_verified=False))
 assert_public(summary);return summary,adopted

def parse_experience(text):
 match=re.search(r'<experience>(.*?)</experience>',text,re.S)
 if not match:return {}
 result={}
 for line in match.group(1).splitlines():
  key,sep,value=line.partition(':')
  if sep and key.strip().lower()in('cue','lesson','evidence','confidence'):result[key.strip().lower()]=value.strip()
 return result if has_experience(result)else {}

def reflect_live(acceptance_path,out):
 out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);summary,adopted=applied_summary(acceptance_path);context=out/'context';(context/'source').mkdir(parents=True);(context/'harness/scripts').mkdir(parents=True)
 write(context/'source/applied-execution.json',summary);(context/'harness/AGENTS.md').write_text(RULES);(context/'harness/scripts/policy.py').write_text('POLICY = '+repr(adopted['policy'])+'\n')
 mission='''Reflect on the selected strategy's actual Kit application. This is a post-execution feedback phase, not a claim of another code edit. The independently executed one-rule counterfactual explains the alternative next decision, but is not a live A/B timing experiment. Write a narrowly conditioned, reusable lesson only if the native receipt evidence supports it. Never claim general speed improvement or iron production. Do not write files. Return <experience> with separate cue:, lesson:, evidence:, confidence: lines, or NO_ENTRY if insufficient.'''
 prop=StrategyEditor(ChannelSpec('opencode','local/codex-editor'),audit_dir=out/'codex-audit',attempts=1);reply=prop.call(mission,context,'live-experience');answer=json.loads((out/'codex-audit/live-experience/answer.json').read_text())
 if answer['files']:raise ValueError('Post-execution reflection cannot change a harness tree')
 experience=parse_experience(reply.text);lib=Library(root=LIVE/'project-library/seq',domain='minecraft',surface=CodexSubstrate().surface());before=len(lib.entries());entry=None
 if experience:
  entry=lib.add('applied-water-'+adopted['run_id'],{'AGENTS.md':RULES,'scripts/policy.py':'POLICY = '+repr(adopted['policy'])+'\n'},why='Observed one native contained-source stage; no live speed comparison.',label='applied-policy',run_id=adopted['run_id'],experience=experience)
 refs=[str(p.relative_to(KIT))for p in lib.dir.rglob('EXPERIENCE.md')];adopted.update(experience_refs=refs,experience_entries_after=len(lib.entries()),post_execution_reflection=dict(path=str(out),entry_created=entry is not None,scope=summary['scope']));write(ADOPTION,adopted)
 result=dict(complete=True,model_reflection_verified=True,entry_created=entry is not None,entries_before=before,entries_after=len(lib.entries()),experience=experience,experience_path=str(entry/'EXPERIENCE.md')if entry else None,summary=summary,raw_reflection=reply.text,live_speed_improvement_verified=False);write(out/'live-reflection-result.json',result);return result

def validated_retrieval(text,experience):
 body=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip());decision=json.loads(body)
 raw=decision.get('action');citation=decision.get('cited_lesson','')
 # Descriptive prose is data, never an executable action. Accept only this
 # exact allowlisted enum, optionally followed by one explanatory line.
 match=re.fullmatch(r'(find_zombie)(?::[ \t]+[^\r\n]+)?',raw)if isinstance(raw,str)else None
 if not match or not isinstance(citation,str)or len(citation)<8 or citation not in experience:
  raise ValueError('Next model call did not demonstrate valid experience retrieval')
 return dict(action=match.group(1),cited_lesson=citation,raw_action=raw)

def verify_retrieval(reflection_out,out):
 reflection=json.loads((Path(reflection_out)/'live-reflection-result.json').read_text());out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
 if not reflection['entry_created']:
  result=dict(model_called=False,reason='NO_ENTRY',previous_experience_available=False);write(out/'retrieval-result.json',result);return result
 source=Path(reflection['experience_path']);text=source.read_text();context=out/'context';(context/'source').mkdir(parents=True);(context/'prior-experience').mkdir();(context/'prior-experience/EXPERIENCE.md').write_text(text);context_after=dict(stage='iron',health=20,connected=True,water_protocol=True,source_count=9,bait_open=True,zombie_captured=False,water_released=False);write(context/'source/current-phase.json',context_after)
 mission='''Read the prior-experience document before deciding. Upper source preparation is now complete but bait access remains open and no zombie is captured. Do not repeat completed source preparation or release the outlet. Do not use tools or write files. Return JSON in text with keys action and cited_lesson. The action value must be exactly find_zombie with no prose; cite a short exact phrase from the prior lesson to prove retrieval. This is a planning check, not game execution.'''
 prop=StrategyEditor(ChannelSpec('opencode','local/codex-editor'),audit_dir=out/'codex-audit',attempts=1);reply=prop.call(mission,context,'retrieve-experience');answer=json.loads((out/'codex-audit/retrieve-experience/answer.json').read_text())
 if answer['files']:raise ValueError('Retrieval cannot edit a harness')
 decision=validated_retrieval(reply.text,text)
 result=dict(model_called=True,previous_experience_available=True,verified=True,source_experience_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_experience_path=str(source),decision=decision,game_actions_executed=0);write(out/'retrieval-result.json',result);return result
