import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from village_project import execute

class PackedProfileSupportTests(unittest.TestCase):
 def run_profile(self,profile):
  with tempfile.TemporaryDirectory()as d:
   p=Path(d)/'profile.json';p.write_text(json.dumps(profile));c=Mock();c.status.return_value={'time':1,'inventory':[]};menu={'time':1,'inventory':[],'menu':{'slots':[{'count':0} for _ in range(27)]}};target={'minecraft:ghast_tear':1}
   with patch('village_project._safe'),patch('packed_supplies.open_box',return_value=menu),patch('packed_supplies.choose_box',return_value=(1,12,target)),patch('packed_supplies.take_box',return_value={'stage':'returned'}) as take:
    result=execute(c,{'action':'take_packed_materials','profile':str(p),'targets':target},d,lambda:{})
   return result,take.call_args
 def test_pinned_oak_is_passed_to_native_workspace_check(self):
  result,call=self.run_profile({'ender_chest':[1,2,3],'shulker_pad':[4,5,6],'shulker_pad_support_state':'Block{minecraft:oak_planks}'})
  self.assertTrue(result['complete']);self.assertEqual(call.kwargs['expected_pad_support'],'Block{minecraft:oak_planks}')
 def test_default_stays_grass_only(self):
  _,call=self.run_profile({'ender_chest':[1,2,3],'shulker_pad':[4,5,6]});self.assertIsNone(call.kwargs['expected_pad_support'])
 def test_arbitrary_support_rejected_before_open(self):
  with self.assertRaises(ValueError):self.run_profile({'ender_chest':[1,2,3],'shulker_pad':[4,5,6],'shulker_pad_support_state':'Block{minecraft:lava}'})
if __name__=='__main__':unittest.main()
