import copy,unittest
from owned_added_container_menu import allowed
from material_client import Client,Handoff

def state(screen='DispenserScreen',kind='DispenserMenu'):
 return dict(connected=True,manual_movement=False,world_session='w',control_revision=12,dimension='minecraft:overworld',health=20,screen=screen,menu=dict(id=4,type=kind,material_owned=True),supervision_lease=dict(kind='materials',job_session='owner',world_session='w',revision=12))
class AddedMenuTest(unittest.TestCase):
 def test_owned_dispenser_and_hopper(self):
  for screen,kind in [('DispenserScreen','DispenserMenu'),('HopperScreen','HopperMenu')]:self.assertTrue(allowed(state(screen,kind),'w','owner',12))
 def test_user_screen_and_mismatched_screen_type_stay_foreign(self):
  for screen,kind in [('DispenserScreen','HopperMenu'),('HopperScreen','DispenserMenu'),('AnvilScreen','DispenserMenu'),('ChatScreen','DispenserMenu')]:self.assertFalse(allowed(state(screen,kind),'w','owner',12))
  s=state();s['menu']['material_owned']=False;self.assertFalse(allowed(s,'w','owner',12))
 def test_native_scope_and_user_input_cannot_be_borrowed(self):
  changes=[('connected',False),('manual_movement',True),('world_session','other'),('control_revision',13)]
  for key,value in changes:
   s=state();s[key]=value;self.assertFalse(allowed(s,'w','owner',12))
  for key,value in [('kind','parking'),('job_session','other'),('world_session','other'),('revision',13)]:
   s=state();s['supervision_lease'][key]=value;self.assertFalse(allowed(s,'w','owner',12))
 def test_missing_native_witness_and_boolean_menu_id_are_rejected(self):
  for changes in [{'material_owned':None},{'id':0},{'id':True}]:
   s=state();s['menu'].update(changes);self.assertFalse(allowed(s,'w','owner',12))
  for task in [None,'']:self.assertFalse(allowed(state(),'w',task,12))
 def client(self,s):
  c=Client.__new__(Client);c.world='w';c.task='owner';c.rev=12;c.dimension='minecraft:overworld';c.raw=lambda:s;return c
 def test_material_client_accepts_only_native_owned_new_menus(self):
  for screen,kind in [('DispenserScreen','DispenserMenu'),('HopperScreen','HopperMenu')]:
   s=state(screen,kind);self.assertIs(s,self.client(s).status())
 def test_material_client_still_yields_to_foreign_dispenser(self):
  s=state();s['menu']['material_owned']=False
  with self.assertRaises(Handoff):self.client(s).status()

from types import SimpleNamespace
from owned_added_container_menu import opening_ticket,published,acknowledge,late_allowed

def before_open():
 s=state();s.update(screen='',time=1000,game_interaction_protocol=1,game_interaction={'interaction_serial':50});s['menu']={'id':0,'type':'InventoryMenu','cursor':{'count':0}};s['supervision_lease']['id']='lease';return s

def open_request():return dict(id='open2',op='interact',task_session='owner',world_session='w',expected_revision=12,pos=[1,2,3],expected_state='Block{minecraft:dispenser}[facing=up,triggered=false]',expected_hand='minecraft:netherite_sword')
def native_use():
 r=open_request();return dict(protocol=1,request_id='open2',world_session='w',pos=r['pos'],state_before=r['expected_state'],hand=r['expected_hand'],method='useItemOn',result_returned=True,consumed_action=True)
def late_frame(menu_id=2):
 s=state();s.update(time=2200,game_interaction_protocol=1,game_interaction={'interaction_serial':50},last_block_interaction=native_use());s['supervision_lease']['id']='lease';s['menu'].update(id=menu_id,material_owned=False);return s
