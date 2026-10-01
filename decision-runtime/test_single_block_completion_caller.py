import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from material_client import Client


class SingleBlockCompletionCallerTest(unittest.TestCase):
 def client(self, root, phase, proof):
  class Fake(Client):
   def __init__(self):
    self.root=self.out=Path(root);self.world='world';self.rev=40;self.anchor=[1,2,3]
    self.owned=False;self.last=None;self.polls=0;self.request_ids=set()
   def raw(self):
    state={'world_session':'world','control_revision':40,'connected':True,'screen':'',
           'manual_movement':False,'health':20,'server':'simpcraft.com',
           'dimension':'minecraft:overworld','pos':[1,2,3],'time':1,'inventory':[]}
    path=self.root/'request.json'
    if path.exists():
     request=json.loads(path.read_text());self.request_ids.add(request['id']);self.polls+=1
     state.update(control_revision=41,id=request['id'],last_request=request['id'],
                  phase='running' if self.polls==1 else phase,
                  detail='outcome pending; no second excavation sent' if phase=='waiting' else 'bounded targets confirmed',
                  **proof)
    return state
  return Fake()

 def test_waiting_mine_print_and_recovery_return_once_without_replaying(self):
  for operation in ('mine_block','recover_shulker','professional_print'):
   with self.subTest(operation=operation),tempfile.TemporaryDirectory() as root,patch('material_client.time.sleep'):
    client=self.client(root,'waiting',{'server_confirmed':False,'confirmation_scope':'none','outcome_pending':True})
    result=client.request(operation,seconds=1,pos=[1,2,3])
    self.assertEqual('waiting',result['phase']);self.assertFalse(result['server_confirmed'])
    self.assertEqual(1,len(client.request_ids));self.assertEqual(2,client.polls)

 def test_checked_surfaces_unconfirmed_mining_and_printing_instead_of_success(self):
  for operation in ('mine_block','professional_print'):
   with self.subTest(operation=operation),tempfile.TemporaryDirectory() as root,patch('material_client.time.sleep'):
    client=self.client(root,'waiting',{'server_confirmed':False,'confirmation_scope':'none','outcome_pending':True})
    with self.assertRaisesRegex(RuntimeError,'outcome pending'):
     client.checked(operation,seconds=1,pos=[1,2,3])
    self.assertEqual(1,len(client.request_ids))

 def test_confirmed_mask_receipt_keeps_full_projection_unverified(self):
  with tempfile.TemporaryDirectory() as root,patch('material_client.time.sleep'):
   client=self.client(root,'done',{'server_confirmed':True,
    'confirmation_scope':'current_bounded_mask_distinct_exact_final_server_updates',
    'full_projection_confirmed':False,'bounded_target_count':2})
   result=client.request('professional_print',seconds=1)
   self.assertEqual('done',result['phase']);self.assertFalse(result['full_projection_confirmed'])
   self.assertEqual(2,result['bounded_target_count']);self.assertEqual(1,len(client.request_ids))


if __name__=='__main__':unittest.main()
