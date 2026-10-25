import copy,unittest,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from current_resource_session import validate_binding,CurrentResourceScopeMixin

class ResourceBindingTests(unittest.TestCase):
 def fixture(self):
  k={'world_session':'new-connection','task_session':'owned-task'};a={'world_session':'new-connection','server':'play.example','dimension':'minecraft:overworld'};s={**a,'control_revision':9,'guard_armed':True,'guard_pve_only':True,'supervision_lease':{'kind':'materials','world_session':'new-connection','job_session':'owned-task','revision':9}};return s,k,a,{'resident','historically-missing'},{'resident','historically-missing'},{'server':'play.example','dimension':'minecraft:overworld','home':[1.5,100,2.5],'max_radius':4096,'pads':[[1,64,2]]}
 def test_current_lease_and_all_legacy_ids_are_required(self):
  self.assertIsNone(validate_binding(*self.fixture()))
 def test_wrong_server_dimension_world_owner_revision_or_protection_fails(self):
  for case in ['server','dimension','world','startup','lease','task','revision','guard','protection']:
   with self.subTest(case=case):
    s,k,a,p,r,config=self.fixture()
    if case=='server':s['server']='other.example'
    if case=='dimension':s['dimension']='minecraft:the_nether'
    if case=='world':s['world_session']='other'
    if case=='startup':a['world_session']='old'
    if case=='lease':s['supervision_lease']['kind']='parking'
    if case=='task':s['supervision_lease']['job_session']='other'
    if case=='revision':s['supervision_lease']['revision']=8
    if case=='guard':s['guard_pve_only']=False
    if case=='protection':p.remove('historically-missing')
    with self.assertRaises(RuntimeError):validate_binding(s,k,a,p,r,config)
 def test_role_rejects_villager_actions_excavation_and_new_workstations(self):
  role=CurrentResourceScopeMixin.__new__(CurrentResourceScopeMixin);role._resource_pads={(1,64,2)}
  with self.assertRaises(ValueError):role.send('merchant_open')
  with self.assertRaises(ValueError):role.n('mine_block',pos=[1,2,3])
  with self.assertRaises(ValueError):role.n('use_item',item='minecraft:enchanted_golden_apple')
  with self.assertRaises(ValueError):role.n('navigate',target=[1,2,3],air_only=False)
  with self.assertRaises(ValueError):role.place([1,64,2],[1,63,2],'up',item='minecraft:lectern')
  with self.assertRaises(ValueError):role.n('recover_shulker',pos=[1,2,3])
 def test_adapter_keeps_census_historical_and_retains_missing_id_health_guard(self):
  from village_resource_health import ProtectedResidentHealthError
  s,k,a,protected,required,config=self.fixture();s.update(connected=True,health=20,manual_movement=False,screen='',loaded_villagers={'villagers':[]})
  class Base:
   def __init__(self,out,root,prefix,proof,resume=False):
    self.out=Path(out);self.protected_ids=protected;self.home_min=[0,0,0];self.home_max=[5,5,5];self.q=SimpleNamespace(status=lambda:copy.deepcopy(s));self.check()
  class Adapter(CurrentResourceScopeMixin,Base):pass
  with tempfile.TemporaryDirectory()as tmp:
   project=Path(tmp);out=project/'owner';out.mkdir();census={'complete':True,'world_session':'historical-player-session','expected_known_uuids':list(required),'boundary_checks':[{'roster':[{'uuid':'resident'}]}]};ref=project/'historical.json';ref.write_text(json.dumps(census));(project/'project-state.json').write_text(json.dumps({'current_enclosed_population':{'proof':'historical.json'},'resource_inventory_scope':config}));(out/'transport-kernel.json').write_text(json.dumps(k));(out/'actual-before.json').write_text(json.dumps(a));original=ref.read_bytes();client=Adapter(out,project,'test',out/'proof.json');self.assertEqual(client.check()['world_session'],'new-connection');self.assertEqual(original,ref.read_bytes())
   s['loaded_villagers']['villagers']=[{'uuid':'historically-missing','health':19,'pos':[100,1,100]}]
   with self.assertRaises(ProtectedResidentHealthError):client.check()
   self.assertEqual(original,ref.read_bytes())

if __name__=='__main__':unittest.main()
