import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from concrete_shelter import scan

class ConcreteShelterScanTest(unittest.TestCase):
    def test_partial_or_unloaded_scan_never_becomes_missing_walls(self):
        for reply in ({'phase':'waiting','detail':'Server chunk is not loaded','blocks':[],
                       'scan_cells_read':0,'scan_total_cells':270},
                      {'blocks':[],'scan_cells_read':269,'scan_total_cells':270},
                      {'phase':'error','blocks':[]}):
            c=SimpleNamespace(request=Mock(return_value=reply))
            with self.assertRaisesRegex(RuntimeError,'survey'):scan(c,[0,0,0],[5,8,4])
            c.request.assert_called_once()
    def test_complete_empty_scan_can_prove_air(self):
        c=SimpleNamespace(request=Mock(return_value={'blocks':[],'scan_cells_read':270,'scan_total_cells':270}))
        self.assertEqual({},scan(c,[0,0,0],[5,8,4]))

if __name__=='__main__':unittest.main()
