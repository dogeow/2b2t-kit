import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from material_jobs.renewable_flowers import suitable,grow


def row(pos,name,**changes):
    return {'pos':pos,'state':'Block{minecraft:'+name+'}','solid':True,'fluid':False,'block_entity':False,**changes}


class RenewableFlowersTest(unittest.TestCase):
    def test_natural_grass_with_existing_flowers_elsewhere_is_eligible(self):
        rows=[row([0,64,0],'grass_block'),row([1,65,0],'poppy',solid=False),row([-1,63,0],'dirt')]
        self.assertTrue(suitable(rows,[0,64,0]))
    def test_water_container_built_structure_or_occupied_target_are_preserved(self):
        for obstruction in (row([1,64,0],'water',fluid=True),row([1,64,0],'chest',block_entity=True),
                            row([1,64,0],'oak_planks'),row([0,65,0],'short_grass',solid=False)):
            self.assertFalse(suitable([row([0,64,0],'grass_block'),obstruction],[0,64,0]))
    def test_missing_or_non_grass_floor_does_not_authorize_bone_meal(self):
        self.assertFalse(suitable([],[0,64,0]));self.assertFalse(suitable([row([0,64,0],'dirt')],[0,64,0]))
    def client(self,unknown=False):
        class C:
            world='world';last=None;count=56;calls=[]
            def status(self):return {'world_session':'world','pos':[100.5,66,100.5],
                'inventory':[{'slot':0,'item':'minecraft:bone_meal','count':self.count}]}
            def request(self,op,**params):
                self.last='scan-'+str(len(self.calls));self.calls.append((op,params))
                rows=[row([100,64,100],'grass_block')]
                if self.count==55:rows.append(row([101,65,100],'poppy',solid=False))
                return {'id':self.last,'world_session':'world','phase':'done','scan_cells_read':405,'scan_total_cells':405,'blocks':rows}
            def checked(self,op,**params):
                self.calls.append((op,params))
                if op=='interact':
                    if unknown:raise RuntimeError('unknown dispatch')
                    self.count-=1
                return {'phase':'done'}
        return C()
    def test_one_consumed_bone_meal_records_observed_flowers_without_inventory_credit(self):
        with tempfile.TemporaryDirectory()as t:
            c=self.client();profile={'protected_regions':[{'min':[0,0,0],'max':[10,100,10]}]}
            with patch('work_access.approach_faces',return_value='up'):
                r=grow(c,[100,64,100],profile,Path(t)/'use',c.status)
            self.assertEqual(1,r['used']);self.assertEqual(1,r['observed_flower_count']);self.assertEqual(0,r['inventory_credit'])
            self.assertEqual(1,sum(op=='interact'for op,_ in c.calls))
    def test_unknown_growth_preserves_pending_intent_and_never_repeats(self):
        with tempfile.TemporaryDirectory()as t:
            c=self.client(unknown=True);out=Path(t)/'use';profile={'protected_regions':[{'min':[0,0,0],'max':[10,100,10]}]}
            with patch('work_access.approach_faces',return_value='up'):
                with self.assertRaisesRegex(RuntimeError,'unknown dispatch'):grow(c,[100,64,100],profile,out,c.status)
                with self.assertRaisesRegex(RuntimeError,'not replayed'):grow(c,[100,64,100],profile,out,c.status)
            self.assertTrue(json.loads((out/'bone-meal-use.json').read_text())['pending'])
            self.assertEqual(1,sum(op=='interact'for op,_ in c.calls))

if __name__=='__main__':unittest.main()
