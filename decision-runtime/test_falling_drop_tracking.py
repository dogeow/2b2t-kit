import unittest
from falling_drop_tracking import observe,intercept_pose
class TrackingTest(unittest.TestCase):
 def setUp(self):self.args=dict(item='minecraft:magma_block',expected_count=1,before=15,current=15,entities=[],known_ids=set(),origin=[0,196,0])
 def item(self,uid='new',pos=None,count=1):return {'type':'minecraft:item','uuid':uid,'pos':pos or [0,195,0],'stack':{'item':'minecraft:magma_block','count':count}}
 def test_find_one_exact_new_item(self):self.args['entities']=[self.item()];self.assertEqual(('track','new'),(observe(**self.args).state,observe(**self.args).uuid))
 def test_old_and_far_items_do_not_become_original(self):
  self.args.update(entities=[self.item('old'),self.item('far',[20,195,0])],known_ids={'old'});self.assertEqual('unobserved',observe(**self.args).state)
 def test_no_switch_or_fake_expiry(self):
  self.args.update(tracked_uuid='original',entities=[self.item('other')]);x=observe(**self.args);self.assertEqual(('unobserved','original'),(x.state,x.uuid))
 def test_exact_gain_confirms_only_when_original_not_visible(self):
  self.args.update(current=16,tracked_uuid='original');self.assertEqual('collected',observe(**self.args).state);self.args['entities']=[self.item('original')];self.assertEqual('stop',observe(**self.args).state)
 def test_ambiguous_or_merged_items_stop(self):
  self.args['entities']=[self.item('a'),self.item('b')];self.assertEqual('stop',observe(**self.args).state);self.args['entities']=[self.item(count=2)];self.assertEqual('stop',observe(**self.args).state)
 def test_bad_inventory_and_geometry_refused(self):
  self.args['current']=17;self.assertEqual('stop',observe(**self.args).state);self.assertEqual([1.0,193.0,2.0],intercept_pose([1,195,2],minimum_y=130));self.assertIsNone(intercept_pose([1,130,2],minimum_y=130))
if __name__=='__main__':unittest.main()
