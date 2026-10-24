import unittest
from test_village_adult_enclosure import EnclosureTests,cube,partial
from librarian_room import LibrarianRoom
from librarian_quote_enclosure import require
class PublicQuoteEnclosureTests(unittest.TestCase):
 def fixture(self):
  rows,_=EnclosureTests().fixture();rows[(0,64,0)]=cube();rows[(0,65,0)]=partial('dark_oak_slab','type=bottom,waterlogged=false')
  slot=dict(id='WS01',occupant_uuid='v',work_block=[0,64,0],actual_work_block=[0,64,3],counter_block=[0,64,0],counter_configuration='bottom_slab_and_full_upper_cap')
  actor=dict(uuid='v',type='minecraft:villager',health=20,is_baby=False,bounds=dict(min=[.2,64,1.2],max=[.8,65.95,1.8]))
  return LibrarianRoom.from_slot(slot),slot,dict(blocks=[dict(pos=list(k),**v)for k,v in rows.items()],scan_entities=[actor])
 def test_real_public_counter_allows_read_without_relaxing_workpoint_reset_check(self):
  r,s,f=self.fixture();self.assertEqual('quote_observation_only_not_lectern_reset',require(r,s,f)['scope'])
  with self.assertRaises(ValueError):r.require_caps({tuple(v['pos']):v for v in f['blocks']})
 def test_open_perimeter_or_wrong_body_never_admitted(self):
  for change in ['wall','body','counter','wet']:
   r,s,f=self.fixture()
   if change=='wall':f['blocks']=[v for v in f['blocks']if v['pos']not in [[-1,64,2],[-1,65,2]]]
   if change=='body':f['scan_entities'][0]['bounds']['min'][2]=-.1
   if change=='counter':s['counter_block']=[1,64,0]
   if change=='wet':next(v for v in f['blocks']if v['pos']==[0,65,0])['state']='Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=true]'
   with self.subTest(change=change),self.assertRaises(ValueError):require(r,s,f)

 def test_legacy_label_without_separate_counter_keeps_original_workpoint_check(self):
  r,s,f=self.fixture();s.pop('counter_block')
  with self.assertRaises(ValueError):require(r,s,f)
  s['actual_work_block']=[0,64,0];r=LibrarianRoom.from_slot(s)
  self.assertEqual('workpoint_caps',require(r,s,f)['kind'])
