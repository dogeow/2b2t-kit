import copy,unittest
from village_refit_bounds import verified_bounds, with_verified_assignment
from village_assignment_guard import uncontained_adults
class RefitBoundsTest(unittest.TestCase):
 def fixture(self):
  x,y,z=5,10,20;slot=dict(profession='fisherman',original_container_preserved=True,occupant_uuid='own',bed_foot=[x,y,z],bed_head=[x,y,z+1],work_block=[x,y,z-2],previous_work_block=[x,y,z-3]);rows={}
  cells=[[sx,h,zz]for sx in [x-1,x+1]for h in range(y,y+3)for zz in range(z-2,z+2)]+[[x,h,z+2]for h in range(y,y+3)]+[[x,y+3,zz]for zz in range(z-2,z+2)]+[[x,y-1,zz]for zz in range(z-2,z+2)]+[[x,y+2,z-3]]
  for p in cells:rows[tuple(p)]=dict(pos=p,state='Block{minecraft:cobblestone}',solid=True,fluid=False)
  for zz in [z-3,z-2]:rows[x,y,zz]=dict(pos=[x,y,zz],state='Block{minecraft:barrel}[facing=north,open=false]',block_entity=True)
  rows[x,y+1,z-3]=dict(pos=[x,y+1,z-3],state='Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]')
  for zz,part in [(z,'foot'),(z+1,'head')]:rows[x,y,zz]=dict(pos=[x,y,zz],state='Block{minecraft:white_bed}[facing=south,occupied=false,part='+part+']')
  actor=dict(uuid='own',type='minecraft:villager',health=20,is_baby=False,pos=[5.5,10,21.5],bounds=dict(min=[5.2,10,21.2],max=[5.8,11.95,21.8]));scene=dict(world_session='w',scan_total_cells=90,scan_cells_read=90,blocks=list(rows.values()),scan_entities=[actor]);return scene,slot
 def test_real_bed_head_extension_fixes_only_the_obsolete_bound(self):
  scene,slot=self.fixture();bounds=verified_bounds(scene,slot,'w');self.assertEqual(bounds,{'min':[5,10,18],'max_exclusive':[6,13,22]});state={'world_session':'w','loaded_villagers':{'villagers':scene['scan_entities']}};policy={'world_session':'w','adult_assignment_bounds':{'own':{'min':[5,10,18],'max_exclusive':[6,13,21]}}};home={'min':[0,0,0],'max_exclusive':[30,30,30]};self.assertEqual(uncontained_adults(state,policy,home),['own']);policy['adult_assignment_bounds']['own']=bounds;self.assertEqual(uncontained_adults(state,policy,home),[]);state['loaded_villagers']['villagers'][0]['pos'][2]=22.1;self.assertEqual(uncontained_adults(state,policy,home),['own'])
 def test_missing_barrier_bed_or_original_container_does_not_authorize_widening(self):
  for p in [[4,10,18],[5,13,20],[5,9,21],[5,10,22],[5,10,17],[5,10,21]]:
   scene,slot=self.fixture();scene['blocks']=[v for v in scene['blocks']if v['pos']!=p]
   with self.subTest(p=p),self.assertRaises(ValueError):verified_bounds(scene,slot,'w')
 def test_partial_scan_other_world_and_outside_or_injured_resident_are_rejected(self):
  for mode in ['partial','world','outside','injured']:
   scene,slot=self.fixture()
   if mode=='partial':scene['scan_cells_read']=89
   elif mode=='world':scene['world_session']='elsewhere'
   elif mode=='outside':scene['scan_entities'][0]['bounds']['max'][2]=22.1
   else:scene['scan_entities'][0]['health']=19
   with self.subTest(mode=mode),self.assertRaises(ValueError):verified_bounds(scene,slot,'w')
 def test_policy_commit_preserves_all_other_assignments_and_is_idempotent(self):
  scene,slot=self.fixture();policy={'world_session':'w','adult_assignment_bounds':{'own':{'min':[5,10,18],'max_exclusive':[6,13,21]},'other':{'min':[0,0,0],'max_exclusive':[1,3,3]}},'shared_adult_bounds':{'parents':{'min':[30,10,0],'max_exclusive':[40,13,10]}},'all_contained_verified':True};before=copy.deepcopy(policy);updated=with_verified_assignment(policy,scene,slot,'w');self.assertEqual(policy,before);self.assertEqual(updated['adult_assignment_bounds']['other'],before['adult_assignment_bounds']['other']);self.assertEqual(updated['shared_adult_bounds'],before['shared_adult_bounds']);self.assertEqual(updated,with_verified_assignment(updated,scene,slot,'w'))
 def test_policy_commit_rejects_unrelated_world_unknown_resident_or_broad_expansion(self):
  for mode in ['world','missing','two_cells','other_x']:
   scene,slot=self.fixture();policy={'world_session':'w','adult_assignment_bounds':{'own':{'min':[5,10,18],'max_exclusive':[6,13,21]}}}
   if mode=='world':policy['world_session']='other'
   elif mode=='missing':policy['adult_assignment_bounds']={}
   elif mode=='two_cells':policy['adult_assignment_bounds']['own']['max_exclusive'][2]=20
   else:policy['adult_assignment_bounds']['own']['min'][0]=4
   with self.subTest(mode=mode),self.assertRaises(ValueError):with_verified_assignment(policy,scene,slot,'w')
if __name__=='__main__':unittest.main()
