import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from central_library_walk import route
from librarian_room import LibrarianRoom
class Builder:
 def __init__(self,pos):self.pos=pos;self.q=SimpleNamespace(world='w');self.book={};self.calls=[]
 def check(self):return {'pos':self.pos}
 def save(self):pass
 def n(self,op,**params):self.calls.append((op,params));self.pos=params['target']
 def scan(self,*a):return {},{(761022,66,797814):{'state':'Block{minecraft:oak_trapdoor}[half=top,open=false,waterlogged=false]'},(761022,67,797814):{'solid':True}}
class Tests(unittest.TestCase):
 def config(self,d,**changes):
  root=Path(d);proof={'complete':True,'pending':None,'open_roofs':[],'world_session':'w','patient_uuid':'source','geometry':{'verified':True}};proof.update(changes);(root/'proof.json').write_text(json.dumps(proof));(root/'project-state.json').write_text(json.dumps({'central_library_receiver':{'occupant_uuid':'source','front':[761016,64,797809],'bedless_proof':'proof.json'},'locked_trades':{'book':{'villager_uuid':'paid'}},'locked_optional_trades':{}}));(root/'layout-plan.json').write_text(json.dumps({'slots':[{'id':'ES03','occupant_uuid':'paid','work_block':[761022,65,797813],'actual_work_block':[761022,65,797814],'interior_depth':2}]}));return root
 def room(self):return LibrarianRoom('source',(761016,64,797809),-1)
 def test_already_at_central_public_pose_sends_no_movement(self):
  with tempfile.TemporaryDirectory()as d:
   b=Builder([761016.5,64.,797810.5]);self.assertTrue(route(b,self.room(),self.config(d)));self.assertEqual([],b.calls)
 def test_west_return_uses_lower_half_step_approach(self):
  with tempfile.TemporaryDirectory()as d:
   b=Builder([761002.5,64.,797810.5]);self.assertTrue(route(b,self.room(),self.config(d)));self.assertEqual([761016.5,64.,797810.5],b.pos);self.assertIn([761014.5,64.,797810.5],[v[1]['target']for v in b.calls]);self.assertTrue(all(v[0]=='walk'for v in b.calls))
 def test_east_return_descends_only_at_the_witnessed_central_approach(self):
  with tempfile.TemporaryDirectory()as d:
   b=Builder([761028.5,65.,797810.5]);self.assertTrue(route(b,self.room(),self.config(d)));self.assertEqual([[761028.5,65.,797811.5],[761016.5,65.,797811.5],[761016.5,64.,797810.5]],[v[1]['target']for v in b.calls])
 def test_outbound_reaches_normal_west_gallery_then_defers_existing_room_route(self):
  with tempfile.TemporaryDirectory()as d:
   b=Builder([761016.5,64.,797810.5]);self.assertFalse(route(b,LibrarianRoom('paid',(761028,65,797809),-1),self.config(d)));self.assertEqual([761014.5,64.,797811.5],b.pos);self.assertFalse(b.book['central_public_routes'][0]['pending'])
 def test_foreign_world_unfinished_or_wrong_resident_proof_sends_nothing(self):
  for mutation in ({'world_session':'other'},{'pending':{'op':'mine'}},{'complete':False},{'patient_uuid':'other'},{'geometry':{'verified':False}}):
   with tempfile.TemporaryDirectory()as d:
    b=Builder([761002.5,64.,797810.5]);root=self.config(d,**mutation)
    with self.assertRaises(RuntimeError):route(b,self.room(),root)
    self.assertEqual([],b.calls)
 def test_pending_prior_route_is_not_replayed(self):
  with tempfile.TemporaryDirectory()as d:
   b=Builder([761002.5,64.,797810.5]);b.book['central_public_routes']=[{'pending':True}]
   with self.assertRaises(RuntimeError):route(b,self.room(),self.config(d))
   self.assertEqual([],b.calls)
 def test_exact_paid_inset_public_pose_is_admitted_but_private_room_is_not(self):
  for z,valid in [(797813.5,True),(797815.5,False)]:
   with tempfile.TemporaryDirectory()as d:
    b=Builder([761022.5,65.,z]);root=self.config(d)
    if valid:self.assertTrue(route(b,self.room(),root))
    else:
     with self.assertRaises(RuntimeError):route(b,self.room(),root)
     self.assertEqual([],b.calls)
 def test_main_only_route_does_not_change_existing_controller(self):
  with tempfile.TemporaryDirectory()as d:
   b=Builder([761002.5,64.,797811.5]);self.assertFalse(route(b,LibrarianRoom('paid',(761028,65,797809),-1),self.config(d)));self.assertEqual([],b.calls)
