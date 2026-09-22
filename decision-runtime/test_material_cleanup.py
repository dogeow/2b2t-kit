import tempfile,unittest,json
from pathlib import Path
from types import SimpleNamespace
from material_cleanup import register,run
class CleanupTest(unittest.TestCase):
 def test_cleanup_is_not_cleared_until_callback_succeeds(self):
  with tempfile.TemporaryDirectory() as d:
   c=SimpleNamespace(out=Path(d));calls=[]
   def fail():calls.append('try');raise RuntimeError('Not recovered')
   register(c,'box',fail);errors=run(c);self.assertEqual(len(errors),1);self.assertIn('box',c.resource_cleanup)
   register(c,'box',lambda:calls.append('returned'));self.assertEqual(run(c),[]);self.assertNotIn('box',c.resource_cleanup);self.assertEqual(calls,['try','returned'])
 def test_material_finish_runs_owned_cleanup_before_stopping_heartbeat(self):
  import ast
  source=(Path(__file__).parent/'material_client.py').read_text();tree=ast.parse(source)
  cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MaterialClient');finish=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='finish');text=ast.get_source_segment(source,finish)
  self.assertLess(text.index('cleanup_resources(self)'),text.index('self.heartbeat.close()'))
if __name__=='__main__':unittest.main()
