import unittest
from renewable_trade_budget import funding_priority
class FundingPurposeTests(unittest.TestCase):
 def test_reserve_never_invents_a_priority(self):
  self.assertEqual(funding_priority({},[],reserve_only=True),{'funding_purpose':'future_lock_reserve'})
 def test_missing_wanted_quote_does_not_implicitly_allow_funding(self):
  with self.assertRaises(RuntimeError):funding_priority({},[])
 def test_pending_quote_cannot_be_downgraded_to_reserve(self):
  for seed in [{'priority_enchantment':'minecraft:smite'},{'preserved_wanted_quote':{'result':{}}}]:
   with self.assertRaises(RuntimeError):funding_priority(seed,[],reserve_only=True)
 def test_existing_quote_maintains_exact_resident_and_book(self):
  waiting={'merchant':{'villager_uuid':'v'},'result':{'waiting_for_payment':True,'selected':{'enchantment':'minecraft:smite','level':5}}}
  value=funding_priority({'quotes':[waiting]},[{'id':'ES08','occupant_uuid':'v'}])
  self.assertEqual(value['priority_slot'],'ES08');self.assertEqual(value['priority_level'],5);self.assertEqual(value['preserved_wanted_quote'],waiting)
