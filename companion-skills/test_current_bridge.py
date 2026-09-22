import tempfile,json,unittest,time
from pathlib import Path
from kit_skills.automation_path import resolve_automation
from kit_skills.library import SkillManager
from kit_skills.learning import learn_transaction,skill_from_request
from kit_skills.model import verify_episode
class CurrentBridgeTest(unittest.TestCase):
 def test_isolated_live_instance_beats_stale_global_mailbox(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);global_dir=r/'config/twob2tkit/automation';isolated=r/'versions/26.1.2/config/twob2tkit/automation'
   for p,t in [(global_dir,1),(isolated,100000)]:p.mkdir(parents=True);(p/'status.json').write_text(json.dumps({'time':t}))
   self.assertEqual(resolve_automation(game_root=r,now=100),isolated)
   (global_dir/'status.json').write_text('{"time":100000}')
   with self.assertRaises(ValueError):resolve_automation(game_root=r,now=100)
   self.assertEqual(resolve_automation(global_dir,game_root=r,now=100),global_dir)
 def frames(self,op,args):
  req={'id':'r1','op':op,'server':'simpcraft.com','dimension':'minecraft:overworld','site':[0,64,0],
       'world_session':'w','expected_revision':4,'expires_at':105000,'task_session':'materials-test','background_ok':True,**args}
  before={'time':100000,'connected':True,'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'w','health':20,'inventory':[]}
  after={**before,'time':101000,'id':'r1','last_request':'r1','phase':'done'}
  return req,before,after
 def test_scoped_approach_is_learned_without_replaying_transport_envelope(self):
  req,before,after=self.frames('approach_block',{'pos':[1,64,2],'face':'up','expected_state':'Block{minecraft:stone}','seconds':60})
  after['build_supply']={'phase':'done','source':'approach:1, 64, 2','approach_only':True,'failure':''}
  with tempfile.TemporaryDirectory() as d:
   m=SkillManager(d)
   try:
    r=learn_transaction(m,req,before,after);self.assertEqual(r['successful_runs'],1)
    skill=m.get('approach_work_block')['skill'];self.assertNotIn('world_session',skill['parameters']);self.assertNotIn('expected_revision',skill['parameters'])
    req['id']='r2';after.update(id='r2',last_request='r2',world_session='other')
    r=learn_transaction(m,req,before,after);self.assertEqual(r['status'],'candidate');self.assertEqual(r['failed_runs'],1)
   finally:m.close()
 def test_depot_done_is_not_success_without_actual_target_inventory(self):
  req,before,after=self.frames('collect_supply',{'source_key':'minecraft:overworld:1:64:2','materials':{'minecraft:lantern':9},'seconds':120})
  with tempfile.TemporaryDirectory() as d:
   m=SkillManager(d)
   try:
    result=learn_transaction(m,req,before,after);self.assertEqual(result['successful_runs'],0)
   finally:m.close()
if __name__=='__main__':unittest.main()
