import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from village_feeding import feed
class SleepingStandoff(unittest.TestCase):
 def test_real_feed_loop_preserves_food_before_approaching_a_sleeping_adult(self):
  class Owner:
   world='w'
   def __init__(self):self.calls=[];self.tick=0
   def status(self):
    self.tick+=1
    return {'world_session':'w','time':self.tick,'health':20,'pos':[1.5,64,3.5],'player_uuid':'self','hand':{'item':'minecraft:bread','count':6},'inventory':[{'slot':0,'item':'minecraft:bread','count':6,'max_stack':64}],'loaded_villagers':{'villagers':[{'uuid':'parent','pos':[3.5,64.5625,3.5],'health':20,'is_baby':False,'visible':True}]}}
   def native(self,op,**params):
    self.calls.append(op)
    if op not in ('scan','select_item'):raise AssertionError('No movement or Q should follow sleeping observation')
    return {'phase':'done','blocks':[]}
  owner=Owner()
  with tempfile.TemporaryDirectory()as directory,patch('village_feeding.feeding_containment',return_value={'verified':True}),patch('village_feeding.read',return_value={'villagers':[{'uuid':'parent','sleeping':True}]}):
   result=feed(owner,Path(directory),{'parent':3},Path(directory)/'feeding.json',[0,64,0],[7,67,7],ground_standoff=True)
  self.assertEqual(['scan','select_item'],owner.calls);self.assertEqual('parent',result['waiting_for_awake_founder']);self.assertFalse(result['complete']);self.assertEqual(6,result['bread_actual']);self.assertIsNone(result['pending_food']);self.assertIsNone(result['pending']);self.assertEqual({'parent':0},result['delivered'])
