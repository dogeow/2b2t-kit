import json
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from material_jobs import equipment as e


class ToolChest:
    """Normal unstackable quick-moves; exercise actual store and restore code."""
    world='world'
    def __init__(self,carried=1,existing=0):
        self.resource_cleanup={};self.moves=[]
        self.scope={'id':'materials-preserved-reply','bridge_version':4,'time':1000,'control_revision':2,
                    'server':'simpcraft.com:25565','dimension':'minecraft:overworld','player_uuid':'same-player',
                    'connected':True,'manual_movement':False,'health':20,'health_recovery_hold':False,
                    'safety_hold':{'active':False}}
        self.tool={'item':'minecraft:diamond_pickaxe','count':1,'durability':700,
                   'enchantments':[{'id':'minecraft:silk_touch','level':1}],'max_stack':1}
        self.slots=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(63)]
        for slot in list(range(existing))+list(range(27,27+carried)):
            self.slots[slot]=dict(self.tool,slot=slot)
    def status(self):
        return copy.deepcopy({**self.scope,'world_session':self.world,'inventory':[dict(row,slot=i) for i,row in enumerate(self.slots[27:])],
            'menu':{'id':1,'type':'ChestMenu','slots':self.slots,'cursor':{'item':'minecraft:air','count':0}}})
    def checked(self,op,**params):
        if op=='close_menu':return self.status()
        assert op=='slot_click' and params['kind']=='quick_move' and params['menu_id']==1
        source=self.slots[params['slot']]
        assert (source['item'],source['count'])==(params['expected_item'],params['expected_count'])
        pool=self.slots[:27] if params['slot']>=27 else self.slots[27:]
        destination=next(row for row in pool if not row['count'])
        self.moves.append((source['slot'],destination['slot']))
        self.slots[destination['slot']]=dict(source,slot=destination['slot'])
        self.slots[source['slot']]={'slot':source['slot'],'item':'minecraft:air','count':0,'max_stack':1}
        return self.status()


