import copy,json,tempfile,unittest
from pathlib import Path
from projected_source_return import return_receipt,return_water
from projected_source_column import SOURCE
import test_projected_source_column as previous
from test_projected_source_column import LOW,HIGH,KEY,WORLD
class Tests(unittest.TestCase):
 def receipt(self):
  a=dict(request_id='return-one',world_session=WORLD,operation='bucket_place',pos=[11,67,20],projected_source_return=True,source_column_profile='nine_rows',use_count=1,source_return_block_probe_count=1,confirmed=True,unknown_outcome=False,server_block_confirmed=True,server_inventory_confirmed=True,server_observed_state=SOURCE)
  return dict(id='return-one',world_session=WORLD,phase='done',bucket_water=a)
 def test_only_the_real_probe_and_both_server_receipts_prove_return(self):
  r=self.receipt();self.assertTrue(return_receipt(r,'return-one',WORLD,[11,67,20]))
  for key,value in [('source_return_block_probe_count',0),('source_return_block_probe_count',2),('source_return_block_probe_count',True),('use_count',2),('projected_source_return',False),('server_inventory_confirmed',False),('server_block_confirmed',False),('server_observed_state','Block{minecraft:air}'),('unknown_outcome',True)]:
   a=copy.deepcopy(r);a['bucket_water'][key]=value;self.assertFalse(return_receipt(a,'return-one',WORLD,[11,67,20]),key)
 def test_wrong_request_world_profile_or_cell_cannot_join(self):
  r=self.receipt()
  for req,world,p,profile in [('other',WORLD,[11,67,20],None),('return-one','other',[11,67,20],None),('return-one',WORLD,[10,67,20],None),('return-one',WORLD,[11,67,20],'four_rows')]:self.assertFalse(return_receipt(r,req,world,p,profile))
 class Fake:
  task='unit';world=WORLD;last='';uses=0;sent=False;stamp=0
  def __init__(self,unknown=False):base=previous.CompletedOverflowSupplyTest().prepared();self.model,self.frame=base.model,base.frame;self.unknown=unknown
  def status(self):return dict(projected_source_return_protocol=1,health=20,food=20,air_supply=300,world_session=self.world,screen='',manual_movement=False,guard_busy=False,guard_armed=True,supervision_lease={'job_session':self.task},hand={'item':'minecraft:water_bucket','count':1},inventory=[dict(slot=0,item='minecraft:bucket'if self.sent else'minecraft:water_bucket',count=1),dict(slot=1,item='minecraft:bucket',count=2)])
  def request(self,op,**p):
   if op=='projection_model':return {'projection_model':self.model}
   assert op=='bucket_place'and p['projected_source_return'];self.uses+=1;self.last='return-one';self.sent=True;r=Tests().receipt()
   if self.unknown:r['phase']='waiting';r['bucket_water']['server_block_confirmed']=False;r['bucket_water']['unknown_outcome']=True;r['bucket_water']['confirmed']=False
   return r
  def checked(self,op,**p):
   if op=='select_item':return {}
   assert op=='scan';self.stamp+=1;r=copy.deepcopy(self.frame);r['time']=self.stamp;return r
 def test_one_return_preserves_all_27_sources_in_three_independent_frames(self):
  c=self.Fake()
  with tempfile.TemporaryDirectory()as d:
   r=return_water(c,LOW,HIGH,[11,67,20],[11,67,21],'north',KEY,Path(d)/'one');self.assertTrue(r['complete']);self.assertEqual(27,r['original_source_cells_preserved']);self.assertEqual(3,len(set(r['frames'])));self.assertEqual(1,c.uses)
 def test_missing_original_block_ack_stays_pending_without_retry(self):
  c=self.Fake(True)
  with tempfile.TemporaryDirectory()as d:
   out=Path(d)/'one'
   with self.assertRaises(RuntimeError):return_water(c,LOW,HIGH,[11,67,20],[11,67,21],'north',KEY,out)
   r=json.loads((out/'progress.json').read_text());self.assertIsNotNone(r['pending']);self.assertEqual(1,c.uses)
 def test_old_protocol_is_rejected_before_dispatch(self):
  class Old(self.Fake):
   def status(self):s=super().status();s['projected_source_return_protocol']=0;return s
  c=Old()
  with tempfile.TemporaryDirectory()as d:
   out=Path(d)/'one'
   with self.assertRaises(RuntimeError):return_water(c,LOW,HIGH,[11,67,20],[11,67,21],'north',KEY,out)
   self.assertFalse(json.loads((out/'progress.json').read_text())['dispatch_started']);self.assertEqual(0,c.uses)
