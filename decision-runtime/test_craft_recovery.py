import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from craft_recovery import clear_owned_workbench

class Client:
 owned_material_menu=5
 def __init__(self):
  self.calls=[];self.pending=None
  slots=[{'slot':i,'item':'minecraft:air','count':0} for i in range(46)]
  slots[1].update(item='minecraft:iron_ingot',count=5)
  self.s={'menu':{'id':5,'type':'CraftingMenu','cursor':{'item':'minecraft:iron_nugget','count':16},'slots':slots}}
 def status(self):
  if self.pending:
   p=self.pending;self.pending=None;m=self.s['menu']
   if p['kind']=='pickup':m['slots'][p['slot']].update(m['cursor']);m['cursor']={'item':'minecraft:air','count':0}
   else:m['slots'][p['slot']].update(item='minecraft:air',count=0)
  return copy.deepcopy(self.s)
 def checked(self,op,**args):self.calls.append(args);self.pending=args;return copy.deepcopy(self.s)

class InventoryClient:
 owned_material_menu=None
 def __init__(self,out):
  self.out=Path(out);self.calls=[];self.pending=None;self.world='world-a';self.task='task-a';self.rev=7
  self.heartbeat=SimpleNamespace(id='lease-a',attached=True)
  self.owned_inventory_crafting={'menu_id':0,'world_session':self.world,'task_session':self.task}
  slots=[{'slot':i,'item':'minecraft:air','count':0} for i in range(46)]
  slots[1].update(item='minecraft:cobbled_deepslate',count=1)
  slots[9].update(item='minecraft:baked_potato',count=4)
  slots[10].update(item='minecraft:bone',count=2)
  self.s={'connected':True,'world_session':self.world,'control_revision':7,'screen':'',
          'manual_movement':False,'guard_armed':True,
          'inventory_cursor_precondition_protocol':1,
          'inventory_isolation':{'supported':True,'active':True},
          'supervision_lease':{'id':'lease-a','kind':'materials','job_session':self.task,
                               'world_session':self.world,'revision':7},
          'menu':{'id':0,'type':'InventoryMenu',
                  'cursor':{'item':'minecraft:cobbled_deepslate','count':49},'slots':slots}}
 def status(self):
  if self.pending:
   p=self.pending;self.pending=None;m=self.s['menu']
   if p['kind']=='pickup':m['slots'][p['slot']].update(m['cursor']);m['cursor']={'item':'minecraft:air','count':0}
   else:m['slots'][p['slot']].update(item='minecraft:air',count=0)
  return copy.deepcopy(self.s)
 def checked(self,op,**args):
  menu=self.s['menu'];slot=menu['slots'][args['slot']];cursor=menu['cursor']
  assert (slot['item'],slot['count'])==(args['expected_item'],args['expected_count'])
  assert (cursor['item'],cursor['count'])==(args['expected_cursor'],args['expected_cursor_count'])
  self.calls.append(args);self.pending=args;return copy.deepcopy(self.s)

