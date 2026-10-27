import unittest,math
from pathlib import Path
from tempfile import TemporaryDirectory
from material_jobs.air_return_calibration import calibrate
class C:
 world='world';last=''
 def __init__(self,unknown=False):
  self.samples=0;self.unknown=unknown;self.actions=[]
  self.q={'pos':[.5,65.,.5],'health':20,'auto_log':True,'air_supply':300,'max_air_supply':300,'under_water':False}
 def request(self,op,**kw):
  self.last=op;self.actions.append(op)
  if op=='scan':
   rows=[{'pos':[x,y,z],'state':'Block{minecraft:water}[level=0]','block_entity':False}for x in range(kw['min'][0],kw['max'][0]+1)for y in range(kw['min'][1],kw['max'][1]+1)for z in range(kw['min'][2],kw['max'][2]+1)]
   return {'phase':'done','scan_cells_read':len(rows),'blocks':rows}
  if op=='air_return_set':self.q.update(air_budget_source='observed'if self.samples>=3 else'equipment',air_budget_samples=self.samples)
  if op in('navigate','walk'):
   if self.unknown and op=='walk':raise RuntimeError('unknown entry')
   submerged=self.q['under_water'];self.q['pos']=kw['target'];self.q['under_water']=kw['target'][1]<62
   self.q['air_supply']=290 if self.q['under_water'] else 300
   if submerged and not self.q['under_water']:self.samples+=1
  return {'phase':'done'}
 def checked(self,op,**kw):return self.request(op,**kw)
class CalibrationTest(unittest.TestCase):
 def test_only_native_observed_three_samples_complete_without_changing_floors(self):
  c=C()
  with TemporaryDirectory()as d:r=calibrate(c,Path(d)/'run',lambda:c.q)
  self.assertTrue(r['complete']);self.assertFalse(r['safety_floors_changed']);self.assertEqual(3,r['native_observed_budget']['air_budget_samples']);self.assertFalse(c.q['under_water']);self.assertEqual(300,c.q['air_supply'])
 def test_unknown_water_entry_is_not_repeated_or_followed_by_another_move(self):
  c=C(True)
  with TemporaryDirectory()as d,self.assertRaisesRegex(RuntimeError,'unknown entry'):calibrate(c,Path(d)/'run',lambda:c.q)
  self.assertEqual(1,c.actions.count('walk'));self.assertEqual('walk',c.actions[-1])
