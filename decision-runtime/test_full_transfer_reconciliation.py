import copy,unittest
from full_transfer_reconciliation import full_deposit
class FullTransferTests(unittest.TestCase):
 def fixture(self):
  air={'item':'minecraft:air','count':0};inv=lambda n:[{'slot':i,'item':'minecraft:white_bed','count':1}for i in range(n)]
  menu=lambda n:dict(id=1,type='ChestMenu',cursor={'count':0},slots=[{'slot':i,'item':'minecraft:white_bed','count':1}for i in range(n)]+[air]*(27-n)+[air]*36)
  a=dict(id='open',world_session='w',inventory=inv(6),menu=menu(6));s=dict(world_session='w',inventory=inv(3),menu=menu(9),health=20,manual_movement=False,phase='done',screen='ContainerScreen',last_request='last',pos=[1,2,3],control_revision=4)
  c=dict(action='transfer',deposit=True,item='minecraft:white_bed',target=0);err=dict(error='Destination has no space for minecraft:white_bed',type='RuntimeError',native_inflight=None,unconfirmed_native_request=None,last_request='last');e=[dict(request_id='open'),dict(request_id='last',world_session='w',params={'task_session':'t','kind':'quick_move','expected_item':'minecraft:white_bed'},phase='done',op='slot_click',inventory_delta={'minecraft:white_bed':-3},revision_after=4,position_after=[1,2,3])];return c,err,a,s,e
 def test_conserved_partial_beds_are_not_replayed(self):
  args=self.fixture();r=full_deposit(*args,'w','t');self.assertEqual(r['confirmed_moved'],3);self.assertEqual(r['actual_held'],3)
 def test_recorded_read_only_storage_scan_is_allowed(self):
  c,x,a,s,e=self.fixture();e.insert(1,dict(request_id='read',op='scan',phase='done',world_session='w',params={'task_session':'t'},inventory_delta={}));self.assertIsNotNone(full_deposit(c,x,a,s,e,'w','t'))
 def test_unknown_foreign_or_unaccounted_items_are_rejected(self):
  for mode in ['unknown','cursor','world','stock','box','click','delta','task','moving','error']:
   with self.subTest(mode=mode):
    c,x,a,s,e=self.fixture()
    if mode=='unknown':x['unconfirmed_native_request']={'id':'pending'}
    if mode=='cursor':s['menu']['cursor']['count']=1
    if mode=='world':s['world_session']='other'
    if mode=='stock':s['inventory'].append({'slot':10,'item':'minecraft:diamond','count':1})
    if mode=='box':s['menu']['slots'][0]={'item':'minecraft:diamond','count':1}
    if mode=='click':e[-1]['params']['kind']='pickup'
    if mode=='delta':e[-1]['inventory_delta']={'minecraft:white_bed':-4}
    if mode=='task':e[-1]['params']['task_session']='other'
    if mode=='moving':s['manual_movement']=True
    if mode=='error':x['error']='Inventory transfer not confirmed; no duplicate click'
    self.assertIsNone(full_deposit(c,x,a,s,e,'w','t'))
if __name__=='__main__':unittest.main()
