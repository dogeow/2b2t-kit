import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from library_district_route import route,at_reserve_gallery
from librarian_room import LibrarianRoom,walk_public
class Builder:
 def __init__(self,pos):self.pos=pos;self.q=SimpleNamespace(world='w');self.book={};self.calls=[]
 def check(self):return {'pos':self.pos,'inventory':[]}
 def save(self):pass
 def n(self,op,**p):self.calls.append((op,p))
class Tests(unittest.TestCase):
 def configuration(self,root,**changes):
  proof={'complete':True,'pending':None,'open_roofs':[],'world_session':'w'};proof.update(changes);(root/'proof.json').write_text(json.dumps(proof));(root/'project-state.json').write_text(json.dumps({'reserve_library_counter':{'uuid':'reserve','work_block':[760991,64,797802],'proof':'proof.json','two_column_enclosure_verified':True}}))
 def room(self):return LibrarianRoom('reserve',(760991,64,797802),-1,interior_x_offsets=(-1,0))
 def test_private_room_roof_and_remote_positions_are_not_public_gallery(self):
  work=[760991,64,797802];self.assertTrue(at_reserve_gallery([760991.5,64.1,797803.5],work))
  for p in ([760991.5,64,797801.5],[760991.5,70,797803.5],[761022.5,65,797811.5],[760991.5,float('nan'),797803.5],[True,64,797803.5]):self.assertFalse(at_reserve_gallery(p,work))
 def test_wrong_world_pending_or_incomplete_route_proof_sends_no_input(self):
  for mutation in ({'world_session':'other'},{'pending':{'op':'mine'}},{'complete':False},{'open_roofs':[[1,2,3]]}):
   with tempfile.TemporaryDirectory()as d:
    root=Path(d);self.configuration(root,**mutation);b=Builder([760991.5,64,797803.5])
    with self.assertRaises(RuntimeError):route(b,self.room(),root,None,None)
    self.assertEqual([],b.calls)
 def test_original_pending_district_route_is_not_replayed(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);self.configuration(root);b=Builder([760991.5,64,797803.5]);b.book['district_routes']=[{'pending':True}]
   with self.assertRaises(RuntimeError):route(b,self.room(),root,None,None)
   self.assertEqual([],b.calls)
 def test_local_reserve_access_does_not_send_main_gallery_waypoint(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);self.configuration(root);b=Builder([760991.5,64,797803.5]);self.assertTrue(route(b,self.room(),root,None,None));self.assertEqual([760991.5,64.,797803.5],b.calls[0][1]['target'])
 def test_optional_hook_prevents_legacy_main_route_for_reserve(self):
  b=Builder([760991.5,64,797803.5]);b.walk_librarian_public=lambda room:True;walk_public(b,self.room());self.assertEqual([],b.calls)
 def test_main_only_adapter_keeps_existing_route(self):
  b=Builder([761022.5,65,797811.5]);b.walk_librarian_public=lambda room:False;room=LibrarianRoom('v',(761022,65,797813),1);walk_public(b,room);self.assertTrue(b.calls);self.assertEqual(room.public_pose()[2],b.calls[-1][1]['target'][2])
if __name__=='__main__':unittest.main()

class InsetServiceTests(unittest.TestCase):
 def config(self):return {'work_block':[760991,64,797801],'public_counter':[760991,64,797802],'service_roof':[760991,67,797803],'service_pose':[760991.5,64.1,797803.5]}
 def test_inset_preserves_public_service_column_beyond_both_caps(self):
  from library_district_route import service_geometry
  self.assertEqual(([760991,67,797803],[760991.5,64.1,797803.5]),service_geometry(self.config()))
  cfg=self.config();del cfg['service_roof']
  with self.assertRaises(ValueError):service_geometry(cfg)
 def test_invalid_or_nonfinite_service_pose_refused(self):
  from library_district_route import service_geometry
  for pose in ([760991.5,65.1,797803.5],[760991.5,float('nan'),797803.5],[760991.5,64.1,797802.5]):
   cfg=self.config();cfg['service_pose']=pose
   with self.assertRaises(ValueError):service_geometry(cfg)
 def test_closed_cap_in_wrong_service_column_refuses_before_mining(self):
  from library_district_route import clear_service_column
  class ScanOnly:
   def scan(self,*args):return {},{(1,63,2):{'solid':True,'fluid':False},(1,65,2):{'state':'Block{minecraft:oak_trapdoor}'},(1,67,2):{'state':'Block{minecraft:cobblestone}'}}
  with self.assertRaises(RuntimeError):clear_service_column(ScanOnly(),[1,67,2])

