import copy
import unittest
from unittest.mock import Mock,patch

from material_jobs_backend import Backend
from material_jobs.protocol import JobBlocked

START=[761014.5006,64,797843.3066]
TARGET=[761014.5,65,797841.5]


def floor(pos):
    return {'pos':list(pos),'state':'Block{minecraft:stone}','solid':True,
            'fluid':False,'block_entity':False,'passable':False}


class EntryClient:
    world='near-entry-world'
    def __init__(self):
        self.pos=START[:];self.calls=[];self.phase=None;self.scan_world=self.world
        self.bad_arrival=False;self.walk_phase='done'
        self.rows={(761014,63,z):floor((761014,63,z)) for z in range(797839,797846)}
        for z in (797841,797842):self.rows[(761014,64,z)]=floor((761014,64,z))
    def status(self):return {'pos':self.pos[:],'flight':False,'on_ground':True}
    def request(self,op,**params):
        self.calls.append((op,copy.deepcopy(params)))
        if op!='scan':raise AssertionError('Only scan may be requested directly')
        return {'world_session':self.scan_world,'phase':self.phase,
                'blocks':[copy.deepcopy(r) for p,r in self.rows.items()
                          if all(params['min'][i]<=p[i]<=params['max'][i] for i in range(3))]}
    def checked(self,op,**params):
        self.calls.append((op,copy.deepcopy(params)))
        if op!='walk':raise AssertionError('Near entry must use ordinary walking')
        if self.walk_phase!='done':raise RuntimeError('Uncertain native walk result')
        self.pos=params['target'][:]
        if self.bad_arrival:self.pos[1]-=.6
        return {'phase':'done'}


class NearWorkbenchEntryTest(unittest.TestCase):
    def job(self,client):
        job=Backend.__new__(Backend);job.ensure_client=lambda:client;job.checkpoint=Mock()
        return job

    def test_actual_2_066m_one_block_doorstep_scans_then_walks_without_air_detour(self):
        client=EntryClient();job=self.job(client)
        with patch('material_jobs.acquisition._travel') as air:
            job.approach_route_entry(TARGET)
        air.assert_not_called()
        self.assertEqual(['scan','walk'],[op for op,_ in client.calls])
        self.assertEqual(63,client.calls[0][1]['min'][1])
        self.assertEqual(67,client.calls[0][1]['max'][1])
        self.assertEqual({'target':TARGET,'arrival':.3,'restore_flight':False,'seconds':12},client.calls[1][1])
        self.assertEqual(TARGET,client.pos)

    def test_missing_wet_nonfull_support_or_headroom_never_walks_or_flies(self):
        changes=[lambda c:c.rows.pop((761014,63,797843)),
                 lambda c:c.rows[(761014,63,797843)].update(fluid=True),
                 lambda c:c.rows[(761014,63,797843)].update(solid=False),
                 lambda c:c.rows.__setitem__((761014,65,797842),floor((761014,65,797842))),
                 lambda c:c.rows.__setitem__((761014,67,797842),floor((761014,67,797842)))]
        for change in changes:
            client=EntryClient();change(client)
            with patch('material_jobs.acquisition._travel') as air:
                with self.assertRaises(JobBlocked):self.job(client).approach_route_entry(TARGET)
            air.assert_not_called();self.assertEqual(['scan'],[op for op,_ in client.calls])

    def test_middle_cell_drop_or_two_high_step_cannot_hide_behind_valid_endpoints(self):
        for change in (lambda c:[c.rows.pop((761014,64,797842)),c.rows.pop((761014,63,797842))],
                       lambda c:c.rows.__setitem__((761014,65,797842),floor((761014,65,797842)))):
            client=EntryClient();change(client)
            with self.assertRaises(JobBlocked):self.job(client).approach_route_entry(TARGET)
            self.assertEqual(['scan'],[op for op,_ in client.calls])

    def test_error_or_foreign_scan_cannot_authorize_empty_space(self):
        for phase,world in (('error',EntryClient.world),(None,'foreign')):
            client=EntryClient();client.phase=phase;client.scan_world=world
            with self.assertRaises(JobBlocked):self.job(client).approach_route_entry(TARGET)
            self.assertEqual(['scan'],[op for op,_ in client.calls])

    def test_real_arrival_and_unknown_walk_are_never_replayed(self):
        client=EntryClient();client.bad_arrival=True
        with self.assertRaisesRegex(JobBlocked,'实际到点'):self.job(client).approach_route_entry(TARGET)
        self.assertEqual(['scan','walk'],[op for op,_ in client.calls])
        client=EntryClient();client.walk_phase='waiting'
        with self.assertRaisesRegex(RuntimeError,'Uncertain'):self.job(client).approach_route_entry(TARGET)
        self.assertEqual(['scan','walk'],[op for op,_ in client.calls])

    def test_position_change_after_fresh_geometry_stops_before_walk(self):
        client=EntryClient();job=self.job(client)
        def checkpoint():
            if client.calls:client.pos[0]+=.2
        job.checkpoint=checkpoint
        with self.assertRaisesRegex(JobBlocked,'实际位置已改变'):job.approach_route_entry(TARGET)
        self.assertEqual(['scan'],[op for op,_ in client.calls])


if __name__=='__main__':unittest.main()
