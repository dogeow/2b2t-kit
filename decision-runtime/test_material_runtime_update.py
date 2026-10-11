import hashlib,json,tempfile,unittest
from pathlib import Path

from material_jobs.runtime_update import ensure,validate
from material_jobs.protocol import JobBlocked


class RuntimeUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.automation=self.root/'automation'
        p=self.root/'runtime/twob2tkit-engine.jar';p.parent.mkdir();p.write_bytes(b'verified-stage')
        self.plan={'version':'1.7.98','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
        self.out=self.root/'out';self.out.mkdir()

    def client(self,loaded='1.7.97',after='1.7.98',phase='done'):
        class Client:
            world='world';calls=[]
            def status(c):
                version=after if c.calls else loaded
                return {'world_session':c.world,'runtime_reload_protocol':1,'runtime_host_api':3,
                        'runtime_version':version,'navigation_runtime_version':version}
            def checked(c,op):
                c.calls.append(op);return {'phase':phase,'world_session':c.world}
        return Client()

    def test_matching_file_loads_once_and_checks_current_runtime(self):
        c=self.client();ensure(c,self.automation,self.out,self.plan)
        self.assertEqual(c.calls,['runtime_reload'])
        proof=json.loads((self.out/'runtime-update.json').read_text())
        self.assertEqual(proof['state'],'loaded');self.assertEqual(proof['after_version'],'1.7.98')

    def test_bad_stage_cannot_send_reload(self):
        c=self.client();bad={**self.plan,'sha256':'0'*64}
        with self.assertRaises(JobBlocked):ensure(c,self.automation,self.out,bad)
        self.assertEqual(c.calls,[])

    def test_unknown_result_or_old_version_retains_evidence_without_retry(self):
        for phase,after in [('waiting','1.7.98'),('done','1.7.97')]:
            c=self.client(phase=phase,after=after)
            with self.assertRaises(JobBlocked):ensure(c,self.automation,self.out,self.plan)
            self.assertEqual(c.calls,['runtime_reload'])
            self.assertEqual(json.loads((self.out/'runtime-update.json').read_text())['state'],'unverified')

    def test_already_loaded_skips_new_action(self):
        c=self.client(loaded='1.7.98');ensure(c,self.automation,self.out,self.plan)
        self.assertEqual(c.calls,[])

    def test_no_explicit_plan_does_not_read_or_act(self):
        c=self.client();ensure(c,self.automation,self.out,None);self.assertEqual(c.calls,[])
        for bad in [{},{'version':'x','sha256':'a'*64},{**self.plan,'path':'arbitrary'}]:
            with self.assertRaises(ValueError):validate(bad)
