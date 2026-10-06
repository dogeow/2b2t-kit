import json
import unittest
import httpx
from local_decision_runtime import prepare, valid_config


class LocalRuntimeTest(unittest.TestCase):
    def config(self):return {'provider':'ollama','enabled':True,'local_model':'clef-flash','keep_loaded':True,'context_length':4096}
    def test_missing_model_does_not_start_a_download(self):
        seen=[]
        def handler(request):
            seen.append(request.url.path)
            return httpx.Response(200,json={'models':[]})
        with httpx.Client(base_url='http://127.0.0.1:11434',transport=httpx.MockTransport(handler))as c:
            with self.assertRaisesRegex(RuntimeError,'not installed'):prepare(c,self.config())
        self.assertNotIn('/api/pull',seen)
    def test_foreign_resident_model_is_not_unloaded(self):
        seen=[]
        def handler(request):
            seen.append(request.url.path)
            return httpx.Response(200,json={'models':[{'name':'clef-flash:latest'}] if request.url.path=='/api/tags' else [{'name':'personal-model:latest'}]})
        with httpx.Client(base_url='http://127.0.0.1:11434',transport=httpx.MockTransport(handler))as c:
            with self.assertRaisesRegex(RuntimeError,'not evicted'):prepare(c,self.config())
        self.assertNotIn('/api/generate',seen)
    def test_context_override_and_persistent_warmup(self):
        calls=[];ps=[0]
        def handler(request):
            body=json.loads(request.content)if request.content else {};calls.append((request.url.path,body))
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'clef-flash:latest'}]})
            if request.url.path=='/api/ps':
                ps[0]+=1
                return httpx.Response(200,json={'models':[] if ps[0]==1 else [{'name':'kit-clef-flash:latest','context_length':4098,'size_vram':123}]})
            return httpx.Response(200,json={'status':'success'})
        with httpx.Client(base_url='http://127.0.0.1:11434',transport=httpx.MockTransport(handler))as c:
            model,size=prepare(c,self.config())
        self.assertEqual(('kit-clef-flash',123),(model,size))
        create=next(b for p,b in calls if p=='/api/create');self.assertEqual({'num_ctx':4096},create['parameters'])
        warm=next(b for p,b in calls if p=='/v1/systemone');self.assertEqual(-1,warm['keep_alive'])
    def test_unrelated_kit_prefix_is_not_owned(self):
        seen=[]
        def handler(request):
            seen.append(request.url.path)
            return httpx.Response(200,json={'models':[{'name':'clef-flash:latest'}] if request.url.path=='/api/tags' else [{'name':'kit-personal:latest'}]})
        with httpx.Client(base_url='http://127.0.0.1:11434',transport=httpx.MockTransport(handler))as c:
            with self.assertRaisesRegex(RuntimeError,'not evicted'):prepare(c,self.config())
        self.assertNotIn('/api/generate',seen)
    def test_warmup_failure_releases_owned_alias(self):
        calls=[]
        def handler(request):
            body=json.loads(request.content)if request.content else {};calls.append((request.url.path,body))
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'clef-flash:latest'}]})
            if request.url.path=='/api/ps':return httpx.Response(200,json={'models':[]})
            if request.url.path=='/v1/systemone':return httpx.Response(500,json={'error':'failed'})
            return httpx.Response(200,json={})
        with httpx.Client(base_url='http://127.0.0.1:11434',transport=httpx.MockTransport(handler))as c:
            with self.assertRaises(httpx.HTTPStatusError):prepare(c,self.config())
        self.assertIn(('/api/generate',{'model':'kit-clef-flash','keep_alive':0}),calls)
    def test_invalid_runtime_options_fail_closed(self):
        for change in ({'context_length':65536},{'local_model':'arbitrary-remote-model'},{'keep_loaded':'yes'}):
            with self.subTest(change=change),self.assertRaises(ValueError):valid_config({**self.config(),**change})


if __name__=='__main__':unittest.main()
