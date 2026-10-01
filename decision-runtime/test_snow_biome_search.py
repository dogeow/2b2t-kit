import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from material_jobs.discovery import (_coarse_snow_frontier, discover, frontier)
from material_jobs.acquisition import _resource_ledger_scope_path
from material_jobs.acquisition import Unavailable
from material_jobs.protocol import search_coverage
from material_jobs.snow_harvest import _return_seed_home
from material_jobs.snow_biome_search import (LEDGER_KEY, anchors, cold_tiles,
                                               ledger_state, parse_reply)


def survey_reply(request_id, center, *, cold=True, loaded=True, world='world', offset=-64,
                 phase=None):
    sample = {'pos':[center[0]+offset, 80, center[1]],
              'chunk':[(center[0]+offset)//16, center[1]//16],
              'biome':'minecraft:snowy_plains' if cold else 'minecraft:plains',
              'precipitation':'snow' if cold else 'rain',
              'cold_enough_to_snow':cold,
              'base_temperature':0.0 if cold else 0.8}
    rows = [sample] if loaded else []
    return {'id':request_id,'phase':phase,'world_session':world,
            'snow_biome_survey':{'center':list(center),'radius':64,'stride':64,
                'requested_samples':9,'loaded_samples':len(rows),
                'unloaded_samples':8 if rows else 9,'samples':rows}}


class SnowBiomeSearchUnitTest(unittest.TestCase):
    def test_profile_radius_one_and_fifteen_fall_back_empty_while_sixteen_is_bounded(self):
        for radius,expected in ((1,0),(15,0),(16,1)):
            with self.subTest(radius=radius):
                found=anchors([0,145,0],radius)
                self.assertEqual(expected,len(found))
                self.assertTrue(all((x+.5)**2+(z+.5)**2<=radius**2 for x,z in found))

    def test_coarse_cells_are_real_search_coverage_without_inventing_tiles(self):
        self.assertEqual(4,search_coverage({'new_tiles':0,'coarse_new_cells':4}))
        self.assertEqual(2,search_coverage({'new_tiles':2,'coarse_new_cells':'bad'}))
        self.assertEqual(7,search_coverage({'new_tiles':0,'coarse_new_cells':0,
                                           'seed_processed':7}))
        self.assertEqual(1,search_coverage({'new_tiles':0,'coarse_new_cells':0,
                                           'bobby_checked':1}))
        self.assertEqual(0,search_coverage({'new_tiles':-1,'coarse_new_cells':False}))

    def test_anchor_ring_is_unique_bounded_and_keeps_negative_origins(self):
        found=anchors([-1,145,-1],256)
        self.assertEqual(len(found),len(set(found)))
        self.assertEqual((-8,-8),found[0])
        self.assertTrue(all(((x+.5)+1)**2+((z+.5)+1)**2<=256**2 for x,z in found))

    def test_reply_requires_current_identity_counts_and_loaded_sample_grid(self):
        good=survey_reply('current',(8,8))
        parsed=parse_reply(good,'current','world',(8,8))
        self.assertEqual(1,parsed['loaded_samples'])
        compatible=survey_reply('current',(8,8),phase='done')
        self.assertEqual(1,parse_reply(compatible,'current','world',(8,8))['loaded_samples'])
        for phase in ('error','waiting','stopped'):
            with self.subTest(phase=phase):
                rejected=survey_reply('current',(8,8),phase=phase)
                with self.assertRaises(ValueError):
                    parse_reply(rejected,'current','world',(8,8))
        for changed in ({'id':'old'},{'world_session':'other'}):
            bad=json.loads(json.dumps(good));bad.update(changed)
            with self.assertRaises(ValueError):parse_reply(bad,'current','world',(8,8))
        bad=json.loads(json.dumps(good));bad['snow_biome_survey']['requested_samples']=8
        with self.assertRaises(ValueError):parse_reply(bad,'current','world',(8,8))

    def test_only_positive_cold_loaded_samples_become_allowed_detailed_tiles(self):
        cold=survey_reply('id',(8,8))['snow_biome_survey']['samples'][0]
        warm=dict(cold,pos=[8,80,8],chunk=[0,0],biome='minecraft:plains',
                  precipitation='rain',cold_enough_to_snow=False)
        self.assertEqual({'-64:0'},set(cold_tiles([cold,warm],[(-64,0),(0,0)])))
        self.assertEqual({},cold_tiles([cold],[(-48,0)]))

    def test_coarse_ledger_is_persistent_and_refuses_corruption(self):
        entry={'state':'loaded_no_cold_sample','anchor':[8,8],
               'world_session':'world','observed_at':100,
               'loaded_samples':9,'unloaded_samples':0,'candidate_tiles':[]}
        ledger={};state=ledger_state(ledger);state['visited']['8:8']=entry
        self.assertEqual(entry,ledger_state(ledger)['visited']['8:8'])
        ledger[LEDGER_KEY]['visited']=[]
        with self.assertRaises(RuntimeError):ledger_state(ledger)

    def test_each_visited_entry_fails_closed_on_bad_key_anchor_state_or_count(self):
        valid={'state':'loaded_no_cold_sample','anchor':[8,8],
               'world_session':'world','observed_at':100,
               'loaded_samples':9,'unloaded_samples':0,'candidate_tiles':[]}
        cases=(('bad-key',valid),
               ('8:8',{**valid,'anchor':[9,8]}),
               ('8:8',{**valid,'state':'unknown'}),
               ('8:8',{**valid,'loaded_samples':8}))
        for key,entry in cases:
            with self.subTest(key=key,entry=entry):
                ledger={};state=ledger_state(ledger);state['visited'][key]=entry
                with self.assertRaises(RuntimeError):ledger_state(ledger)


class SnowBiomeDiscoveryIntegrationTest(unittest.TestCase):
    class Client:
        world='world';anchor=[0,145,0]
        def __init__(self,protocol=1,cold=True,valid=True,offset=-64,cold_surveys=None):
            self.protocol=protocol;self.cold=cold;self.valid=valid
            self.offset=offset;self.cold_surveys=cold_surveys;self.surveys=0
            self.pos=[0,145,0];self.time=100;self.requests=[];self.last=None
        def status(self):
            return {'pos':list(self.pos),'time':self.time,'projection_selection':{},
                    'snow_biome_survey_protocol':self.protocol}
        def request(self,op,**params):
            self.requests.append((op,params));self.time+=1
            if op=='scan_snow_biomes':
                self.surveys+=1
                self.last='survey-'+str(len(self.requests))
                cold=self.cold and (self.cold_surveys is None
                                    or self.surveys<=self.cold_surveys)
                reply=survey_reply(self.last,tuple(params['center']),cold=cold,
                                   offset=self.offset)
                if not self.valid:reply['snow_biome_survey']['requested_samples']=2
                return reply
            if op=='scan':return {'blocks':[]}
            raise AssertionError(op)

    def profile(self,radius=64):
        return {'server':'test','dimension':'minecraft:overworld','search_radius':radius,
                'search_origin':[0,145,0],'resource_regions':[],
                'protected_regions':[{'min':[-220,50,-220],'max':[-200,100,-200]}]}

    def test_loaded_cold_sample_is_persisted_and_only_its_tile_gets_detailed_scan(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'):
            client=self.Client()
            self.assertIsNone(discover(client,'minecraft:snow',self.profile(),folder,
                                       lambda:None,max_tiles=1))
            self.assertEqual('scan_snow_biomes',client.requests[0][0])
            detailed=[params for op,params in client.requests if op=='scan']
            self.assertEqual(5,len(detailed))
            self.assertTrue(all(params['min'][0]==-67 and params['min'][2]==-3
                                for params in detailed))
            ledgers=list(Path(folder).glob('*.json'));self.assertEqual(1,len(ledgers))
            saved=json.loads(ledgers[0].read_text())
            self.assertEqual('cold_candidates',saved[LEDGER_KEY]['visited']['8:8']['state'])
            self.assertEqual([-64,0],saved[LEDGER_KEY]['candidates']['-64:0']['tile'])

    def test_four_warm_coarse_cells_continue_without_expensive_vertical_scans(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'):
            client=self.Client(cold=False)
            self.assertIsNone(discover(client,'minecraft:snow',self.profile(256),folder,
                                       lambda:None,max_tiles=8))
            self.assertEqual(4,len(client.requests))
            self.assertTrue(all(op=='scan_snow_biomes' for op,_ in client.requests))
            self.assertEqual(4,client.material_search_progress['coarse_new_cells'])
            self.assertEqual(0,client.material_search_progress['new_tiles'])
            self.assertTrue(client.material_search_progress['has_more'])

    def test_old_host_stops_before_any_new_or_legacy_search_movement(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel') as travel:
            client=self.Client(protocol=0)
            self.assertIsNone(discover(client,'minecraft:snow',self.profile(),folder,
                                       lambda:None,max_tiles=1))
            self.assertEqual([],client.requests);travel.assert_not_called()
            self.assertEqual('host_protocol_unavailable',
                             client.material_search_progress['coarse_fallback'])

    def test_locator_protocol_without_verified_seed_falls_back_to_loaded_coarse_survey(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'):
            client=self.Client(cold=True);original=client.status
            client.status=lambda:{**original(),'snow_seed_locator_protocol':1,
                                  'snow_seed_locator_available':False}
            self.assertIsNone(discover(client,'minecraft:snow',self.profile(),folder,
                                       lambda:None,max_tiles=1))
            self.assertFalse(any(op=='snow_seed_candidates' for op,_ in client.requests))
            self.assertEqual('scan_snow_biomes',client.requests[0][0])

    def test_invalid_coarse_reply_falls_back_without_claiming_anchor_observed(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'):
            client=self.Client(valid=False)
            self.assertIsNone(discover(client,'minecraft:snow',self.profile(),folder,
                                       lambda:None,max_tiles=1))
            self.assertEqual('scan_snow_biomes',client.requests[0][0])
            self.assertEqual(5,len([1 for op,_ in client.requests if op=='scan']))
            resource=_resource_ledger_scope_path(
                Path(folder),self.profile()['server'],self.profile()['dimension'],
                'minecraft:snow')
            saved=json.loads(resource.read_text())
            self.assertEqual({},saved[LEDGER_KEY]['visited'])
            self.assertEqual('invalid_or_unavailable_reply',
                             client.material_search_progress['coarse_fallback'])

    def test_furnace_buffer_rejects_coarse_tile_before_persistence_or_detailed_scan(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'):
            client=self.Client(offset=64,cold_surveys=1)
            profile=self.profile(256);profile['furnace_positions']=[[70,64,8]]
            self.assertIsNone(discover(client,'minecraft:snow',profile,folder,
                                       lambda:None,max_tiles=1))
            self.assertFalse(any(op=='scan' for op,_ in client.requests))
            saved=json.loads(next(Path(folder).glob('*.json')).read_text())
            self.assertNotIn('64:0',saved[LEDGER_KEY]['candidates'])
            self.assertEqual('loaded_cold_protected',
                             next(iter(saved[LEDGER_KEY]['visited'].values()))['state'])

    def test_small_profile_radii_return_bounded_empty_without_movement_or_exception(self):
        for radius in (1,15):
            with self.subTest(radius=radius),tempfile.TemporaryDirectory() as folder,\
                    patch('material_jobs.discovery._travel') as travel:
                client=self.Client()
                self.assertIsNone(discover(client,'minecraft:snow',self.profile(radius),folder,
                                           lambda:None,max_tiles=1))
                self.assertEqual([],client.requests);travel.assert_not_called()
                self.assertFalse(client.material_search_progress['has_more'])

    def test_persisted_large_radius_candidate_is_not_reused_after_radius_shrinks(self):
        for radius in (1,15):
            with self.subTest(radius=radius),tempfile.TemporaryDirectory() as folder:
                client=self.Client();large=self.profile(64)
                path=_resource_ledger_scope_path(Path(folder),large['server'],
                                                 large['dimension'],'minecraft:snow')
                ledger={'schema':1,'item':'minecraft:snow','tiles':{},
                        'route_failures':{},'algorithm_version':2}
                allowed=frontier(large['search_origin'],64,large)
                with patch('material_jobs.discovery._travel'):
                    result=_coarse_snow_frontier(
                        client,large,ledger,path,lambda:None,large['search_origin'],{},allowed)
                self.assertEqual([(-64,0)],result['tiles'])
                self.assertTrue(path.exists());client.requests=[]
                small=self.profile(radius)
                with patch('material_jobs.discovery._travel') as travel:
                    self.assertIsNone(discover(client,'minecraft:snow',small,folder,
                                               lambda:None,max_tiles=1))
                self.assertEqual([],client.requests);travel.assert_not_called()
                self.assertFalse(client.material_search_progress['has_more'])


class SeedSnowDiscoveryIntegrationTest(unittest.TestCase):
    class Client:
        world='world';anchor=[0,145,0]
        def __init__(self,cold=True,outbound_done=True,sampler_available=True):
            self.cold=cold;self.outbound_done=outbound_done
            self.sampler_available=sampler_available
            self.pos=[0,145,0];self.time=100
            self.requests=[];self.last=None
        def status(self):
            return {'pos':list(self.pos),'time':self.time,'projection_selection':{},
                    'snow_biome_survey_protocol':1,'snow_seed_locator_protocol':1,
                    'snow_seed_locator_available':True,
                    'world_session':self.world,'navigating':False,
                    'native_material_busy':False,'health':20,'food':20,
                    'guard_armed':True,'guard_pve_only':True,'under_water':False,
                    'manual_movement':False,'safety_hold':{'active':False}}
        def request(self,op,**params):
            self.requests.append((op,params));self.time+=1
            self.last=op+'-'+str(len(self.requests))
            if op=='snow_seed_candidates':
                if not self.sampler_available:
                    return {'id':self.last,'world_session':self.world,'phase':'done',
                            'snow_seed_candidates':{'protocol':1,'available':False,
                                                    'reason':'sampler_unavailable'}}
                cursor=params['cursor'];next_cursor=min(81,cursor+5)
                return {'id':self.last,'world_session':self.world,'phase':'done',
                    'snow_seed_candidates':{'protocol':1,'available':True,'cursor':cursor,
                        'next_cursor':next_cursor,'processed':5,'total':81,
                        'done':next_cursor==81,
                        'radius':4096,'stride':256,'candidates':[{
                            'sample_cursor':cursor+3,'x':1024,'z':-512,'sample_y':128,
                            'biome':'minecraft:snowy_plains','distance':1145,
                            'token':'11111111-1111-1111-1111-111111111111',
                            'route_id':'22222222-2222-2222-2222-222222222222',
                            'expires_at':2_000_000_000_000,
                            'target':[1024.5,200.0,-511.5]}]}}
            if op=='navigate':
                if 'target' in params and not self.outbound_done:
                    self.pos=[256.5,180,-127.5]
                    return {'id':self.last,'world_session':self.world,
                            'phase':'waiting','detail':'cruise stopped'}
                self.pos=(list(params['target']) if 'target' in params
                          else [0,160,0])
                return {'id':self.last,'world_session':self.world,'phase':'done'}
            if op=='scan_snow_biomes':
                return survey_reply(self.last,tuple(params['center']),cold=self.cold,offset=0)
            if op=='scan':
                rows=[{'pos':[1024,63,-512],'state':'Block{minecraft:dirt}',
                       'solid':True,'passable':False,'fluid':False,'block_entity':False},
                      {'pos':[1024,64,-512],'state':'Block{minecraft:snow}[layers=1]',
                       'solid':False,'passable':True,'fluid':False,'block_entity':False}]
                return {'id':self.last,'world_session':self.world,
                        'blocks':[row for row in rows if all(
                            params['min'][i]<=row['pos'][i]<=params['max'][i]
                            for i in range(3))]}
            raise AssertionError(op)

    def profile(self):
        return {'server':'test','dimension':'minecraft:overworld','search_radius':256,
                'search_origin':[0,145,0],'resource_regions':[],
                'protected_regions':[{'min':[-220,50,-220],'max':[-200,100,-200]}]}

    def test_seed_candidate_cruises_then_requires_loaded_server_biome_and_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.Client(cold=True)
            found=discover(client,'minecraft:snow',self.profile(),folder,
                           lambda:None,max_tiles=2)
            self.assertEqual(('minecraft:snow',[1024,58,-512],[1039,72,-497]),
                             (found['item'],found['min'],found['max']))
            self.assertEqual(['snow_seed_candidates','navigate','scan_snow_biomes'],
                             [op for op,_ in client.requests[:3]])
            self.assertEqual(5340,client.requests[1][1]['seconds'])
            self.assertTrue(any(op=='scan' for op,_ in client.requests[3:]))
            self.assertEqual('11111111-1111-1111-1111-111111111111',
                             client.snow_expedition_token)
            self.assertEqual([1024.5,200.0,-511.5],client.anchor)
            saved=json.loads(next(Path(folder).glob('*.json')).read_text())
            seed=saved['seed_snow_search']
            self.assertEqual(4,seed['next_cursor'])
            self.assertNotIn('token',seed['candidates']['1024:-512'])
            self.assertNotIn('seed',json.dumps(seed).lower())

    def test_server_biome_mismatch_returns_to_host_origin_without_python_target(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.Client(cold=False)
            self.assertIsNone(discover(client,'minecraft:snow',self.profile(),folder,
                                       lambda:None,max_tiles=2))
            moves=[params for op,params in client.requests if op=='navigate']
            self.assertEqual(2,len(moves));self.assertIn('target',moves[0])
            self.assertNotIn('target',moves[1]);self.assertTrue(moves[1]['snow_expedition_return'])
            self.assertTrue(all(move['seconds']==5340 for move in moves))
            self.assertEqual([0,160,0],client.pos)
            self.assertEqual([0,160,0],client.anchor)
            resource=_resource_ledger_scope_path(
                Path(folder),self.profile()['server'],self.profile()['dimension'],
                'minecraft:snow')
            saved=json.loads(resource.read_text())
            self.assertEqual('server_mismatch',saved['seed_snow_search']['candidates']['1024:-512']['state'])
            self.assertEqual('home_arrived',saved['seed_snow_search']['routes'][-1]['state'])

    def test_structured_local_sampler_unavailable_falls_back_to_loaded_server_coarse(self):
        with tempfile.TemporaryDirectory() as folder,patch('material_jobs.discovery._travel'):
            client=self.Client(sampler_available=False)
            self.assertIsNone(discover(client,'minecraft:snow',self.profile(),folder,
                                       lambda:None,max_tiles=1))
            self.assertEqual('snow_seed_candidates',client.requests[0][0])
            self.assertTrue(any(op=='scan_snow_biomes' for op,_ in client.requests[1:]))

    def test_terminal_stopped_outbound_uses_same_token_once_to_return_home(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.Client(outbound_done=False)
            self.assertIsNone(discover(client,'minecraft:snow',self.profile(),folder,
                                       lambda:None,max_tiles=2))
            path=next(Path(folder).glob('*.json'));saved=json.loads(path.read_text())
            self.assertIsNone(saved['seed_snow_search']['active_route'])
            self.assertEqual('home_arrived',saved['seed_snow_search']['routes'][-1]['state'])
            self.assertEqual('returned_before_arrival',
                             saved['seed_snow_search']['candidates']['1024:-512']['state'])
            moves=[params for op,params in client.requests if op=='navigate']
            self.assertEqual(2,len(moves));self.assertIn('target',moves[0])
            self.assertNotIn('target',moves[1]);self.assertTrue(moves[1]['snow_expedition_return'])

    def test_unsafe_stopped_outbound_holds_same_route_and_never_issues_return(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.Client(outbound_done=False);original=client.status
            client.status=lambda:{**original(),'manual_movement':True}
            with self.assertRaises(Unavailable) as held:
                discover(client,'minecraft:snow',self.profile(),folder,
                         lambda:None,max_tiles=2)
            self.assertEqual('route_uncertain',held.exception.code)
            path=next(Path(folder).glob('*.json'));saved=json.loads(path.read_text())
            self.assertEqual('outbound_uncertain',
                             saved['seed_snow_search']['active_route']['state'])
            self.assertEqual(1,sum(op=='navigate' for op,_ in client.requests))
            before=len(client.requests)
            with self.assertRaises(Unavailable):
                discover(client,'minecraft:snow',self.profile(),folder,
                         lambda:None,max_tiles=2)
            self.assertEqual(before,len(client.requests))

    def test_successful_acquisition_return_clears_discovery_hold_for_next_search(self):
        with tempfile.TemporaryDirectory() as folder:
            client=self.Client(cold=True);profile=self.profile()
            self.assertIsNotNone(discover(client,'minecraft:snow',profile,folder,
                                          lambda:None,max_tiles=2))
            resource=next(Path(folder).glob('*.json'))
            self.assertEqual('candidate_arrived',
                json.loads(resource.read_text())['seed_snow_search']['active_route']['state'])
            acquisition=Path(folder)/'acquisition.json'
            local={'schema':1,'world_session':client.world,'item':'minecraft:snow',
                   'visited':{},'seed_expedition':{'state':'active'}}
            acquisition.write_text(json.dumps(local))
            self.assertTrue(_return_seed_home(client,lambda:None,acquisition,local)['host_target'])
            closed=json.loads(resource.read_text())['seed_snow_search']
            self.assertIsNone(closed['active_route'])
            self.assertEqual('home_arrived',closed['routes'][-1]['state'])
            before=len(client.requests)
            self.assertIsNotNone(discover(client,'minecraft:snow',profile,folder,
                                          lambda:None,max_tiles=2))
            self.assertGreater(len(client.requests),before)


if __name__=='__main__':
    unittest.main()
