import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from material_jobs.resource_tree_trip import current_tree_region,platform_input_ready,backend_client,run

class RealForestRegionTests(unittest.TestCase):
    def test_existing_backend_owner_is_required(self):
        request={'projection_key':'map'}
        c=SimpleNamespace(root=Path('/game/automation'),task='t',world='w',rev=3)
        s={'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':3}}
        c.status=Mock(return_value=s)
        backend=SimpleNamespace(client=c,request=request,ensure_client=Mock(return_value=c))
        self.assertIs(c,backend_client(backend,c.root,request))
        for bad in ({**s,'supervision_lease':{**s['supervision_lease'],'job_session':'other'}},
                    {**s,'supervision_lease':{**s['supervision_lease'],'revision':4}}):
            c.status.return_value=bad
            with self.assertRaises(RuntimeError):backend_client(backend,c.root,request)

    def test_borrowed_trip_returns_real_logs_without_new_controller_finish_or_recursive_map(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp)/'config/twob2tkit/automation';root.mkdir(parents=True)
            request={'projection_key':'map','context':{'server':'simpcraft.com','dimension':'minecraft:overworld'}}
            s={'world_session':'w','server':'simpcraft.com','dimension':'minecraft:overworld','health':20,'food':20,
               'projection_selection':{'key':'map','min':[0,64,0],'max':[127,64,127]},
               'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w','revision':3},
               'inventory':[{'slot':0,'item':'minecraft:dirt','count':1,'max_stack':64}]+
                   [{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(1,36)],
               'chopper_remaining':0,'chopper_platforms':0}
            c=SimpleNamespace(root=root,task='t',world='w',rev=3,last='scan',native_inflight=None,
                              status=Mock(side_effect=lambda **kw:s),set_progress=Mock(),finish=Mock())
            c.request=Mock(return_value={'id':'scan','world_session':'w','tree_survey':{'loaded_columns':37249,
                'trees':[{'pos':[1030,70,1030],'natural_leaves':4}]}})
            backend=SimpleNamespace(client=c,request=request,profile={'protected_regions':[]},
                                    ensure_client=Mock(return_value=c),checkpoint=Mock())
            candidate={'source':'bobby_cache','cache_server':'simpcraft.com','dimension':'minecraft:overworld',
                'chunk':[64,64],'tile':[1024,1024],'target':[1032.5,200.0,1032.5],
                'distance_sq':1310720.0,'region_file':'r.2.2.mca','fingerprint':'a'*64,
                'mtime_ns':100,'ctime_ns':101,'size':8192,'file_id':7,'biomes':['minecraft:taiga']}
            def outbound(client,candidate,server,dimension,path,*args):
                path.write_text(json.dumps({}))
            def harvest(*args):
                s['inventory'][1]={'slot':1,'item':'minecraft:spruce_log','count':8,'max_stack':64}
                return {'phase':'done'}
            with patch('material_jobs.resource_tree_trip.cache.validate_candidate',return_value=True), \
                    patch('material_jobs.resource_tree_trip.MaterialClient')as new_owner, \
                    patch('material_jobs.resource_tree_trip.lift_for_travel'), \
                    patch('material_jobs.resource_tree_trip.route.outbound',side_effect=outbound), \
                    patch('material_jobs.resource_tree_trip.route.mark_harvesting'), \
                    patch('material_jobs.resource_tree_trip.route.return_home')as returned, \
                    patch('material_jobs.resource_tree_trip.acquire',side_effect=harvest), \
                    patch('material_jobs.resource_tree_trip.continue_projection')as continued:
                result=run(root,request,candidate,'spruce',8,Path(tmp)/'trip',backend=backend)
            self.assertEqual(8,result['return_stock']);self.assertTrue(result['backend_owner_retained'])
            returned.assert_called_once();new_owner.assert_not_called();continued.assert_not_called();c.finish.assert_not_called()
            self.assertGreater(backend.checkpoint.call_count,0)

    def test_plain_main_bag_platform_input_is_required_before_any_tree_trip(self):
        row={'slot':8,'item':'minecraft:dirt','count':1,'max_stack':64}
        self.assertTrue(platform_input_ready({'inventory':[row]}))
        for r in ({**row,'count':0},{**row,'slot':40},{**row,'custom_name':'keep'},
                  {**row,'item':'minecraft:grass_block'}):
            self.assertFalse(platform_input_ready({'inventory':[r]}))
    def test_cache_hint_without_actual_species_roots_cannot_be_harvested(self):
        r={'id':'scan','world_session':'world','tree_survey':{'loaded_columns':37249,'trees':[]}}
        with self.assertRaises(RuntimeError):current_tree_region(r,'world','scan','minecraft:dark_oak_log',{'tile':[1024,1024]},[])

    def test_only_loaded_current_natural_roots_outside_protected_land_register_a_source(self):
        r={'id':'scan','world_session':'world','tree_survey':{'loaded_columns':37249,
           'trees':[{'pos':[1030,70,1030],'natural_leaves':4}]}}
        source=current_tree_region(r,'world','scan','minecraft:dark_oak_log',{'tile':[1024,1024]},[])
        self.assertEqual(128,source['max'][0]-source['min'][0]+1)
        self.assertEqual('scan',source['scan_id'])
        for bad in ({**r,'world_session':'old'}, {**r,'id':'other'}):
            with self.assertRaises(RuntimeError):current_tree_region(bad,'world','scan','minecraft:dark_oak_log',{'tile':[1024,1024]},[])
        with self.assertRaises(RuntimeError):current_tree_region(r,'world','scan','minecraft:dark_oak_log',{'tile':[1024,1024]},[{'min':[1024,0,1024],'max':[1030,100,1030]}])

if __name__=='__main__':unittest.main()