if __name__=='__main__':unittest.main()

class PublicRouteChainTests(unittest.TestCase):
 def test_reserve_departure_reaches_gallery_before_central_approach(self):
  from central_library_walk import chain_public_routes
  calls=[]
  def district():calls.append('restored_exit');return False
  def central():self.assertEqual(['restored_exit'],calls);calls.append('central');return True
  self.assertTrue(chain_public_routes(central,district,reserve_departure=True));self.assertEqual(['restored_exit','central'],calls)
 def test_normal_central_departure_is_normalized_before_district(self):
  from central_library_walk import chain_public_routes
  calls=[]
  def central():calls.append('central_exit');return False
  def district():self.assertEqual(['central_exit'],calls);return True
  self.assertTrue(chain_public_routes(central,district,reserve_departure=False))
 def test_success_or_unknown_failure_never_starts_second_route(self):
  from central_library_walk import chain_public_routes
  for reserve in (False,True):
   calls=[]
   def forbidden():calls.append('unsafe');raise AssertionError('Second route must not run')
   first=lambda:True
   self.assertTrue(chain_public_routes(forbidden if reserve else first,first if reserve else forbidden,reserve_departure=reserve));self.assertEqual([],calls)
   def failed():raise RuntimeError('Original pending gate')
   with self.assertRaisesRegex(RuntimeError,'Original pending gate'):chain_public_routes(forbidden if reserve else failed,failed if reserve else forbidden,reserve_departure=reserve)
   self.assertEqual([],calls)

class UpperGalleryFallbackTests(unittest.TestCase):
 config=Tests.config
 room=Tests.room
 def test_central_fallback_uses_existing_half_steps_without_entering_solid_lower_aisle(self):
  from central_library_walk import upper_gallery_print_fallback
  with tempfile.TemporaryDirectory()as d:
   b=Builder([761016.5,64.,797810.5]);root=self.config(d);self.assertTrue(upper_gallery_print_fallback(b,self.room(),root));self.assertEqual([761016.5,65.,797811.5],b.pos);self.assertTrue(all(op=='walk'for op,params in b.calls));self.assertFalse(b.book['upper_gallery_print_fallbacks'][0]['pending']);self.assertIn([761015.5,64.5,797811.5],[p['target']for op,p in b.calls])
 def test_foreign_world_or_source_rejects_before_movement(self):
  from central_library_walk import upper_gallery_print_fallback
  for change in ({'world_session':'other'},{'patient_uuid':'other'}):
   with tempfile.TemporaryDirectory()as d:
    b=Builder([761016.5,64.,797810.5]);root=self.config(d,**change)
    with self.assertRaises(RuntimeError):upper_gallery_print_fallback(b,self.room(),root)
    self.assertEqual([],b.calls)
 def test_noncentral_workpoint_keeps_its_original_fallback(self):
  from central_library_walk import upper_gallery_print_fallback
  b=Builder([0,64,0]);self.assertFalse(upper_gallery_print_fallback(b,LibrarianRoom('other',(1,64,2),1),'/no-file-read'));self.assertEqual([],b.calls)
