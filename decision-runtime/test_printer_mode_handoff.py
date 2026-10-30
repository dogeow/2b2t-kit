import unittest
import copy,json,tempfile
from pathlib import Path
from unittest.mock import patch
from printer_mode_handoff import PrinterModeHandoff
from kit_runtime.journal import write_json as real_write_json
from printer_mode_handoff import restoration_target,idle_for_mode


class PrinterModeHandoffTests(unittest.TestCase):
    def test_original_choice_is_restored_only_without_new_external_changes(self):
        self.assertTrue(restoration_target(True,3,dict(external_mode_revision=3)))
        self.assertFalse(restoration_target(False,3,dict(external_mode_revision=3)))
    def test_later_user_choices_beat_the_old_restore_target(self):
        self.assertFalse(restoration_target(True,3,dict(external_mode_revision=4,last_external_enabled=False)))
        self.assertTrue(restoration_target(False,3,dict(external_mode_revision=5,last_external_enabled=True)))
    def test_unknown_and_older_revisions_are_not_restore_authority(self):
        for p in [{},{'external_mode_revision':2},{'external_mode_revision':4},
                  {'external_mode_revision':4,'last_external_enabled':'false'}]:
            self.assertIsNone(restoration_target(True,3,p))
    def test_mode_change_cannot_preempt_an_owner_or_manual_input(self):
        state=dict(connected=True,health=20,projection_selection=dict(key='key'))
        self.assertTrue(idle_for_mode(state,'key'))
        for change in [dict(manual_movement=True),dict(screen='ContainerScreen'),dict(health=17),
                       dict(supervision_lease=dict(job_session='other')),dict(professional_printer=dict(owned=True)),
                       dict(build_job=dict(active=True)),dict(projection_batch=dict(active=True)),
                       dict(safety_hold=dict(active=True)),dict(navigating=True)]:
            self.assertFalse(idle_for_mode({**state,**change},'key'))

    def _mode_fixture(self,root,out):
        token=PrinterModeHandoff.__new__(PrinterModeHandoff)
        token.root=root;token.out=out;token.key='key';token.pending=False
        state=dict(time=100,world_session='world',control_revision=7,connected=True,health=20,
                   pos=[0,80,0],server='server',dimension='minecraft:overworld',
                   projection_selection=dict(key='key'),professional_printer=dict(enabled=True,external_mode_revision=3))
        requests=[]
        def write(path,value):
            real_write_json(path,value)
            if path==root/'request.json':
                requests.append(copy.deepcopy(value))
                reply={**state,'id':value['id'],'phase':'done','professional_printer':dict(enabled=False,external_mode_revision=3)}
                real_write_json(root/('reply-'+value['id']+'.json'),reply)
        return token,state,requests,write

    def test_next_owner_waits_for_acknowledged_mode_to_reach_status_without_resending(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);out=root/'proof';out.mkdir();token,state,requests,write=self._mode_fixture(root,out);seen=[]
            def fresh(*args,**kwargs):
                frame=copy.deepcopy(state)
                if seen:
                    frame['last_request']=requests[0]['id'];frame['professional_printer']['enabled']=False
                else:frame['last_request']='previous-owner'
                seen.append(frame);return frame
            with patch('printer_mode_handoff.write_json',side_effect=write),patch('printer_mode_handoff.read_fresh',side_effect=fresh),patch('printer_mode_handoff.time.sleep'):
                reply=token._set(state,False,'pause')
            self.assertEqual(2,len(seen));self.assertEqual(1,len(requests));self.assertFalse(token.pending)
            self.assertEqual(requests[0]['id'],reply['id']);self.assertTrue((out/'pause-status-synced.json').exists())

    def test_manual_takeover_world_or_user_mode_change_during_ack_observation_cannot_be_overridden(self):
        for changed in [dict(manual_movement=True),dict(world_session='new-world'),
                        dict(professional_printer=dict(enabled=True,external_mode_revision=4))]:
            with self.subTest(changed=changed),tempfile.TemporaryDirectory()as d:
                root=Path(d);out=root/'proof';out.mkdir();token,state,requests,write=self._mode_fixture(root,out)
                with patch('printer_mode_handoff.write_json',side_effect=write),patch('printer_mode_handoff.read_fresh',return_value={**state,**changed}):
                    with self.assertRaisesRegex(RuntimeError,'Control changed'):token._set(state,False,'pause')
                self.assertEqual(1,len(requests));self.assertFalse(token.pending)

    def test_status_timeout_keeps_known_reply_and_never_repeats_pause(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);out=root/'proof';out.mkdir();token,state,requests,write=self._mode_fixture(root,out)
            with patch('printer_mode_handoff.write_json',side_effect=write),patch('printer_mode_handoff.read_fresh',return_value={**state,'last_request':'older'}),patch('printer_mode_handoff.time.monotonic',side_effect=range(20)),patch('printer_mode_handoff.time.sleep'):
                with self.assertRaisesRegex(RuntimeError,'acknowledged but status'):token._set(state,False,'pause')
            self.assertEqual(1,len(requests));self.assertFalse(token.pending);self.assertTrue((out/'pause-reply.json').exists())

    def test_missing_native_reply_retains_unknown_identity_without_polling_status_or_resending(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);out=root/'proof';out.mkdir();token,state,requests,unused=self._mode_fixture(root,out)
            def write(path,value):
                real_write_json(path,value)
                if path==root/'request.json':requests.append(value)
            with patch('printer_mode_handoff.write_json',side_effect=write),patch('printer_mode_handoff.read_fresh')as fresh,patch('printer_mode_handoff.time.monotonic',side_effect=range(20)),patch('printer_mode_handoff.time.sleep'):
                with self.assertRaisesRegex(RuntimeError,'Original printer mode request unknown'):token._set(state,False,'pause')
            self.assertTrue(token.pending);self.assertEqual(1,len(requests));fresh.assert_not_called()


if __name__=='__main__':unittest.main()
