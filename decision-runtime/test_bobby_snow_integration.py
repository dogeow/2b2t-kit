import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.acquisition import Unavailable, held_resource_route
from material_jobs.discovery import discover


def hint(chunk=(64,-32)):
    cx,cz=chunk;tile=[cx*16,cz*16]
    return {'source':'bobby_cache','cache_server':'test',
            'dimension':'minecraft:overworld','chunk':[cx,cz],'tile':tile,
            'target':[tile[0]+8.5,200.0,tile[1]+8.5],
            'region_file':f'r.{cx//32}.{cz//32}.mca','fingerprint':'a'*64,
            'mtime_ns':100,'ctime_ns':101,'size':8192,'file_id':7,
            'biomes':['minecraft:snowy_slopes'],
            'distance_sq':float((tile[0]+8.5)**2+(tile[1]+8.5)**2)}


class Client:
    world='world'
    def __init__(self,root,*,cold=True,survey_available=True):
        self.root=Path(root)/'config/twob2tkit/automation';self.root.mkdir(parents=True,exist_ok=True)
        (Path(root)/'.bobby').mkdir(exist_ok=True)
        self.anchor=[0.5,145.0,0.5];self.pos=list(self.anchor);self.time=100
        self.rev=7;self.task='materials-job';self.last=None;self.actions=[]
        self.cold=cold;self.survey_available=survey_available
    def status(self):
        return {'world_session':self.world,'server':'test:25565',
                'dimension':'minecraft:overworld','pos':list(self.pos),'time':self.time,
                'control_revision':self.rev,'projection_selection':{},
                'snow_biome_survey_protocol':1,'snow_seed_locator_protocol':1,
                'snow_seed_locator_available':True,'health':20,'food':20,
                'under_water':False,'flight':True,'guard_armed':True,
                'guard_pve_only':True,'manual_movement':False,
                'safety_hold':{'active':False},'navigating':False,
                'native_material_busy':False,
                'supervision_lease':{'kind':'materials','job_session':self.task,
                    'world_session':self.world,'revision':self.rev,
                    'search_origin':[0.5,145.0,0.5],
                    'return_target':{'x':-20.5,'z':12.5,'cruise_y':170.0,
                        'dimension':'minecraft:overworld','source':'saved_home'}}}
    def checked(self,op,**params):
        reply=self.request(op,**params)
        if reply.get('phase')!='done':raise RuntimeError(reply.get('detail',op))
        return reply
    def request(self,op,**params):
        self.actions.append((op,copy.deepcopy(params)));self.time+=1
        self.last=op+'-'+str(len(self.actions))
        base={'id':self.last,'world_session':self.world,'phase':'done'}
        if op=='guard':return base
        if op=='navigate':self.pos=list(params['target']);return base
        if op=='scan_snow_biomes':
            if not self.survey_available:
                return {**base,'phase':'error','detail':'real chunks not loaded'}
            x,z=params['center'];sample={'pos':[x,96,z],'chunk':[x//16,z//16],
                'biome':'minecraft:snowy_slopes' if self.cold else 'minecraft:plains',
                'precipitation':'snow' if self.cold else 'rain',
                'cold_enough_to_snow':self.cold,'base_temperature':-.3 if self.cold else .8}
            return {**base,'snow_biome_survey':{'center':[x,z],'radius':64,'stride':64,
                'requested_samples':9,'loaded_samples':1,'unloaded_samples':8,
                'samples':[sample]}}
        if op=='scan':
            x,z=1024,-512
            rows=[{'pos':[x,62,z],'state':'Block{minecraft:stone}',
                   'solid':True,'passable':False,'fluid':False,'block_entity':False},
                  {'pos':[x,63,z],'state':'Block{minecraft:snow_block}',
                   'solid':True,'passable':False,'fluid':False,'block_entity':False},
                  {'pos':[x,64,z],'state':'Block{minecraft:snow}[layers=1]',
                   'solid':False,'passable':True,'fluid':False,'block_entity':False}]
            return {**base,'blocks':[row for row in rows if all(
                params['min'][i]<=row['pos'][i]<=params['max'][i] for i in range(3))]}
        raise AssertionError(op)


def profile():
    return {'server':'test:25565','dimension':'minecraft:overworld',
            'search_radius':256,'search_origin':[0.5,145,0.5],
            'resource_regions':[],
            'protected_regions':[{'min':[-200,50,-200],'max':[-180,100,-180]}]}


class BobbySnowIntegrationTest(unittest.TestCase):
    def test_disabled_seed_uses_unvisited_cache_then_live_biome_and_natural_snowpack(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(directory);resource=client.root.parent/'material-resource-ledger'
            with patch('material_jobs.discovery.shared_hints_disabled',return_value=True),\
                 patch('material_jobs.discovery.bobby_snow_candidates',return_value=[hint()]),\
                 patch('material_jobs.discovery.validate_bobby_candidate',return_value=True),\
                 patch('material_jobs.discovery.validate_bobby_world',return_value=True):
                found=discover(client,'minecraft:snow',profile(),resource,lambda:None,max_tiles=2)
            self.assertTrue(found['allow_natural_snowpack'])
            evidence=found['bobby_snow_route']
            self.assertEqual(('minecraft:snowy_slopes','world',[64,-32]),
                             (evidence['live_biome'],evidence['world_session'],evidence['chunk']))
            self.assertFalse(any(op=='snow_seed_candidates' for op,_ in client.actions))
            self.assertEqual('scan_snow_biomes',
                             next(op for op,_ in client.actions if op=='scan_snow_biomes'))
            self.assertTrue(hasattr(client,'bobby_snow_route_id'))
            saved=json.loads(next(resource.glob('*.json')).read_text())['bobby_snow_cache']
            self.assertEqual('candidate_arrived',saved['active_route']['state'])
            self.assertEqual('saved_home',saved['active_route']['return_source'])
            self.assertEqual([-20.5,170.0,12.5],saved['active_route']['return_target'])
            self.assertLessEqual(max(((row['target'][0]-row['from'][0])**2
                +(row['target'][2]-row['from'][2])**2)**.5
                for row in saved['active_route']['recent_segments']),320)

    def test_live_mismatch_returns_same_route_and_next_call_skips_visited_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(directory,cold=False);resource=client.root.parent/'material-resource-ledger'
            second=hint((80,-32))
            patches=(patch('material_jobs.discovery.shared_hints_disabled',return_value=True),
                     patch('material_jobs.discovery.bobby_snow_candidates',
                           return_value=[hint(),second]),
                     patch('material_jobs.discovery.validate_bobby_candidate',return_value=True),
                     patch('material_jobs.discovery.validate_bobby_world',return_value=True))
            with patches[0],patches[1],patches[2],patches[3]:
                self.assertIsNone(discover(client,'minecraft:snow',profile(),resource,
                                           lambda:None,max_tiles=1))
            saved=json.loads(next(resource.glob('*.json')).read_text())['bobby_snow_cache']
            self.assertIsNone(saved['active_route'])
            self.assertEqual('home_arrived',saved['routes'][-1]['state'])
            self.assertEqual([-20.5,170.0,12.5],client.pos)
            self.assertEqual('server_mismatch',next(iter(saved['visited'].values()))['state'])

    def test_persisted_active_route_blocks_before_native_requests_or_new_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(directory);resource=client.root.parent/'material-resource-ledger'
            with patch('material_jobs.discovery.shared_hints_disabled',return_value=True),\
                 patch('material_jobs.discovery.bobby_snow_candidates',return_value=[hint()]),\
                 patch('material_jobs.discovery.validate_bobby_candidate',return_value=True),\
                 patch('material_jobs.discovery.validate_bobby_world',return_value=True):
                discover(client,'minecraft:snow',profile(),resource,lambda:None,max_tiles=1)
            before=len(client.actions)
            restarted=Client(directory)
            with self.assertRaises(Unavailable):
                discover(restarted,'minecraft:snow',profile(),resource,lambda:None,max_tiles=1)
            self.assertEqual([],restarted.actions)
            held=held_resource_route(restarted.root,restarted.world,'minecraft:snow',
                                     profile(),Path(directory)/'acquisition')
            self.assertEqual('route_uncertain',held['code'])
            self.assertGreater(before,0)

    def test_unavailable_real_chunk_survey_returns_home_without_authorizing_snow(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Client(directory,survey_available=False)
            resource=client.root.parent/'material-resource-ledger'
            with patch('material_jobs.discovery.shared_hints_disabled',return_value=True),\
                 patch('material_jobs.discovery.bobby_snow_candidates',return_value=[hint()]),\
                 patch('material_jobs.discovery.validate_bobby_candidate',return_value=True),\
                 patch('material_jobs.discovery.validate_bobby_world',return_value=True):
                self.assertIsNone(discover(client,'minecraft:snow',profile(),resource,
                                           lambda:None,max_tiles=1))
            saved=json.loads(next(resource.glob('*.json')).read_text())['bobby_snow_cache']
            self.assertIsNone(saved['active_route'])
            self.assertEqual('survey_unavailable',next(iter(saved['visited'].values()))['state'])
            self.assertFalse(any(op=='scan' for op,_ in client.actions))
            self.assertEqual([-20.5,170.0,12.5],client.pos)


if __name__=='__main__':unittest.main()
