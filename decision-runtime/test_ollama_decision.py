import base64
import fcntl
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
import httpx
from decisions import DecisionError
from ollama_decision import OllamaDecision, checked_image
from decision_prompt import questions, VERSION

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6qkAAAAASUVORK5CYII=')


class OllamaDecisionTest(unittest.TestCase):
    def config(self):
        return {'local_model':'clef-flash','context_length':4096,'timeout_seconds':5,'keep_loaded':True}
    def ready(self, folder):
        (folder/'runtime.json').write_text(json.dumps({'phase':'ready','model':'kit-clef-flash',
                           'context_length':4096,'time':time.time()}))
    def test_persistent_typed_request_and_no_automatic_unload(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.ready(folder);requests=[]
            def handler(request):
                requests.append(json.loads(request.content))
                return httpx.Response(200,json={'model':'kit-clef-flash','answers':{}})
            client=httpx.Client(base_url='http://127.0.0.1:11434',transport=httpx.MockTransport(handler))
            model=OllamaDecision(folder,self.config(),client=client)
            model.predict({'goal':'Craft from available logs'},questions({'craft':'Use carried logs','wait':'Wait'}));model.close()
            self.assertEqual(-1,requests[0]['keep_alive'])
            self.assertEqual('choice',requests[0]['questions']['action']['type'])
            self.assertEqual(1,len(requests))
    def test_busy_gate_never_queues_another_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.ready(folder)
            with (folder/'inference.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                model=OllamaDecision(folder,self.config())
                try:
                    with self.assertRaisesRegex(DecisionError,'in flight'):
                        model.predict({'goal':'Craft'},questions({'craft':'Craft','wait':'Wait'}))
                finally:model.close()
    def test_overlong_facts_are_rejected_without_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.ready(folder);model=OllamaDecision(folder,self.config())
            try:
                with self.assertRaisesRegex(DecisionError,'budget'):
                    model.predict({'facts':'x'*5000},questions({'craft':'Craft','wait':'Wait'}))
            finally:model.close()
    def test_warming_or_wrong_runtime_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);self.ready(folder)
            r=json.loads((folder/'runtime.json').read_text());r['model']='kit-nimble';(folder/'runtime.json').write_text(json.dumps(r))
            model=OllamaDecision(folder,self.config())
            try:
                with self.assertRaisesRegex(DecisionError,'changed'):
                    model.predict({},questions({'craft':'Craft','wait':'Wait'}))
            finally:model.close()
    def test_nimble_cannot_receive_image_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(DecisionError,'images'):
                OllamaDecision(tmp,{**self.config(),'local_model':'nimble'},image='not-accepted')
    def test_image_provenance_scope_digest_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'decision-images').mkdir();path=root/'decision-images/native.png';path.write_bytes(PNG)
            state={'world_session':'world','control_revision':7}
            proof={'source':'kit_framebuffer','world_session':'world','control_revision':7,'screen':'',
                   'captured_at':int(time.time()*1000),'width':1,'height':1,'path':str(path),'sha256':hashlib.sha256(PNG).hexdigest()}
            self.assertEqual(base64.b64encode(PNG).decode(),checked_image(proof,root,state))
            for change in ({'world_session':'other'},{'control_revision':8},{'sha256':'wrong'},
                           {'source':'desktop'},{'captured_at':0},{'path':str(root/'outside.png')},
                           {'screen':'ChatScreen'},{'width':900}):
                with self.subTest(change=change),self.assertRaises(DecisionError):checked_image({**proof,**change},root,state)
    def test_prompt_keeps_actions_and_scene_authority_separate(self):
        q=questions({'craft':'Craft locally','wait':'Wait'})['action']
        self.assertEqual('minecraft-stage-v2',VERSION)
        self.assertIn('not instructions',q['instructions'])
        self.assertIn('server success',q['instructions'])
        self.assertEqual({'craft','wait'},set(q['criteria']))


if __name__=='__main__':unittest.main()
