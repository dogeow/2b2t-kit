import json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'work/village-trading-20261017'))
from scoped_village_resource_builder import current_cohort_scope
class CurrentCohortTests(unittest.TestCase):
 def test_only_exact_verified_current_cohort_changes_scope(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'cohort.json';gate={'current_proof':'cohort.json','world_session':'w','all_center_residents_contained_verified':True,'current_observed_full_body_count':1,'adult_assignment_bounds':{'u':{}}};proof={'world':'w','audit':[{'uuid':'u','audit':{'verified':True}}]};p.write_text(json.dumps(proof));self.assertEqual(current_cohort_scope(d,gate),'w')
   for change in ('world','failed','person','count','outside'):
    g=dict(gate);w=json.loads(json.dumps(proof))
    if change=='world':w['world']='other'
    if change=='failed':w['audit'][0]['audit']['verified']=False
    if change=='person':w['audit'][0]['uuid']='other'
    if change=='count':g['current_observed_full_body_count']=2
    if change=='outside':g['current_proof']='../other.json'
    p.write_text(json.dumps(w))
    with self.subTest(change=change),self.assertRaises(ValueError):current_cohort_scope(d,g)
if __name__=='__main__':unittest.main()
