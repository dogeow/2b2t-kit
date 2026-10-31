import copy,json,tempfile,unittest
from pathlib import Path
from projected_bubble_column import cells_for,scan_bounds,geometry,fill,BUBBLE
LOW=[20,63,30];HIGH=[20,69,30]
class Tests(unittest.TestCase):
 def fixture(self):return json.loads((Path(__file__).parent/'test_fixtures/up-bubble-column.json').read_text())
 def test_exact_original_bubble_and_outlet_have_all_56_pins(self):
  f=self.fixture();p=geometry(f['model'],f['frame'],LOW,HIGH,'unit-world');self.assertEqual(56,len(p['bubble_boundary_pins']));self.assertEqual(7,len(p['bubble_cells']));self.assertEqual([14,69,29],p['outlet_cells'][-1]);self.assertEqual([20,70,30],p['bubble_service_cap'])
 def test_wrong_lift_direction_seal_or_cap_is_not_adopted(self):
  for mode in ['direction','seal','cap']:
   f=self.fixture()
   if mode=='direction':next(v for v in f['model']['expected']if v['pos']==LOW)['state']='Block{minecraft:bubble_column}[drag=true]'
   if mode=='seal':f['frame']['blocks'][0]['state']='Block{minecraft:stone}'
   if mode=='cap':f['frame']['blocks'].append(dict(pos=[20,70,30],state='Block{minecraft:glass}',block_entity=False))
   with self.assertRaises(RuntimeError):geometry(f['model'],f['frame'],LOW,HIGH,'unit-world')
 def test_no_prediction_or_cross_world_evidence_is_accepted(self):
  for key,value in [('world_session','other'),('scan_coherent',False),('scan_cells_read',323)]:
   f=self.fixture();f['frame'][key]=value
   with self.assertRaises(RuntimeError):geometry(f['model'],f['frame'],LOW,HIGH,'unit-world')
 def test_invalid_height_width_and_noninteger_bounds(self):
  for hi in [[21,69,30],[20,68,30],[20,69.0,30]]:
   with self.assertRaises(ValueError):cells_for(LOW,hi)
 def test_preflight_failure_is_not_a_dispatched_water_request(self):
  class Fake:
   task='unit';
   def status(self):return {'projected_bubble_column_protocol':0}
  with tempfile.TemporaryDirectory()as d:
   out=Path(d)/'one'
   with self.assertRaises(RuntimeError):fill(Fake(),LOW,HIGH,LOW,'unit-bubble',out)
   q=json.loads((out/'progress.json').read_text());self.assertFalse(q['dispatch_started']);self.assertIsNone(q['pending'])

