import json
from pathlib import Path
import contextlib
import io
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from kit_cli import KitControlError, compact, make_request, send


def state():
    return {'time': int(time.time()*1000), 'connected': True, 'server': 'simpcraft.com',
            'dimension': 'minecraft:overworld', 'world_session': 'world-1',
            'control_revision': 8, 'last_request': 'prior', 'pos': [10, 90, 20],
            'manual_movement': False, 'gravel': {'active': False, 'collected': 0}}


def publish_json(path, payload):
    """Match the native bridge's atomic publication of complete JSON files."""
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload))
    temporary.replace(path)


class KitCliTest(unittest.TestCase):
    def test_default_status_reads_current_26_2_instance_without_sending_actions(self):
        import kit_cli
        with patch('kit_cli.live_status',return_value=state())as observe,patch('kit_cli.compact',return_value={}),patch('kit_cli.send')as send,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0,kit_cli.main(['gravel','status']))
        self.assertEqual(Path('/Applications/.minecraft/versions/26.2/config/twob2tkit/automation'),observe.call_args.args[0])
        send.assert_not_called()

    def test_explicit_legacy_instance_remains_available_for_rollback(self):
        import kit_cli
        legacy='/Applications/.minecraft/versions/26.1.2'
        with patch('kit_cli.live_status',return_value=state())as observe,patch('kit_cli.compact',return_value={}),patch('kit_cli.send')as send,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0,kit_cli.main(['--game-dir',legacy,'gravel','status']))
        self.assertEqual(Path(legacy)/'config/twob2tkit/automation',observe.call_args.args[0]);send.assert_not_called()
    def test_depot_channel_does_not_touch_active_gameplay_mailbox_and_accepts_repeated_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'status.json').write_text(json.dumps(state()))
            (root/'request.json').write_text('{"id":"active-gameplay"}')
            old={'id':'prior-source','op':'projection_supply_set'}
            (root/'projection-supply-request.json').write_text(json.dumps(old))
            (root/'projection-supply-reply-prior-source.json').write_text(json.dumps({**old,'phase':'done'}))
            request=make_request(state(),'projection_supply_set');request.update(schema=1,pos=[10,64,20],enabled=True)
            def respond():
                path=root/'projection-supply-request.json';until=time.monotonic()+1
                while time.monotonic()<until:
                    if json.loads(path.read_text()).get('id')==request['id']:
                        reply={**request,'phase':'done','changed':False,'control_revision':8,'observed_at':int(time.time()*1000)}
                        publish_json(root/('projection-supply-reply-'+request['id']+'.json'),reply);return
                    time.sleep(.01)
            worker=threading.Thread(target=respond);worker.start()
            try:reply=send(root,request,timeout=1,supply_channel=True)
            finally:worker.join()
            self.assertFalse(reply['changed']);self.assertEqual('active-gameplay',json.loads((root/'request.json').read_text())['id'])
    def test_unconfirmed_depot_permission_is_preserved_and_never_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'status.json').write_text(json.dumps(state()))
            prior='{ "id": "pending-source", "op": "projection_supply_set" }'
            (root/'projection-supply-request.json').write_text(prior)
            request=make_request(state(),'projection_supply_set');request.update(pos=[10,64,20],enabled=False)
            with self.assertRaisesRegex(KitControlError,'尚未确认'):
                send(root,request,timeout=.1,supply_channel=True)
            self.assertEqual(prior,(root/'projection-supply-request.json').read_text())

    def test_request_is_scoped_to_current_world_and_never_uses_ui(self):
        request = make_request(state(), 'gravel_start', radius=48, depth=28, limit=0)
        self.assertEqual('world-1', request['world_session'])
        self.assertEqual(8, request['expected_revision'])
        self.assertEqual([10, 90, 20], request['site'])
        self.assertEqual((48, 28, 0), (request['radius'], request['depth'], request['limit']))
        self.assertNotIn('key', request)
        self.assertNotIn('click', request)

    def test_foreign_pending_request_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'status.json').write_text(json.dumps(state()))
            (root/'request.json').write_text('{"id":"other"}')
            with self.assertRaisesRegex(KitControlError, '已有尚未确认'):
                send(root, make_request(state(), 'gravel_config'), timeout=.2)
            self.assertEqual('other', json.loads((root/'request.json').read_text())['id'])

    def test_receipt_completes_without_resending_and_outputs_compact_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'config/twob2tkit/automation'
            root.mkdir(parents=True)
            (root/'status.json').write_text(json.dumps(state()))
            (root/'request.json').write_text('{"id":"prior"}')
            (root.parent.parent/'twob2tkit.json').write_text('{"gravelRadius":48,"gravelDepth":28,"gravelLimit":0}')
            request = make_request(state(), 'gravel_start')

            def respond():
                until=time.monotonic()+1
                while time.monotonic()<until:
                    if json.loads((root/'request.json').read_text()).get('id')==request['id']:
                        receipt=state();receipt.update(id=request['id'],last_request=request['id'],phase='done')
                        receipt['gravel']['active']=True
                        publish_json(root/('reply-'+request['id']+'.json'),receipt)
                        overwritten=state();overwritten.update(id='native-child',last_request=request['id'],phase='running')
                        overwritten['gravel']['active']=True
                        publish_json(root/'status.json',overwritten)
                        return
                    time.sleep(.01)

            worker=threading.Thread(target=respond)
            worker.start()
            try:
                result=send(root,request,timeout=1)
            finally:
                worker.join()
            self.assertTrue(compact(root,result)['active'])
            self.assertEqual(48,compact(root,result)['radius'])
            self.assertEqual(request['id'],json.loads((root/'request.json').read_text())['id'])


if __name__=='__main__':
    unittest.main()
