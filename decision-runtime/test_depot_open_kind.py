import unittest
from unittest.mock import Mock,patch
from material_depots import _open_depot

class DepotOpenKindTest(unittest.TestCase):
    def test_recorded_personal_ender_deposit_uses_ender_verification_and_allows_empty(self):
        c=Mock();p=[1,64,2]
        with patch('material_storage_index.records',return_value=[{'pos':p,'block_id':'minecraft:ender_chest'}]),patch('material_depots.open_grounded_chest',return_value={'menu':{}})as opened:
            _open_depot(c,p,deposit_only=True)
            opened.assert_called_once_with(c,p,block_id='minecraft:ender_chest',allow_empty=True)
    def test_unknown_type_or_missing_record_does_not_claim_an_ender_chest(self):
        c=Mock();p=[1,64,2]
        with patch('material_storage_index.records',return_value=[]),patch('material_depots.open_grounded_chest')as opened:
            _open_depot(c,p)
            opened.assert_called_once_with(c,p)
        with patch('material_storage_index.records',return_value=[{'pos':p,'block_id':'minecraft:barrel'}]),patch('material_depots.open_grounded_chest')as opened:
            with self.assertRaises(RuntimeError):_open_depot(c,p,deposit_only=True)
            opened.assert_not_called()
