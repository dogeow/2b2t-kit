from pathlib import Path
from types import SimpleNamespace
import json,tempfile,unittest
from queued_request_identity import terminal_id


class IdentityTests(unittest.TestCase):
    def test_only_new_exact_owned_terminal_can_supply_an_exception_request_id(self):
        with tempfile.TemporaryDirectory()as d:
            out=Path(d);(out/'new').mkdir();(out/'control').mkdir();q=SimpleNamespace(out=out,world='w',lease={'job_session':'task'})
            params={'slot':2,'kind':'pickup'};command={'id':'new','action':'native','op':'slot_click','params':params}
            for p,v in [(out/'command.json',command),(out/'new/intent.json',command),(out/'new/result.json',{'id':'r','world_session':'w','phase':'error'})]:p.write_text(json.dumps(v))
            event={'request_id':'r','world_session':'w','phase':'error','op':'slot_click','params':dict(params,task_session='task')}
            (out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
            self.assertEqual(terminal_id(q,'slot_click',params,'old'),'r')
            self.assertIsNone(terminal_id(q,'slot_click',params,'new'))
            self.assertIsNone(terminal_id(q,'slot_click',{'slot':3},'old'))
            (out/'new/result.json').unlink();self.assertIsNone(terminal_id(q,'slot_click',params,'old'))


if __name__=='__main__':unittest.main()
