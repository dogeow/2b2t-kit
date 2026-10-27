import sys,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from strategy_loop import StrategyAdapter,public_cases,assert_public
from harness_strategy import BASELINE,DEFAULT,RULES,choose,validate_tree,evaluate,digest,load_selected
class StrategyTests(unittest.TestCase):
 def test_known_failures_change_the_plan_and_heldout_safety_still_holds(self):
  train,held=public_cases();a=evaluate(BASELINE,train);b=evaluate(DEFAULT,train);self.assertGreater(b['passed'],a['passed']);self.assertEqual(b['passed'],b['total']);self.assertEqual(evaluate(DEFAULT,held)['passed'],len(held))
 def test_only_literal_allowlisted_strategy_values(self):
  for source in ['import os\nPOLICY={}','POLICY=__import__("os")','POLICY='+repr({**DEFAULT,'unknown':'retry'})]:
   with self.subTest(source=source),self.assertRaises((ValueError,SyntaxError)):validate_tree({'AGENTS.md':RULES,'scripts/policy.py':source})
  self.assertEqual(validate_tree({'AGENTS.md':RULES,'scripts/policy.py':'POLICY='+repr(DEFAULT)}),DEFAULT)
 def test_critical_gates_cannot_be_disabled_by_an_efficiency_choice(self):
  for p in [BASELINE,DEFAULT]:
   self.assertEqual(choose(p,{'stage':'iron','manual':True})['action'],'wait_for_player')
   self.assertEqual(choose(p,{'stage':'iron','unknown_native':True})['action'],'hold_unknown_action')
   self.assertEqual(choose(p,{'stage':'iron','health':19})['action'],'hold_for_health')
 def test_source_data_contains_no_base_identifiers(self):
  train,held=public_cases();assert_public(train);assert_public(held)
  for payload in [{'uuid':'3545a43d-658e-4b73-a2dd-2d47e1271d6d'},{'position':[761080,90,797814]},{'password':'x'}]:
   with self.assertRaises(ValueError):assert_public(payload)
 def test_adoption_must_be_a_verified_heldout_pass_and_matching_hash(self):
  with tempfile.TemporaryDirectory()as td:
   p=Path(td)/'policy.json';d=dict(schema=2,run_id='fixture',model_iteration_verified=True,policy=DEFAULT,policy_sha256=digest(DEFAULT),heldout={'passed':2,'total':2});p.write_text(json.dumps(d));self.assertTrue(load_selected(p)['active']);d['policy_sha256']='changed';p.write_text(json.dumps(d))
   with self.assertRaises(ValueError):load_selected(p)
 def test_candidate_execution_is_a_real_replay_and_has_no_game_input(self):
  with tempfile.TemporaryDirectory()as td,patch('strategy_loop.ADOPTION',Path(td)/'missing.json'):
   a=StrategyAdapter(Path(td)/'run');tree=a.base_harness();(tree/'scripts/policy.py').write_text('POLICY='+repr(DEFAULT));out=a.execute(a.task_id,tree,'candidate');r=json.loads((out/'replay.json').read_text());self.assertEqual(r['passed'],r['total']);self.assertEqual(r['live_actions_executed'],0);self.assertTrue(r['single_choice_ablations'])
if __name__=='__main__':unittest.main()
