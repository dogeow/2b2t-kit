import unittest
from material_jobs.cached_cave_water import surfaces,water_volume
class CachedWaterHintTest(unittest.TestCase):
 def test_volume_excludes_y31_and_requires_explicit_water_source_property(self):
  def tag(name,properties=None):
   entry={'Name':name}
   if properties is not None:entry['Properties']=properties
   return {'sections':[{'Y':1,'block_states':{'palette':[entry]}}]}
  self.assertEqual({'cached_low_water_cells':3840,'cached_source_cells':3840},water_volume(tag('minecraft:water',{'level':'0'})))
  for properties in (None,{'level':'1'},[]):
   self.assertEqual({'cached_low_water_cells':3840,'cached_source_cells':0},water_volume(tag('minecraft:water',properties)))
  self.assertEqual({'cached_low_water_cells':0,'cached_source_cells':0},water_volume(tag('minecraft:stone',{'level':'0'})))
 def test_only_water_with_two_explicit_air_cells_is_a_hint(self):
  palette=[{'Name':'minecraft:stone'},{'Name':'minecraft:water'},{'Name':'minecraft:cave_air'}];values=[0]*4096
  def put(x,y,z,v):values[(y*16+z)*16+x]=v
  put(4,10,5,1);put(4,11,5,2);put(4,12,5,2)
  packed=[sum(values[i+j]<<(j*4)for j in range(min(16,4096-i)))for i in range(0,4096,16)]
  packed=[v-(1<<64)if v>=(1<<63)else v for v in packed]
  tag={'xPos':10,'zPos':20,'sections':[{'Y':0,'block_states':{'palette':palette,'data':packed}}]}
  self.assertEqual([[164,10,325]],surfaces(tag))
  self.assertEqual([],surfaces({'xPos':0,'zPos':0,'sections':[{'Y':0,'block_states':{'palette':[{'Name':'minecraft:water'}]}}]}))
