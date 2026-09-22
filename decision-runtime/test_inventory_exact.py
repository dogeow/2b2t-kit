import unittest,tempfile,json
from pathlib import Path
from inventory_exact import take_exact
class Client:
 def __init__(self,out):
  self.out=out;self.calls=0;self.menu={'type':'ChestMenu','id':4,'cursor':{'item':'minecraft:air','count':0},'slots':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(63)]};self.menu['slots'][0].update(item='minecraft:diamond',count=64)
 def status(self):return {'menu':json.loads(json.dumps(self.menu))}
 def checked(self,op,**r):
  self.calls+=1;s=self.menu['slots'][r['slot']];c=self.menu['cursor'];assert s['item']==r['expected_item'] and s['count']==r['expected_count']
  if r.get('button',0)==1:
   s.update(item=c['item'],count=s['count']+1);c['count']-=1
   if not c['count']:c['item']='minecraft:air'
  else:
   a=dict(s);s.update(item=c['item'],count=c['count']);c.update(item=a['item'],count=a['count'])
class ExactTest(unittest.TestCase):
 def test_takes_two_and_returns_sixty_two_without_drop_or_quick_move(self):
  with tempfile.TemporaryDirectory() as d:
   c=Client(Path(d));r=take_exact(c,0,2);self.assertTrue(r['complete']);self.assertEqual(c.menu['slots'][0]['count'],62);self.assertEqual(c.menu['slots'][27]['count'],2);self.assertEqual(c.menu['cursor']['count'],0);self.assertEqual(c.calls,4)
 def test_incomplete_prior_transfer_never_restarts(self):
  with tempfile.TemporaryDirectory() as d:
   c=Client(Path(d));(c.out/'exact-transfer-active.json').write_text('{"complete":false}')
   with self.assertRaises(RuntimeError):take_exact(c,0,1)
   self.assertEqual(c.calls,0)
 def test_reserves_the_last_empty_slot_for_shulker_recovery(self):
  with tempfile.TemporaryDirectory() as d:
   c=Client(Path(d))
   for s in c.menu['slots'][28:]:s.update(item='minecraft:stone',count=64)
   with self.assertRaises(RuntimeError):take_exact(c,0,1,reserve_empty=1)
   self.assertEqual(c.calls,0)
 def test_uses_empty_slot_instead_of_merging_unknown_components(self):
  with tempfile.TemporaryDirectory() as d:
   c=Client(Path(d));c.menu['slots'][27].update(item='minecraft:diamond',count=5)
   r=take_exact(c,0,1);self.assertEqual(r['destination'],28);self.assertEqual(c.menu['slots'][27]['count'],5)
 def test_rejects_damageable_or_nested_container_items(self):
  with tempfile.TemporaryDirectory() as d:
   c=Client(Path(d));c.menu['slots'][0].update(item='minecraft:diamond_pickaxe',count=1,durability=200,max_stack=1)
   with self.assertRaises(RuntimeError):take_exact(c,0,1)
   self.assertEqual(c.calls,0)
if __name__=='__main__':unittest.main()
