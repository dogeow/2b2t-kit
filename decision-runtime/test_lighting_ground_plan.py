"""Current-scan pure ground routes; no Client or live interfaces."""
from copy import deepcopy
import math
import unittest

from lighting_ground_plan import GroundPlanRejected, plan

WORLD='current-world'
LOW,HIGH=[0,0,0],[4,4,2]

def row(pos,state='Block{minecraft:stone}',**changes):
    result={'pos':list(pos),'state':state,'solid':True,'fluid':False,'passable':False,
        'replaceable':False,'block_entity':False,'zombie_spawn_floor':True,'zombie_block_light_risk':True,
        'spawn_block_light':0,'monster_spawn_block_light_limit':0}
    result.update(changes);return result

def receipt(low,high,rows,rid='scan'):
    total=math.prod(b-a+1 for a,b in zip(low,high))
    return {'id':rid,'phase':'done','world_session':WORLD,'control_revision':7,'scan_start_revision':7,
        'scan_end_revision':7,'scan_cells_read':total,'scan_total_cells':total,'scan_started_at':1000,'scan_ended_at':1001,
        'scan_scope':'loaded_client_cells_sampled_on_client_ticks_not_atomic_server_snapshot',
        'scan_entity_scope':'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd',
        'scan_entities':[],'blocks':rows}

