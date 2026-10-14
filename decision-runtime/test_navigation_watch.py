import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from material_client import Client
from material_jobs.navigation_watch import FlightWatch, NavigationStalled, pause_stalled


class NavigationWatchTest(unittest.TestCase):
    def setUp(self):
        self.client = SimpleNamespace(world='world', rev=3, last='materials-flight', task='task',
                                      heartbeat=SimpleNamespace(id='lease'))
        self.envelope = dict(request_id='materials-flight', op='navigate', world_session='world',
                             task_session='task', lease_id='lease', base_revision=3,
                             request_revision=3, expected_revision=4, server='example.test',
                             dimension='minecraft:overworld')
        self.state = dict(connected=True, manual_movement=False, screen='', guard_busy=False,
                          under_water=False, flight=True, health=20, phase='running', op='navigate',
                          navigating=True, id='materials-flight', last_request='materials-flight',
                          world_session='world', control_revision=4, server='example.test:25565',
                          dimension='minecraft:overworld', pos=[100.5,220,799999.5], time=100,
                          supervision_lease=dict(kind='materials', id='lease', job_session='task',
                                                 world_session='world', revision=4))

    def test_border_collision_stops_after_ten_seconds_of_fresh_stillness(self):
        watch=FlightWatch()
        self.assertFalse(watch.poll(self.client,self.state,self.envelope,0))
        self.assertFalse(watch.poll(self.client,{**self.state,'time':101},self.envelope,9.9))
        self.assertTrue(watch.poll(self.client,{**self.state,'time':102},self.envelope,10))
        self.assertFalse(watch.poll(self.client,self.state,self.envelope,11), 'stale samples are not evidence')

    def test_real_movement_and_guard_or_ui_pauses_reset_timer(self):
        for change in ({'pos':[100.5,220,799998.5]}, {'guard_busy':True}, {'screen':'InventoryScreen'},
                       {'interface_paused':True}):
            watch=FlightWatch();watch.poll(self.client,self.state,self.envelope,0)
            self.assertFalse(watch.poll(self.client,{**self.state,**change,'time':101},self.envelope,10))
            self.assertFalse(watch.poll(self.client,{**self.state,'time':102},self.envelope,11))

    def test_foreign_revision_manual_emergency_or_terminal_never_cancel(self):
        for change in ({'manual_movement':True},{'world_session':'new'}, {'control_revision':5},
                       {'last_request':'other'}, {'phase':'done'}, {'health':18}, {'flight':False},
                       {'control_stop':{'kind':'manual','revision':4}},
                       {'supervision_lease':{**self.state['supervision_lease'],'id':'foreign'}}):
            watch=FlightWatch();watch.poll(self.client,self.state,self.envelope,0)
            self.assertFalse(watch.poll(self.client,{**self.state,**change,'time':101},self.envelope,11))

    def test_recheck_manual_takeover_never_publishes_pause(self):
        self.client.raw=lambda:{**self.state,'manual_movement':True}
        with patch.object(Client,'request') as send:
            self.assertFalse(pause_stalled(self.client,self.envelope))
        send.assert_not_called()

    def test_exact_pause_retains_original_without_arrival_credit_or_replay(self):
        with tempfile.TemporaryDirectory() as t:
            c=self.client;c.out=c.root=Path(t);c.raw=lambda:deepcopy(self.state)
            (c.root/'request.json').write_text(json.dumps({'id':c.last,'op':'navigate'}))
            def send(client, op, **params):
                self.assertIs(c,client);self.assertEqual('material_job_pause',op)
                self.assertEqual('task',params['task_session']);self.assertFalse(params['release'])
                c.last='pause';c.rev=5
                return {'id':'pause','phase':'done'}
            c.status=lambda **kw:{**self.state,'control_revision':5,'navigating':False,
                'movement_keys':{'forward':False,'back':False,'jump':False,'sneak':False},
                'supervision_lease':{**self.state['supervision_lease'],'revision':5}}
            with patch.object(Client,'request',side_effect=send) as dispatch:
                with self.assertRaises(NavigationStalled):pause_stalled(c,self.envelope)
            dispatch.assert_called_once()
            report=json.loads((c.out/'stalled-flight-materials-flight.json').read_text())
            self.assertFalse(report['pause_pending']);self.assertFalse(report['arrival_credit'])
            self.assertFalse(report['original_request_replayed'])
            self.assertEqual('materials-flight',report['original_request']['request_id'])

    def test_unknown_pause_preserves_pending_and_is_never_retried(self):
        with tempfile.TemporaryDirectory() as t:
            c=self.client;c.out=c.root=Path(t);c.raw=lambda:deepcopy(self.state)
            with patch.object(Client,'request',side_effect=RuntimeError('unknown')) as send:
                with self.assertRaisesRegex(RuntimeError,'unknown'):pause_stalled(c,self.envelope)
            send.assert_called_once()
            self.assertTrue(json.loads((c.out/'stalled-flight-materials-flight.json').read_text())['pause_pending'])


if __name__=='__main__':unittest.main()
