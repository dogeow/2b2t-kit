import unittest
from unittest.mock import patch
from transport_kernel_manifest import manifest

class TransportKernelManifestTests(unittest.TestCase):
 def test_loaded_function_identity_is_independent_of_current_source_file(self):
  original=manifest();self.assertEqual(original['protocol'],2)
  with patch('boat_towing.run',lambda *args,**kwargs:None):changed=manifest()
  self.assertNotEqual(original['loaded_code_sha256']['boat_towing.run'],changed['loaded_code_sha256']['boat_towing.run'])
  self.assertEqual(original['source_sha256'],changed['source_sha256'])

if __name__=='__main__':unittest.main()
