import unittest,copy,tempfile
from pathlib import Path
from unittest.mock import patch
from material_jobs.mud_conversion import column,side_stations,pre_use_rejected,refill_column

def row(pos,name,solid=False,**kw):
    return {'pos':pos,'state':'Block{minecraft:'+name+'}',
            'solid':solid,'fluid':False,'block_entity':False,**kw}

class MudConversionTest(unittest.TestCase):
    def test_client_inventory_gain_cannot_replace_original_server_sequence_ack(self):
        from test_dry_clay_columns import Fake,block
        from material_jobs import mud_conversion as module
        with tempfile.TemporaryDirectory()as directory:
            c=Fake(Path(directory));c.blocks={tuple(r['pos']):r for r in self.base()}
            c.blocks[(1,71,3)]=block([1,71,3],'clay')
            tip=row([1,69,3],'pointed_dripstone');tip['state']+='[thickness=tip,vertical_direction=down,waterlogged=false]'
            c.blocks[(1,69,3)]=tip;c.pos=[1.5,72.2,3.5];original=c.request
            def request(op,**kw):
                reply=original(op,**kw)
                if op=='mine_block':reply.update(op=op,mining_target=kw['pos'],server_ack_sequence=1)
                return reply
            c.request=request;out=Path(directory)/'harvest'
            with patch('work_access.approach_faces',return_value='up'):
                with self.assertRaisesRegex(RuntimeError,'acknowledgement'):module.harvest(c,[1,71,3],out,lambda:None)
                with self.assertRaisesRegex(RuntimeError,'retained'):module.harvest(c,[1,71,3],out,lambda:None)
            self.assertEqual(1,sum(op=='mine_block'for op,_ in c.calls))
            import json
            self.assertTrue(json.loads((out/'clay-harvest.json').read_text())['pending'])

    def test_late_item_entity_is_observed_after_one_mining_dispatch(self):
        from test_dry_clay_columns import Fake,block
        from material_jobs import mud_conversion as module
        with tempfile.TemporaryDirectory()as directory:
            c=Fake(Path(directory));c.blocks={tuple(r['pos']):r for r in self.base()}
            c.blocks[(1,71,3)]=block([1,71,3],'clay')
            tip=row([1,69,3],'pointed_dripstone');tip['state']+='[thickness=tip,vertical_direction=down,waterlogged=false]'
            c.blocks[(1,69,3)]=tip;c.pos=[1.5,72.2,3.5]
            original=c.request;mine_calls=[];reads=[0]
            def request(op,**kw):
                if op!='mine_block':return original(op,**kw)
                mine_calls.append(kw);c.blocks.pop(tuple(kw['pos']));c.last='actual-mine'
                return {'id':c.last,'op':'mine_block','phase':'done','world_session':c.world,
                        'mining_target':kw['pos'],'server_confirmed':True,'native_sequence':2,'server_ack_sequence':2,
                        'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack'}
            c.request=request;status=c.status
            def delayed():
                s=status()
                if mine_calls:
                    reads[0]+=1
                    if reads[0]>=4:s['entities']=[{'type':'minecraft:item','uuid':'late-four-balls','pos':[1.5,71.1,3.5],
                                                 'stack':{'item':'minecraft:clay_ball','count':4}}]
                return s
            c.status=delayed
            def pickup(client,drop,*a,**kw):
                self.assertEqual('late-four-balls',drop['uuid']);client.counts['minecraft:clay_ball']+=4;return True
            with (patch('work_access.approach_faces',return_value='up'),patch('drop_collection.collect_drop',side_effect=pickup)as picked,
                  patch.object(module.time,'sleep')):
                result=module.harvest(c,[1,71,3],Path(directory)/'harvest',lambda:None)
            self.assertEqual(1,len(mine_calls));picked.assert_called_once();self.assertEqual(4,result['actual_clay_balls_gained'])
            self.assertEqual(2,result['mining_receipt']['server_ack_sequence'])
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
    def test_dense_bed_has_a_proved_lower_pose_entirely_below_new_spike(self):
        points=side_stations(self.base(),[1,71,3]);below=[1.5,66.2,3.5]
        self.assertIn(below,points);self.assertLess(below[1]+1.8,69)
        for height in(66,67,68):
            self.assertNotIn(below,side_stations(self.base()+[row([1,height,3],'stone')],[1,71,3]))

if __name__=='__main__':unittest.main()
