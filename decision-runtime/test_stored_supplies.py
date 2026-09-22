import unittest
from stored_supplies import requests_from_receipts,recover_stored
class StoredSuppliesTest(unittest.TestCase):
 def test_deduplicates_sources_and_skips_carried_targets(self):
  receipt={'minecraft:lantern':[{'count':9,'pos':[1,2,3]}],'minecraft:barrel':[{'count':10,'pos':[1,2,3]}]}
  self.assertEqual(requests_from_receipts([receipt,receipt],{'minecraft:lantern':9,'minecraft:barrel':10},{'minecraft:barrel':10}),[([1,2,3],{'minecraft:lantern':9})])
 def test_visit_done_does_not_claim_missing_stock_was_supplied(self):
  class Client:
   def status(self):return {'projection_selection':{'key':'same'},'inventory':[]}
   def fetch(self,pos,items):return {'phase':'done'}
  result=recover_stored(Client(),'same',{'minecraft:lantern':9},[{'minecraft:lantern':[{'count':9,'pos':[1,2,3]}]}])
  self.assertEqual(result['remaining_targets'],{'minecraft:lantern':9});self.assertEqual(result['visits'][0]['received']['minecraft:lantern'],0)
if __name__=='__main__':unittest.main()
