import unittest
from unittest.mock import Mock,patch
from village_owner_startup import open_verified_owner
class VillageOwnerStartupTests(unittest.TestCase):
 def test_kernel_failure_opens_no_native_owner(self):
  for failure in [AttributeError('missing cargo safety'),RuntimeError('bad code manifest')]:
   with self.subTest(failure=failure),patch('village_owner_startup.manifest',side_effect=failure):
    factory=Mock()
    with self.assertRaises(type(failure)):open_verified_owner(factory,'root')
    factory.assert_not_called()
 def test_old_protocol_opens_no_native_owner(self):
  with patch('village_owner_startup.manifest',return_value={'protocol':1}):
   factory=Mock()
   with self.assertRaises(RuntimeError):open_verified_owner(factory,'root')
   factory.assert_not_called()
 def test_verified_manifest_precedes_one_lease_open(self):
  order=[];proof={'protocol':2};owner=object()
  with patch('village_owner_startup.manifest',side_effect=lambda:order.append('verify')or proof):
   factory=Mock(side_effect=lambda *a,**kw:order.append('open')or owner)
   result= open_verified_owner(factory,'root','out','server',remote_finish='guard')
  self.assertEqual(order,['verify','open']);self.assertEqual(result,(owner,proof));factory.assert_called_once_with('root','out','server',remote_finish='guard')
if __name__=='__main__':unittest.main()