class EquipmentTests(unittest.TestCase):
    def test_task_boundary_keeps_only_confirmed_durable_non_silk_pickaxe_and_restores_variants(self):
        c=ToolChest(carried=0);variants=[
            {'item':'minecraft:diamond_pickaxe','count':1,'durability':142,'max_stack':1,
             'enchantments':[{'id':'minecraft:efficiency','level':4},{'id':'minecraft:fortune','level':3}]},
            {'item':'minecraft:diamond_pickaxe','count':1,'durability':1561,'max_stack':1,'enchantments':[]},
            {'item':'minecraft:diamond_pickaxe','count':1,'durability':482,'max_stack':1,'enchantments':[]},
            {'item':'minecraft:diamond_pickaxe','count':1,'durability':440,'max_stack':1,
             'enchantments':[{'id':'minecraft:silk_touch','level':1}]}]
        for slot,tool in enumerate(variants,27):c.slots[slot]=dict(tool,slot=slot)
        with tempfile.TemporaryDirectory() as d,patch.object(e,'open_grounded_chest',side_effect=lambda c,p:c.status()),patch.object(e,'take_box') as take:
            result=e.prepare(c,'minecraft:cobbled_deepslate',128,{'depots':[[1,2,3]]},Path(d),lambda:None)
            self.assertEqual('done',result['phase']);take.assert_not_called()
            carried=[r for r in c.status()['inventory'] if r['count']]
            self.assertEqual([1561],[r['durability'] for r in carried])
            saved=json.loads((Path(d)/'silk-tools.json').read_text())
            self.assertEqual([142,482,440],[r['tool']['durability'] for r in saved['tools']])
            self.assertEqual(['durability_below_minimum','durability_below_minimum','silk_touch'],[r['reason'] for r in saved['tools']])
            self.assertTrue(all(r['minimum_durability']==700 and r['state']=='stored' for r in saved['tools']))
            e.restore(c,Path(d)/'silk-tools.json')
            self.assertCountEqual([e.identity(r) for r in variants],[e.identity(r) for r in c.status()['inventory'] if r['count']])
            self.assertEqual(0,sum(r['count'] for r in c.slots[:27]))
            self.assertFalse(c.resource_cleanup)

    def test_durability_boundary_and_legacy_silk_only_behavior(self):
        c=ToolChest(carried=0)
        for slot,remaining in ((27,699),(28,700),(29,1561)):
            c.slots[slot]={'slot':slot,'item':'minecraft:diamond_pickaxe','count':1,'durability':remaining,'enchantments':[],'max_stack':1}
        with tempfile.TemporaryDirectory() as d,patch.object(e,'open_grounded_chest',side_effect=lambda c,p:c.status()):
            e.store_silk(c,{'depots':[[1,2,3]]},Path(d))
            self.assertEqual([],c.moves)
            e.store_silk(c,{'depots':[[1,2,3]]},Path(d),minimum=700)
            self.assertEqual([700,1561],[r['durability'] for r in c.status()['inventory'] if r['count']])

    def test_missing_qualified_pickaxe_never_stores_all_remaining_tools(self):
        c=ToolChest(carried=0)
        c.slots[27]={'slot':27,'item':'minecraft:diamond_pickaxe','count':1,'durability':142,'enchantments':[],'max_stack':1}
        with tempfile.TemporaryDirectory() as d,patch.object(e,'open_grounded_chest') as open:
            result=e.prepare(c,'minecraft:cobbled_deepslate',128,{'depots':[[1,2,3]]},Path(d),lambda:None)
        self.assertEqual('blocked',result['phase']);open.assert_not_called();self.assertEqual([],c.moves)

    def test_low_durability_transfer_keeps_recovery_registration_when_ack_is_unknown(self):
        c=ToolChest(carried=0)
        c.slots[27]={'slot':27,'item':'minecraft:diamond_pickaxe','count':1,'durability':142,'enchantments':[],'max_stack':1}
        def unconfirmed(*args,**kwargs):
            self.assertEqual(1,len(c.resource_cleanup));raise RuntimeError('unconfirmed low durability transfer')
        with tempfile.TemporaryDirectory() as d,patch.object(e,'open_grounded_chest',side_effect=lambda c,p:c.status()),patch.object(e.InventorySession,'click',side_effect=unconfirmed):
            with self.assertRaisesRegex(RuntimeError,'unconfirmed'):e.store_silk(c,{'depots':[[1,2,3]]},Path(d),minimum=700)
            self.assertEqual('storing',json.loads((Path(d)/'silk-tools.json').read_text())['tools'][0]['state'])
            with self.assertRaisesRegex(RuntimeError,'未确认'):e.store_silk(c,{'depots':[[1,2,3]]},Path(d),minimum=700)

    def test_silk_tool_identity_ignores_slot_but_not_damage_or_enchantment(self):
        tool={'slot':2,'item':'minecraft:diamond_pickaxe','count':1,'durability':700,
              'enchantments':[{'id':'minecraft:silk_touch','level':1}]}
        self.assertTrue(e.is_silk(tool))
        self.assertEqual(e.identity(tool),e.identity(dict(tool,slot=51)))
        self.assertNotEqual(e.identity(tool),e.identity(dict(tool,durability=699)))
        self.assertNotEqual(e.identity(tool),e.identity(dict(tool,enchantments=[])))

    def test_unknown_store_click_registers_recovery_before_mutation(self):
        tool={'slot':2,'item':'minecraft:diamond_pickaxe','count':1,'durability':700,
              'enchantments':[{'id':'minecraft:silk_touch','level':1}]}
        slots=[{'slot':0,'item':'minecraft:air','count':0}]+[
            dict(tool,slot=1)]+[{'slot':i,'item':'minecraft:air','count':0} for i in range(2,37)]
        state={'inventory':[tool],'menu':{'id':3,'slots':slots,'cursor':{'count':0}}}
        class C:
            world='world';resource_cleanup={}
            def status(self):return state
        c=C()
        def clicked(*args,**kw):
            self.assertEqual(len(c.resource_cleanup),1)
            raise RuntimeError('unacknowledged click')
        with tempfile.TemporaryDirectory() as d, patch.object(e,'open_grounded_chest',return_value=state), \
                patch.object(e.InventorySession,'click',side_effect=clicked):
            with self.assertRaisesRegex(RuntimeError,'unacknowledged'):
                e.store_silk(c,{'depots':[[1,2,3]]},Path(d))
            saved=json.loads((Path(d)/'silk-tools.json').read_text())
            self.assertEqual(saved['tools'][0]['state'],'storing')
            self.assertEqual(saved['tools'][0]['pos'],[1,2,3])

    def test_identical_existing_or_multiple_carried_tools_return_from_exact_saved_slots(self):
        for carried,existing in ((1,1),(2,0)):
            with self.subTest(carried=carried,existing=existing),tempfile.TemporaryDirectory() as d:
                c=ToolChest(carried,existing);path=Path(d)/'silk-tools.json'
                with patch.object(e,'open_grounded_chest',side_effect=lambda c,p:c.status()):
                    e.store_silk(c,{'depots':[[1,2,3]]},Path(d))
                    stored=json.loads(path.read_text())['tools']
                    destinations=[entry['chest_slot'] for entry in stored]
                    self.assertEqual(list(range(existing,existing+carried)),destinations)
                    self.assertEqual(0,sum(row['count'] for row in c.slots[27:]))
                    e.restore(c,path)
                self.assertEqual(carried,sum(row['count'] for row in c.slots[27:]))
                self.assertEqual(existing,sum(row['count'] for row in c.slots[:27]))
                self.assertEqual(destinations,[source for source,target in c.moves[carried:]])
                self.assertTrue(all(entry['state']=='returned' for entry in json.loads(path.read_text())['tools']))
                self.assertNotIn(str(path),c.resource_cleanup)

    def test_changed_saved_tool_slot_cannot_redirect_recovery_to_identical_neighbor(self):
        with tempfile.TemporaryDirectory() as d:
            c=ToolChest(carried=1,existing=1);path=Path(d)/'silk-tools.json'
            with patch.object(e,'open_grounded_chest',side_effect=lambda c,p:c.status()):
                e.store_silk(c,{'depots':[[1,2,3]]},Path(d))
                slot=json.loads(path.read_text())['tools'][0]['chest_slot']
                c.slots[slot]={'slot':slot,'item':'minecraft:diamond_sword','count':1,'max_stack':1}
                calls=len(c.moves)
                with self.assertRaisesRegex(RuntimeError,'原槽位或属性改变'):
                    e.restore(c,path)
            self.assertEqual(calls,len(c.moves))
            self.assertEqual('minecraft:diamond_pickaxe',c.slots[0]['item'])
            self.assertEqual('stored',json.loads(path.read_text())['tools'][0]['state'])


class ReconnectedEquipmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'silk-tools.json'
        self.c=ToolChest(carried=2)
        self.c.root=Path(self.temp.name)/'automation';self.c.root.mkdir()
        self.open=patch.object(e,'open_grounded_chest',side_effect=lambda c,p:c.status()).start()
        self.addCleanup(patch.stopall)
        e.store_silk(self.c,{'depots':[[1,2,3]]},self.path.parent)
        self.old=self.c.status();self.c.world='reconnected-world';self.c.scope['time']=2000
        self.c.moves.clear();self.open.reset_mock()

    def journal(self):return json.loads(self.path.read_text())

    def reject(self,pattern=''):
        before=self.path.read_text()
        with self.assertRaisesRegex(RuntimeError,pattern):
            e.restore_after_reconnect(self.c,self.path,self.old)
        self.assertEqual(before,self.path.read_text());self.assertFalse(self.c.moves)
        self.open.assert_not_called()

    def test_same_player_reconnect_restores_exact_slots_without_rewriting_original_world(self):
        self.c.scope['server']='SiMpCrAfT.CoM'
        e.restore_after_reconnect(self.c,self.path,self.old)
        saved=self.journal()
        self.assertEqual('world',saved['world_session'])
        self.assertTrue(all(t['state']=='returned' for t in saved['tools']))
        self.assertEqual([(0,27),(1,28)],self.c.moves)
        self.assertFalse(self.c.resource_cleanup)
        self.assertEqual(2,sum(r['count'] for r in self.c.slots[27:]))
        self.assertEqual(0,sum(r['count'] for r in self.c.slots[:27]))
        self.assertEqual({'previous_world_session':'world','world_session':'reconnected-world',
                         'server':'simpcraft.com','dimension':'minecraft:overworld','player_uuid':'same-player',
                         'previous_snapshot_id':'materials-preserved-reply','previous_observed_at':1000,
                         'observed_at':2000},saved['recoveries'][0])

    def test_same_world_uses_original_restore_without_reconnect_authorization(self):
        self.c.world='world'
        e.restore_after_reconnect(self.c,self.path,None)
        self.assertNotIn('recoveries',self.journal())
        self.assertEqual(2,len(self.c.moves))

    def test_changed_player_server_dimension_or_missing_player_refuses_before_open(self):
        for key,value in (('player_uuid','other-player'),('player_uuid',''),('server','other.example'),
                          ('dimension','minecraft:the_nether'),('connected',False)):
            with self.subTest(key=key,value=value):
                saved=self.c.scope[key];self.c.scope[key]=value
                self.reject('不一致');self.c.scope[key]=saved

    def test_incomplete_or_wrong_original_native_reply_is_not_scope_authorization(self):
        original=copy.deepcopy(self.old)
        for key,value in (('world_session','unrelated-world'),('id',''),('player_uuid',''),('bridge_version',None),
                          ('inventory',None),('menu',{}),('time',0)):
            with self.subTest(key=key):
                self.old={**original,key:value};self.reject('完整原生回执')
        self.old=original

    def test_unknown_storing_or_returning_refuses_even_when_earlier_tool_is_stored(self):
        original=self.journal()
        for unknown in ('storing','returning','missing'):
            with self.subTest(state=unknown):
                value=copy.deepcopy(original);value['tools'][1]['state']=unknown
                self.path.write_text(json.dumps(value));self.reject('结果不确定')

    def test_manual_unhealthy_or_native_hold_refuses_without_cleanup_or_unlock(self):
        for change in ({'manual_movement':True},{'manual_movement':None},{'health':17.9},
                       {'health':float('nan')},{'health_recovery_hold':True},
                       {'safety_hold':{'active':True}},{'safety_hold':{}}):
            with self.subTest(change=change):
                original=copy.deepcopy(self.c.scope);self.c.scope.update(change)
                self.reject('未确认健康');self.c.scope=original

    def test_script_health_hold_is_honored_and_never_cleared(self):
        hold=self.c.root/'material-health-hold.json'
        hold.write_text(json.dumps({'active':True,'time':1500}))
        self.reject('Material task exited for health')
        self.assertTrue(json.loads(hold.read_text())['active'])

    def test_missing_exact_slot_or_changed_variant_never_substitutes_neighbor(self):
        saved=self.journal();del saved['tools'][0]['chest_slot'];self.path.write_text(json.dumps(saved))
        self.reject('准确仓库槽位')

    def test_variant_changed_after_reconnect_keeps_original_stored_state(self):
        for field,value in (('durability',699),('enchantments',[]),('item','minecraft:netherite_pickaxe')):
            with self.subTest(field=field):
                original=copy.deepcopy(self.c.slots[0]);self.c.slots[0][field]=value
                with self.assertRaisesRegex(RuntimeError,'原槽位或属性改变'):
                    e.restore_after_reconnect(self.c,self.path,self.old)
                self.assertFalse(self.c.moves)
                self.assertTrue(all(t['state']=='stored' for t in self.journal()['tools']))
                self.c.slots[0]=original

    def test_full_bag_keeps_stored_and_never_sends_click(self):
        for slot in range(27,63):
            self.c.slots[slot]={'slot':slot,'item':'minecraft:cobblestone','count':64,'max_stack':64}
        with self.assertRaisesRegex(RuntimeError,'没有空槽'):
            e.restore_after_reconnect(self.c,self.path,self.old)
        self.assertFalse(self.c.moves)
        self.assertTrue(all(t['state']=='stored' for t in self.journal()['tools']))

    def test_one_free_slot_returns_one_and_leaves_other_stored_then_retries_only_remaining(self):
        for slot in range(28,63):
            self.c.slots[slot]={'slot':slot,'item':'minecraft:cobblestone','count':64,'max_stack':64}
        with self.assertRaisesRegex(RuntimeError,'没有空槽'):
            e.restore_after_reconnect(self.c,self.path,self.old)
        self.assertEqual(['returned','stored'],[t['state'] for t in self.journal()['tools']])
        self.assertEqual([(0,27)],self.c.moves)
        self.c.slots[28]={'slot':28,'item':'minecraft:air','count':0,'max_stack':1}
        e.restore_after_reconnect(self.c,self.path,self.old)
        self.assertEqual([(0,27),(1,28)],self.c.moves)

    def test_ambiguous_transfer_needs_source_decrease_inventory_gain_and_empty_cursor(self):
        def check_once(c,predicate):
            self.assertFalse(predicate(c.status()))
            raise RuntimeError('unconfirmed transfer')
        for missing in ('source_decrease','inventory_gain','empty_cursor'):
            with self.subTest(missing=missing):
                saved=self.journal();saved['tools']=[dict(saved['tools'][0],state='stored')]
                self.path.write_text(json.dumps(saved));slots=copy.deepcopy(self.c.slots)
                original_status=self.c.status
                def move(*args,**kwargs):
                    if missing!='source_decrease':self.c.slots[0]={'slot':0,'item':'minecraft:air','count':0,'max_stack':1}
                    if missing!='inventory_gain':self.c.slots[27]=dict(self.c.tool,slot=27)
                    if missing=='empty_cursor':
                        def cursor_status():
                            s=original_status();s['menu']['cursor']=dict(self.c.tool);return s
                        self.c.status=cursor_status
                with patch.object(e.InventorySession,'click',side_effect=move) as click,patch.object(e,'wait',side_effect=check_once):
                    with self.assertRaisesRegex(RuntimeError,'unconfirmed transfer'):
                        e.restore_after_reconnect(self.c,self.path,self.old)
                    self.assertEqual(1,click.call_count)
                self.assertEqual('returning',self.journal()['tools'][0]['state'])
                self.c.slots=slots;self.c.status=original_status


if __name__=='__main__':
    unittest.main()
