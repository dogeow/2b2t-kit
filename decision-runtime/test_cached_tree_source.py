import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from material_jobs.cached_tree_source import acquire, locate, outside_protected
from material_jobs.protocol import JobPaused


class CachedTreeSourceTest(unittest.TestCase):
    def test_forest_footprint_avoids_protected_map_and_invalid_boxes(self):
        candidate={'tile':[1024,1024]}
        self.assertTrue(outside_protected(candidate,[{'min':[0,0,0],'max':[127,319,127]}]))
        self.assertFalse(outside_protected(candidate,[{'min':[1050,0,1050],'max':[1100,319,1100]}]))
        self.assertFalse(outside_protected(candidate,[{'min':[1,2],'max':[3,4]}]))

    def test_cache_disk_work_keeps_existing_owner_checkpointing(self):
        first={'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'w','pos':[0,160,0]}
        client=SimpleNamespace(root=Path('/game/config/twob2tkit/automation'),status=Mock(return_value=first))
        backend=SimpleNamespace(checkpoint=Mock())
        future=Mock();future.done.side_effect=[False,True];future.result.return_value=[{'tile':[1024,1024]}]
        pool=Mock();pool.submit.return_value=future
        with tempfile.TemporaryDirectory()as tmp,patch('material_jobs.cached_tree_source.ThreadPoolExecutor',return_value=pool),patch('material_jobs.cached_tree_source.time.sleep'):
            rows=locate(client,backend,'spruce',Path(tmp))
        self.assertEqual([{'tile':[1024,1024]}],rows)
        self.assertGreaterEqual(backend.checkpoint.call_count,2)
        self.assertGreaterEqual(client.status.call_count,3)
        pool.shutdown.assert_called_once_with(wait=False,cancel_futures=True)

    def test_cache_scope_change_discards_hints(self):
        first={'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'w','pos':[0,160,0]}
        client=SimpleNamespace(root=Path('/game/config/twob2tkit/automation'),status=Mock(side_effect=[first,{**first,'world_session':'new'}]))
        future=Mock();future.done.return_value=True;future.result.return_value=[{'tile':[1024,1024]}]
        pool=Mock();pool.submit.return_value=future
        with tempfile.TemporaryDirectory()as tmp,patch('material_jobs.cached_tree_source.ThreadPoolExecutor',return_value=pool):
            with self.assertRaises(JobPaused):locate(client,SimpleNamespace(checkpoint=Mock()),'spruce',Path(tmp))

    def test_only_same_client_can_dispatch_a_cached_trip(self):
        backend=SimpleNamespace(client=object(),request={'mode':'projection'})
        with self.assertRaises(JobPaused):acquire(backend,object(),'minecraft:spruce_log',8,Path('/unused'))

    def test_protected_cache_candidates_never_start_travel_or_harvest(self):
        s={'inventory':[{'slot':0,'item':'minecraft:dirt','count':1,'max_stack':64}],
           'projection_selection':{'min':[1024,64,1024],'max':[1151,64,1151]}}
        client=SimpleNamespace(status=Mock(return_value=s),set_progress=Mock())
        backend=SimpleNamespace(client=client,request={'mode':'projection'},profile={'protected_regions':[]})
        with tempfile.TemporaryDirectory()as tmp,patch('material_jobs.cached_tree_source.locate',return_value=[{'tile':[1024,1024]}]),patch('material_jobs.cached_tree_source.tree_trip')as trip:
            self.assertIsNone(acquire(backend,client,'minecraft:spruce_log',8,Path(tmp)))
        trip.assert_not_called()


if __name__=='__main__':unittest.main()