class Tests(unittest.TestCase):
 def test_failed_crafting_returns_cursor_and_grid_before_release(self):
  c=Client()
  with patch('craft_recovery.time.sleep'):self.assertTrue(clear_owned_workbench(c))
  self.assertEqual([a['kind'] for a in c.calls],['pickup','quick_move'])
  self.assertEqual(c.s['menu']['slots'][10]['count'],16)
  self.assertEqual(c.s['menu']['cursor']['count'],0)
 def test_different_menu_is_never_changed(self):
  c=Client();c.s['menu']['id']=6
  self.assertFalse(clear_owned_workbench(c));self.assertEqual(c.calls,[])
 def test_full_inventory_never_drops_cursor(self):
  c=Client()
  for slot in c.s['menu']['slots'][-36:]:slot.update(item='minecraft:stone',count=64)
  with self.assertRaises(RuntimeError):clear_owned_workbench(c)
  self.assertEqual(c.calls,[])
 def test_failed_inventory_craft_recovers_cursor_and_grid_under_owned_guard(self):
  with tempfile.TemporaryDirectory() as temp:
   c=InventoryClient(temp)
   with patch('craft_recovery.time.sleep'):self.assertTrue(clear_owned_workbench(c))
   self.assertEqual([a['kind'] for a in c.calls],['pickup','quick_move'])
   self.assertEqual(11,c.calls[0]['slot']);self.assertNotIn(0,[a['slot'] for a in c.calls])
   self.assertEqual(('minecraft:cobbled_deepslate',49),
                    (c.s['menu']['slots'][11]['item'],c.s['menu']['slots'][11]['count']))
   self.assertEqual(0,c.s['menu']['cursor']['count']);self.assertEqual(0,c.s['menu']['slots'][1]['count'])
   self.assertIsNone(c.owned_inventory_crafting);self.assertTrue(c.s['guard_armed'])
   receipt=__import__('json').loads((Path(temp)/'craft-recovery.json').read_text())
   self.assertEqual({'item':'minecraft:air','count':0},receipt['cursor']['expected_destination'])
   self.assertTrue(receipt['confirmed']);self.assertTrue(receipt['guard_armed'])
 def test_inventory_recovery_requires_exact_marker_isolation_and_lease(self):
  with tempfile.TemporaryDirectory() as temp:
   mutations=(lambda c:setattr(c,'owned_inventory_crafting',None),
              lambda c:c.s['inventory_isolation'].update(active=False),
              lambda c:c.s.update(screen='InventoryScreen'),
              lambda c:c.s.update(manual_movement=True),
              lambda c:c.s['supervision_lease'].update(id='foreign'),
              lambda c:c.s['supervision_lease'].update(revision=8))
   for mutate in mutations:
    c=InventoryClient(temp);mutate(c)
    self.assertFalse(clear_owned_workbench(c));self.assertEqual([],c.calls)
 def test_inventory_recovery_uses_slot9_but_never_offhand45(self):
  with tempfile.TemporaryDirectory() as temp:
   c=InventoryClient(temp)
   for row in c.s['menu']['slots'][9:45]:row.update(item='minecraft:stone',count=64)
   c.s['menu']['slots'][9].update(item='minecraft:air',count=0)
   c.s['menu']['slots'][45].update(item='minecraft:air',count=0)
   c.s['menu']['slots'][1].update(item='minecraft:air',count=0)
   with patch('craft_recovery.time.sleep'):self.assertTrue(clear_owned_workbench(c))
   self.assertEqual(9,c.calls[0]['slot'])
   c=InventoryClient(temp)
   for row in c.s['menu']['slots'][9:45]:row.update(item='minecraft:stone',count=64)
   c.s['menu']['slots'][45].update(item='minecraft:air',count=0)
   with self.assertRaisesRegex(RuntimeError,'ordinary inventory'):
    clear_owned_workbench(c)
   self.assertEqual([],c.calls)
 def test_inventory_recovery_timeout_never_repeats_destination_click(self):
  with tempfile.TemporaryDirectory() as temp:
   c=InventoryClient(temp)
   def lost(op,**args):c.calls.append(args);return copy.deepcopy(c.s)
   c.checked=lost
   with patch('craft_recovery.time.monotonic',side_effect=[0,0,0,0,7]):
    with self.assertRaisesRegex(RuntimeError,'no repeated click'):clear_owned_workbench(c)
   self.assertEqual(1,len(c.calls));self.assertEqual(11,c.calls[0]['slot'])
 def test_cursor_arriving_after_grid_return_stops_recovery_without_replay(self):
  with tempfile.TemporaryDirectory() as temp:
   c=InventoryClient(temp);original=c.status
   def late_cursor():
    grid_pending=bool(c.pending and c.pending['kind']=='quick_move')
    state=original()
    if grid_pending:
     c.s['menu']['cursor']={'item':'minecraft:cobbled_deepslate','count':2}
     state=copy.deepcopy(c.s)
    return state
   c.status=late_cursor
   with patch('craft_recovery.time.monotonic',side_effect=[0,0,0,0,0,0,7]):
    with self.assertRaisesRegex(RuntimeError,'no repeated click'):clear_owned_workbench(c)
   self.assertEqual(['pickup','quick_move'],[call['kind'] for call in c.calls])
   self.assertEqual(2,c.s['menu']['cursor']['count'])
   self.assertIsNotNone(c.owned_inventory_crafting)
 def test_recovery_waits_for_final_cell_rollback_to_converge_before_first_click(self):
  with tempfile.TemporaryDirectory() as temp:
   c=InventoryClient(temp);c.s['time']=100
   # Failure observation from the live race: cursor 6 and final cell empty.
   c.s['menu']['cursor']={'item':'minecraft:cobbled_deepslate','count':6}
   c.s['menu']['slots'][4].update(item='minecraft:air',count=0)
   authoritative=copy.deepcopy(c.s);authoritative['time']=102
   authoritative['menu']['cursor']['count']=5
   authoritative['menu']['slots'][4].update(item='minecraft:cobbled_deepslate',count=1)
   settled=copy.deepcopy(authoritative);settled['time']=103
   settled_again=copy.deepcopy(authoritative);settled_again['time']=104
   observations=[copy.deepcopy(c.s),authoritative,settled,settled_again]
   original=c.status
   def converging_status():
    if observations:
     value=observations.pop(0)
     if not observations:c.s=copy.deepcopy(value)
     return value
    c.s['time']+=1
    return original()
   c.status=converging_status
   with patch('craft_recovery.time.sleep'):self.assertTrue(clear_owned_workbench(c))
   self.assertEqual(5,c.calls[0]['expected_cursor_count'])
   self.assertEqual(11,c.calls[0]['slot'])
   self.assertIn(4,[call['slot'] for call in c.calls if call['kind']=='quick_move'])
   self.assertEqual(0,c.s['menu']['cursor']['count'])
   self.assertTrue(all(not c.s['menu']['slots'][slot]['count'] for slot in range(1,5)))
if __name__=='__main__':unittest.main()
