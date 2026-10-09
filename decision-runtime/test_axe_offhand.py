import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from axe_offhand import AxeOffhand
class Client:
 def __init__(self):
  self.rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(46)]
  self.rows[45]={'slot':45,'item':'minecraft:shield','count':1,'max_stack':1,'durability':300,'max_durability':336}
  self.busy=False;self.health=20;self.moves=[]
 def status(self):return {'world_session':'w','health':self.health,'guard_busy':self.busy,'guard_armed':True,'guard_pve_only':True,'manual_movement':False,'screen':'','menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0},'slots':copy.deepcopy(self.rows)}}
 def move(self,session,state,source,dest,amount):
  self.moves.append((source['slot'],dest['slot'],amount));self.rows[dest['slot']]={**source,'slot':dest['slot']};self.rows[source['slot']]={'slot':source['slot'],'item':'minecraft:air','count':0,'max_stack':1}
class ShieldTest(unittest.TestCase):
 def setUp(self):
  p=patch('axe_offhand.InventorySession._wait',side_effect=lambda state,menu,predicate,*a,**kw:state if predicate(state['menu']) else (_ for _ in ()).throw(RuntimeError('unconfirmed')))
  p.start();self.addCleanup(p.stop)
 def test_exact_shield_metadata_returns_to_original_offhand(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client();original=copy.deepcopy(c.rows[45])
   with patch('axe_offhand.move_amount',side_effect=c.move):
    s=AxeOffhand(c,Path(root)/'shield').park();self.assertEqual(0,c.rows[45]['count']);s.restore()
   self.assertEqual(original,c.rows[45]);self.assertEqual([(45,9,1),(9,45,1)],c.moves);self.assertEqual({},c.resource_cleanup)
 def test_busy_hurt_or_full_backpack_does_not_store_shield(self):
  for case in ('busy','hurt','full'):
   with tempfile.TemporaryDirectory()as root:
    c=Client()
    if case=='busy':c.busy=True
    if case=='hurt':c.health=19
    if case=='full':
     for r in c.rows[9:36]:r.update(item='minecraft:diamond',count=64,max_stack=64)
    with patch('axe_offhand.move_amount')as move:
     with self.assertRaises(RuntimeError):AxeOffhand(c,Path(root)/'shield').park()
     move.assert_not_called()
 def test_unknown_click_and_changed_stored_shield_cannot_be_replayed(self):
  with tempfile.TemporaryDirectory()as root:
   c=Client();s=AxeOffhand(c,Path(root)/'unknown')
   with patch('axe_offhand.move_amount',side_effect=RuntimeError('unknown'))as move:
    with self.assertRaisesRegex(RuntimeError,'unknown'):s.park()
    with self.assertRaisesRegex(RuntimeError,'Unknown'):s.restore()
    self.assertEqual(1,move.call_count)
  with tempfile.TemporaryDirectory()as root:
   c=Client()
   with patch('axe_offhand.move_amount',side_effect=c.move):
    s=AxeOffhand(c,Path(root)/'changed').park();c.rows[9]['durability']=299
    with self.assertRaisesRegex(RuntimeError,'changed'):s.restore()
   self.assertEqual(1,len(c.moves))
if __name__=='__main__':unittest.main()
