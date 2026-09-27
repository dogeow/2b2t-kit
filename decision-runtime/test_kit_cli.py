import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from kit_cli import KitControlError, compact, make_request, send


def state():
    return {'time': int(time.time()*1000), 'connected': True, 'server': 'simpcraft.com',
            'dimension': 'minecraft:overworld', 'world_session': 'world-1',
            'control_revision': 8, 'last_request': 'prior', 'pos': [10, 90, 20],
            'manual_movement': False, 'gravel': {'active': False, 'collected': 0}}


class KitCliTest(unittest.TestCase):
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
                        (root/('reply-'+request['id']+'.json')).write_text(json.dumps(receipt))
                        overwritten=state();overwritten.update(id='native-child',last_request=request['id'],phase='running')
                        overwritten['gravel']['active']=True
                        (root/'status.json').write_text(json.dumps(overwritten))
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
