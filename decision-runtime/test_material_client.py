import unittest
from unittest.mock import patch
from material_client import Client,MaterialClient
BUSY='Construction guard is defending or eating; wait before changing items or starting work'
class Tests(unittest.TestCase):
 def test_only_pre_dispatch_guard_busy_is_retried(self):
  c=MaterialClient.__new__(MaterialClient);c.task='t';c.status=lambda:{}
  with patch.object(Client,'request',side_effect=[{'phase':'error','detail':BUSY},{'phase':'done'}]) as call,patch('material_client.time.sleep'):
   self.assertEqual(c.request('slot_click')['phase'],'done');self.assertEqual(call.call_count,2)
 def test_ambiguous_inventory_errors_are_never_replayed(self):
  c=MaterialClient.__new__(MaterialClient);c.task='t';c.status=lambda:{}
  with patch.object(Client,'request',return_value={'phase':'error','detail':'Inventory transfer not confirmed'}) as call:
   self.assertEqual(c.request('slot_click')['phase'],'error');self.assertEqual(call.call_count,1)
if __name__=='__main__':unittest.main()
