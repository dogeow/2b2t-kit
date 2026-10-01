"""Fresh child stack metadata enables approved Ender stock; uncertain sources still stop."""
import copy
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from container_access import OutdoorChestChanged
from material_jobs_backend import Backend,observed_packed_stack_sizes
from material_jobs.protocol import JobBlocked,JobPaused
from material_plan import inventory_counts

WHEAT='minecraft:wheat'
AIR=[761021,64,797852]
ENDER=[761021,64,797850]
PAD=[761020,64,797848]


class PackedMetadataTest(unittest.TestCase):
    def fixture(self,folder,*,registry=None,child=None):
        self.inventory=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(36)]
        self.ender=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(27)]
        self.ender[16]={'slot':16,'item':'minecraft:shulker_box','count':1,'max_stack':1,
                        'contains':[child or {'item':WHEAT,'count':64,'max_stack':64}]}
        def state():
            return copy.deepcopy({'inventory':self.inventory,'menu':{'id':2,'type':'ChestMenu',
                'cursor':{'item':'minecraft:air','count':0},'slots':self.ender+self.inventory}})
        client=SimpleNamespace(status=state,owned_material_menu=2,checked=Mock(),transfer=Mock())
        job=Backend.__new__(Backend);job.profile={'depots':[AIR],'ender_chest':ENDER,'shulker_pad':PAD}
        job.request={'mode':'item','target_stack_sizes':registry or {}}
        job.stock=lambda:inventory_counts(state());job.ensure_client=lambda:client
        job.prepare_travel=Mock();job.stage_near_base=Mock();job.close_owned_menu=Mock()
        job.checkpoint=lambda:None;job.action=lambda name:nullcontext((client,Path(folder)))
        return job,client,state
    def test_real_nested_wheat_size_supports_fetch_after_known_air_without_registry_guess(self):
        with tempfile.TemporaryDirectory() as folder:
            job,client,state=self.fixture(folder)
            original=copy.deepcopy(job.profile)
            def take(c,ender,pad,slot,targets):
                self.assertIs(c,client);self.assertEqual((ENDER,PAD,16), (ender,pad,slot))
                self.assertEqual({WHEAT:4},targets)
                self.inventory[0]={'slot':0,'item':WHEAT,'count':4,'max_stack':64}
                self.ender[16]['contains'][0]['count']=60
            with patch('container_access.open_grounded_chest',side_effect=OutdoorChestChanged(AIR,'minecraft:chest',None,[])), \
                 patch('packed_supplies.open_box',side_effect=lambda *args:state()) as opened, \
                 patch('packed_supplies.take_box',side_effect=take) as taken:
                result=job.fetch({WHEAT:4})
            self.assertEqual('done',result['phase']);self.assertEqual({},result['missing'])
            self.assertEqual([AIR],result['unavailable_sources']);self.assertEqual(4,job.stock()[WHEAT])
            opened.assert_called_once_with(client,ENDER,'ChestMenu');taken.assert_called_once()
            client.transfer.assert_not_called();self.assertEqual(original,job.profile)
            source=json.loads((Path(folder)/'sources.json').read_text())[0]
            self.assertEqual('unavailable',source['phase']);self.assertEqual([],source['scan_evidence']['scan']['blocks'])
    def test_missing_child_size_is_explicit_waiting_not_false_empty_stock(self):
        with tempfile.TemporaryDirectory() as folder:
            job,client,state=self.fixture(folder,child={'item':WHEAT,'count':64})
            with patch('packed_supplies.open_box',side_effect=lambda *args:state()),patch('packed_supplies.take_box') as take:
                result=job.fetch_packed({WHEAT:4})
            self.assertEqual('waiting',result['phase']);self.assertEqual('packed_stack_metadata_unknown',result['code'])
            self.assertEqual([WHEAT],result['items']);take.assert_not_called();client.transfer.assert_not_called()
    def test_registered_legacy_size_remains_supported_without_inventing_a_new_size(self):
        rows=[{'item':'minecraft:shulker_box','count':1,'max_stack':1,
               'contains':[{'item':WHEAT,'count':64}]}]
        self.assertEqual(64,observed_packed_stack_sizes(rows,{WHEAT:64})[WHEAT])
        self.assertNotIn(WHEAT,observed_packed_stack_sizes(rows,{}))
    def test_invalid_registry_is_rejected_before_sizes_are_inferred(self):
        for registry in (None,[],{WHEAT:True},{WHEAT:0}):
            with self.subTest(registry=registry),self.assertRaises(JobBlocked):
                observed_packed_stack_sizes([],registry)
    def test_conflicts_and_invalid_child_metadata_stop_before_box_pickup(self):
        bad=[({'item':WHEAT,'count':64,'max_stack':64},{WHEAT:32}),
             ({'item':WHEAT,'count':64,'max_stack':32},{}),
             ({'item':WHEAT,'count':64,'max_stack':0},{}),
             ({'item':WHEAT,'count':64,'max_stack':100},{}),
             ({'item':WHEAT,'count':64,'max_stack':'64'},{}),
             ({'item':WHEAT,'count':1,'max_stack':True},{}),
             ({'item':WHEAT,'count':-1,'max_stack':64},{})]
        for child,registry in bad:
            with self.subTest(child=child),tempfile.TemporaryDirectory() as folder:
                job,client,state=self.fixture(folder,registry=registry,child=child)
                with patch('packed_supplies.open_box',side_effect=lambda *args:state()),patch('packed_supplies.take_box') as take:
                    with self.assertRaises(JobBlocked):job.fetch_packed({WHEAT:4})
                take.assert_not_called();client.transfer.assert_not_called()
    def test_fresh_size_change_after_menu_observation_cannot_reuse_old_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            job,client,state=self.fixture(folder)
            def changed():
                self.ender[16]['contains'][0]['max_stack']=99
                return state()
            client.status=changed
            original=state()
            with patch('packed_supplies.open_box',return_value=original),patch('packed_supplies.take_box') as take:
                with self.assertRaises(JobBlocked):job.fetch_packed({WHEAT:4})
            take.assert_not_called();client.transfer.assert_not_called()
    def test_unknown_open_or_transfer_receipt_never_falls_back_to_another_container(self):
        with tempfile.TemporaryDirectory() as folder:
            job,client,state=self.fixture(folder)
            with patch('container_access.open_grounded_chest',side_effect=RuntimeError('pending unknown container operation')), \
                 patch('packed_supplies.open_box') as fallback:
                with self.assertRaisesRegex(RuntimeError,'pending unknown'):job.fetch({WHEAT:4})
            fallback.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            job,client,state=self.fixture(folder)
            self.ender[0]={'slot':0,'item':WHEAT,'count':4,'max_stack':64}
            client.transfer.side_effect=JobPaused('unknown transfer receipt')
            with patch('container_access.open_grounded_chest',side_effect=lambda *args,**kwargs:state()), \
                 patch('container_access.verify_opened_chest'),patch('packed_supplies.open_box') as fallback:
                with self.assertRaisesRegex(JobPaused,'unknown transfer'):job.fetch({WHEAT:4})
            fallback.assert_not_called()
            source=json.loads((Path(folder)/'sources.json').read_text())[0]
            self.assertEqual('waiting',source['phase']);self.assertEqual({},source['provided'])
    def test_no_registered_ender_source_is_never_discovered_or_invented(self):
        with tempfile.TemporaryDirectory() as folder:
            job,client,state=self.fixture(folder);job.profile.pop('ender_chest')
            with patch('packed_supplies.open_box') as fallback:job.fetch_packed({WHEAT:4})
            fallback.assert_not_called();client.transfer.assert_not_called()


if __name__=='__main__':unittest.main()
