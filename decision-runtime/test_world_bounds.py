import json,tempfile,unittest
from pathlib import Path
from material_jobs.world_bounds import check,permits

RULE={'schema':1,'server':'simpcraft.com','dimension':'minecraft:overworld',
      'min_x':-800000,'max_x':800000,'min_z':-800000,'max_z':800000,'margin':32}
class WorldBoundsTest(unittest.TestCase):
    def test_original_map_is_inside_but_southern_desert_is_outside(self):
        self.assertTrue(permits(RULE,[761021,220,797829]))
        for p in ([761021,220,801157],[799968,220,0],[-800000,220,0],[0,220,float('nan')]):
            self.assertFalse(permits(RULE,p))
    def test_rejects_before_dispatch_and_does_not_block_safety_reads_or_another_server(self):
        with tempfile.TemporaryDirectory()as t:
            root=Path(t)/'automation';root.mkdir();(root.parent/'world-travel-bounds.json').write_text(json.dumps(RULE))
            state={'server':'simpcraft.com:25565','dimension':'minecraft:overworld'}
            with self.assertRaisesRegex(RuntimeError,'世界边界'):
                check(root,state,'navigate',{'target':[761021,220,801157]})
            check(root,state,'safe_logout',{});check(root,state,'snapshot',{})
            check(root,{**state,'server':'another.example'},'navigate',{'target':[0,220,900000]})
    def test_every_walk_path_waypoint_is_checked(self):
        with tempfile.TemporaryDirectory()as t:
            root=Path(t)/'automation';root.mkdir();(root.parent/'world-travel-bounds.json').write_text(json.dumps(RULE))
            with self.assertRaises(RuntimeError):
                check(root,{'server':'simpcraft.com','dimension':'minecraft:overworld'},'walk_path',{'path':[[0,64,0],[0,64,800000]]})

    def test_projection_air_seed_checks_native_target_parameter(self):
        with tempfile.TemporaryDirectory()as t:
            root=Path(t)/'automation';root.mkdir();(root.parent/'world-travel-bounds.json').write_text(json.dumps(RULE))
            state={'server':'simpcraft.com','dimension':'minecraft:overworld'}
            check(root,state,'projection_air_seed',{'target':[761060,64,797758]})
            with self.assertRaises(RuntimeError):
                check(root,state,'projection_air_seed',{'target':[761060,64,801157],'pos':[0,64,0]})
            with self.assertRaises(RuntimeError):
                check(root,state,'projection_air_seed',{'pos':[761060,64,797758]})

if __name__=='__main__':unittest.main()
