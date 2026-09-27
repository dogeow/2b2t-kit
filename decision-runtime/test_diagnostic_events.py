import json,tempfile,unittest
from pathlib import Path
from kit_runtime.diagnostics import EventLog,redact,tail_events
class DiagnosticEventsTest(unittest.TestCase):
 def test_credentials_are_removed_but_token_usage_survives(self):
  result=redact({'authorization':'Bearer example-token','apiKey':'apikey_example_12345678','usage':{'input_tokens':12},'detail':'failed apikey_example_12345678 Bearer example.secret'})
  text=json.dumps(result);self.assertNotIn('example-token',text);self.assertNotIn('apikey_example_',text);self.assertNotIn('example.secret',text);self.assertEqual(12,result['usage']['input_tokens'])
 def test_diagnostic_rotation_is_bounded_without_touching_transaction_journal(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);raw=p/'events.jsonl';raw.write_text('authoritative');log=EventLog(p/'jev-decisions.jsonl',256,2)
   for n in range(30):log.emit('decision',index=n,text='x'*60)
   self.assertEqual('authoritative',raw.read_text());self.assertEqual(3,len(list(p.glob('jev-decisions*.jsonl'))));self.assertEqual(29,tail_events(log.path)[-1]['index'])
 def test_tail_ignores_partial_record_and_limits_volume(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'events.jsonl';p.write_text(''.join(json.dumps({'n':i})+'\n' for i in range(100))+'{"incomplete":')
   rows=tail_events(p,limit=5,max_bytes=256);self.assertLessEqual(len(rows),5);self.assertEqual(99,rows[-1]['n'])
if __name__=='__main__':unittest.main()

class DiagnosticBoundsTest(unittest.TestCase):
 def test_large_mapping_is_not_materialized_to_log_its_prefix(self):
  seen=[]
  class Large(dict):
   def items(self):
    for n in range(10000):seen.append(n);yield str(n),n
   def __len__(self):return 10000
  result=redact(Large());self.assertEqual(32,len(seen));self.assertEqual(9968,result['omitted_fields'])
 def test_opaque_bearer_and_credentials_as_keys_are_fully_redacted(self):
  result=redact({'detail':'failed Bearer example/opaque+token=', 'apikey_example_12345678':'value'})
  text=json.dumps(result);self.assertNotIn('opaque',text);self.assertNotIn('apikey_example',text)
