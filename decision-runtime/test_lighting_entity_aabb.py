"""Native integer entity scans require exact finite body overlap before blocking."""
from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest

import lighting_cli as lighting
from potato_farm import ENTITY_SCOPE_AT_SCAN_END
from test_lighting_cli import FakeClient,LOW,HIGH,snapshot


def cow():
    return {'type':'minecraft:cow','alive':True,'hostile':False,
            'bounds':{'min':[-.8973,72,2.0],'max':[.0027,73.4,2.9]}}


class Moving(FakeClient):
    def __init__(self,root):
        super().__init__(root);self.pos=[.50005,75,2.5];self.moves=[]
        self.entities=[cow()];self.changes={}
    def request(self,op,**params):
        if op=='snapshot':
            self.tick+=1;return snapshot(tick=self.tick)|{'pos':self.pos[:]}
        if op=='scan':
            low,high=params['min'],params['max'];count=math.prod(b-a+1 for a,b in zip(low,high))
            return {'phase':'done','world_session':self.world,'blocks':[],
                'control_revision':self.rev,'scan_start_revision':self.rev,'scan_end_revision':self.rev,
                'scan_cells_read':count,'scan_total_cells':count,'scan_entities':deepcopy(self.entities),
                'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END,**deepcopy(self.changes)}
        return super().request(op,**params)
    def checked(self,op,**params):
        if op=='navigate':self.moves.append(deepcopy(params));self.pos=list(params['target']);return {'phase':'done'}
        return super().checked(op,**params)


class EntityAabbTests(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        client=Moving(Path(tmp.name));runner=lighting.LightingRun(client,LOW,HIGH,1,tmp.name,snapshot(),
                                     movement_bounds={'min':[-2,60,-2],'max':[6,90,6]})
        return client,runner

    def test_real_cow_shape_outside_body_is_not_an_intersection_or_overpass(self):
        client,runner=self.fixture();target=[.50005,73.5,2.5]
        runner.move(target)
        self.assertEqual([{'target':target,'arrival':.25,'seconds':45,'air_only':True}],client.moves)
        self.assertEqual(0,client.interactions);self.assertEqual([],runner.report.get('routes',[]))

    def test_each_disjoint_axis_and_touching_face_are_filtered_before_vertical_gate(self):
        for axis in range(3):
            with self.subTest(axis=axis):
                client,runner=self.fixture();low=[.2,73.6,2.2];high=[.8,74,2.8]
                body_min=[.50005-.35,73.5,2.5-.35]
                low[axis]=body_min[axis]-1;high[axis]=body_min[axis]
                client.entities[0]['bounds']={'min':low,'max':high}
                runner.move([.50005,73.5,2.5]);self.assertEqual(1,len(client.moves))

    def test_tiny_real_overlap_still_blocks_a_vertical_leg_without_harming_cow(self):
        client,runner=self.fixture();client.entities[0]['bounds']={'min':[.1,73.5,2.1],'max':[.150051,74,2.9]}
        with self.assertRaisesRegex(lighting.LightingBlocked,'intersects movement'):runner.move([.50005,73.5,2.5])
        self.assertEqual([],client.moves);self.assertEqual(0,client.interactions)

    def test_missing_or_malformed_box_even_outside_never_authorizes_movement(self):
        for change in ('missing','min','max','nan','infinity','bool','reverse','type','alive','hostile','foreign_entity','item'):
            with self.subTest(change=change):
                client,runner=self.fixture();entity=client.entities[0]
                if change=='missing':entity.pop('bounds')
                elif change in ('min','max'):entity['bounds'][change]=[0,0]
                elif change=='nan':entity['bounds']['max'][0]=float('nan')
                elif change=='infinity':entity['bounds']['max'][0]=float('inf')
                elif change=='bool':entity['bounds']['max'][0]=True
                elif change=='reverse':entity['bounds']['max'][0]=entity['bounds']['min'][0]
                elif change in ('type','alive','hostile'):entity.pop(change)
                elif change=='foreign_entity':entity['world_session']='foreign'
                else:entity['type']='minecraft:item';entity.pop('bounds')
                with self.assertRaises(lighting.LightingBlocked):runner.move([.50005,73.5,2.5])
                self.assertEqual([],client.moves)

    def test_foreign_partial_stale_or_unknown_entity_scope_never_passes(self):
        for changes in ({'world_session':'foreign'},{'phase':'waiting'},{'scan_entity_scope':'unknown'},
                        {'scan_cells_read':0},{'scan_end_revision':99},{'control_revision':True},
                        {'scan_total_cells':None}):
            with self.subTest(changes=changes):
                client,runner=self.fixture();client.changes=changes
                with self.assertRaises(lighting.LightingBlocked):runner.move([.50005,73.5,2.5])
                self.assertEqual([],client.moves)
        client,runner=self.fixture();client.entities[0]['bounds']={'min':[10,72,2],'max':[11,73.4,2.9]}
        with self.assertRaisesRegex(lighting.LightingBlocked,'scan scope'):runner.move([.50005,73.5,2.5])
        self.assertEqual([],client.moves)

    def test_station_reapproach_uses_same_exact_entity_gate_without_high_detour(self):
        client,runner=self.fixture()
        runner.approach_station([0,71,2],snapshot()|{'pos':client.pos[:]},0,0)
        self.assertEqual(1,len(client.moves));self.assertEqual([.5,73.5,2.5],client.pos)
        self.assertEqual('fresh_clear_sweep',runner.report['station_reapproaches'][0]['route'])

    def test_full_details_reject_missing_or_contradictory_metadata_before_zero(self):
        row={'solid':True,'fluid':False,'passable':False,'replaceable':False,'block_entity':False,
             'zombie_spawn_floor':True,'zombie_block_light_risk':True,'spawn_block_light':0,'monster_spawn_block_light_limit':0}
        self.assertEqual({(0,63,0):row},lighting.validate_native_details({(0,63,0):row}))
        for key in row:
            with self.subTest(missing=key):
                changed=deepcopy(row);changed.pop(key)
                with self.assertRaises(lighting.LightingBlocked):lighting.validate_native_details({(0,63,0):changed})
        for change in ({'zombie_block_light_risk':False},{'spawn_block_light':True},
                       {'monster_spawn_block_light_limit':16},{'passable':0}):
            with self.subTest(change=change),self.assertRaises(lighting.LightingBlocked):
                lighting.validate_native_details({(0,63,0):{**row,**change}})


if __name__=='__main__':unittest.main()
