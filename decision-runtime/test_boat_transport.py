import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from boat_transport import _available,_journal,owned,dry_support

class BoatTransportTests(unittest.TestCase):
    def test_known_dry_village_path_supports_a_boat_without_accepting_other_partial_blocks(self):
        path={'state':'Block{minecraft:dirt_path}','solid':False,'fluid':False,'block_entity':False}
        self.assertTrue(dry_support(path))
        self.assertTrue(dry_support({'state':'Block{minecraft:grass_block}[snowy=false]','solid':True}))
        for update in ({'fluid':True},{'block_entity':True},{'state':'Block{minecraft:water}'},
                       {'state':'Block{minecraft:short_grass}'},{'state':'Block{minecraft:oak_slab}[type=bottom,waterlogged=false]'}):
            self.assertFalse(dry_support({**path,**update}))
        self.assertFalse(dry_support({}))
    def test_a_different_output_folder_or_server_port_alias_cannot_replay_an_unknown_boat_use(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory)
            c=SimpleNamespace(root=root/'native',world='w',server='example.com',status=lambda:{'dimension':'minecraft:overworld'})
            c.root.mkdir();path,book=_journal(c,'support:[1, 63, 2]',root/'original','place',{'minecraft:oak_boat':2})
            c.server='example.com:25565'
            with self.assertRaises(RuntimeError):_available(c,'support:[1, 63, 2]','place')
            with self.assertRaises(RuntimeError):_journal(c,'support:[1, 63, 2]',root/'another','place',{'minecraft:oak_boat':2})
            self.assertFalse((root/'another').exists())
            book.update(complete=True,pending=None);path.write_text(json.dumps(book))
            self.assertIsNotNone(_available(c,'support:[1, 63, 2]','place'))
    def test_old_world_or_foreign_material_owner_cannot_start_a_boat_action(self):
        c=SimpleNamespace(world='w',task='t')
        q={'connected':True,'world_session':'w','health':20,'food':20,'guard_armed':True,'guard_pve_only':True,'village_boat_protocol':1,
           'supervision_lease':{'kind':'materials','job_session':'t','world_session':'w'},'menu':{'type':'InventoryMenu','cursor':{'count':0}}}
        self.assertEqual(owned(c,q),q)
        for update in ({'world_session':'old'},{'manual_movement':True},{'health':18},{'screen':'InventoryScreen'},
                       {'supervision_lease':{'kind':'materials','job_session':'other','world_session':'w'}}):
            with self.assertRaises(RuntimeError):owned(c,{**q,**update})

if __name__=='__main__':unittest.main()