class ReceiptTests(unittest.TestCase):
 class Fake:
  task='unit';world='unit-world';last=''
  def __init__(self,mode='done',index=0):
   self.fixture=json.loads((Path(__file__).parent/'test_fixtures/up-bubble-column.json').read_text());self.mode=mode;self.index=index;self.target=[LOW[0],LOW[1]+index,LOW[2]];self.sent=False;self.uses=0;self.stamp=0
  def status(self):
   return dict(projected_bubble_column_protocol=1,health=20,air_supply=300,screen='',manual_movement=False,guard_busy=False,guard_armed=True,world_session=self.world,supervision_lease={'job_session':self.task},hand={'item':'minecraft:water_bucket','count':1},inventory=[dict(item='minecraft:bucket'if self.sent else'minecraft:water_bucket',count=1,slot=0),dict(item='minecraft:water_bucket',count=1,slot=1),dict(item='minecraft:bucket',count=3,slot=2)])
  def request(self,op,**params):
   if op=='projection_model':return {'projection_model':self.fixture['model']}
   assert op=='bucket_place';self.uses+=1;self.last='unit-native-water';self.sent=self.mode!='refused'
   if self.mode=='refused':return dict(id=self.last,world_session=self.world,phase='error',last_bucket_admission_rejection=dict(protocol=2,input_sent=False,request_id=self.last,world_session=self.world,material_owner_current=True,bucket_task_active=False,active_request_id='',active_command='',navigation_active=False))
   ack=dict(request_id=self.last,world_session=self.world,pos=self.target,operation='bucket_place',use_count=1,projected_bubble_column=True,expected_bubble_state=BUBBLE,confirmed=True,unknown_outcome=False,server_block_confirmed=True,server_inventory_confirmed=True)
   if self.mode=='unknown':ack.update(confirmed=False,unknown_outcome=True,server_inventory_confirmed=False)
   return dict(id=self.last,world_session=self.world,phase='done'if self.mode in ('done','corrected_source','spill','bad_outlet')else'waiting',bucket_water=ack)
  def checked(self,op,**params):
   if op=='select_item':return {}
   assert op=='scan';r=copy.deepcopy(self.fixture['frame']);self.stamp+=1;r['time']=self.stamp
   for i in range(self.index):r['blocks'].append(dict(pos=[LOW[0],LOW[1]+i,LOW[2]],state=BUBBLE,block_entity=False))
   if self.mode in ('already_source','already_bubble'):r['blocks'].append(dict(pos=self.target,state='Block{minecraft:water}[level=0]'if self.mode=='already_source'else BUBBLE,block_entity=False))
   if self.sent:
    r['blocks'].append(dict(pos=self.target,state='Block{minecraft:water}[level=0]'if self.mode=='corrected_source'else BUBBLE,block_entity=False))
    if self.index==6:
     for i,p in enumerate(cells_for(LOW,HIGH)[1],1):r['blocks'].append(dict(pos=p,state=f'Block{{minecraft:water}}[level={6 if self.mode=="bad_outlet"and i==7 else i}]',block_entity=False))
    if self.mode=='spill':r['blocks'].append(dict(pos=[LOW[0]+1,LOW[1],LOW[2]+1],state='Block{minecraft:water}[level=1]',block_entity=False))
   return r
 def test_confirmed_native_bubble_and_inventory_need_independent_three_frames(self):
  c=self.Fake()
  with tempfile.TemporaryDirectory()as d:
   q=fill(c,LOW,HIGH,LOW,'unit-bubble',Path(d)/'one');self.assertTrue(q['complete']);self.assertEqual(3,len(set(q['frames'])));self.assertEqual(1,c.uses);self.assertIsNone(q['pending'])
 def test_missing_inventory_receipt_stays_pending_and_is_never_replayed(self):
  c=self.Fake('unknown')
  with tempfile.TemporaryDirectory()as d:
   out=Path(d)/'one'
   with self.assertRaises(RuntimeError):fill(c,LOW,HIGH,LOW,'unit-bubble',out)
   q=json.loads((out/'progress.json').read_text());self.assertEqual('one_upward_bubble_use',q['pending']);self.assertTrue(q['dispatch_started']);self.assertEqual(1,c.uses)
 def test_explicit_no_input_refusal_is_not_an_unknown_bucket_use(self):
  from projected_source_column import SourceAdmissionRejected
  c=self.Fake('refused')
  with tempfile.TemporaryDirectory()as d:
   out=Path(d)/'one'
   with self.assertRaises(SourceAdmissionRejected):fill(c,LOW,HIGH,LOW,'unit-bubble',out)
   q=json.loads((out/'progress.json').read_text());self.assertIsNone(q['pending']);self.assertTrue(q['rejected_before_use']);self.assertEqual(1,c.uses);self.assertFalse(c.sent)

 def test_each_of_the_seven_stages_preserves_the_prefix_and_finishes_the_outlet(self):
  for index in range(7):
   with self.subTest(index=index),tempfile.TemporaryDirectory()as d:
    c=self.Fake(index=index);q=fill(c,LOW,HIGH,c.target,'unit-bubble',Path(d)/'one')
    self.assertTrue(q['complete']);self.assertEqual(index+1,q['completed_bubbles']);self.assertEqual(1,c.uses);self.assertEqual(3,len(set(q['frames'])))
 def test_corrected_source_spill_and_wrong_final_outlet_never_prove_completion(self):
  from unittest.mock import patch
  for mode,index in [('corrected_source',0),('spill',0),('bad_outlet',6)]:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    c=self.Fake(mode,index);out=Path(d)/'one'
    with patch('projected_bubble_column.time.monotonic',side_effect=[0,16]):
     with self.assertRaises(RuntimeError):fill(c,LOW,HIGH,c.target,'unit-bubble',out)
    q=json.loads((out/'progress.json').read_text());self.assertTrue(q['target_confirmed']);self.assertFalse(q['complete']);self.assertIsNone(q['pending']);self.assertEqual(1,c.uses)
 def test_existing_source_or_bubble_is_not_poured_again(self):
  for mode in ['already_source','already_bubble']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as d:
    c=self.Fake(mode);out=Path(d)/'one'
    with self.assertRaises(RuntimeError):fill(c,LOW,HIGH,c.target,'unit-bubble',out)
    q=json.loads((out/'progress.json').read_text());self.assertFalse(q['dispatch_started']);self.assertIsNone(q['pending']);self.assertEqual(0,c.uses)
