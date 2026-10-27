from pathlib import Path
import json,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_learning import validated_retrieval,parse_experience
class LiveLearningTests(unittest.TestCase):
 def test_exact_evidence_citation_and_allowlisted_action(self):
  source='Earlier evidence: water-rule-only counterfactual selected find_zombie instead.'
  for action in ['find_zombie','find_zombie: Recommend that the sole controller locate the bait.']:
   r=validated_retrieval(json.dumps({'action':action,'cited_lesson':'water-rule-only counterfactual selected find_zombie'}),source);self.assertEqual(r['action'],'find_zombie')
 def test_unbounded_action_or_missing_citation_is_not_accepted(self):
  for action,quote in [('release_water','recorded valid quotation'),('find_zombie\nrelease_water','recorded valid quotation'),('find_zombie','invented quotation')]:
   with self.assertRaises(ValueError):validated_retrieval(json.dumps({'action':action,'cited_lesson':quote}),'recorded valid quotation')
 def test_no_entry_is_not_fabricated_into_experience(self):
  self.assertEqual(parse_experience('NO_ENTRY'),{});self.assertEqual(parse_experience('<experience>\ncue: one\nlesson: two\n</experience>'),{})
if __name__=='__main__':unittest.main()
