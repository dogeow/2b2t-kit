import copy
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from existing_wheat_source import observed_request,register
from potato_farm import plan,request_from_layout,survey_rows,FarmWait
from material_jobs.registered_wheat import registered_fields,make_registered_pickup
from farm_reseed import registered


class Tests(unittest.TestCase):
    def setUp(self):
        self.center=[0,63,0];rows=[]
        def row(pos,state,solid=False,fluid=False,entity=False):
            return {'pos':pos,'state':state,'solid':solid,'fluid':fluid,'block_entity':entity,
                    'spawn_block_light':7,'sky_light':14}
        for x in range(-4,5):
            for z in range(-4,5):
                rows.append(row([x,62,z],'Block{minecraft:stone}',solid=True))
                if(x,z)==(0,0):rows.append(row([x,63,z],'Block{minecraft:water}[level=0]',fluid=True))
                elif(x,z)==(3,0):
                    rows.append(row([x,63,z],'Block{minecraft:grass_block}',solid=True))
                    rows.append(row([x,64,z],'Block{minecraft:chest}',entity=True))
                else:
                    rows.append(row([x,63,z],'Block{minecraft:farmland}[moisture=7]'))
                    rows.append(row([x,64,z],'Block{minecraft:wheat}[age=7]'))
        inv=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(43)]
        inv[0].update(item='minecraft:wheat_seeds',count=64);inv[1].update(item='minecraft:wheat_seeds',count=36)
        self.frames=[{'phase':'done','world_session':'world','server':'example.test','dimension':'minecraft:overworld',
            'time':t,'control_revision':1,'scan_start_revision':1,'scan_end_revision':1,'scan_cells_read':484,'scan_total_cells':484,
            'manual_movement':False,'inventory':copy.deepcopy(inv),'blocks':copy.deepcopy(rows),
            'scan_entities':[],'scan_entity_scope':'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd'}for t in (10,11)]

    def test_observed_large_field_uses_existing_cells_and_preserves_chest(self):
        req=observed_request(self.frames,self.center,4);layout=plan(req)
        self.assertEqual(79,len(layout['cells']));self.assertNotIn([3,63,0],layout['cells'])
        self.assertEqual([3,64,0],layout['existing_source']['protected_obstacles'][0]['pos'])
        self.assertEqual(layout,plan(request_from_layout(layout)))
        with self.assertRaises(ValueError):plan({'authorized':True,'crop':'wheat','center':self.center,'radius':4})

    def test_changed_protected_chest_or_crop_selection_rejects_registration(self):
        for change in ('chest','crop','volume','world','inventory'):
            with self.subTest(change=change):
                frames=copy.deepcopy(self.frames)
                if change=='chest':next(r for r in frames[1]['blocks']if r['block_entity'])['state']='Block{minecraft:barrel}'
                elif change=='crop':frames[1]['blocks']=[r for r in frames[1]['blocks']if r['pos']!=[-4,64,-4]]
                elif change=='volume':frames[1]['scan_cells_read']=1
                elif change=='world':frames[1]['world_session']='other'
                else:frames[1]['inventory'][1]['count']=35
                with self.assertRaises((ValueError,FarmWait)):observed_request(frames,self.center,4)

    def test_registration_is_observation_only_and_compatible_with_existing_harvest_and_reseed(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);result=register(root,self.frames,self.center,4,root/'observed')
            self.assertEqual(0,result['new_seed_debit']);self.assertEqual(0,result['grain_inventory_credit'])
            c=SimpleNamespace(root=root,server='example.test');fields=list(registered_fields(c));self.assertEqual(1,len(fields))
            req,path=fields[0];self.assertEqual(79,len(plan(req)['cells']))
            values=registered(root,path,[[-4,63,-4]],server='example.test')
            book=json.loads(values[-1].read_text());self.assertEqual('observed_existing_wheat_source',book['kind'])
            self.assertEqual(0,book['new_planting_uses']);self.assertEqual(100,book['seeds_before']);self.assertEqual(100,book['seeds_after'])

    def test_existing_source_still_rejects_low_sky_and_mutated_chest_during_live_scan(self):
        req=observed_request(self.frames,self.center,4);layout=plan(req)
        records={','.join(map(str,p)):{'planted':True}for p in layout['cells']}
        for change in ('sky','chest'):
            frame=copy.deepcopy(self.frames[0])
            if change=='sky':next(r for r in frame['blocks']if r['pos']==[-4,63,-4])['sky_light']=0
            else:next(r for r in frame['blocks']if r['block_entity'])['state']='Block{minecraft:barrel}'
            with self.assertRaises(FarmWait):survey_rows(frame,layout,records)

    def test_large_field_pickup_and_plant_access_preserve_observed_source_bounds(self):
        from potato_loot_flight import make_plant_access
        from test_potato_loot_flight import FlightClient
        request=observed_request(self.frames,self.center,4);source=request['existing_source']
        c=FlightClient();drop={'pos':[4.1,64.0,0.5],'stack':{'item':'minecraft:wheat'}}
        access=make_plant_access(self.center,radius=4,existing_source=source)
        with patch('drop_collection.collect_drop',return_value={'movement_only':True})as collect:
            pickup=make_registered_pickup(self.center,radius=4,existing_source=source)
            pickup(c,drop,c.status());collect.assert_called_once()
        access(c,[4,63,0],c.status(),'before_plant')
        self.assertEqual([4.5,64.6,0.5],c.extra['pos'])
        with self.assertRaises(FarmWait):access(c,[3,63,0],c.status(),'before_plant')
        for factory in (make_registered_pickup,make_plant_access):
            with self.assertRaises(ValueError):factory(self.center,radius=4)
