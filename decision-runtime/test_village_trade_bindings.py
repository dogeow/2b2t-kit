import unittest,copy
from village_trade_bindings import bind_verified_book
class TradeBindingsTests(unittest.TestCase):
 def fixture(self):
  offer={'cost_a':{'item':'minecraft:emerald','count':16},'cost_b':{'item':'minecraft:book','count':1},'result':{'item':'minecraft:enchanted_book','count':1,'stored_enchantments':[{'id':'minecraft:channeling','level':1}]}}
  p={'enchantment_targets':{'minecraft:fire_aspect':2,'minecraft:unbreaking':3,'minecraft:channeling':1},'locked_trades':{'minecraft:fire_aspect':{'villager_uuid':'old','level':2,'proof':'old-proof'}}};l={'slots':[{'id':'old','occupant_uuid':'old','role':{'kind':'librarian'}},{'id':'new','occupant_uuid':'new','role':{'kind':'librarian','enchantment':'minecraft:unbreaking','level':3}}]};r={'locked':True,'uuid':'new','selected':{'enchantment':'minecraft:channeling','level':1,'offer':offer},'purchase':{'complete':True,'uuid':'new','trader_xp_before':0,'opening_request_id':'before'},'reopened_merchant':{'villager_uuid':'new','protocol':1,'trader_xp':2,'opening_request_id':'after','offers':[offer],'observation_scope':'current_server_received_merchant_menu_not_trade_completion'},'book_purchased':False,'payment':{'kind':'bookshelf_purchase','offer':{'cost_a':{'item':'minecraft:emerald','count':9},'cost_b':{'item':'minecraft:air','count':0}}}};return p,l,r
 def test_actual_counter_label_and_displaced_requested_role_are_both_retained(self):
  p,l,r=self.fixture();a,b=bind_verified_book(p,l,'new',r,'proof');self.assertEqual(b['slots'][1]['role']['enchantment'],'minecraft:channeling');self.assertEqual(a['unassigned_librarian_roles'],{'minecraft:unbreaking':3});self.assertEqual(b['slots'][0]['role']['enchantment'],'minecraft:fire_aspect');self.assertEqual(a['locked_trades']['minecraft:channeling']['actual_lock_payment'],{'minecraft:emerald':9});self.assertNotIn('minecraft:channeling',p['locked_trades'])
 def test_wrong_resident_or_unverified_or_nonmaximum_quote_never_mutates_inputs(self):
  for mode in ['resident','unverified','level','missing_book']:
   with self.subTest(mode=mode):
    p,l,r=self.fixture();original=copy.deepcopy((p,l))
    if mode=='resident':r['uuid']='other'
    if mode=='unverified':r['locked']=False
    if mode=='level':r['selected']['level']=2
    if mode=='missing_book':r['reopened_merchant']['offers']=[{'result':{'item':'minecraft:bookshelf','count':1}}]
    with self.assertRaises((ValueError,RuntimeError)):bind_verified_book(p,l,'new',r,'proof')
    self.assertEqual((p,l),original)
 def test_reapplying_the_same_receipt_is_metadata_only_and_idempotent(self):
  p,l,r=self.fixture();a,b=bind_verified_book(p,l,'new',r,'proof');self.assertEqual(bind_verified_book(a,b,'new',r,'proof'),(a,b))
if __name__=='__main__':unittest.main()
