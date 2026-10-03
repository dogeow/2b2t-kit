"""Daily registered planting never tills or plants ordinary terrain."""
import json
from pathlib import Path
import tempfile
import unittest

from potato_farm import run
from test_potato_farm import FarmClient,SPEC,row
from test_wheat_farm import WheatClient,WHEAT


class ExistingFarmlandTests(unittest.TestCase):
    def test_daily_potato_and_wheat_reject_grass_dirt_before_hoe_selection_or_world_interaction(self):
        for request,client in ((SPEC,FarmClient()),(WHEAT,WheatClient())):
            with self.subTest(crop=request.get('crop','potato')),tempfile.TemporaryDirectory() as folder:
                result=run(client,request,folder,existing_farmland_only=True)
                self.assertEqual('WAIT_EXISTING_FARMLAND',result['code']);self.assertEqual(0,result['planted_cells'])
                self.assertTrue(all(op=='scan' for op,_ in client.calls));self.assertEqual(250,client.inv[0]['durability'])
                self.assertFalse(json.loads(Path(result['journal']).read_text())['pending'])
    def test_daily_existing_farmland_plants_only_with_seed_and_leaves_hoe_untouched(self):
        for request,client in ((SPEC,FarmClient(farmland=True)),(WHEAT,WheatClient(farmland=True))):
            with self.subTest(crop=request.get('crop','potato')),tempfile.TemporaryDirectory() as folder:
                result=run(client,request,folder,max_cells=4,existing_farmland_only=True)
                self.assertEqual('FARM_BATCH',result['code']);self.assertEqual(4,result['planted_cells'])
                self.assertEqual(250,client.inv[0]['durability']);self.assertEqual(4,len(client.interact_calls()))
                self.assertTrue(all(not p['expected_hand'].endswith('_hoe') for p in client.interact_calls()))
    def test_farmland_becoming_grass_before_single_interact_stops_without_tilling(self):
        client=WheatClient(farmland=True);native=client.request;scans=0
        def changed(op,**params):
            nonlocal scans
            if op=='scan':
                scans+=1
                if scans==3:client.rows[(-2,63,-2)]=row([-2,63,-2],'Block{minecraft:grass_block}[snowy=false]')
            return native(op,**params)
        client.request=changed
        with tempfile.TemporaryDirectory() as folder:
            result=run(client,WHEAT,folder,max_cells=1,existing_farmland_only=True)
            self.assertEqual('WAIT_EXISTING_FARMLAND',result['code']);self.assertFalse(client.interact_calls())
            self.assertEqual(250,client.inv[0]['durability'])
    def test_explicit_new_field_default_still_uses_original_authorized_till_workflow(self):
        client=WheatClient()
        with tempfile.TemporaryDirectory() as folder:
            result=run(client,WHEAT,folder,max_cells=1)
        self.assertEqual('FARM_BATCH',result['code']);self.assertEqual(2,len(client.interact_calls()));self.assertEqual(249,client.inv[0]['durability'])


if __name__=='__main__':unittest.main()
