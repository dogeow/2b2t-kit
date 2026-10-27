import unittest,tempfile,json
from pathlib import Path
from copy import deepcopy
from village_queue import VillageQueue
class HarnessOutputObservationTests(unittest.TestCase):
 def run_case(self,change=None):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);out=root/'owner';out.mkdir();job=out/'stage';job.mkdir();plan={'world_session':'w','task_session':'t','decision':{'action':'find_zombie'},'fresh_scan_id':'r'};p=out/'plan.json';p.write_text(json.dumps(plan));(out/'command.json').write_text(json.dumps({'id':'stage','action':'harness_iron_stage','plan':str(p)}));error={'type':'FileNotFoundError','error':'missing .loaded-hostiles.json-1.tmp','last_request':'r','native_inflight':None,'unconfirmed_native_request':None};(job/'error.json').write_text(json.dumps(error));state={'world_session':'w','phase':'done','id':'r','last_request':'r','pos':[1,2,3],'control_revision':2,'inventory':[{'slot':0,'item':'minecraft:stone','count':3}],'screen':''};(root/'reply-r.json').write_text(json.dumps(deepcopy(state)));(root/'request.json').write_text(json.dumps({'id':'r'}));q=object.__new__(VillageQueue);q.root=root;q.out=out;q.world='w';q.lease={'job_session':'t'};q.status=lambda:state;calls=[];q.native=lambda op:(calls.append(op)or{'id':'snapshot'})
   if change:change(state,plan,error,p,job)
   try:return q.observe_unstarted_harness_log_failure(),calls
   except RuntimeError:return None,calls
 def test_read_only_finder_file_failure_allows_only_snapshot(self):self.assertEqual(({'id':'snapshot'},['snapshot']),self.run_case())
 def test_other_stage_or_inventory_change_is_rejected(self):
  def change(s,plan,e,p,j):plan['decision']['action']='prepare_contained_sources';p.write_text(json.dumps(plan))
  self.assertEqual((None,[]),self.run_case(change));self.assertEqual((None,[]),self.run_case(lambda s,*args:s['inventory'][0].update(count=4)))
 def test_unknown_native_request_stays_retained(self):
  def change(s,p,e,path,j):e['unconfirmed_native_request']='unknown';(j/'error.json').write_text(json.dumps(e))
  self.assertEqual((None,[]),self.run_case(change))
if __name__=='__main__':unittest.main()
