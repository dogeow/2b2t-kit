import copy,unittest
from material_jobs.canal_seals import plan_seal,CB
class Tests(unittest.TestCase):
 def fixture(self):
  rows=[];expected=[]
  for p,state in [([10,61,20],'Block{minecraft:dirt}'),([10,60,20],CB),([10,62,20],CB),([9,61,20],CB),([11,61,20],CB),([10,61,21],'Block{minecraft:dirt}'),([10,61,19],'Block{minecraft:water}[level=8]'),([10,62,19],'Block{minecraft:water}[level=0]')]:
   fluid='minecraft:water}'in state;rows.append(dict(pos=p,state=state,solid=not fluid,fluid=fluid,block_entity=False));expected.append(dict(pos=p,state=CB if p==[10,61,20]else state))
  expected=[v for v in expected if v['pos']!=[10,62,19]]
  return {'expected':expected},{'phase':'done','world_session':'unit','blocks':rows,'scan_cells_read':45,'scan_total_cells':45,'scan_coherent':True,'scan_predictions':{'complete':True,'pending_count':0}}
 def test_verified_sealed_north_canal_has_native_pins_and_offset_work_pose(self):
  m,f=self.fixture();p=plan_seal(m,f,[10,61,20],'unit');self.assertTrue(p['ready']);self.assertEqual([10.5,63.1,19.32],p['work_pose']);self.assertEqual(6,len(p['expected_neighbors']));self.assertFalse(p['world_changes'])
 def test_original_air_under_target_is_skipped_without_key_error(self):
  m,f=self.fixture();m['expected']=[v for v in m['expected']if v['pos']!=[10,60,20]];self.assertEqual('bottom_not_original_cobblestone',plan_seal(m,f,[10,61,20],'unit')['reason'])
 def test_missing_top_side_or_container_does_not_authorize_removal(self):
  for pos,field,value in [([10,62,20],'state','Block{minecraft:dirt}'),([9,61,20],'solid',False),([11,61,20],'block_entity',True),([10,61,21],'fluid',True)]:
   m,f=self.fixture();next(v for v in f['blocks']if v['pos']==pos)[field]=value;self.assertFalse(plan_seal(m,f,[10,61,20],'unit')['ready'])
 def test_target_container_or_fluid_is_never_authorized(self):
  for key in ['fluid','block_entity']:
   m,f=self.fixture();next(v for v in f['blocks']if v['pos']==[10,61,20])[key]=True;self.assertEqual('target_has_fluid_or_block_entity',plan_seal(m,f,[10,61,20],'unit')['reason'])
 def test_work_gate_and_body_obstruction_are_kept(self):
  m,f=self.fixture();next(v for v in f['blocks']if v['pos']==[10,62,19])['state']='Block{minecraft:spruce_fence_gate}[open=true]';self.assertEqual('work_ray_obstruction',plan_seal(m,f,[10,61,20],'unit')['reason'])
  m,f=self.fixture();f['blocks'].append(dict(pos=[10,63,19],state=CB));self.assertEqual('work_body_not_air',plan_seal(m,f,[10,61,20],'unit')['reason'])
 def test_known_unknown_and_already_correct_are_not_replayed(self):
  m,f=self.fixture();self.assertEqual('protected_unknown_target',plan_seal(m,f,[10,61,20],'unit',protected=[[10,61,20]])['reason']);next(v for v in f['blocks']if v['pos']==[10,61,20])['state']=CB;self.assertEqual('already_correct',plan_seal(m,f,[10,61,20],'unit')['reason'])
 def test_wrong_world_incomplete_prediction_or_duplicate_scan_is_rejected(self):
  for key,value in [('world_session','other'),('scan_coherent',False),('scan_cells_read',44),('scan_predictions',{'complete':True,'pending_count':1})]:
   m,f=self.fixture();f[key]=value;self.assertFalse(plan_seal(m,f,[10,61,20],'unit')['ready'])
  m,f=self.fixture();f['blocks'].append(copy.deepcopy(f['blocks'][0]));self.assertEqual('duplicate_scan_positions',plan_seal(m,f,[10,61,20],'unit')['reason'])
