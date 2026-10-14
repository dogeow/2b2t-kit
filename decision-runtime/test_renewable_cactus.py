import unittest
from material_jobs.renewable_cactus import dye_budget,suitable,side_pose_clear,side_poses,harvestable_top,authorized_planting_cell,owned_farm_top,planting_transit_height

def row(pos,name):
    return {'pos':pos,'state':'Block{minecraft:'+name+'}','solid':True,'fluid':False,'block_entity':False}

class RenewableCactusTest(unittest.TestCase):
    def test_seed_reserve_is_never_counted_as_dye_stock(self):
        self.assertEqual(0,dye_budget(5));self.assertEqual(0,dye_budget(6));self.assertEqual(16,dye_budget(22))
        with self.assertRaises(ValueError):dye_budget(22,0)
    def test_only_dry_sand_with_empty_growth_and_side_space(self):
        p=[100,65,100];floor=row([100,64,100],'sand')
        self.assertTrue(suitable([floor],p))
        for blocker in ([100,65,100],[100,66,100],[100,67,100],[101,65,100]):
            self.assertFalse(suitable([floor,row(blocker,'stone')],p))
        floor['fluid']=True;self.assertFalse(suitable([floor],p))
    def test_existing_farms_and_unstable_support_are_not_overwritten(self):
        p=[100,65,100]
        self.assertFalse(suitable([row([100,64,100],'dirt')],p))
        floor=row([100,64,100],'sand');floor['block_entity']=True
        self.assertFalse(suitable([floor],p));self.assertFalse(suitable([],p))
    def test_collision_free_cactus_top_is_still_a_damage_hazard(self):
        cactus=row([100,64,100],'cactus');cactus.update(solid=False,passable=True)
        low,high=[97,62,97],[103,70,103]
        self.assertFalse(side_pose_clear([cactus],low,high,[100.5,64.95,100.5]))
        self.assertFalse(side_pose_clear([cactus],low,high,[100.5,65.15,100.5]))
    def test_side_pose_keeps_padded_body_out_of_cactus_cells(self):
        cactus=row([100,65,100],'cactus');cactus.update(solid=False,passable=False)
        low,high=[97,63,97],[103,71,103]
        poses=side_poses([cactus],low,high,[100,65,100])
        self.assertEqual(4,len(poses))
        self.assertTrue(all(side_pose_clear([cactus],low,high,p)for _,p in poses))
    def test_neighboring_cactus_or_water_cannot_be_used_as_side_access(self):
        low,high=[97,63,97],[103,71,103]
        cactus=row([100,65,100],'cactus');cactus.update(solid=False,passable=False)
        for name in ('cactus','water'):
            blocked=row([102,65,100],name);blocked.update(passable=True,solid=False,fluid=name=='water')
            poses=side_poses([cactus,blocked],low,high,[100,65,100])
            self.assertNotIn('east',[face for face,_ in poses])
    def test_unobserved_body_or_opaque_container_is_not_clearance(self):
        self.assertFalse(side_pose_clear([], [100,65,100],[100,66,100],[100.5,65.25,100.5]))
        chest=row([101,65,100],'chest');chest.update(passable=True,block_entity=True)
        self.assertFalse(side_pose_clear([chest],[97,63,97],[103,71,103],[101.8,65.25,100.5]))
    def test_flowering_top_can_be_harvested_without_cutting_the_base(self):
        p=[100,65,100];base=row([100,64,100],'cactus');top=row(p,'cactus')
        flower=row([100,66,100],'cactus_flower')
        self.assertTrue(harvestable_top([base,top,flower],p))
        self.assertFalse(harvestable_top([base,top,row([100,66,100],'cactus')],p))
        self.assertFalse(harvestable_top([row([100,64,100],'sand'),top,flower],p))
        flower['fluid']=True
        self.assertFalse(harvestable_top([base,top,flower],p))
    def test_approved_farm_cells_do_not_remove_general_base_protection(self):
        p=[100,65,100];state={'server':'test','dimension':'minecraft:overworld'}
        box={'min':[90,50,90],'max':[150,90,150],'note':'base_courtyard_villa_projection_no_survey'}
        profile={'protected_regions':[box],'resource_regions':[{'item':'minecraft:sand',
            'source':'previous_authorized_sand_site','original_authorized_bounds':{'min':[90,64,90],'max':[150,78,150]}}],
            'cactus_planting_plan':{'authorized':True,'source':'user_requested_renewable_farm',
            'world_session':'w','server':'test','dimension':'minecraft:overworld','positions':[p]}}
        self.assertTrue(authorized_planting_cell(profile,state,'w',p))
        self.assertEqual([box],profile['protected_regions'])
        self.assertFalse(authorized_planting_cell(profile,state,'other-world',p))
        self.assertFalse(authorized_planting_cell(profile,state,'w',[101,65,100]))
        profile['depots']=[[100,64,110]]
        self.assertFalse(authorized_planting_cell(profile,state,'w',p))
    def test_only_proved_owned_growth_can_be_harvested_inside_the_base(self):
        state={'server':'test','dimension':'minecraft:overworld'}
        profile={'renewable_cactus_farms':[{'server':'test','dimension':'minecraft:overworld',
            'complete':True,'planting_receipt':'actual-receipt','positions':[[100,65,100]]}]}
        self.assertTrue(owned_farm_top(profile,state,[100,66,100]))
        self.assertFalse(owned_farm_top(profile,state,[100,65,100]))
        self.assertFalse(owned_farm_top(profile,state,[101,66,100]))
        profile['renewable_cactus_farms'][0]['complete']=False
        self.assertFalse(owned_farm_top(profile,state,[100,66,100]))
    def test_planting_side_pose_remains_clear_after_the_cactus_is_placed(self):
        p=[100,65,100];floor=row([100,64,100],'sand')
        lo,hi=[97,63,97],[103,70,103]
        poses=side_poses([floor],lo,hi,p,foot_offset=.65)
        self.assertEqual(4,len(poses))
        cactus=row(p,'cactus');cactus.update(solid=False,passable=False)
        self.assertTrue(all(side_pose_clear([floor,cactus],lo,hi,point)for _,point in poses))
    def test_planting_transit_rises_before_crossing_a_cactus_row(self):
        self.assertEqual(85,planting_transit_height([100,65.5,100],65))
        self.assertEqual(111,planting_transit_height([100,110,100],65))

if __name__=='__main__':unittest.main()
