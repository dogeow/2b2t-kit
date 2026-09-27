import copy,itertools,json,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from packed_supplies import contents,choose_box
class PackedTest(unittest.TestCase):
 def test_player_must_step_off_temporary_shulker_pad(self):
  from packed_supplies import player_intersects_pad
  pad=[10,64,20]
  self.assertTrue(player_intersects_pad([10.5,64.87,20.5],pad))
  self.assertFalse(player_intersects_pad([12.5,65,20.5],pad))
  self.assertFalse(player_intersects_pad([10.5,65.1,20.5],pad))
 def test_selects_exact_enchanted_book_in_mixed_box(self):
  from packed_supplies import matching_source
  rows=[{'slot':0,'item':'minecraft:enchanted_book','count':1,
         'stored_enchantments':[{'id':'minecraft:efficiency','level':5}]},
        {'slot':1,'item':'minecraft:enchanted_book','count':1,
         'stored_enchantments':[{'id':'minecraft:silk_touch','level':1}]}]
  required={'minecraft:enchanted_book':{'minecraft:silk_touch':1}}
  self.assertEqual(matching_source(rows,'minecraft:enchanted_book',required)['slot'],1)
  self.assertIsNone(matching_source(rows,'minecraft:enchanted_book',
                    {'minecraft:enchanted_book':{'minecraft:respiration':3}}))
 def test_skips_nearly_broken_fishing_rods(self):
  from packed_supplies import matching_source
  rows=[{'slot':0,'item':'minecraft:fishing_rod','count':1,'durability':6},
        {'slot':1,'item':'minecraft:fishing_rod','count':1,'durability':47}]
  self.assertEqual(matching_source(rows,'minecraft:fishing_rod',
                    minimum_durability={'minecraft:fishing_rod':24})['slot'],1)
 def test_tool_enchantments_and_durability_must_match_the_same_item(self):
  from packed_supplies import matching_source
  tool='minecraft:diamond_pickaxe';required={tool:{'minecraft:efficiency':3}};minimum={tool:1000}
  rows=[{'slot':0,'item':tool,'count':1,'durability':152,'enchantments':[{'id':'minecraft:efficiency','level':4}]},
        {'slot':1,'item':tool,'count':1,'durability':1500,'enchantments':[{'id':'minecraft:efficiency','level':2}]},
        {'slot':2,'item':tool,'count':1,'durability':1490,'enchantments':[{'id':'minecraft:efficiency','level':5}]}]
  self.assertIsNone(matching_source(rows[:2],tool,minimum_durability=minimum,required_enchantments=required))
  self.assertEqual(2,matching_source(rows,tool,minimum_durability=minimum,required_enchantments=required)['slot'])
  # Existing qualified tools are visible to the caller before it chooses whether to withdraw another.
  self.assertEqual(2,matching_source(rows[2:],tool,minimum_durability=minimum,required_enchantments=required)['slot'])
 def test_stored_book_enchantments_cannot_satisfy_ordinary_tool_requirements(self):
  from packed_supplies import matching_source
  tool='minecraft:diamond_pickaxe';book='minecraft:enchanted_book';efficiency=[{'id':'minecraft:efficiency','level':5}]
  self.assertIsNone(matching_source([{'item':tool,'count':1,'durability':1500,'stored_enchantments':efficiency}],tool,
                    minimum_durability={tool:1000},required_enchantments={tool:{'minecraft:efficiency':3}}))
  self.assertIsNone(matching_source([{'item':book,'count':1,'enchantments':efficiency}],book,
                    required_stored_enchantments={book:{'minecraft:efficiency':3}}))
 def test_duplicate_stacks_are_summed_not_overwritten(self):
  self.assertEqual(contents([{'item':'minecraft:paper','count':64},{'item':'minecraft:paper','count':16}]),{'minecraft:paper':80})
 def test_only_observed_useful_box_is_selected_and_existing_stock_is_subtracted(self):
  rows=[{'slot':0,'item':'minecraft:shulker_box','count':1,'contains':[{'item':'minecraft:paper','count':64}]},{'slot':3,'item':'minecraft:shulker_box','count':1,'contains':[{'item':'minecraft:diamond','count':32}]}]
  choice=choose_box(rows,{'minecraft:paper':30,'minecraft:diamond':2},{'minecraft:paper':30})
  self.assertEqual(choice,(2,3,{'minecraft:diamond':2}))
 def test_empty_or_unobserved_box_is_not_guessed(self):
  self.assertIsNone(choose_box([{'slot':1,'item':'minecraft:shulker_box','count':1}],{'minecraft:diamond':2},{}))

