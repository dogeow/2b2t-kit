import hashlib,json,tempfile,unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch
from material_jobs.discovery import tiles, excluded, choose_region, frontier, representative_seeds, discover, ALGORITHM_VERSION, _entrance
from material_jobs.acquisition import record_route_failure


def row(x,y,z,name='deepslate',**extra):
    return {'pos':[x,y,z],'state':'Block{minecraft:'+name+'}','solid':True,'passable':False,
            'fluid':False,'block_entity':False,**extra}


class DiscoveryTests(unittest.TestCase):
    def test_bounded_unique_frontier_keeps_negative_coordinates(self):
        found=list(tiles([-1,80,-1],64))
        self.assertEqual(len(found),len(set(found)))
        self.assertTrue(all(abs(x+16)<=64 and abs(z+16)<=64 for x,z in found))

    def test_depot_and_locked_projection_are_excluded(self):
        self.assertTrue(excluded([40,0,40],[55,70,55],{'depots':[[0,64,0]]},{}))
        self.assertTrue(excluded([70,0,70],[85,70,85],{}, {'min':[100,64,100],'max':[116,186,110]}))
        self.assertFalse(excluded([200,0,200],[215,70,215],{'depots':[[0,64,0]]},{}))

    def test_unknown_material_does_not_trigger_excavation(self):
        self.assertIsNone(choose_region([], 'minecraft:netherite_ingot',0,0,[0,70,0]))

    def test_bare_logs_without_leaves_are_not_a_forest(self):
        rows=[{'pos':[0,y,0],'state':'Block{minecraft:oak_log}'} for y in range(4)]
        self.assertIsNone(choose_region(rows,'minecraft:oak_log',0,0,[0,70,0]))

    def test_authorized_south_sand_hint_is_first_without_expanding_frontier(self):
        origin=[761020,95,797850]
        profile={'resource_regions':[{'item':'minecraft:sand','min':[761000,64,797932],
                    'max':[761025,78,797966],'source':'previous_authorized_sand_site'}]}
        ordered=frontier(origin,256,profile)
        self.assertEqual(set(tiles(origin,256)),set(ordered))
        self.assertLessEqual(ordered[0][0],761025);self.assertGreaterEqual(ordered[0][0]+15,761000)
        self.assertLessEqual(ordered[0][1],797966);self.assertGreaterEqual(ordered[0][1]+15,797932)
        self.assertEqual([],list(tiles(origin,32)))

    def test_dense_upper_layer_cannot_crowd_out_deeper_spatial_representatives(self):
        rows=[row(x,y,z) for x in range(16) for z in range(16) for y in (-8,-24,-40,-56)]
        seeds,buckets=representative_seeds(rows,0,0,[0,145,0])
        self.assertEqual(64,buckets);self.assertEqual(64,len(seeds))
        self.assertEqual(4,len({r['pos'][1]//16 for r in seeds[:4]}))
        self.assertEqual(16,len({(r['pos'][0]//4,r['pos'][2]//4) for r in seeds}))

    def test_alternative_shaft_avoids_tree_in_fixed_centre_and_preserves_native_buffer(self):
        rows=[row(x,y,z) for x in range(6) for z in range(6) for y in range(-20,0)]
        rows += [row(x,y,z,'stone') for x in range(6) for z in range(6) for y in range(0,5)]
        rows.append(row(2,5,2,'oak_log'))
        diagnostics={}
        result=choose_region(rows,'minecraft:cobbled_deepslate',0,0,[3,145,3],diagnostics=diagnostics)
        self.assertIsNotNone(result)
        shaft=result['access_shaft']
        self.assertFalse(shaft['min'][0]<=2<=shaft['max'][0] and shaft['min'][2]<=2<=shaft['max'][2])
        self.assertGreater(diagnostics['entrances_tried'],1)
        self.assertGreater(diagnostics['reject_reasons']['tree_entry'],0)
        self.assertGreater(diagnostics['target_blocks'],32)

    def test_every_wet_entrance_is_rejected_even_when_deep_rock_is_abundant(self):
        rows=[row(x,y,z) for x in range(-3,19) for z in range(-3,19) for y in range(-20,1)]
        rows += [row(x,1,z,'water',solid=False,fluid=True) for x in range(-3,19) for z in range(-3,19)]
        diagnostics={}
        self.assertIsNone(choose_region(rows,'minecraft:cobbled_deepslate',0,0,[3,145,3],diagnostics=diagnostics))
        self.assertGreater(diagnostics['target_blocks'],1000)
        self.assertGreater(diagnostics['reject_reasons']['wet_entry'],0)

    def test_only_harmless_grass_above_actual_ground_is_allowed(self):
        for plant,fluid,expected in (('short_grass',False,True),('fern',False,True),('water',True,False),('fire',False,False)):
            with self.subTest(plant=plant):
                rows=[row(x,y,z,'stone') for x in range(2) for z in range(2) for y in range(5)]
                rows.append(row(0,5,0,plant,solid=False,passable=True,fluid=fluid))
                cells={tuple(r['pos']):r for r in rows};columns=defaultdict(list)
                for r in rows:columns[(r['pos'][0],r['pos'][2])].append(r)
                plan,reason=_entrance(columns,cells,0,0,0,{})
                self.assertEqual(expected,plan is not None)
                if expected:self.assertEqual(4,plan['surface_y'])


class DiscoveryContinuationTests(unittest.TestCase):
    def test_same_session_failed_entrance_is_skipped_but_new_session_requires_fresh_survey(self):
        with tempfile.TemporaryDirectory() as folder:
            c=self.client();c.root=Path(folder)/'automation';c.root.mkdir()
            profile=self.profile();item='minecraft:cobbled_deepslate'
            region={'item':item,'min':[0,-18,0],'max':[1,-1,1],
                    'source':'natural_survey','surface_y':10,
                    'access_shaft':{'min':[0,0,0],'max':[1,10,1]}}
            record_route_failure(c,profile,item,region,'guard_displaced','defense displaced player',[.5,13.1,.5])
            directory=Path(folder)/'material-resource-ledger'
            scope=hashlib.sha256((profile['server']+'|'+profile['dimension']+'|'+item).encode()).hexdigest()[:20]
            path=directory/(scope+'.json')
            ledger=json.loads(path.read_text())
            ledger['tiles']={'0:0':{'state':'candidate','algorithm_version':ALGORITHM_VERSION,'region':region}}
            path.write_text(json.dumps(ledger))
            with patch('material_jobs.discovery.frontier',return_value=[(0,0)]),\
                 patch('material_jobs.discovery._travel') as travel,\
                 patch('material_jobs.discovery.choose_region',return_value=region):
                self.assertIsNone(discover(c,item,profile,directory,lambda:None,max_tiles=1))
                self.assertEqual('guard_displaced',c.material_search_progress['guard_hold']['code'])
                travel.assert_not_called()
                c.world='new-world'
                self.assertEqual(region,discover(c,item,profile,directory,lambda:None,max_tiles=1))
                self.assertEqual(1,travel.call_count)

    def test_guard_displacement_during_new_tile_travel_holds_same_frontier(self):
        from material_jobs.acquisition import Unavailable
        with tempfile.TemporaryDirectory() as folder:
            c=self.client();c.root=Path(folder)/'automation';c.root.mkdir()
            profile=self.profile();item='minecraft:cobbled_deepslate'
            with patch('material_jobs.discovery.frontier',return_value=[(0,0),(16,0)]),\
                 patch('material_jobs.discovery._travel',side_effect=Unavailable(
                     'guard moved actor','waiting','guard_displaced',
                     {'terminal_verified':True,'replans':2})) as travel:
                self.assertIsNone(discover(c,item,profile,folder,lambda:None,max_tiles=2))
                self.assertEqual([0,0],c.material_search_progress['guard_hold']['tile'])
                self.assertIsNone(discover(c,item,profile,folder,lambda:None,max_tiles=2))
                self.assertEqual(1,travel.call_count)

    def test_checkpoint_pause_after_guard_stop_keeps_original_discovery_tile(self):
        from material_jobs.protocol import JobPaused
        with tempfile.TemporaryDirectory() as folder:
            c=self.client();c.root=Path(folder)/'automation';c.root.mkdir()
            profile=self.profile();item='minecraft:cobbled_deepslate'
            def paused_travel(client,target,checkpoint,trace):
                trace.append({'target':list(target),'route_code':'guard_displaced',
                              'terminal_verified':True,'request_id':'nav-owned',
                              'combat_confirmed':True,'observed_at':100})
                raise JobPaused('health below 18 after combat')
            with patch('material_jobs.discovery.frontier',return_value=[(0,0),(16,0)]),\
                 patch('material_jobs.discovery._travel',side_effect=paused_travel) as travel:
                with self.assertRaises(JobPaused):
                    discover(c,item,profile,folder,lambda:None,max_tiles=2)
                self.assertEqual([0,0],c.material_search_progress['guard_hold']['tile'])
                self.assertIsNone(discover(c,item,profile,folder,lambda:None,max_tiles=2))
                self.assertEqual(1,travel.call_count)

    def test_actual_geometry_hold_still_skips_unsafe_known_route(self):
        with tempfile.TemporaryDirectory() as folder:
            c=self.client();c.root=Path(folder)/'automation';c.root.mkdir()
            profile=self.profile();item='minecraft:cobbled_deepslate'
            region={'item':item,'min':[0,-18,0],'max':[1,-1,1],
                    'source':'natural_survey','surface_y':10,
                    'access_shaft':{'min':[0,0,0],'max':[1,10,1]}}
            record_route_failure(c,profile,item,region,'route_geometry_blocked',
                                 'solid wall',[.5,13.1,.5])
            scope=hashlib.sha256((profile['server']+'|'+profile['dimension']+'|'+item).encode()).hexdigest()[:20]
            path=Path(folder)/'material-resource-ledger'/(scope+'.json')
            ledger=json.loads(path.read_text())
            ledger['tiles']={'0:0':{'state':'candidate',
                                    'algorithm_version':ALGORITHM_VERSION,
                                    'region':region}}
            path.write_text(json.dumps(ledger))
            with patch('material_jobs.discovery.frontier',return_value=[(0,0)]),\
                 patch('material_jobs.discovery._travel') as travel:
                self.assertIsNone(discover(c,item,profile,path.parent,
                                           lambda:None,max_tiles=1))
            self.assertNotIn('guard_hold',c.material_search_progress)
            travel.assert_not_called()

    def test_new_job_reobserves_known_resource_before_exploring_new_tiles(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'):
            c=self.client();profile=self.profile();item='minecraft:cobbled_deepslate'
            x,z=next(iter(frontier(c.anchor,64,profile)))
            scope=hashlib.sha256((profile['server']+'|'+profile['dimension']+'|'+item).encode()).hexdigest()[:20]
            region={'item':item,'min':[x,-18,z],'max':[x+1,-1,z+1],'source':'natural_survey'}
            path=Path(folder)/(scope+'.json')
            path.write_text(json.dumps({'schema':1,'item':item,'tiles':{f'{x}:{z}':{
                'state':'candidate','algorithm_version':ALGORITHM_VERSION,'region':region}}}))
            with patch('material_jobs.discovery.choose_region',return_value=region):
                self.assertEqual(region,discover(c,item,profile,folder,lambda:None,max_tiles=1))
            self.assertEqual(4,len(c.requests))
            self.assertEqual([x-3,-60,z-3],c.requests[0][1]['min'])
            # The current job has now tried this exact region. It must explore
            # elsewhere if acquisition found it empty/unsafe, not spin here.
            profile['resource_regions'].append(region);c.requests=[]
            with patch('material_jobs.discovery.choose_region',return_value=None):
                discover(c,item,profile,folder,lambda:None,max_tiles=1)
            self.assertNotEqual([x-3,-60,z-3],c.requests[0][1]['min'])

    def client(self):
        class Client:
            world='world';anchor=[0,145,0]
            def __init__(self):self.requests=[]
            def status(self):return {'pos':[0,145,0],'time':100,'projection_selection':{}}
            def request(self,op,**params):
                self.requests.append((op,params));return {'blocks':[]}
        return Client()

    def profile(self):return {'server':'test','dimension':'minecraft:overworld','search_radius':64,'resource_regions':[]}

    def test_scanning_budget_reports_real_new_coverage_and_continues_next_call(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'):
            c=self.client();profile=self.profile()
            self.assertIsNone(discover(c,'minecraft:cobbled_deepslate',profile,folder,lambda:None,max_tiles=8))
            first=dict(c.material_search_progress)
            self.assertEqual(8,first['new_tiles']);self.assertEqual(8,first['scanned_total']);self.assertTrue(first['has_more'])
            bounds=[r[1]['min'] for r in c.requests]
            discover(c,'minecraft:cobbled_deepslate',profile,folder,lambda:None,max_tiles=8)
            second=c.material_search_progress
            self.assertEqual(8,second['new_tiles']);self.assertEqual(16,second['scanned_total']);self.assertTrue(second['has_more'])
            self.assertTrue(all(low not in bounds for _,request in c.requests[32:] for low in [request['min']]))
            saved=json.loads(Path(second['ledger']).read_text())
            self.assertEqual(ALGORITHM_VERSION,saved['algorithm_version'])
            self.assertEqual(second,saved['search_progress'])
            self.assertTrue(all('diagnostics' in tile and 'blocks' not in tile for tile in saved['tiles'].values()))

    def test_only_exhausted_frontier_reports_has_more_false(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'),\
                patch('material_jobs.discovery.frontier',return_value=[(48,0),(64,0)]):
            c=self.client()
            discover(c,'minecraft:cobbled_deepslate',self.profile(),folder,lambda:None,max_tiles=1)
            self.assertTrue(c.material_search_progress['has_more'])
            discover(c,'minecraft:cobbled_deepslate',self.profile(),folder,lambda:None,max_tiles=1)
            self.assertFalse(c.material_search_progress['has_more'])
            before=len(c.requests)
            discover(c,'minecraft:cobbled_deepslate',self.profile(),folder,lambda:None,max_tiles=1)
            self.assertEqual(before,len(c.requests));self.assertEqual(0,c.material_search_progress['new_tiles'])

    def test_old_empty_is_revalidated_once_and_kept_as_history(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'),\
                patch('material_jobs.discovery.frontier',return_value=[(48,0)]):
            profile=self.profile();item='minecraft:cobbled_deepslate'
            scope=hashlib.sha256((profile['server']+'|'+profile['dimension']+'|'+item).encode()).hexdigest()[:20]
            path=Path(folder)/(scope+'.json')
            old={'state':'empty_or_unsafe','observed_at':1,'world_session':'old','region':None}
            path.write_text(json.dumps({'schema':1,'item':item,'tiles':{'48:0':old}}))
            c=self.client();discover(c,item,profile,folder,lambda:None)
            saved=json.loads(path.read_text())
            self.assertEqual([old],saved['history']['48:0'])
            self.assertEqual(ALGORITHM_VERSION,saved['tiles']['48:0']['algorithm_version'])
            self.assertEqual(1,c.material_search_progress['new_tiles'])
            before=len(c.requests);discover(c,item,profile,folder,lambda:None)
            self.assertEqual(before,len(c.requests))

    def test_authorized_hints_still_cannot_override_base_or_projection_protection(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel') as travel,\
                patch('material_jobs.discovery.frontier',return_value=[(48,0)]):
            profile=self.profile();profile['depots']=[[0,64,0]]
            c=self.client();discover(c,'minecraft:cobbled_deepslate',profile,folder,lambda:None)
            travel.assert_not_called();self.assertEqual([],c.requests)
            self.assertEqual(0,c.material_search_progress['new_tiles']);self.assertFalse(c.material_search_progress['has_more'])

    def test_snow_candidate_at_search_origin_48_boundary_is_rejected_and_search_continues(self):
        item='minecraft:snow'
        near={'item':item,'min':[48,64,0],'max':[63,79,15],
              'source':'natural_survey','surface_y':64}
        safe={'item':item,'min':[64,64,0],'max':[79,79,15],
              'source':'natural_survey','surface_y':64}
        with tempfile.TemporaryDirectory() as folder:
            c=self.client();c.root=Path(folder)/'automation';c.root.mkdir()
            status=c.status;c.status=lambda:{**status(),'snow_biome_survey_protocol':1}
            profile={'server':'test','dimension':'minecraft:overworld','search_radius':128,
                     'search_origin':[0,145,0],'resource_regions':[],
                     'protected_regions':[{'min':[-100,50,-100],'max':[-80,95,-80]}]}
            def selected(rows,requested,x,z,*args,**kwargs):
                self.assertEqual(item,requested)
                return near if x==48 else safe if x==64 else None
            with patch('material_jobs.discovery.frontier',return_value=[(48,0),(64,0)]),\
                 patch('material_jobs.discovery._coarse_snow_frontier',return_value={
                     'available':False,'tiles':[],'new_cells':0,'visited':0,
                     'has_more':False,'held':False,'reason':'fixture_fallback'}),\
                 patch('material_jobs.discovery._travel') as travel,\
                 patch('material_jobs.discovery.choose_region',side_effect=selected):
                self.assertEqual(safe,discover(c,item,profile,folder,lambda:None,max_tiles=2))
            self.assertEqual(2,travel.call_count)
            scope=hashlib.sha256(('test|minecraft:overworld|'+item).encode()).hexdigest()[:20]
            ledger=json.loads((Path(folder)/(scope+'.json')).read_text())
            self.assertEqual(('empty_or_unsafe',None,'candidate',safe),
                             (ledger['tiles']['48:0']['state'],ledger['tiles']['48:0']['region'],
                              ledger['tiles']['64:0']['state'],ledger['tiles']['64:0']['region']))
            self.assertEqual(1,ledger['tiles']['48:0']['diagnostics']
                             ['reject_reasons']['protected_site_buffer'])
            self.assertIn('too close',ledger['tiles']['48:0']['diagnostics']['region_validation'])


class ExistingShaftExtensionTests(unittest.TestCase):
    item='minecraft:cobbled_deepslate'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        class Client:
            world='world';anchor=[0,145,0]
            def __init__(self):
                self.pos=[65,145,1];self.rows=[];self.requests=[];self.override=None
            def status(self):
                return {'pos':self.pos,'time':100,'projection_selection':{},'world_session':self.world,
                        'server':'test','dimension':'minecraft:overworld'}
            def request(self,op,**params):
                self.requests.append((op,params))
                self.last='material-scan-'+str(len(self.requests))
                if self.override is not None:return {'id':self.last,'world_session':self.world,**self.override}
                # Real AutomationBridge read replies omit phase.
                return {'id':self.last,'world_session':self.world,
                    'blocks':[r for r in self.rows if all(params['min'][i]<=r['pos'][i]<=params['max'][i] for i in range(3))]}
        self.client=Client()
        self.parent={'item':self.item,'source':'natural_survey','min':[64,-3,0],'max':[65,14,1],
                     'surface_y':66,'access_shaft':{'min':[64,15,0],'max':[65,66,1]}}
        self.profile={'server':'test','dimension':'minecraft:overworld','search_radius':256,
                      'resource_regions':[self.parent]}
        self.fill(-21,-4)
        scope=hashlib.sha256(('test|minecraft:overworld|'+self.item).encode()).hexdigest()[:20]
        self.path=self.folder/(scope+'.json')

    def fill(self,low,high,name='deepslate'):
        self.client.rows=[row(x,y,z,name) for x in (64,65) for z in (0,1) for y in range(low-1,high+1)]

    def discover(self):
        with patch('material_jobs.discovery.frontier',return_value=[]),patch('material_jobs.discovery._travel') as travel:
            result=discover(self.client,self.item,self.profile,self.folder,lambda:None,max_tiles=1)
        travel.assert_not_called()
        return result

    def test_reuses_known_two_by_two_shaft_before_new_horizontal_exploration(self):
        result=self.discover()
        self.assertEqual([64,-21,0],result['min']);self.assertEqual([65,-4,1],result['max'])
        self.assertEqual(72,result['available']);self.assertEqual(72,result['remaining'])
        self.assertEqual({'min':[64,-3,0],'max':[65,66,1]},result['access_shaft'])
        self.assertEqual(66,result['surface_y']);self.assertEqual(1,len(self.client.requests))
        self.assertEqual([61,-23,-3],self.client.requests[0][1]['min'])
        self.assertEqual([68,-2,4],self.client.requests[0][1]['max'])
        saved=json.loads(self.path.read_text());entry=next(iter(saved['extensions'].values()))
        self.assertEqual('candidate',entry['state']);self.assertEqual('world',entry['world_session'])
        self.assertEqual(ALGORITHM_VERSION,entry['algorithm_version'])

    def test_registered_extension_is_not_repeated_and_deepest_used_region_can_continue(self):
        first=self.discover();self.profile['resource_regions'].append(first)
        self.fill(-39,-22)
        second=self.discover()
        self.assertEqual([64,-39,0],second['min']);self.assertEqual([65,-22,1],second['max'])
        self.assertEqual({'min':[64,-21,0],'max':[65,66,1]},second['access_shaft'])
        self.assertEqual(2,len(self.client.requests));self.assertEqual(2,len(json.loads(self.path.read_text())['extensions']))

    def test_floor_minus_fifty_eight_limit_produces_smaller_valid_batch(self):
        self.parent.update(min=[64,-50,0],max=[65,-33,1],access_shaft={'min':[64,-32,0],'max':[65,66,1]})
        self.fill(-58,-51)
        result=self.discover()
        self.assertEqual(-58,result['min'][1]);self.assertEqual(-51,result['max'][1]);self.assertEqual(32,result['available'])

    def test_one_remaining_layer_below_known_region_is_not_an_invalid_native_area(self):
        self.parent.update(min=[64,-57,0],max=[65,-40,1],access_shaft={'min':[64,-39,0],'max':[65,66,1]})
        self.assertIsNone(self.discover());self.assertFalse(self.client.requests)

    def test_four_by_four_region_is_never_extended_sideways_or_widened(self):
        self.parent.update(max=[67,14,3],access_shaft={'min':[66,15,2],'max':[67,66,3]})
        self.assertIsNone(self.discover());self.assertFalse(self.client.requests)

    def test_historical_candidate_not_in_current_known_regions_does_not_authorize_extension(self):
        self.path.write_text(json.dumps({'schema':1,'item':self.item,'tiles':{'64:0':{'state':'candidate','region':self.parent}}}))
        self.profile['resource_regions']=[]
        self.assertIsNone(self.discover());self.assertFalse(self.client.requests)

    def test_empty_or_wet_extension_is_cached_but_old_world_failure_is_rechecked(self):
        self.client.rows.append(row(63,-12,0,'water',fluid=True,solid=False))
        self.assertIsNone(self.discover());self.assertEqual(1,len(self.client.requests))
        self.assertIsNone(self.discover());self.assertEqual(1,len(self.client.requests))
        self.fill(-21,-4);self.client.world='world-after-reconnect'
        self.assertIsNotNone(self.discover());self.assertEqual(2,len(self.client.requests))
        saved=json.loads(self.path.read_text());entry=next(iter(saved['extensions'].values()))
        self.assertEqual('world-after-reconnect',entry['world_session']);self.assertTrue(saved['extension_history'])

    def test_no_target_or_no_solid_floor_never_creates_a_resource_candidate(self):
        self.fill(-21,-4,'stone')
        self.assertIsNone(self.discover())
        entry=next(iter(json.loads(self.path.read_text())['extensions'].values()))
        self.assertEqual('no_target_blocks',entry['reason']);self.assertEqual(0,entry['available'])
        self.path.unlink();self.fill(-21,-4)
        self.client.rows=[r for r in self.client.rows if r['pos']!=[64,-22,0]]
        self.assertIsNone(self.discover())
        self.assertEqual('unsafe_or_unsupported',next(iter(json.loads(self.path.read_text())['extensions'].values()))['reason'])

    def test_unknown_or_partial_scan_does_not_write_empty_extension_evidence(self):
        for response in ({'phase':'waiting','world_session':'world','blocks':[]},
                         {'phase':'error','world_session':'world','blocks':[]},
                         {'phase':'stopped','world_session':'world','blocks':[]},
                         {'id':'different-request','world_session':'world','blocks':[]},
                         {'phase':'done','world_session':'other','blocks':[]},
                         {'phase':'done','world_session':'world','blocks':[{'pos':[64,-4,0]}]}):
            with self.subTest(response=response):
                self.client.override=response
                with self.assertRaises(RuntimeError):self.discover()
                self.assertFalse(self.path.exists())

    def test_read_only_scan_without_phase_requires_current_request_identity(self):
        result=self.discover()
        self.assertEqual(72,result['available'])
        self.assertEqual('material-scan-1',self.client.last)
        self.assertEqual(1,len(self.client.requests))

    def test_cache_missing_algorithm_or_foreign_scope_is_observed_again(self):
        self.fill(-21,-4,'stone');self.discover()
        saved=json.loads(self.path.read_text());key=next(iter(saved['extensions']))
        for changed in ({'algorithm_version':0},{'server':'different'},{'dimension':'minecraft:the_nether'}):
            old=json.loads(json.dumps(saved));old['extensions'][key].update(changed);self.path.write_text(json.dumps(old))
            before=len(self.client.requests);self.discover()
            self.assertEqual(before+1,len(self.client.requests))

    def test_full_shaft_footprint_respects_base_and_projection_protection(self):
        for changes in ({'depots':[[65,200,1]]},
                        {'protected_regions':[{'min':[64,20,0],'max':[65,25,1]}]}):
            with self.subTest(changes=changes):
                self.profile.update(changes)
                self.assertIsNone(self.discover());self.assertFalse(self.client.requests)
                for key in changes:self.profile.pop(key)

    def test_all_footprint_corners_must_fit_384_current_and_440_anchor_scope(self):
        # Center is 384 away, but the near edge is 385 away.
        self.client.pos=[449,145,1]
        self.assertIsNone(self.discover());self.assertFalse(self.client.requests)
        self.client.pos=[65,145,1];self.client.anchor=[-375,145,1];self.profile['search_origin']=[65,145,1]
        self.assertIsNone(self.discover());self.assertFalse(self.client.requests)

    def test_no_qualified_extension_falls_back_to_existing_frontier(self):
        self.fill(-21,-4,'stone')
        with patch('material_jobs.discovery.frontier',return_value=[(96,0)]),patch('material_jobs.discovery._travel') as travel,patch('material_jobs.discovery.choose_region',return_value=None) as choose:
            self.assertIsNone(discover(self.client,self.item,self.profile,self.folder,lambda:None,max_tiles=1))
        self.assertEqual(5,len(self.client.requests));self.assertEqual([61,-23,-3],self.client.requests[0][1]['min'])
        self.assertEqual([93,-60,-3],self.client.requests[1][1]['min']);travel.assert_called_once();choose.assert_called_once()


if __name__=='__main__':
    unittest.main()
