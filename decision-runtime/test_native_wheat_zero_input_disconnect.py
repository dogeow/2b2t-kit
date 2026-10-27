import copy,unittest
from unittest.mock import patch
from native_wheat_zero_input_disconnect import prove,record,HOST_HASHES

class ZeroInputDisconnectTests(unittest.TestCase):
    def fixture(self):
        cells=[[1,63,2]];inventory={'minecraft:wheat':1,'minecraft:wheat_seeds':8}
        book={'cells':cells,'world_session':'old','complete':False,'inventory_credit':0,'pending':{'operation':'planter_wheat_batch','soils':cells},'inventory_before':inventory}
        unknown={'op':'planter_wheat_batch','params':{'soils':cells},'request_id':'r','world_session':'old','task_session':'t','original_request_replayed':False}
        mailbox={**unknown,'id':'r','soils':cells,'expires_at':100,'server':'s','dimension':'d'}
        identity={'world_session':'old','server':'s','dimension':'d','player_uuid':'player'}
        batch={'protocol':1,'total':1,'grain_before':1,'harvest_sent':0,'removed_confirmed':0,'plant_sent':0,'replanted_confirmed':0,'cells_server_confirmed':False,'crop_positions':[[1,64,2]]}
        f={'world_session':'new','connected':True,'health':20,'manual_movement':False,'screen':'','supervision_lease':None,'planter_active':False,'navigating':False,'planter_status':'已停止：离开世界','last_request':'r','server':'s','dimension':'d','player_uuid':'player','kit_version':'2026.10.17.5','menu':{'cursor':{'count':0}},'planter_material_batch':batch}
        return book,unknown,mailbox,identity,[{**f,'time':101},{**f,'time':102}]
    def proving(self,parts,hashes=HOST_HASHES):
        with patch('native_wheat_zero_input_disconnect.inventory_counts',return_value=parts[0]['inventory_before']):return prove(*parts,hashes)
    def test_no_input_proof_keeps_historical_job_incomplete_without_harvest_credit(self):
        parts=self.fixture();p=self.proving(parts);updated=record(parts[0],p)
        self.assertFalse(updated['complete']);self.assertIsNone(updated['pending']);self.assertEqual(0,updated['inventory_credit']);self.assertIsNotNone(parts[0]['pending'])
    def test_any_sent_or_acknowledged_input_or_replaced_retained_identity_is_refused(self):
        for key in('harvest_sent','removed_confirmed','plant_sent','replanted_confirmed'):
            parts=copy.deepcopy(self.fixture());parts[-1][-1]['planter_material_batch'][key]=1
            with self.assertRaises(RuntimeError):self.proving(parts)
        for key,value in(('last_request','another'),('planter_active',True),('world_session','old'),('player_uuid','other'),('health',19)):
            parts=copy.deepcopy(self.fixture());parts[-1][-1][key]=value
            with self.assertRaises(RuntimeError):self.proving(parts)
        with self.assertRaises(RuntimeError):self.proving(self.fixture(),{**HOST_HASHES,'auto_planter':'unknown'})
