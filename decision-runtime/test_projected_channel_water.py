import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from projected_channel_water import flow_frame,source_receipt,place

SOURCE=[20,63,30]


def frame():
    return dict(world_session='w',phase='done',scan_cells_read=8,scan_total_cells=8,scan_coherent=True,
                scan_ended_at=10,blocks=[dict(pos=[20-i,63,30],state=f'Block{{minecraft:water}}[level={i}]')for i in range(8)])


def receipt():
    return dict(id='bucket-once',world_session='w',phase='done',bucket_water=dict(request_id='bucket-once',
        world_session='w',pos=SOURCE,projected_water_channel=True,confirmed=True,unknown_outcome=False,
        use_count=1,server_block_confirmed=True,server_inventory_confirmed=True,
        server_observed_state='Block{minecraft:water}[level=0]',channel_direction='west',channel_length=8))


class Client:
    world='w'
    last=None
    def __init__(self):
        self.calls=[];self.bad_flow=False;self.unknown=False;self.tick=10
        self.state=dict(projected_water_channel_protocol=1,world_session='w',health=20,
            projection_selection=dict(key='key'),hand=dict(item='minecraft:water_bucket',count=1),
            inventory=[dict(slot=i,item='minecraft:water_bucket'if i==0 else'minecraft:air',count=1 if i==0 else 0)for i in range(36)])
    def status(self):return copy.deepcopy(self.state)
    def checked(self,op,**kwargs):return self.request(op,**kwargs)
    def request(self,op,**kwargs):
        self.calls.append((op,kwargs))
        if op=='bucket_place':
            self.last='bucket-once'
            if self.unknown:return dict(id=self.last,phase='waiting')
            self.state['inventory'][0].update(item='minecraft:bucket')
            return receipt()
        if op=='scan':
            f=frame();self.tick+=1;f['scan_ended_at']=self.tick
            if self.bad_flow:f['blocks'].pop()
            return f
        return dict(phase='done')


class ProjectedChannelWaterTests(unittest.TestCase):
    def test_source_receipt_alone_is_not_downstream_completion(self):
        self.assertTrue(source_receipt(receipt(),'bucket-once','w',SOURCE))
        self.assertFalse(flow_frame(receipt(),SOURCE,'w'))
    def test_complete_exact_stream_requires_coherent_current_world(self):
        self.assertTrue(flow_frame(frame(),SOURCE,'w'))
        for k,v in [('scan_coherent',False),('world_session','old'),('scan_cells_read',7),('phase','running')]:
            f=frame();f[k]=v
            with self.subTest(field=k):self.assertFalse(flow_frame(f,SOURCE,'w'))
    def test_wrong_water_level_and_duplicate_or_missing_cells_are_rejected(self):
        for mode in ['source','duplicate','missing','wrong-axis']:
            f=frame()
            if mode=='source':f['blocks'][4]['state']='Block{minecraft:water}[level=0]'
            elif mode=='duplicate':f['blocks'][4]=copy.deepcopy(f['blocks'][3])
            elif mode=='missing':f['blocks'].pop()
            else:f['blocks'][4]['pos'][2]+=1
            with self.subTest(mode=mode):self.assertFalse(flow_frame(f,SOURCE,'w'))
    def test_uncertain_or_partial_bucket_receipts_are_never_accepted(self):
        for k,v in [('unknown_outcome',True),('use_count',2),('server_inventory_confirmed',False),('projected_water_channel',False)]:
            r=receipt();r['bucket_water'][k]=v
            with self.subTest(field=k):self.assertFalse(source_receipt(r,'bucket-once','w',SOURCE))
    def test_one_use_followed_by_two_separate_complete_flow_frames(self):
        c=Client()
        with tempfile.TemporaryDirectory()as d,patch('projected_channel_water.time.sleep'):
            result=place(c,SOURCE,'key',Path(d)/'run')
        self.assertTrue(result['source_confirmed']);self.assertTrue(result['flow_confirmed'])
        self.assertLess(*result['flow_observations'])
        self.assertEqual(1,sum(op=='bucket_place'for op,_ in c.calls))
    def test_unknown_use_is_not_repeated_or_credited(self):
        c=Client();c.unknown=True
        with tempfile.TemporaryDirectory()as d,self.assertRaisesRegex(RuntimeError,'never repeat'):
            place(c,SOURCE,'key',Path(d)/'run')
        self.assertEqual(1,sum(op=='bucket_place'for op,_ in c.calls))
        self.assertEqual(0,sum(op=='scan'for op,_ in c.calls))
    def test_incomplete_flow_keeps_confirmed_source_and_never_uses_bucket_again(self):
        c=Client();c.bad_flow=True
        with tempfile.TemporaryDirectory()as d,patch('projected_channel_water.time.monotonic',side_effect=[0,11]),\
             self.assertRaisesRegex(RuntimeError,'downstream incomplete'):
            place(c,SOURCE,'key',Path(d)/'run')
        self.assertEqual(1,sum(op=='bucket_place'for op,_ in c.calls))
    def test_native_recovery_time_does_not_expire_the_downstream_observation(self):
        c=Client();c.native_recovery_pause_seconds=0;original=c.status
        def status():
            if any(op=='scan'for op,_ in c.calls):c.native_recovery_pause_seconds=20
            return original()
        c.status=status
        with tempfile.TemporaryDirectory()as d,patch('projected_channel_water.time.sleep'),\
             patch('projected_channel_water.time.monotonic',side_effect=[0,21,21.1]):
            self.assertTrue(place(c,SOURCE,'key',Path(d)/'run')['complete'])
        self.assertEqual(1,sum(op=='bucket_place'for op,_ in c.calls))


if __name__=='__main__':unittest.main()