class GroundPlanTests(unittest.TestCase):
    def setUp(self):
        rows=[row((x,0,z))for x in range(5)for z in range(3)]
        # Two-high tunnel at x2..4, existing entrance at x0.
        rows.extend(row((x,3,1),zombie_spawn_floor=False,zombie_block_light_risk=False)for x in range(2,5))
        self.scan=receipt(LOW,HIGH,rows)
        self.kw={'low':LOW,'high':HIGH,'context':dict(world_session=WORLD,control_revision=7,now_ms=1002,request_id='scan'),
            'entry':[.5,1,1.5],'supports':[[4,0,1]],'protected':[],
            'movement_bounds':{'min':[-10,0,-10],'max':[10,319,10]}}
        self.exit={'receipt':receipt([0,-64,1],[0,319,1],[row((0,0,1))],'exit'),
                   'request_id':'exit','min':[0,-64,1],'max':[0,319,1]}
    def test_current_two_high_route_is_reversible_without_roof_free_target_assumption(self):
        before=deepcopy(self.scan);result=plan(self.scan,**self.kw,exit_scan=self.exit)
        self.assertEqual(result['state'],'route_candidate');self.assertTrue(result['exit_proved'])
        self.assertEqual(len(result['candidates']),1);candidate=result['candidates'][0]
        self.assertEqual(candidate['return_route'],list(reversed(candidate['outward_route'])))
        self.assertTrue(candidate['native_visible_up_face_and_actual_eye_range_required'])
        self.assertEqual(result['placement_credit'],0);self.assertEqual(result['game_operations'],0)
        self.assertEqual(self.scan,before)
    def test_unproved_sky_exit_requires_current_full_entrance_column(self):
        result=plan(self.scan,**self.kw)
        self.assertEqual(result['state'],'needs_scan');self.assertFalse(result['exit_proved'])
        self.assertEqual(result['needs_scan'][-1]['min'],[0,-64,1])
    def test_partial_stale_wrong_rid_world_revision_or_unknown_entities_reject(self):
        cases=[('phase','waiting'),('world_session','old-world'),('id','older'),('scan_cells_read',74),
               ('scan_end_revision',8),('scan_ended_at',1),('scan_entity_scope','unknown')]
        for key,value in cases:
            scan=deepcopy(self.scan);scan[key]=value
            with self.subTest(key=key),self.assertRaises(GroundPlanRejected):plan(scan,**self.kw)
        scan=deepcopy(self.scan);scan['blocks'][0].pop('passable')
        with self.assertRaises(GroundPlanRejected):plan(scan,**self.kw)
    def test_unknown_target_or_entry_boundary_is_needs_scan_not_closed(self):
        kw=deepcopy(self.kw);kw['supports']=[[5,0,1]]
        result=plan(self.scan,**kw)
        self.assertEqual(result['state'],'needs_scan');self.assertEqual(result['candidates'],[])
        self.assertFalse(result['physical_impossibility_claimed'])
    def test_protected_target_or_danger_floor_never_authorizes_placement(self):
        kw=deepcopy(self.kw);kw['protected']=[{'min':[4,0,1],'max':[4,2,1]}]
        self.assertEqual(plan(self.scan,**kw)['candidates'],[])
        scan=deepcopy(self.scan);scan['blocks'][0].update(state='Block{minecraft:magma_block}')
        kw=deepcopy(self.kw);kw['entry']=[.5,1,.5]
        self.assertEqual(plan(scan,**kw)['candidates'],[])
    def test_current_entity_body_intersection_blocks_entrance_or_route(self):
        scan=deepcopy(self.scan);scan['scan_entities']=[{'type':'minecraft:cow','alive':True,'hostile':False,
            'world_session':WORLD,'bounds':{'min':[.2,1,1.2],'max':[.8,2.4,1.8]}}]
        result=plan(scan,**self.kw)
        self.assertEqual(result['candidates'],[])
        self.assertIn('entry_ground_body_or_entity_is_not_proved',result['diagnostics'])
    def test_nearby_nonintersecting_entity_does_not_become_a_body_collision(self):
        scan=deepcopy(self.scan);scan['scan_entities']=[{'type':'minecraft:cow','alive':True,'hostile':False,
            'world_session':WORLD,'bounds':{'min':[.8,1,2.1],'max':[1.4,2.4,2.8]}}]
        self.assertEqual(plan(scan,**self.kw,exit_scan=self.exit)['state'],'route_candidate')
    def test_existing_noncolliding_torch_or_grass_does_not_fake_air_or_block_physics(self):
        for state in ('Block{minecraft:torch}','Block{minecraft:short_grass}','Block{minecraft:dandelion}'):
            scan=deepcopy(self.scan);scan['blocks'].append(row((1,1,1),state,solid=False,passable=True,
                replaceable=True,zombie_spawn_floor=False,zombie_block_light_risk=False))
            self.assertEqual(plan(scan,**self.kw,exit_scan=self.exit)['state'],'route_candidate')
    def test_unloaded_foreign_or_roofed_exit_is_never_a_safe_ascent(self):
        exit=deepcopy(self.exit);exit['receipt']['world_session']='foreign'
        with self.assertRaises(GroundPlanRejected):plan(self.scan,**self.kw,exit_scan=exit)
        exit=deepcopy(self.exit);exit['receipt']['blocks'].append(row((0,4,1)))
        result=plan(self.scan,**self.kw,exit_scan=exit)
        self.assertFalse(result['exit_proved']);self.assertEqual(result['state'],'needs_scan')
    def test_higher_steps_are_not_silently_promoted_to_same_ground_route(self):
        kw=deepcopy(self.kw);kw['supports']=[[4,1,1]]
        scan=deepcopy(self.scan);scan['blocks'].append(row((4,1,1)))
        self.assertEqual(plan(scan,**kw)['candidates'],[])
    def test_later_exit_floor_loss_or_current_body_entity_does_not_prove_return(self):
        exit=deepcopy(self.exit);exit['receipt']['blocks']=[]
        self.assertFalse(plan(self.scan,**self.kw,exit_scan=exit)['exit_proved'])
        exit=deepcopy(self.exit);exit['receipt']['scan_entities']=[{'type':'minecraft:cow','alive':True,'hostile':False,
            'world_session':WORLD,'bounds':{'min':[.2,1,1.2],'max':[.8,2.4,1.8]}}]
        self.assertFalse(plan(self.scan,**self.kw,exit_scan=exit)['exit_proved'])

if __name__=='__main__':unittest.main()
