import unittest,tempfile,json
from pathlib import Path
from village_keeper_registration import register
class KeeperRegistrationTest(unittest.TestCase):
 def fixture(self,base):
  p=dict(enchantment_targets={'minecraft:protection':4},optional_enchantment_targets={},locked_trades={},locked_optional_trades={},confirmed_duplicate_keepers={},enchantment_duplicate_policy={});(base/'project-state.json').write_text(json.dumps(p));slot=dict(id='WS03',occupant_uuid='npc');(base/'layout-plan.json').write_text(json.dumps({'slots':[slot]}));(base/'ENCHANTMENT-KEEPERS.md').write_text('进度：必需0/22；顺带0/11\n| 保护 | 4 | 必需 | 待补齐 | — |\n')
  book=dict(item='minecraft:enchanted_book',count=1,stored_enchantments=[dict(id='minecraft:protection',level=4)]);offer=dict(result=book,cost_a=dict(item='minecraft:emerald',count=12),cost_b=dict(item='minecraft:book',count=1));payment=dict(cost_a=dict(item='minecraft:paper',count=24),cost_b=dict(item='minecraft:air',count=0));m=dict(villager_uuid='npc',protocol=1,owned=True,owner_task='task',trader_xp=2,opening_request_id='reopened',observation_scope='current_server_received_merchant_menu_not_trade_completion',offers=[offer]);r=dict(complete=True,pending=None,world_session='world',uuid='npc',locked=True,selected=dict(enchantment='minecraft:protection',level=4,offer=offer),reopened_merchant=m,book_purchased=False,purchase=dict(complete=True,uuid='npc',trader_xp_before=0,opening_request_id='before'),payment=dict(kind='paper_sale',offer=payment));out=base/'owner';out.mkdir();q=out/'native-result.json';q.write_text(json.dumps(r));return slot,r,out,q
 def test_real_paper_sale_records_supplier_without_claiming_book_purchase(self):
  with tempfile.TemporaryDirectory()as tmp:
   base=Path(tmp);slot,r,out,q=self.fixture(base);register(base,out,slot,r,q,'keeper.json','world');p=json.loads((base/'project-state.json').read_text());row=p['locked_trades']['minecraft:protection'];self.assertFalse(row['book_purchased']);self.assertEqual({'minecraft:paper':24},row['actual_lock_payment']);self.assertIn('已核验锁定 | WS03',(base/'ENCHANTMENT-KEEPERS.md').read_text());before=(base/'project-state.json').read_text()
   with self.assertRaises(RuntimeError):register(base,out,slot,r,q,'keeper2.json','world')
   self.assertEqual(before,(base/'project-state.json').read_text());self.assertFalse((out/'keeper2.json').exists())
 def test_stale_world_zero_xp_or_changed_receipt_never_changes_registry(self):
  for mode in['world','xp','receipt']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as tmp:
    base=Path(tmp);slot,r,out,q=self.fixture(base);before=(base/'project-state.json').read_text()
    if mode=='world':r['world_session']='other';q.write_text(json.dumps(r))
    elif mode=='xp':r['reopened_merchant']['trader_xp']=0;q.write_text(json.dumps(r))
    else:q.write_text('{}')
    with self.assertRaises(RuntimeError):register(base,out,slot,r,q,'keeper.json','world')
    self.assertEqual(before,(base/'project-state.json').read_text());self.assertFalse((out/'keeper.json').exists())
 def test_missing_markdown_row_is_preflight_not_partial_registration(self):
  with tempfile.TemporaryDirectory()as tmp:
   base=Path(tmp);slot,r,out,q=self.fixture(base);(base/'ENCHANTMENT-KEEPERS.md').write_text('missing');before=(base/'project-state.json').read_text()
   with self.assertRaises(RuntimeError):register(base,out,slot,r,q,'keeper.json','world')
   self.assertEqual(before,(base/'project-state.json').read_text());self.assertFalse((out/'keeper.json').exists())
