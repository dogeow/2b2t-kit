import copy
import unittest

from material_jobs.construction_access_plan import plan_access, AccessPlanBlocked


WHITE='Block{minecraft:white_concrete}'
POLISHED='Block{minecraft:polished_andesite}'


def fixture(offset=(0,0,0)):
    shift=lambda p:[p[i]+offset[i] for i in range(3)]
    states={}
    for x in range(5):
        for y in range(15):
            for z in range(5):
                if x in (0,4) or z in (0,4) or y in (0,14):states[(x,y,z)]=WHITE
    for y in (2,6,10):
        for x in range(1,4):
            for z in range(1,4):states[(x,y,z)]=POLISHED
    missing={(1,2,1),(1,2,2),(3,6,1)}|{(x,10,z) for x in range(1,4) for z in range(1,4)}
    expected=[{'pos':shift(p),'state':value} for p,value in states.items()]
    blocks=[{'pos':shift(p),'state':value,'solid':True,'passable':False,'replaceable':False,'fluid':False,'block_entity':False}
            for p,value in states.items() if p not in missing]
    scan={'min':shift((-2,-1,-2)),'max':shift((6,16,6)),'blocks':blocks,'complete':True,
          'world_session':'test-world','observed_at':1000,'player':[6.5+offset[0],13.02+offset[1],2.5+offset[2]]}
    selection={'min':shift((0,0,0)),'max':shift((4,14,4)),'key':'fixture'}
    pending=[{'pos':shift(p),'expected':POLISHED} for p in sorted(missing)]
    return scan,expected,selection,pending,{'minecraft:white_concrete':2,'minecraft:polished_andesite':len(missing)}


class ConstructionAccessPlanTest(unittest.TestCase):
    def test_above_layer_phases_choose_high_door_and_preserve_exit(self):
        plan=plan_access(*fixture())
        self.assertEqual([[4,11,2],[4,12,2]],[r['pos'] for r in plan['portal']])
        self.assertEqual([2,6,10],[stage['layer_y'] for stage in plan['stages']])
        self.assertEqual([2,1,9],[len(stage['targets']) for stage in plan['stages']])
        self.assertTrue(all(stage['station'][1]>stage['layer_y'] and stage['exit_preserved'] for stage in plan['stages']))
        self.assertTrue(all(stage['exit_path_after_layer'][-1]==plan['outside_station'] for stage in plan['stages']))
        self.assertEqual(plan['outside_station'],plan['final_exit_path'][-1])
        self.assertEqual(plan['inside_station'],plan['entry_path'][-1])
        self.assertEqual({'minecraft:white_concrete':2},plan['restore_reserve'])
        self.assertEqual(plan['restore_order'][::-1],plan['mine_order'])
        self.assertTrue(plan['geometry_only']);self.assertTrue(plan['requires_live_revalidation'])

    def test_translated_model_has_same_relative_plan_without_fixed_coordinates(self):
        first=plan_access(*fixture());offset=(800,64,-400);other=plan_access(*fixture(offset))
        expected=[[p[i]+offset[i] for i in range(3)] for p in first['restore_order']]
        self.assertEqual(expected,other['restore_order'])
        self.assertEqual([y+offset[1] for y in (2,6,10)],[s['layer_y'] for s in other['stages']])

    def test_unconfirmed_or_unscoped_scan_is_rejected(self):
        for field,value in [('complete',False),('world_session',''),('observed_at',None)]:
            data=list(fixture());data[0][field]=value
            with self.assertRaises(AccessPlanBlocked):plan_access(*data)

    def test_missing_repair_stock_cannot_authorize_breaking_shell(self):
        data=list(fixture());data[-1]['minecraft:white_concrete']=1
        with self.assertRaises(AccessPlanBlocked):plan_access(*data)
        data=list(fixture());data[-1]['minecraft:polished_andesite']=1
        with self.assertRaises(AccessPlanBlocked):plan_access(*data)

    def test_container_or_wet_shell_cells_are_not_selected(self):
        for field in ('block_entity','fluid'):
            data=list(fixture())
            for row in data[0]['blocks']:
                if row['pos'] in ([4,11,2],[4,12,2]):row[field]=True
            plan=plan_access(*data)
            self.assertTrue(all(r['pos'] not in ([4,11,2],[4,12,2]) for r in plan['portal']))

    def test_portal_with_gravity_block_above_is_excluded(self):
        data=list(fixture())
        for row in data[0]['blocks']+data[1]:
            if row['pos']==[4,13,2]:row['state']='Block{minecraft:sand}'
        plan=plan_access(*data)
        self.assertTrue(all(r['pos'] not in ([4,11,2],[4,12,2]) for r in plan['portal']))

    def test_mismatched_expected_shell_cannot_be_temporarily_destroyed(self):
        data=list(fixture())
        for row in data[1]:
            if row['state']==WHITE:row['state']='Block{minecraft:gray_concrete}'
        with self.assertRaises(AccessPlanBlocked):plan_access(*data)

    def test_only_low_opening_would_trap_actor_and_is_rejected(self):
        data=list(fixture())
        for row in data[0]['blocks']:
            if row['state']==WHITE and row['pos'][1]>=11:row['block_entity']=True
        with self.assertRaises(AccessPlanBlocked):plan_access(*data)

    def test_unscanned_initial_approach_is_explicit_never_invented(self):
        data=list(fixture());data[0]['player']=[9.5,13.02,2.5]
        plan=plan_access(*data)
        self.assertTrue(plan['unscanned_approach_prefix'])
        self.assertEqual(plan['approach_anchor'],plan['approach_path'][0])
        self.assertNotEqual(data[0]['player'],plan['approach_path'][0])

    def test_planning_does_not_mutate_scan_model_or_pending(self):
        data=fixture();before=copy.deepcopy(data);plan_access(*data)
        self.assertEqual(before,data)

    def test_bounded_search_refuses_large_input(self):
        with self.assertRaisesRegex(AccessPlanBlocked,'bounded'):plan_access(*fixture(),max_cells=10)

    def test_unsupported_floating_layer_is_not_invented_as_buildable(self):
        data=list(fixture())
        data[0]['blocks']=[r for r in data[0]['blocks'] if not (r['pos'][1]==6 and r['state']==POLISHED)]
        data[1]=[r for r in data[1] if not (r['pos'][1]==6 and r['state']==POLISHED)]
        data[1].append({'pos':[2,6,2],'state':POLISHED})
        data[3]=[r for r in data[3] if r['pos'][1]!=6]+[{'pos':[2,6,2],'expected':POLISHED}]
        with self.assertRaisesRegex(AccessPlanBlocked,'unsupported'):plan_access(*data)


class TraversableTest(unittest.TestCase):
    def test_empty_collision_does_not_make_hazards_or_unknowns_safe(self):
        from material_jobs.construction_access_plan import traversable
        for name in ('fire','soul_fire','wither_rose','cobweb','nether_portal','unknown'):
            with self.subTest(name=name):
                self.assertFalse(traversable({'state':'Block{minecraft:'+name+'}',
                    'passable':True,'fluid':False,'block_entity':False}))
        self.assertTrue(traversable({'state':'Block{minecraft:torch}',
                    'passable':True,'fluid':False,'block_entity':False}))


if __name__=='__main__':unittest.main()
