import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from survival_bridge import Bridge,Paused,valid
from survival_world import World,shelter
from survival import Runner

def row(p,name,solid=True,passable=False):
    return {'pos':list(p),'state':'Block{minecraft:'+name+'}','solid':solid,'passable':passable,'fluid':False,'block_entity':False}

def terrain():return [row((x,0,z),'stone') for x in range(-6,7) for z in range(-6,7)]
def state():
    return {'bridge_version':2,'connected':True,'server':'singleplayer','dimension':'minecraft:overworld','game_mode':'survival',
            'world_name':'Trial','world_session':'a','health':20,'food':20,'manual_movement':False,'window_active':True,
            'screen':'','pos':[.5,1,.5],'control_revision':4,'last_request':'old','phase':'done','entities':[],
            'inventory':[{'item':'minecraft:oak_log','count':2}],'menu':{'id':0,'type':'InventoryMenu','cursor':{'count':0},'slots':[]}}

class WorldTests(unittest.TestCase):
    def test_unknown_space_and_pits_cannot_be_walked_into(self):
        rows=[r for r in terrain() if r['pos']!=[1,0,0]]
        w=World(rows,[-6,0,-6],[6,4,6]);paths=w.paths([.5,1,.5])
        self.assertNotIn((1,1,0),paths);self.assertNotIn((7,1,0),paths)
        self.assertIn((2,1,0),paths) # May route around the hole.
    def test_magma_and_water_never_form_walkway(self):
        rows=[r for r in terrain() if r['pos']!=[1,0,0]]+[row((1,0,0),'magma_block'),row((0,1,1),'water',False,True)]
        paths=World(rows,[-6,0,-6],[6,4,6]).paths([.5,1,.5])
        self.assertNotIn((1,1,0),paths);self.assertNotIn((0,1,1),paths)
    def test_player_standing_on_block_edge_recenters_onto_actual_support(self):
        rows=[r for r in terrain() if r['pos']!=[0,0,0]]
        w=World(rows,[-6,0,-6],[6,4,6]);paths=w.paths([.04,1,.5])
        self.assertEqual(w.route(paths,(-1,1,0)),[(-1,1,0)])
        self.assertFalse(w.paths([.5,1,.5]))
    def test_one_block_step_needs_head_clearance(self):
        rows=terrain()+[row((1,1,0),'stone'),row((0,3,0),'stone')]
        w=World(rows,[-1,0,0],[1,4,0])
        self.assertNotIn((1,2,0),w.paths([.5,1,.5]))
    def test_open_door_allows_entry_but_closed_door_does_not(self):
        base=terrain();opened=row((1,1,0),'oak_door');opened['state']+='[open=true]'
        w=World(base+[opened],[-6,0,-6],[6,4,6]);self.assertTrue(w.open((1,1,0)))
        opened['state']=opened['state'].replace('true','false');self.assertFalse(w.open((1,1,0)))
    def test_resource_selection_respects_camp_and_current_footing(self):
        rows=terrain()+[row((2,1,0),'oak_log'),row((-2,1,0),'oak_log')]
        w=World(rows,[-6,0,-6],[6,4,6]);found=w.resource([.5,1,.5],{'oak_log'},{(2,1,0)})
        self.assertEqual(found[0],(-2,1,0))
        self.assertIsNone(w.resource([.5,1,.5],{'oak_log'},{(2,1,0),(-2,1,0)}))
    def test_hut_has_full_roof_and_only_door_opening(self):
        blocks,door=shelter([0,1,0]);self.assertEqual(len(set(blocks)),55)
        self.assertNotIn(door,blocks);self.assertNotIn((0,2,2),blocks)
        self.assertEqual(sum(y==3 for x,y,z in blocks),25)
    def test_resource_columns_are_removed_from_the_top(self):
        w=World(terrain()+[row((2,y,0),'dirt') for y in (1,2,3)],[-6,0,-6],[6,5,6])
        target,path=w.resource([.5,1,.5],{'dirt'})
        self.assertEqual(target,(2,3,0))
    def test_grass_spread_does_not_count_as_a_hole_in_an_earth_shelter(self):
        w=World([row((0,1,0),'grass_block')],[-1,0,-1],[1,3,1])
        self.assertTrue(w.earth((0,1,0)))
        self.assertFalse(w.earth((1,1,0)))
    def test_camp_rejects_an_obstructed_flat_area(self):
        w=World(terrain(),[-6,0,-6],[6,4,6]);self.assertIsNotNone(w.camp([.5,1,.5]))
        w=World(terrain()+[row((x,2,z),'stone') for x in range(-6,7) for z in range(-6,7)],[-6,0,-6],[6,4,6])
        self.assertIsNone(w.camp([.5,1,.5]))