class SingleColumnRouteTests(Tests):
 def test_single_column_uses_its_own_verified_enclosure_field(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);self.configuration(root);p=json.loads((root/'project-state.json').read_text());cfg=p['reserve_library_counter'];cfg.pop('two_column_enclosure_verified');cfg['enclosure_verified']=True;(root/'project-state.json').write_text(json.dumps(p));b=Builder([760991.5,64,797803.5]);self.assertTrue(route(b,LibrarianRoom('reserve',(760991,64,797802),-1),root,None,None))
 def test_absent_or_nonboolean_enclosure_certificate_is_refused(self):
  for value in (False,'true',1):
   with tempfile.TemporaryDirectory()as d:
    root=Path(d);self.configuration(root);p=json.loads((root/'project-state.json').read_text());cfg=p['reserve_library_counter'];cfg.pop('two_column_enclosure_verified');cfg['enclosure_verified']=value;(root/'project-state.json').write_text(json.dumps(p));b=Builder([760991.5,64,797803.5])
    with self.assertRaises(RuntimeError):route(b,self.room(),root,None,None)
    self.assertEqual([],b.calls)

class WalkingSourceWitnessTests(unittest.TestCase):
 def setup_project(self,root):
  (root/'proof.json').write_text(json.dumps({'complete':True,'pending':None,'open_roofs':[],'world_session':'w'}))
  (root/'walking.json').write_text(json.dumps({'complete':True,'pending':None,'open_roofs':[],'world_session':'w','inventory_conserved':True,'airlock_crossings':[{'pending':False,'lever_restored':True,'both_doors_closed':True}]}))
  cfg={'uuid':'reserve','work_block':[760988,64,797802],'proof':'proof.json','enclosure_verified':True,'walking_airlock_verified':True,'walking_airlock_proof':'walking.json'}
  (root/'project-state.json').write_text(json.dumps({'reserve_library_counter':cfg,'locked_trades':{'book':{'villager_uuid':'paid'}},'locked_optional_trades':{}}))
  (root/'layout-plan.json').write_text(json.dumps({'slots':[{'id':'ES03','occupant_uuid':'paid','work_block':[761022,65,797813],'actual_work_block':[761022,65,797814],'interior_floor_y':65,'interior_depth':2}]}))
 def test_already_at_reserve_is_not_misclassified_as_a_main_counter(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);self.setup_project(root);b=Builder([760988.5,64,797803.5]);self.assertTrue(route(b,LibrarianRoom('reserve',(760988,64,797802),-1),root,None,None));self.assertFalse(b.calls)
 def test_exact_registered_inset_pose_is_aligned_before_return(self):
  from unittest.mock import patch
  class B(Builder):
   def scan(self,*args):return {},{(761022,66,797814):{'state':'Block{minecraft:oak_trapdoor}[half=top,open=false,waterlogged=false]'},(761022,67,797814):{'solid':True}}
   def n(self,op,**p):super().n(op,**p);self.pos=p['target']
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);self.setup_project(root);b=B([761022.5,65,797813.5])
   with patch('library_airlock_route.route',return_value=True):self.assertTrue(route(b,LibrarianRoom('reserve',(760988,64,797802),-1),root,None,None))
   self.assertEqual([761022.5,65.,797811.5],b.calls[0][1]['target']);self.assertEqual('paid',b.book['public_counter_return_alignments'][0]['keeper_uuid'])
 def test_unwitnessed_private_pose_never_sends_alignment_input(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);self.setup_project(root);b=Builder([761022.5,65,797815.5])
   with self.assertRaises(RuntimeError):route(b,LibrarianRoom('reserve',(760988,64,797802),-1),root,None,None)
   self.assertFalse(b.calls)
