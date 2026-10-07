import json
from pathlib import Path
import tempfile
import unittest

from singleplayer_trial_bridge import TrialBridge, TrialImageUnavailable, Paused
from test_singleplayer_trial import registry, state
import test_singleplayer_trial as trial_tests


class InterfacePauseTests(unittest.TestCase):
    def test_readonly_image_menu_refusal_retains_control_and_never_closes_player_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            reg=registry(directory);root=Path(directory)/'automation';root.mkdir()
            blocked=[True];events=[]
            def read(unused):
                p=root/'request.json'
                if not p.exists():return state(reg)
                request=json.loads(p.read_text())
                return state(reg,id=request['id'],last_request=request['id'],
                             screen='InventoryScreen' if blocked[0] else '',
                             phase='error',detail='Close the game interface before requesting a world image')
            bridge=TrialBridge(root,reg,reg['run_id'],reader=read,
                               events=lambda kind,**data:events.append((kind,data)))
            with self.assertRaises(TrialImageUnavailable):bridge.request('decision_screenshot')
            self.assertFalse(bridge.halted)
            self.assertIsNone(bridge.active)
            self.assertFalse(bridge.pending_mutations)
            self.assertEqual('read_only_image_refusal',bridge.last_receipt['receipt_class'])
            self.assertEqual(['decision_screenshot'],[row['op'] for kind,row in events if kind=='native_request'])
            blocked[0]=False
            self.assertEqual('',bridge.read()['screen'])

    def test_unknown_image_error_or_partial_image_does_not_gain_the_menu_refusal_exception(self):
        for change in ({'detail':'capture failed'},{'outcome_pending':True},
                       {'decision_image':{'path':'unverified.png'}}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                reg=registry(directory);root=Path(directory)/'automation';root.mkdir()
                def read(unused):
                    p=root/'request.json'
                    if not p.exists():return state(reg)
                    req=json.loads(p.read_text())
                    return state(reg,id=req['id'],last_request=req['id'],screen='InventoryScreen',
                        **({'phase':'error','detail':'Close the game interface before requesting a world image'}|change))
                bridge=TrialBridge(root,reg,reg['run_id'],reader=read)
                with self.assertRaises(Paused):bridge.request('decision_screenshot')
                self.assertTrue(bridge.halted)

    def test_idle_inventory_waits_without_binding_or_native_commands_then_can_reobserve(self):
        with tempfile.TemporaryDirectory() as directory:
            worker,reg,root=trial_tests.WorkerTests().worker(directory)
            worker.registry=reg;worker.run_id=reg['run_id'];worker.command='start';worker.control=lambda:None
            current=state(reg,screen='InventoryScreen')
            worker.reader=lambda unused:current
            calls=[]
            def bind():
                calls.append(True)
                raise Paused('stop test before native observation')
            worker.bind=bind
            try:
                worker.cycle()
                self.assertEqual('waiting_interface',worker.phase)
                self.assertEqual([],calls)
                self.assertFalse((worker.automation/'request.json').exists())
                self.assertEqual('start',worker.command)
                current['screen']=''
                with self.assertRaisesRegex(Paused,'stop test'):worker.cycle()
                self.assertEqual([True],calls)
            finally:
                worker.pool.shutdown(wait=False)
                if worker.experience:worker.experience.close()

