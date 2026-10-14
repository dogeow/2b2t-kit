import unittest,tempfile
from types import SimpleNamespace
from unittest.mock import patch
from material_jobs.dry_hover_harvest import offers,pickup_offers,run

def row(pos,name,**kw):return {'pos':pos,'state':'Block{minecraft:'+name+'}','fluid':False,'block_entity':False,'solid':True,**kw}
class DryHoverHarvestTest(unittest.TestCase):
    def test_target_removed_before_mining_rescans_without_dispatch_or_ascent(self):
        state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
               'pos':[1.5,4.2,.5],'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
        state['inventory'][0].update(item='minecraft:dripstone_block',count=3)
        c=SimpleNamespace(world='w',status=lambda:state,last='fresh-scan')
        region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,7,3]}
        choice={'target':[0,4,0],'state':'Block{minecraft:dripstone_block}','station':[1.5,4.2,.5],'face':'east'}
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',side_effect=[[row([0,4,0],'dripstone_block')],[]]),patch('material_jobs.dry_hover_harvest.offers',return_value=[choice]),patch('material_jobs.dry_hover_harvest._protected',return_value=False),patch('material_jobs.dry_hover_harvest.move')as move:
            result=run(c,{},region,64,d,lambda:None,max_blocks=1)
        self.assertEqual(3,result['verified_count']);self.assertEqual([],result['receipts'])
        self.assertIsNone(result['pending']);self.assertEqual('current_target_already_air',result['skipped_before_mining'][0]['reason'])
        self.assertEqual([1.5,4.2,.5],move.call_args.args[1]);self.assertEqual(1,move.call_count)
    def test_floor_target_uses_adjacent_air_above_it_not_its_own_footing(self):
        rows=[row([x,4,z],'dripstone_block')for x in range(-2,3)for z in range(-2,3)]
        result=offers(rows,[-3,1,-3],[3,8,3],[1.5,5.2,.5])
        target=[r for r in result if r['target']==[0,4,0]]
        self.assertTrue(target);self.assertTrue(all(r['station'][1]==5.2 for r in target))
        self.assertFalse(any(r['station'][0]==.5 and r['station'][2]==.5 for r in target))
    def test_already_carried_goal_returns_without_new_mining_or_drop_observation(self):
        state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
               'inventory':[{'slot':0,'item':'minecraft:dripstone_block','count':1}]}
        c=SimpleNamespace(world='w',status=lambda:state)
        region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,7,3]}
        with tempfile.TemporaryDirectory()as d:
            result=run(c,{},region,1,d,lambda:None)
        self.assertTrue(result['full_target_reached']);self.assertEqual([],result['receipts'])
    def test_pickup_tracks_actual_item_height_instead_of_old_mining_plane(self):
        points=pickup_offers([],[-3,1,-3],[3,8,3],[1.5,6.2,.5],[.45,3.125,.45])
        self.assertTrue(points);self.assertEqual([.5,3.2,.5],points[0])
    def test_pickup_does_not_enter_blocked_item_cell_or_one_high_gap(self):
        points=pickup_offers([row([0,4,0],'stone')],[-3,1,-3],[3,8,3],[1.5,5.2,.5],[.5,3.125,.5])
        self.assertNotIn([.5,3.2,.5],points)
    def test_existing_torch_and_its_natural_support_remain(self):
        rows=[row([0,4,0],'dripstone_block'),row([0,5,0],'torch',solid=False,passable=True)]
        self.assertEqual([],offers(rows,[-3,1,-3],[3,7,3],[1.5,4.2,.5]))
    def test_actual_air_route_can_hover_without_inventing_a_floor(self):
        got=offers([row([0,4,0],'dripstone_block')],[-3,1,-3],[3,7,3],[1.5,4.2,.5])
        self.assertTrue(got);self.assertEqual([0,4,0],got[0]['target'])
    def test_liquid_cones_structures_or_uncovered_target_prevent_harvest(self):
        base=[row([0,4,0],'dripstone_block')]
        for extra in(row([0,5,1],'pointed_dripstone'),row([1,5,1],'water',fluid=True),row([1,4,1],'chest',block_entity=True)):
            self.assertEqual([],offers(base+[extra],[-3,1,-3],[3,7,3],[1.5,4.2,.5]))
        self.assertEqual([],offers(base,[-1,1,-1],[1,7,1],[1.5,4.2,.5]))
    def test_air_pocket_must_connect_to_the_current_player(self):
        rows=[row([0,4,0],'dripstone_block')]+[row([1,y,z],'stone')for y in range(1,8)for z in range(-3,4)]
        self.assertEqual([],offers(rows,[-3,1,-3],[4,7,3],[3.5,4.2,.5]))
if __name__=='__main__':unittest.main()
