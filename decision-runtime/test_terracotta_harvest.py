import copy
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from material_jobs.terracotta_harvest import natural_context,validate_biomes,verify_region,exposed_targets
from material_jobs.dry_hover_harvest import offers,run


def row(pos,item='terracotta',**kw):
    return {'pos':pos,'state':'Block{minecraft:'+item+'}','solid':True,
            'fluid':False,'block_entity':False,'passable':False,**kw}


def strata():
    return [row([x,y,z])for x in range(-2,3)for y in(3,4)for z in range(-2,3)]


def biome_reply():
    return {'id':'current','world_session':'world','phase':'done','snow_biome_survey':{
        'center':[0,0],'radius':16,'stride':16,'requested_samples':9,
        'loaded_samples':9,'unloaded_samples':0,'samples':[
            {'pos':[x,80,z],'chunk':[x//16,z//16],'biome':'minecraft:badlands'}
            for x in(-16,0,16)for z in(-16,0,16)]}}


class TerracottaHarvestTest(unittest.TestCase):
    def test_keep_the_actual_support_of_surface_plants(self):
        rows=strata();bush=row([0,5,0],'dead_bush',solid=False,passable=True)
        self.assertFalse(natural_context(rows+[bush],[0,4,0]))
        self.assertTrue(natural_context(rows+[bush],[1,4,0]))
    def test_buried_plain_strata_are_skipped_before_descent(self):
        rows=[row([x,y,z])for x in range(16)for y in range(12)for z in range(16)]
        self.assertTrue(exposed_targets(rows,[0,0,0],[15,15,15]))
        rows.extend(row([x,y,z],'orange_terracotta')for x in range(16)for y in range(12,16)for z in range(16))
        self.assertEqual([],exposed_targets(rows,[0,0,0],[15,15,15]))
    def test_fresh_biome_proof_creates_its_own_new_batch_directory(self):
        from pathlib import Path
        c=SimpleNamespace(world='world',last='current',status=lambda:{'pos':[.5,90.,.5]},
                          request=Mock(return_value=biome_reply()))
        region={'item':'minecraft:terracotta','min':[-2,60,-2],'max':[2,75,2]}
        with tempfile.TemporaryDirectory()as out:
            verify_region(c,region,lambda:None,Path(out)/'new-batch')
            self.assertTrue((Path(out)/'new-batch/current-badlands-biomes.json').exists())
    def test_plain_terracotta_has_air_access_without_reclassifying_dripstone(self):
        rows=strata();low=[-4,0,-4];high=[4,8,4];player=[.5,5.2,.5]
        self.assertEqual([],offers(rows,low,high,player))
        got=offers(rows,low,high,player,item='minecraft:terracotta')
        self.assertTrue(got)
        self.assertTrue(all(r['state']=='Block{minecraft:terracotta}'for r in got))
        self.assertFalse(any(r['station']==[.5,4.2,.5]for r in got))

    def test_badlands_strata_cannot_bypass_container_fluid_sand_or_building_protection(self):
        rows=strata();self.assertTrue(natural_context(rows,[0,4,0]))
        for hazard in ('chest','cobblestone','torch','red_sand','cactus','water'):
            with self.subTest(hazard=hazard):
                self.assertFalse(natural_context(rows+[row([0,5,0],hazard)], [0,4,0]))
        self.assertFalse(natural_context([row([0,4,0])],[0,4,0]))
        self.assertFalse(natural_context([row([x,4,z])for x in range(-2,3)for z in range(-2,3)],[0,4,0]))
        self.assertFalse(natural_context(rows+[row([0,5,0],fluid=True)],[0,4,0]))
        self.assertFalse(natural_context(rows+[row([0,5,0],block_entity=True)],[0,4,0]))

    def test_complete_loaded_badlands_required_for_every_source_chunk(self):
        region={'min':[-2,60,-2],'max':[2,75,2]};reply=biome_reply()
        self.assertFalse(validate_biomes(reply,'current','world',[0,0],region)['seed_hint_used_as_proof'])
        mutations=[lambda r:r.update(world_session='old'),lambda r:r.update(id='old'),
            lambda r:r['snow_biome_survey'].update(unloaded_samples=1),
            lambda r:r['snow_biome_survey'].update(loaded_samples=8),
            lambda r:r['snow_biome_survey']['samples'][4].update(biome='minecraft:desert'),
            lambda r:r['snow_biome_survey']['samples'][4].update(pos=[0,80,16]),
            lambda r:r['snow_biome_survey']['samples'][4].update(chunk=[8,8])]
        for mutation in mutations:
            bad=copy.deepcopy(reply);mutation(bad)
            with self.assertRaises(RuntimeError):validate_biomes(bad,'current','world',[0,0],region)

    def test_seed_hint_or_wrong_item_cannot_dispatch_mining(self):
        c=SimpleNamespace(world='world',request=Mock(),status=Mock())
        base={'authorized':True,'source':'natural_survey','min':[0,60,0],'max':[15,75,15]}
        for region in ({**base,'source':'seed_hint'},{**base,'item':'minecraft:cyan_terracotta'},
                       {**base,'item':'minecraft:terracotta','max':[16,75,15]}):
            with tempfile.TemporaryDirectory()as out,self.assertRaises(ValueError):
                run(c,{},region,64,out,lambda:None,item='minecraft:terracotta')
        c.request.assert_not_called();c.status.assert_not_called()

if __name__=='__main__':unittest.main()
