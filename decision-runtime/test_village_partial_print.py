import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from village_queue import VillageQueue
from kit_runtime.journal import write_json
class PartialPrintTests(unittest.TestCase):
 def case(self,directory):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.prefix='observe';q.index=0;q.closing_menu=None;d=q.out/'old';d.mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',{'id':'old','action':'native','op':'professional_print'})
  r={'id':'native','phase':'waiting','detail':'printer interval ended without complete current bounded-mask server confirmation','world_session':'w','control_revision':3,'bounded_targets':[[1,1,1],[2,1,1]],'bounded_target_count':2,'placement_key':'key'};write_json(d/'result.json',r);state={**r,'screen':'','last_request':'native','professional_printer':{'enabled':False,'owned':False,'waiting_for_server':False,'travel_pending':0,'failure':'','complex_proposals':0,'server_confirmed':1,'fast_proposals':1},'projection_batch':{'active':True,'count':2,'placement_key':'key','task_session':'t'}};q.status=lambda **kw:state;return q,d,state
 def test_snapshot_only_does_not_complete_or_clear_original_mask(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,s=self.case(directory);old=(d/'result.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_settled_partial_printer()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(old,(d/'result.json').read_bytes());self.assertTrue(s['projection_batch']['active'])
 def test_unconfirmed_proposal_or_changed_mask_remains_fenced(self):
  for mode in ['unknown','waiting','proposal','mask','complex','active']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,s=self.case(directory)
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='waiting':s['professional_printer']['waiting_for_server']=True
    if mode=='proposal':s['professional_printer']['fast_proposals']=2
    if mode=='mask':s['projection_batch']['placement_key']='other'
    if mode=='complex':s['professional_printer']['complex_proposals']=1
    if mode=='active':s['professional_printer']['enabled']=True
    with self.assertRaises(RuntimeError):q.observe_settled_partial_printer()
if __name__=='__main__':unittest.main()