class OwnershipTests(unittest.TestCase):
    def test_opted_in_background_api_does_not_relax_manual_or_world_guards(self):
        s={**state(),'window_active':False};valid(s,'Trial','a',background=True)
        with self.assertRaises(Paused):valid(s,'Trial','a')
        with self.assertRaises(Paused):valid({**s,'manual_movement':True},'Trial','a',background=True)
        with self.assertRaises(Paused):valid({**s,'server':'another-server'},'Trial','a',background=True)
    def test_multiplayer_creative_world_change_and_manual_control_are_rejected(self):
        for values in ({'server':'simpcraft.com'},{'game_mode':'creative'},{'world_session':'b'},
                       {'world_name':'My real world'},{'manual_movement':True},{'health':15}):
            with self.subTest(values=values),self.assertRaises(Paused):valid({**state(),**values},'Trial','a')
    def test_emergency_stop_between_requests_latches(self):
        with tempfile.TemporaryDirectory() as tmp,patch('survival_bridge.status',return_value=state()) as read:
            bridge=Bridge(Path(tmp),'Trial');read.return_value={**state(),'control_revision':5}
            with self.assertRaises(Paused):bridge.request('walk',target=[1.5,1,.5])
            self.assertFalse((Path(tmp)/'request.json').exists())
    def test_other_request_between_steps_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp,patch('survival_bridge.status',return_value=state()) as read:
            bridge=Bridge(Path(tmp),'Trial');read.return_value={**state(),'last_request':'manual'}
            with self.assertRaises(Paused):bridge.request('scan',min=[0,0,0],max=[1,1,1])
            bridge.stop_owned();self.assertFalse((Path(tmp)/'request.json').exists())
    def test_unacknowledged_pending_request_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp,patch('survival_bridge.status',return_value=state()):
            path=Path(tmp)/'request.json';path.write_text('{"id":"pending"}')
            bridge=Bridge(Path(tmp),'Trial')
            with self.assertRaises(Paused):bridge.request('scan')
            bridge.owned=True;bridge.stop_owned()
            self.assertEqual(json.loads(path.read_text())['id'],'pending')
    def test_budget_stops_before_another_model_call(self):
        with tempfile.TemporaryDirectory() as tmp,patch('survival_bridge.status',return_value=state()):
            bridge=Bridge(Path(tmp),'Trial');runner=Runner(bridge,None,tmp,max_calls=1);runner.calls=1
            with self.assertRaisesRegex(Paused,'模型调用预算'):runner.decide('wood','wood',{})
    def test_cleanup_cannot_stop_a_new_native_task_after_handoff(self):
        with tempfile.TemporaryDirectory() as tmp,patch('survival_bridge.status',return_value=state()) as read:
            b=Bridge(Path(tmp),'Trial');b.owned=True;b.active='old'
            path=Path(tmp)/'request.json';path.write_text('{"id":"old"}')
            read.return_value={**state(),'control_revision':7,'phase':'stopped','chopping':True}
            b.stop_owned();self.assertEqual(json.loads(path.read_text())['id'],'old')
    def test_confirmed_native_stop_latches_even_if_caller_catches_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);reads=0
            def response(*args):
                nonlocal reads
                if not (root/'request.json').exists():return state()
                request=json.loads((root/'request.json').read_text());reads+=1
                return {**state(),'id':request['id'],'last_request':request['id'],'phase':'running' if reads==1 else 'stopped',
                        'control_revision':5 if reads==1 else 6,'detail':'Manual takeover'}
            with patch('survival_bridge.status',side_effect=response),patch('survival_bridge.time.sleep'):
                b=Bridge(root,'Trial')
                with self.assertRaises(Paused):b.request('walk',target=[1,1,1])
                before=(root/'request.json').read_text()
                with self.assertRaisesRegex(Paused,'手动重新开始'):b.request('scan')
                self.assertEqual((root/'request.json').read_text(),before)
    def test_native_deadline_cancellation_also_latches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def response(*args):
                if not (root/'request.json').exists():return state()
                request=json.loads((root/'request.json').read_text())
                return {**state(),'id':request['id'],'last_request':request['id'],'phase':'waiting','control_revision':7,'detail':'deadline exceeded'}
            with patch('survival_bridge.status',side_effect=response):
                b=Bridge(root,'Trial')
                with self.assertRaises(Paused):b.request('walk',target=[1,1,1])
                self.assertTrue(b.halted)
                with self.assertRaisesRegex(Paused,'手动重新开始'):b.request('scan')
    def test_resume_cannot_reuse_another_worlds_camp(self):
        with tempfile.TemporaryDirectory() as tmp,patch('survival_bridge.status',return_value=state()):
            path=Path(tmp)/'old.json';path.write_text(json.dumps({'world_name':'Other'}))
            with self.assertRaises(Paused):Runner(Bridge(Path(tmp),'Trial'),None,tmp,resume=path)

if __name__=='__main__':unittest.main()
