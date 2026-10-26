import copy,unittest
from ground_work_threat_survey import bounds,assess,ENTITY_SCOPE
class GroundWorkThreatSurveyTest(unittest.TestCase):
 def fixture(self):
  feet=[394.5,63.1,980.5];lo,hi=bounds(feet);req={'op':'scan','min':lo,'max':hi,'details':True,'id':'r','world_session':'w','task_session':'t','expected_revision':5};r={'id':'r','phase':'done','world_session':'w','scan_start_revision':5,'scan_end_revision':5,'scan_cells_read':40817,'scan_total_cells':40817,'scan_entity_scope':ENTITY_SCOPE,'scan_ended_at':10000,'scan_entities':[]};return feet,req,r
 def check(self,feet,req,r):return assess(req,r,feet,world='w',task='t',revision=5,now_ms=11000)
 def test_empty_complete_ground_lens_is_only_a_current_local_result(self):
  a=self.check(*self.fixture());self.assertTrue(a['safe_now']);self.assertTrue(a['future_safety_not_proven'])
 def test_reproduced_zombie_outside_old_tree_halo_is_detected(self):
  p,q,r=self.fixture();r['scan_entities']=[{'alive':True,'hostile':True,'type':'minecraft:zombie','pos':[384.91,64,983.51]}];self.assertFalse(self.check(p,q,r)['safe_now'])
 def test_partial_tree_halo_or_status_entity_list_never_proves_absence(self):
  for mode in ['halo','status','stale','partial','world','revision','schema','identity','task']:
   p,q,r=copy.deepcopy(self.fixture())
   if mode=='halo':q['min']=[388,61,978];q['max']=[400,85,990];r['scan_cells_read']=r['scan_total_cells']=4225
   elif mode=='status':r.pop('scan_entity_scope');r['entities']=[]
   elif mode=='stale':r['scan_ended_at']=1000
   elif mode=='partial':r['scan_cells_read']-=1
   elif mode=='world':r['world_session']='other'
   elif mode=='revision':r['scan_end_revision']=6
   elif mode=='schema':r['scan_entities']=[{'type':'minecraft:zombie','pos':[384,64,983],'hostile':True}]
   elif mode=='identity':q['id']='other'
   else:q['task_session']='other'
   with self.subTest(mode=mode),self.assertRaises(ValueError):self.check(p,q,r)
if __name__=='__main__':unittest.main()
