import gzip,hashlib,tempfile,unittest
from pathlib import Path
from workstation_schematic import create
from material_jobs.bobby_snow_cache import _NBTReader
class WorkstationSchematicTests(unittest.TestCase):
 def test_single_block_roundtrip_does_not_double_apply_absolute_origin(self):
  with tempfile.TemporaryDirectory()as tmp:
   out=Path(tmp)/'projection';m=create(out,[761022,65,797814],'north',5000,file='kit/workpoint.litematic',name='Independent workpoint');raw=Path(m['source']).read_bytes();nbt=_NBTReader(gzip.decompress(raw)).root();r=nbt['Regions']['Counters'];self.assertEqual(r['Position'],{'x':0,'y':0,'z':0});self.assertEqual(r['Size'],{'x':1,'y':1,'z':1});self.assertEqual(r['BlockStates'],[1]);self.assertEqual(r['BlockStatePalette'][1]['Name'],'minecraft:lectern');self.assertEqual(r['BlockStatePalette'][1]['Properties']['facing'],'north');self.assertEqual(m['origin'],[761022,65,797814]);self.assertEqual(nbt['MinecraftDataVersion'],5000);self.assertEqual(m['sha256'],hashlib.sha256(raw).hexdigest());self.assertEqual(nbt['Metadata']['TotalBlocks'],1)
 def test_existing_projection_is_never_overwritten(self):
  with tempfile.TemporaryDirectory()as tmp:
   out=Path(tmp)/'projection';m=create(out,[0,65,0],'south',5000,file='kit/a.litematic',name='A');before=Path(m['source']).read_bytes()
   with self.assertRaises(FileExistsError):create(out,[5,65,5],'north',5000,file='kit/b.litematic',name='B')
   self.assertEqual(Path(m['source']).read_bytes(),before)
 def test_invalid_origin_and_paths_fail_before_creating_any_artifact(self):
  with tempfile.TemporaryDirectory()as tmp:
   for i,(origin,file)in enumerate([([True,65,0],'kit/a.litematic'),([0,65.1,0],'kit/a.litematic'),([0,65,0],'../a.litematic'),([0,65,0],'/tmp/a.litematic')]):
    out=Path(tmp)/str(i)
    with self.subTest(origin=origin,file=file),self.assertRaises(ValueError):create(out,origin,'north',5000,file=file,name='A')
    self.assertFalse(out.exists())
