import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_client import Client
from sensitive_data import REDACTED,sanitize
from experience_recording import record_native_transaction


class SensitiveDataTest(unittest.TestCase):
    def test_recursive_sanitizer_preserves_input_and_redacts_only_secret_value(self):
        raw={'snow_expedition_token':'secret','nested':[{
            'snow_expedition_token':'nested-secret','x':1}],'ordinary':'kept'}
        safe=sanitize(raw)
        self.assertEqual(REDACTED,safe['snow_expedition_token'])
        self.assertEqual(REDACTED,safe['nested'][0]['snow_expedition_token'])
        self.assertEqual('kept',safe['ordinary'])
        self.assertEqual('secret',raw['snow_expedition_token'])

    def test_events_movement_failure_and_experience_never_persist_expedition_token(self):
        class ClientUnderTest(Client):
            def __init__(self,root):
                self.root=self.out=Path(root);self.server='test';self.world='world'
                self.rev=0;self.last=None;self.anchor=[0,80,0];self.record_experience=True
                self.experience_state=Path(root)/'experience';self.polls=0
                self.saw_live_token=False
                self.current={'server':'test','dimension':'minecraft:overworld',
                    'world_session':'world','connected':True,'control_revision':0,
                    'manual_movement':False,'screen':'','health':20,'food':20,
                    'guard_busy':False,'under_water':False,'pos':[0,80,0],
                    'time':100,'movement_keys':{},'velocity':[0,0,0]}
            def status(self):return dict(self.current)
            def raw(self):
                self.polls+=1
                if (self.root/'request.json').exists():
                    pending=json.loads((self.root/'request.json').read_text())
                    self.saw_live_token=self.saw_live_token or \
                        pending.get('snow_expedition_token')=='plaintext-secret'
                if self.polls==2:
                    rid=json.loads((self.root/'request.json').read_text())['id']
                    (self.root/f'reply-{rid}.json').write_text(json.dumps({
                        'id':rid,'world_session':'world','control_revision':0,
                        'phase':'waiting','detail':'stopped',
                        'nested':{'token':'reply-secret'}}))
                return dict(self.current)
        class Fixed:
            hex='1234567890abcdef'
        with tempfile.TemporaryDirectory() as folder,\
                patch('material_client.uuid.uuid4',return_value=Fixed()),\
                patch('material_client.time.sleep'),\
                patch('experience_recording.record_native_transaction') as recorded:
            client=ClientUnderTest(folder)
            result=client.request('navigate',target=[10,100,10],seconds=5,
                snow_expedition_token='plaintext-secret')
            self.assertEqual('waiting',result['phase'])
            request=json.loads((Path(folder)/'request.json').read_text())
            reply=json.loads(next(Path(folder).glob('reply-*.json')).read_text())
            self.assertTrue(client.saw_live_token,'host must see the live token before confirmation')
            self.assertEqual(REDACTED,request['snow_expedition_token'])
            self.assertEqual(REDACTED,reply['nested']['token'])
            self.assertEqual('reply-secret',result['nested']['token'],
                             'in-memory confirmed reply remains usable for this process')
            event=json.loads((Path(folder)/'events.jsonl').read_text())
            failure=json.loads(next(Path(folder).glob('movement-failure-*.json')).read_text())
            self.assertEqual(REDACTED,event['params']['snow_expedition_token'])
            self.assertEqual(REDACTED,failure['params']['snow_expedition_token'])
            learned=recorded.call_args.args
            self.assertEqual(REDACTED,learned[0]['snow_expedition_token'])
            self.assertNotIn('plaintext-secret',json.dumps([request,reply,event,failure,learned[0]]))

    def test_seed_candidate_observation_never_opens_experience_store(self):
        with tempfile.TemporaryDirectory() as folder:
            result=record_native_transaction({'id':'read','op':'snow_seed_candidates'},
                {},{'id':'read','phase':'done','snow_seed_candidates':{
                    'token':'plaintext-secret'}},Path(folder)/'skills')
            self.assertEqual('observation',result['status'])
            self.assertFalse((Path(folder)/'skills').exists())


if __name__=='__main__':unittest.main()
