import copy
import json
from pathlib import Path
import tempfile
import unittest
from animal_lure import ground_route, run
from potato_farm import FarmWait
from test_animal_breed import BreedClient
from test_potato_farm import row
from test_potato_harvest import Clock

SCENE = {'min':[-2,62,-2], 'max':[9,66,2]}
DEST = [6.5,64,.5]


class LureClient(BreedClient):
    def __init__(self):
        super().__init__(food=4); self.entities = [self.entities[0]]
        self.entities[0]['pos'] = [-.5,64,.5]; self.extra['pos'] = [.5,64,.5]
        self.inv[12],self.inv[5] = self.inv[5],self.inv[12]
        self.inv[12]['slot']=12; self.inv[5]['slot']=5; self.selected=5
        self.rows = {(x,63,z):row((x,63,z),'Block{minecraft:grass_block}[snowy=false]')
                     for x in range(-2,10) for z in range(-2,3)}
        self.move_phase = 'done'; self.lose_follower=False; self.on_move=None

    def request(self, op, **params):
        if op == 'navigate':
            self.calls.append((op,copy.deepcopy(params)))
            self.assert_step = abs(params['target'][0]-self.extra['pos'][0])+abs(params['target'][2]-self.extra['pos'][2])
            assert self.assert_step<=3 and params['air_only'] is True and params['target'][1]==64
            if self.move_phase == 'done':
                self.extra['pos']=params['target'][:]
                self.entities[0]['pos']=[params['target'][0]-(10 if self.lose_follower else 1),64,params['target'][2]]
                self.rev+=1; self.extra['control_revision']=self.rev; self.extra['supervision_lease']['revision']=self.rev
            if self.on_move: self.on_move(self)
            return {**self.status(),'phase':self.move_phase,'id':'native-lure-'+str(len(self.calls))}
        return super().request(op,**params)

    def moves(self): return [p for op,p in self.calls if op=='navigate']


class AnimalLureTest(unittest.TestCase):
    def execute(self, client, directory=None, **options):
        clock=Clock()
        if directory is not None:
            return run(client,'adult-a',DEST,SCENE,directory,sleep=clock.sleep,monotonic=clock.monotonic,**options)
        with tempfile.TemporaryDirectory() as out:
            result=run(client,'adult-a',DEST,SCENE,out,sleep=clock.sleep,monotonic=clock.monotonic,**options)
            return result,json.loads(Path(result['journal']).read_text())

    def test_fresh_cardinal_ground_route_uses_at_most_three_metre_native_steps_and_no_food_use(self):
        client=LureClient(); result,book=self.execute(client)
        self.assertEqual('done',result['phase'],result); self.assertEqual(2,len(client.moves()))
        self.assertEqual([3.5,6.5],[p['target'][0] for p in client.moves()])
        self.assertEqual(4,client.inv[5]['count']); self.assertFalse(result['breeding_claimed'])
        self.assertEqual(2,len(result['observed_times'])); self.assertEqual(7,len(book['route']))
        self.assertTrue(all(op in ('scan','navigate') for op,_ in client.calls))

    def test_missing_floor_water_partial_floor_body_obstacle_or_untyped_scan_are_not_a_route(self):
        client=LureClient(); state=client.request('scan',min=SCENE['min'],max=SCENE['max'],details=True)
        for change in (lambda s:s.update(blocks=[]),
                       lambda s:s['blocks'][0].pop('solid'),
                       lambda s:[r.update(fluid=True) for r in s['blocks']],
                       lambda s:[r.update(solid=False) for r in s['blocks']]):
            altered=copy.deepcopy(state); change(altered)
            with self.assertRaises(FarmWait): ground_route(altered,[.5,64,.5],DEST,SCENE)
        altered=copy.deepcopy(state)
        altered['blocks'].append(row((0,64,0),'Block{minecraft:chest}'))
        with self.assertRaises(FarmWait): ground_route(altered,[.5,64,.5],DEST,SCENE)
        with self.assertRaises(FarmWait): ground_route(state,[.5,64,.5],DEST,SCENE,max_route=5)

    def test_cow_route_keeps_one_body_cell_from_wall_instead_of_cutting_corner(self):
        client=LureClient(); state=client.request('scan',min=SCENE['min'],max=SCENE['max'],details=True)
        state['blocks'].append(row((3,64,1),'Block{minecraft:oak_trapdoor}[open=true]'))
        state['blocks'].append(row((3,65,1),'Block{minecraft:oak_trapdoor}[open=true]'))
        route=ground_route(state,[.5,64,.5],DEST,SCENE)
        self.assertNotIn([3.5,64,.5],route)
        self.assertTrue(any(p[2]==-.5 for p in route))

    def test_unknown_native_movement_is_durable_and_never_replayed(self):
        client=LureClient(); client.move_phase='waiting'
        with tempfile.TemporaryDirectory() as out:
            first=self.execute(client,directory=out); self.assertEqual('WAIT_RECONCILE',first['code'])
            self.assertEqual(1,len(client.moves())); pending=json.loads(Path(first['journal']).read_text())['pending']
            self.assertEqual([3.5,64,.5],pending['target'])
            calls=len(client.calls); self.assertEqual('WAIT_RECONCILE',self.execute(client,directory=out)['code'])
            self.assertEqual(calls,len(client.calls))

    def test_exact_adult_visible_uuid_and_held_wheat_are_required_before_any_movement(self):
        for change in (lambda c:c.entities[0].update(is_baby=True),
                       lambda c:c.entities[0].update(visible=False),
                       lambda c:c.entities[0].update(pos=[-10,64,.5]),
                       lambda c:c.inv[5].update(item='minecraft:potato'),
                       lambda c:c.extra.update(manual_movement=True)):
            client=LureClient(); change(client); result,_=self.execute(client)
            self.assertEqual('waiting',result['phase']); self.assertEqual([],client.moves())

    def test_lost_follower_injury_or_changed_stock_stops_after_one_native_step(self):
        for change in (lambda c:c.extra.update(health=19,recent_hurt_at=1),
                       lambda c:c.inv[5].update(count=3)):
            client=LureClient(); client.on_move=change; result,_=self.execute(client)
            self.assertEqual('WAIT_SAFETY',result['code']); self.assertEqual(1,len(client.moves()))
        client=LureClient(); client.lose_follower=True; result,_=self.execute(client)
        self.assertEqual('WAIT_FOLLOWER',result['code']); self.assertEqual(1,len(client.moves()))

    def test_declared_scene_volume_and_route_budget_are_bounded(self):
        for options in ({'max_route':41},{'max_route':True},{'follower_wait_seconds':7}):
            with self.assertRaises(ValueError): self.execute(LureClient(),**options)
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaises(ValueError):
                run(LureClient(),'adult-a',DEST,{'min':[0,0,0],'max':[99,99,99]},out)


if __name__=='__main__': unittest.main()