class DropIdentityTest(unittest.TestCase):
 def drop(self,uid='new'):
  return {'uuid':uid,'type':'minecraft:item','pos':[1.5,64,2.5],'stack':{'item':'minecraft:shulker_box','count':1,'contains':[]}}
 def test_new_drop_with_hidden_contents_is_collected_before_content_check(self):
  from packed_supplies import owned_drop
  e=self.drop();self.assertEqual(owned_drop([e],'minecraft:shulker_box',[1,64,2],set()),e)
 def test_existing_or_ambiguous_boxes_are_not_claimed(self):
  from packed_supplies import owned_drop
  self.assertIsNone(owned_drop([self.drop('old')],'minecraft:shulker_box',[1,64,2],{'old'}))
  with self.assertRaises(RuntimeError):owned_drop([self.drop('one'),self.drop('two')],'minecraft:shulker_box',[1,64,2],set())
 def test_inventory_contents_must_match_after_pickup(self):
  from packed_supplies import carried_box
  s={'inventory':[{'item':'minecraft:shulker_box','count':1,'contains':[]}]}
  self.assertIsNone(carried_box(s,'minecraft:shulker_box',{'minecraft:book':2}))

class ReturnWorkflowTest(unittest.TestCase):
 def test_hidden_drop_contents_are_checked_after_pickup_and_box_returns_to_same_slot(self):
  import tempfile,json,copy
  from pathlib import Path
  from unittest.mock import patch
  from packed_supplies import recover_and_return
  remaining={'minecraft:book':2};box={'item':'minecraft:shulker_box','count':1,'contains':[{'item':'minecraft:book','count':2}]}
  with tempfile.TemporaryDirectory() as d:
   class Client:
    def __init__(self):
     self.out=Path(d);self.resource_cleanup={};self.moves=[]
     self.s={'screen':'','inventory':[],'entities':[{'uuid':'fresh-box','type':'minecraft:item','pos':[1.5,64,2.5],'stack':{'item':'minecraft:shulker_box','count':1,'contains':[]}}],'menu':{'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0}}}
    def status(self):return copy.deepcopy(self.s)
    def checked(self,op,**kw):
     self.moves.append((op,kw));m=self.s['menu']
     if op=='close_menu':self.s['screen']='';return
     cell=m['slots'][kw['slot']];assert cell['item']==kw['expected_item'] and cell['count']==kw['expected_count']
     value={k:v for k,v in cell.items() if k!='slot'};cell.update(m['cursor']);m['cursor']=value
   c=Client();journal=c.out/'box.json';record={'slot':1,'item':'minecraft:shulker_box','initial_counts':{'minecraft:book':3},'remaining_counts':remaining,'temporary_position':[1,64,2],'stage':'broken','before_drop_uuids':[]}
   def pickup(client,drop,observation=None):
    self.assertEqual(drop['uuid'],'fresh-box');client.s['inventory']=[dict(box,slot=9)];client.s['entities']=[];return True
   def open_ender(client,*args):
    slots=[{'slot':i,'item':'minecraft:air','count':0} for i in range(63)];slots[27]=dict(box,slot=27)
    client.s['menu']={'id':10,'type':'ChestMenu','cursor':{'item':'minecraft:air','count':0},'slots':slots};client.s['screen']='ContainerScreen';return client.status()
   with patch('packed_supplies.collect_drop',side_effect=pickup),patch('packed_supplies.open_box',side_effect=open_ender):recover_and_return(c,record,[4,64,5],journal)
   self.assertEqual(record['stage'],'returned');self.assertEqual(record['drop_uuid'],'fresh-box')
   self.assertEqual(c.s['menu']['slots'][1]['contains'],box['contains']);self.assertEqual(c.s['menu']['cursor']['count'],0)
   self.assertEqual([kw['slot'] for op,kw in c.moves if op=='slot_click'],[27,1])


class EquipmentWithdrawalTest(unittest.TestCase):
 TOOL='minecraft:diamond_pickaxe'
 BOX='minecraft:pink_shulker_box'
 ENDER=[761021,64,797850]
 PAD=[761020,64,797848]

 def tool(self,durability,efficiency):
  return {'item':self.TOOL,'count':1,'max_stack':1,'durability':durability,'max_durability':1561,
          'enchantments':[{'id':'minecraft:efficiency','level':efficiency}]}

 def client(self,folder,*,qualified_existing=False,source_durability=1490,corrupt_receipt=False):
  owner=self
  class Client:
   def __init__(self):
    self.out=Path(folder);self.actions=[];self.placed=False;self.kind='InventoryMenu';self.menu_id=1;self.returned=False
    self.inventory=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(36)]
    for i,remaining in enumerate((152,596,632)):self.inventory[i]=dict(owner.tool(remaining,4),slot=i)
    if qualified_existing:self.inventory[3]=dict(owner.tool(1300,3),slot=3)
    self.box=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(27)]
    self.box[0]=dict(owner.tool(100,5),slot=0)
    self.box[1]=dict(owner.tool(source_durability,5),slot=1)
    self.box[2]=dict(owner.tool(source_durability,4),slot=2)
    self.ender=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(27)]
    self.ender[24]={'slot':24,'item':owner.BOX,'count':1,'max_stack':1,'contains':copy.deepcopy(self.box[:3])}
   def status(self):
    base=self.ender if self.kind=='ChestMenu' else self.box if self.kind=='ShulkerBoxMenu' else []
    slots=[dict(row,slot=i) for i,row in enumerate(base+self.inventory)]
    return copy.deepcopy({'inventory':self.inventory,'pos':[761022.5,65,797848.5],'screen':'' if self.kind=='InventoryMenu' else 'ContainerScreen',
                          'entities':[],'menu':{'id':self.menu_id,'type':self.kind,'slots':slots,'cursor':{'item':'minecraft:air','count':0}}})
   def checked(self,op,**args):
    self.actions.append((op,args))
    if op=='close_menu':self.kind='InventoryMenu';return self.status()
    if op in ('select_item','recover_shulker'):return self.status()
    if op!='slot_click' or args['kind']!='quick_move':raise AssertionError('Unexpected equipment operation')
    rows=self.ender if self.kind=='ChestMenu' else self.box;source=rows[args['slot']]
    assert source['item']==args['expected_item'] and source['count']==args['expected_count']
    destination=next(i for i,row in enumerate(self.inventory) if not row['count'])
    value=copy.deepcopy(source)
    if corrupt_receipt and self.kind=='ShulkerBoxMenu':value['durability']=100
    self.inventory[destination]=dict(value,slot=destination)
    rows[args['slot']]={'slot':args['slot'],'item':'minecraft:air','count':0,'max_stack':1}
    return self.status()
  return Client()

 def run_withdrawal(self,c,target):
  from packed_supplies import take_box
  def block(client,pos):
   if pos==[self.PAD[0],self.PAD[1]-1,self.PAD[2]]:return 'Block{minecraft:grass_block}[snowy=false]'
   if pos==self.PAD and client.placed:return 'Block{minecraft:pink_shulker_box}[facing=up]'
   return None
  def opening(client,pos,kind):client.kind=kind;client.menu_id+=1;return client.status()
  def place(client,pos,state,hand,faces,before_use=None):
   if before_use:before_use()
   self.assertEqual(self.BOX,hand);client.placed=True
   index=next(i for i,row in enumerate(client.inventory) if row['item']==self.BOX and row['count'])
   client.inventory[index]={'slot':index,'item':'minecraft:air','count':0,'max_stack':1}
  def returned(client,record,ender,journal):
   client.returned=True;record['stage']='returned';journal.write_text(json.dumps(record))
  with ExitStack() as stack:
   for name,value in [('block',block),('open_box',opening),('use_with_margin',place),('recover_and_return',returned)]:
    stack.enter_context(patch('packed_supplies.'+name,side_effect=value))
   stack.enter_context(patch('packed_supplies.register_cleanup'))
   stack.enter_context(patch('packed_supplies.time.sleep'))
   stack.enter_context(patch('packed_supplies.time.monotonic',side_effect=itertools.count(step=.5)))
   return take_box(c,self.ENDER,self.PAD,24,{self.TOOL:target},minimum_durability={self.TOOL:1000},
                   required_enchantments={self.TOOL:{'minecraft:efficiency':3}})

 def test_three_worn_tools_do_not_satisfy_an_additional_qualified_tool(self):
  with tempfile.TemporaryDirectory() as folder:
   c=self.client(folder);record=self.run_withdrawal(c,4)
   self.assertEqual({self.TOOL:1},record['taken']);self.assertTrue(c.returned)
   tools=[r for r in c.inventory if r['item']==self.TOOL and r['count']]
   self.assertEqual(4,len(tools));self.assertEqual(1,sum(r['durability']>=1000 for r in tools))
   self.assertEqual(1,c.box[2]['count']);self.assertEqual(0,c.box[1]['count'])
   self.assertEqual(24,record['slot']);self.assertEqual(1000,record['minimum_durability'][self.TOOL])

 def test_real_box_action_uses_shared_preflight_before_any_scan_or_inventory_mutation(self):
  from packed_supplies import take_box,workspace_requirement,PackedWorkspaceRequired,REQUIRED_FREE_SLOTS
  with tempfile.TemporaryDirectory() as folder:
   c=self.client(folder)
   for slot in range(3,34):
    c.inventory[slot]={'slot':slot,'item':'minecraft:cobblestone','count':64,'max_stack':64}
   expected=workspace_requirement(c.status())
   self.assertEqual(REQUIRED_FREE_SLOTS-1,expected['free_slots'])
   with patch('packed_supplies.block') as scan,patch('packed_supplies.open_box') as opened:
    with self.assertRaises(PackedWorkspaceRequired) as caught:
     take_box(c,self.ENDER,self.PAD,24,{self.TOOL:4})
   self.assertEqual(expected,caught.exception.receipt)
   scan.assert_not_called();opened.assert_not_called();self.assertFalse(c.actions)
   self.assertFalse((c.out/'packed-transfer-active.json').exists())

 def test_count_only_target_cannot_report_worn_equipment_as_sufficient(self):
  with tempfile.TemporaryDirectory() as folder:
   c=self.client(folder)
   with self.assertRaisesRegex(RuntimeError,'current total plus'):self.run_withdrawal(c,1)
   self.assertEqual([],c.actions)

 def test_insufficient_durability_is_deferred_without_taking_extra_items(self):
  with tempfile.TemporaryDirectory() as folder:
   c=self.client(folder,source_durability=999);record=self.run_withdrawal(c,4)
   self.assertEqual({},record['taken']);self.assertIn(self.TOOL,record['deferred']);self.assertTrue(c.returned)
   self.assertEqual(3,sum(r['count'] for r in c.inventory if r['item']==self.TOOL))

 def test_existing_good_tool_does_not_hide_wrong_new_tool_receipt(self):
  with tempfile.TemporaryDirectory() as folder:
   c=self.client(folder,qualified_existing=True,corrupt_receipt=True)
   with self.assertRaisesRegex(RuntimeError,'confirmation missing'):self.run_withdrawal(c,5)
   self.assertFalse(c.returned)
   self.assertEqual(0,c.box[1]['count']);self.assertEqual(1,c.box[2]['count'])
   self.assertEqual('placed',json.loads((c.out/'packed-transfer-active.json').read_text())['stage'])
   self.assertEqual(2,len([args for op,args in c.actions if op=='slot_click']))

if __name__=='__main__':unittest.main()
