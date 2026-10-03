import tempfile
import unittest
from pathlib import Path
import lighting_cli as lighting
from test_lighting_cli import FakeClient, snapshot, LOW, HIGH, ENTITY_SCOPE_AT_SCAN_END


class Moving(FakeClient):
    def __init__(self, root, *, hostile=False, malformed=False, endpoint=False, solid=False):
        super().__init__(root); self.pos=[.5,65.5,2.5]; self.moves=[]
        self.hostile,self.malformed,self.endpoint,self.solid=hostile,malformed,endpoint,solid
    def request(self, op, **params):
        if op=='snapshot':
            self.tick+=1; return {**snapshot(tick=self.tick),'pos':list(self.pos)}
        if op=='scan':
            low,high=params['min'],params['max'];entities=[]
            x=3.5 if self.endpoint else 2.0
            if low[0]<=x<=high[0]+1 and low[1]<=66.8 and high[1]>=65:
                entity={'type':'minecraft:sheep','alive':True,'hostile':self.hostile,
                        'bounds':{'min':[x-.4,65,2.1],'max':[x+.4,66.8,2.9]}}
                if self.malformed:entity['bounds']['max'][1]=float('nan')
                entities=[entity]
            rows=[{'pos':[0,67,2],'state':'Block{minecraft:stone}'}] if self.solid and high[1]>67 else []
            return {'phase':'done','world_session':self.world,'blocks':rows,
                    'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END,'scan_entities':entities}
        return super().request(op,**params)
    def checked(self,op,**params):
        if op=='navigate':self.moves.append(params);self.pos=list(params['target']);return {'phase':'done'}
        return super().checked(op,**params)


class EntityOverpassTest(unittest.TestCase):
    def runner(self, root, **kwargs):
        c=Moving(root,**kwargs);r=lighting.LightingRun(c,LOW,HIGH,1,root,snapshot(),
                        movement_bounds={'min':[-2,60,-2],'max':[6,90,6]})
        return c,r
    def test_passive_sheep_gets_three_independently_verified_air_only_legs(self):
        with tempfile.TemporaryDirectory() as root:
            c,r=self.runner(root);r.move([3.5,65.5,2.5])
            self.assertEqual(3,len(c.moves));self.assertTrue(all(x['air_only'] for x in c.moves))
            self.assertEqual([3.5,65.5,2.5],c.pos);self.assertEqual(68.8,c.moves[0]['target'][1])
            self.assertEqual(0,c.interactions);self.assertEqual('passive_entity_overpass',r.report['routes'][0]['kind'])
    def test_unknown_or_hostile_entity_never_uses_a_guessed_overpass(self):
        for kwargs in ({'hostile':True},{'malformed':True}):
            with self.subTest(kwargs=kwargs),tempfile.TemporaryDirectory() as root:
                c,r=self.runner(root,**kwargs)
                with self.assertRaises(lighting.LightingBlocked):r.move([3.5,65.5,2.5])
                self.assertEqual([],c.moves)
    def test_endpoint_animal_or_new_solid_is_not_crossed(self):
        for kwargs,maximum in (({'endpoint':True},2),({'solid':True},0)):
            with self.subTest(kwargs=kwargs),tempfile.TemporaryDirectory() as root:
                c,r=self.runner(root,**kwargs)
                with self.assertRaises(lighting.LightingBlocked):r.move([3.5,65.5,2.5])
                self.assertLessEqual(len(c.moves),maximum)
    def test_players_neutrals_and_vehicles_do_not_get_passive_animal_overpass(self):
        for kind in ('minecraft:player','minecraft:villager','minecraft:iron_golem','minecraft:bee','minecraft:wolf','minecraft:boat','minecraft:minecart'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root:
                c,r=self.runner(root);native=c.request
                def request(op,**params):
                    result=native(op,**params)
                    if op=='scan':
                        for entity in result['scan_entities']:entity['type']=kind
                    return result
                c.request=request
                with self.assertRaises(lighting.LightingBlocked):r.move([3.5,65.5,2.5])
                self.assertEqual([],c.moves)

    def test_height_limit_cannot_expand_authorized_movement_box(self):
        with tempfile.TemporaryDirectory() as root:
            c,r=self.runner(root);r.move_high=(6,69,6)
            with self.assertRaises(lighting.LightingBlocked):r.move([3.5,65.5,2.5])
            self.assertEqual([],c.moves)


if __name__=='__main__':unittest.main()
