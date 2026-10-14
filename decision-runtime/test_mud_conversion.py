import unittest
from material_jobs.mud_conversion import column,side_stations,pre_use_rejected,refill_column

def row(pos,name,solid=False,**kw):
    return {'pos':pos,'state':'Block{minecraft:'+name+'}',
            'solid':solid,'fluid':False,'block_entity':False,**kw}

class MudConversionTest(unittest.TestCase):
    def test_refill_only_accepts_air_or_existing_mud_clay_above_real_dry_tip(self):
        tip=row([1,69,3],'pointed_dripstone');tip['state']+='[thickness=tip,vertical_direction=down,waterlogged=false]'
        rows=self.base()[1:]+[tip]
        self.assertFalse(refill_column(rows,[1,71,3])['filled'])
        for name in ('mud','clay'):
            self.assertTrue(refill_column(rows+[row([1,71,3],name)],[1,71,3])['filled'])
        self.assertIsNone(refill_column(rows+[row([1,71,3],'stone',True)],[1,71,3]))
        self.assertIsNone(refill_column(rows[:1],[1,71,3]))
        bad=row([1,69,3],'sulfur_spike');bad['state']+='[thickness=tip,vertical_direction=down,waterlogged=false]'
        self.assertIsNone(refill_column(rows[:1]+[bad],[1,71,3]))
    def test_only_exact_pre_use_rejection_allows_another_side_pose(self):
        self.assertTrue(pre_use_rejected({'phase':'error','detail':'Target interaction face is occluded or out of reach'}))
        for phase,detail in [('done','server state available'),('waiting','unconfirmed'),
                ('error','Interaction became occluded while rotating')]:
            self.assertFalse(pre_use_rejected({'phase':phase,'detail':detail}))
    def base(self):return [row([1,71,3],'mud'),row([1,70,3],'dark_oak_planks',True)]
    def test_missing_full_support_and_occupied_tip_refused(self):
        self.assertFalse(column(self.base(),[1,71,3])['ready'])
        self.assertIsNone(column(self.base()[:1],[1,71,3]))
        self.assertIsNone(column(self.base()+[row([1,69,3],'sulfur_spike')],[1,71,3]))
        self.assertIsNone(column(self.base()+[row([1,69,3],'stone',True)],[1,71,3]))
    def test_only_actual_dry_downward_dripstone_ready(self):
        for name,props,expected in [
            ('pointed_dripstone','[thickness=tip,vertical_direction=down,waterlogged=false]',True),
            ('sulfur_spike','[thickness=tip,vertical_direction=down,waterlogged=false]',False),
            ('pointed_dripstone','[thickness=tip,vertical_direction=up,waterlogged=false]',False),
            ('pointed_dripstone','[thickness=tip,vertical_direction=down,waterlogged=true]',False),
            ('pointed_dripstone','[thickness=frustum,vertical_direction=down,waterlogged=false]',False)]:
            tip=row([1,69,3],name);tip['state']+=props
            result=column(self.base()+[tip],[1,71,3]);self.assertEqual(bool(result and result['ready']),expected)
    def test_clay_is_output_not_pending_mud(self):
        rows=self.base();rows[0]=row([1,71,3],'clay',True)
        self.assertIsNone(column(rows,[1,71,3]))
        tip=row([1,69,3],'pointed_dripstone');tip['state']+='[thickness=tip,vertical_direction=down,waterlogged=false]'
        self.assertTrue(column(rows+[tip],[1,71,3],top_id='minecraft:clay')['ready'])
        self.assertIsNone(column(rows+[tip],[1,71,3],top_id='minecraft:stone'))
    def test_placement_station_never_occupies_new_spike_or_neighbor_spike(self):
        rows=self.base()+[row([0,69,3],'pointed_dripstone')]
        points=side_stations(rows,[1,71,3])
        self.assertNotIn([1.5,68.2,3.5],points)
        self.assertNotIn([.5,68.2,3.5],points)
        self.assertIn([2.5,68.2,3.5],points)

if __name__=='__main__':unittest.main()
