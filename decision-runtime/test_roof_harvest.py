import unittest
from material_jobs.roof_harvest import bounds,completed_mine,offers,dry_roof_context,retained_light,light_supports,valid_entry
from material_jobs.protocol import JobBlocked
from material_jobs.local_air_path import plan


def block(pos,name='stone',**kw):
    return {'pos':pos,'state':'Block{minecraft:'+name+'}','solid':True,
            'fluid':False,'block_entity':False,'passable':False,**kw}


class RoofHarvestTests(unittest.TestCase):
    def test_scope_needs_authorized_natural_two_layer_region(self):
        good={'source':'natural_survey','authorized':True,'min':[1,62,1],'max':[6,63,6]}
        self.assertEqual(([1,62,1],[6,63,6]),bounds(good))
        for change in ({'authorized':False},{'source':'seed_hint'},{'max':[17,63,6]},
                       {'max':[6,64,6]},{'min':[True,62,1]}):
            with self.assertRaises(JobBlocked):bounds({**good,**change})

    def test_mining_proof_retains_original_id_after_followup_scan(self):
        reply={'id':'mine-1','world_session':'world-1','phase':'done'}
        self.assertTrue(completed_mine(reply,'mine-1','world-1',[]))
        self.assertFalse(completed_mine(reply,'scan-2','world-1',[]))
        self.assertFalse(completed_mine(reply,'mine-1','world-2',[]))
        self.assertFalse(completed_mine(reply,'mine-1','world-1',[block([1,62,1])]))
        for phase in (None,'waiting','error'):
            self.assertFalse(completed_mine({**reply,'phase':phase},'mine-1','world-1',[]))

    def rows(self):
        return [block([1,61,1]),block([0,61,1]),block([1,62,1],'dripstone_block'),block([1,63,1])]

    def test_supported_adjacent_air_station_is_required(self):
        args=([1,62,1],[1,63,1],[.5,62,1.5])
        self.assertEqual(1,len(offers(self.rows(),*args)))
        self.assertEqual([],offers(self.rows()[1:],*args))
        self.assertEqual([],offers(self.rows()+[block([0,63,1])],*args))

    def test_pointed_dripstone_water_container_and_falling_are_not_relaxed(self):
        for danger in (block([2,60,1],'pointed_dripstone'),block([2,62,1],'water',fluid=True),
                       block([2,62,1],'chest',block_entity=True),block([2,64,1],'gravel')):
            self.assertEqual([],offers(self.rows()+[danger],[1,62,1],[1,63,1],[.5,62,1.5]))

    def test_unsafe_drip_target_does_not_drive_extra_corridor_excavation(self):
        rows=self.rows()+[block([2,60,1],'pointed_dripstone'),block([3,61,1]),
            block([3,62,1]),block([3,63,1]),block([4,61,1])]
        self.assertEqual([],offers(rows,[1,62,1],[3,63,1],[4.5,62,1.5]))

    def test_offer_outside_local_air_move_radius_is_rejected(self):
        self.assertEqual([],offers(self.rows(),[1,62,1],[1,63,1],[20.5,62,1.5]))

    def test_nearby_isolated_air_pocket_is_not_an_approach(self):
        rows=self.rows()+[block([x,y,z])for x in range(2,5)for y in range(60,66)
            for z in range(-1,4)]
        self.assertEqual([],offers(rows,[1,62,1],[1,63,1],[4.5,62,1.5]))

    def test_observed_upper_air_can_connect_a_station(self):
        rows=self.rows()+[block([x,y,z])for x in range(2,5)for y in range(60,64)
            for z in range(-1,4)]
        # The wall is open at foot y64/head y65, so the station is reachable.
        self.assertEqual(1,len(offers(rows,[1,62,1],[3,63,1],[4.5,64,1.5])))

    def separated(self):
        return [block([x,60,z])for x in range(-2,3)for z in range(-2,3)]+[
            block([0,61,0],'dripstone_block'),block([0,59,0],'pointed_dripstone',solid=False)]

    def test_pointed_beneath_complete_unchanged_full_floor_is_separated(self):
        self.assertTrue(dry_roof_context(self.separated(),[0,61,0],61))

    def test_floor_hole_partial_floor_fluid_and_container_cannot_separate_hazards(self):
        rows=self.separated()
        self.assertFalse(dry_roof_context(rows[1:],[0,61,0],61))
        for changed in (block([-2,60,-2],'stone_slab'),block([-2,60,-2],solid=False),
                        block([-2,60,-2],fluid=True),block([-2,60,-2],block_entity=True)):
            self.assertFalse(dry_roof_context([changed]+rows[1:],[0,61,0],61))

    def test_pointed_in_body_or_floor_and_other_hazards_remain_refused(self):
        rows=self.separated()
        for danger in (block([1,60,0],'pointed_dripstone',solid=False),
                       block([1,61,0],'pointed_dripstone',solid=False),
                       block([1,59,0],'water',fluid=True),block([1,62,0],'gravel')):
            self.assertFalse(dry_roof_context(rows+[danger],[0,61,0],61))

    def test_safe_retained_torch_is_not_mined_or_treated_as_a_wall(self):
        torch=block([0,62,1],'torch',solid=False,passable=True)
        self.assertTrue(retained_light(torch))
        rows=self.rows()+[torch]
        self.assertTrue(dry_roof_context(rows,[1,62,1],62))
        self.assertEqual(1,len(offers(rows,[1,62,1],[1,63,1],[.5,62,1.5])))

    def test_torch_name_does_not_override_collision_or_fluid_metadata(self):
        for changed in (block([0,62,1],'torch'),
                        block([0,62,1],'torch',solid=False,passable=True,fluid=True),
                        block([0,62,1],'torch',solid=False,passable=True,block_entity=True)):
            self.assertFalse(retained_light(changed))
            self.assertFalse(dry_roof_context(self.rows()+[changed],[1,62,1],62))

    def test_standing_torch_support_is_never_selected_for_mining(self):
        torch=block([1,63,1],'torch',solid=False,passable=True)
        self.assertEqual({(1,62,1)},light_supports([torch]))
        self.assertEqual([],offers(self.rows()+[torch],[1,62,1],[1,63,1],[.5,62,1.5]))

    def test_wall_torch_support_follows_observed_orientation(self):
        torch=block([2,62,1],'wall_torch',solid=False,passable=True)
        torch['state']='Block{minecraft:wall_torch}[facing=east]'
        self.assertEqual({(1,62,1)},light_supports([torch]))
        self.assertEqual([],offers(self.rows()+[torch],[1,62,1],[1,63,1],[.5,62,1.5]))

    def test_missing_wall_orientation_protects_all_possible_supports(self):
        torch=block([2,62,1],'wall_torch',solid=False,passable=True)
        self.assertEqual({(1,62,1),(3,62,1),(2,62,0),(2,62,2)},light_supports([torch]))

    def test_entry_requires_registered_lower_cell_and_existing_upper_station(self):
        low,high=[1,61,1],[6,62,6]
        self.assertTrue(valid_entry([1,61,1],low,high,[1.5,62,1.5]))
        for entry,position in (([0,61,1],[1.5,62,1.5]),([1,62,1],[1.5,62,1.5]),
                ([True,61,1],[1.5,62,1.5]),([1,61,1],[10.5,62,1.5]),
                ([1,61,1],[1.5,61,1.5]),([1,61,1],[1.5,146,1.5])):
            self.assertFalse(valid_entry(entry,low,high,position))

    def test_roof_moves_stay_inside_immediate_native_precision_radius(self):
        path=plan([], [0.556,62,0.5],[0.5,62,6.5],[-3,60,-3],[3,65,9],max_straight=2)
        self.assertEqual([[0.5,62,0.5],[0.5,62,2.5],[0.5,62,4.5],[0.5,62,6.5]],path)
        # The observed offset cannot turn a three-cell turn into 3.003 cells.
        self.assertLess(((path[1][0]-.556)**2+(path[1][2]-.5)**2)**.5,3)
        with self.assertRaises(JobBlocked):
            plan([], [0.5,62,0.5],[0.5,62,6.5],[-3,60,-3],[3,65,9],max_straight=0)


if __name__=='__main__':unittest.main()