class LateOwnedMenuTest(unittest.TestCase):
 def ready(self):
  c=SimpleNamespace();t=opening_ticket(before_open(),open_request(),'owner');self.assertIsNotNone(t);published(c,t);f=late_frame();acknowledge(c,open_request(),dict(id='open2',phase='done',world_session='w',last_block_interaction=native_use()),f);return c
 def test_delayed_native_dispenser_is_correlated_without_rewriting_native_flag(self):
  c=self.ready();s=late_frame();self.assertTrue(late_allowed(c,s));self.assertFalse(s['menu']['material_owned'])
 def test_no_completed_native_use_never_adopts(self):
  c=SimpleNamespace();published(c,opening_ticket(before_open(),open_request(),'owner'));self.assertFalse(late_allowed(c,late_frame()))
 def test_unrecognized_hand_user_menu_and_missing_before_scope_never_make_ticket(self):
  for key,value in [('expected_hand','minecraft:cobblestone'),('task_session','other'),('world_session','other')]:
   r=open_request();r[key]=value;self.assertIsNone(opening_ticket(before_open(),r,'owner'))
  for key,value in [('screen','DispenserScreen'),('manual_movement',True)]:
   s=before_open();s[key]=value;self.assertIsNone(opening_ticket(s,open_request(),'owner'))
 def test_wrong_native_interaction_and_failed_use_never_acknowledge(self):
  for key,value in [('request_id','other'),('pos',[2,2,3]),('hand','minecraft:air'),('consumed_action',False),('method','useItem')]:
   c=SimpleNamespace();published(c,opening_ticket(before_open(),open_request(),'owner'));n=native_use();n[key]=value;acknowledge(c,open_request(),dict(id='open2',phase='done',world_session='w',last_block_interaction=n),late_frame());self.assertFalse(late_allowed(c,late_frame()))
 def test_any_later_human_input_or_foreign_scope_rejects(self):
  for key,value in [('world_session','other'),('control_revision',13),('manual_movement',True),('screen','HopperScreen')]:
   c=self.ready();s=late_frame();s[key]=value;self.assertFalse(late_allowed(c,s))
  c=self.ready();s=late_frame();s['game_interaction']['interaction_serial']=51;self.assertFalse(late_allowed(c,s))
  for key,value in [('id','other'),('job_session','other'),('kind','parking'),('world_session','other')]:
   c=self.ready();s=late_frame();s['supervision_lease'][key]=value;self.assertFalse(late_allowed(c,s))
 def test_late_first_menu_has_bounded_time_window(self):
  c=self.ready();s=late_frame();s['time']=11000;self.assertFalse(late_allowed(c,s))
 def test_one_bound_menu_persists_through_read_only_poll_and_inventory_clicks(self):
  c=self.ready();s=late_frame();self.assertTrue(late_allowed(c,s));acknowledge(c,{'op':'snapshot','id':'read3'},dict(phase=None),s);s['time']=50000;self.assertTrue(late_allowed(c,s));s['menu']['id']=3;self.assertFalse(late_allowed(c,s))
 def test_close_removes_binding_and_prevents_reused_menu_id(self):
  c=self.ready();self.assertTrue(late_allowed(c,late_frame()));acknowledge(c,{'op':'close_menu'},dict(phase='done'),late_frame());self.assertFalse(late_allowed(c,late_frame()))
 def test_second_native_open_gets_its_own_id_and_cannot_inherit_previous_menu(self):
  c=self.ready();self.assertTrue(late_allowed(c,late_frame()));r=open_request();r['id']='open4';published(c,opening_ticket(before_open(),r,'owner'));self.assertFalse(late_allowed(c,late_frame()))
 def test_material_client_adopts_late_menu_from_exact_receipt(self):
  c=self.ready();s=late_frame();real=Client.__new__(Client);real.world='w';real.task='owner';real.rev=12;real.dimension='minecraft:overworld';real.raw=lambda:s;real._owned_added_opening=c._owned_added_opening;real._owned_added_bound=None;self.assertIs(s,real.status());self.assertFalse(s['menu']['material_owned'])

if __name__=='__main__':unittest.main()
