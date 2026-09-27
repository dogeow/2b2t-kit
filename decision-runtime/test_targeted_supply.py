"""Ordinary material fetches exercise real exact inventory transfer offline."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from material_jobs_backend import Backend
from material_jobs.protocol import JobBlocked
from material_plan import inventory_counts
from test_material_depots import StorageClient


class TargetedSupplyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = StorageClient(self.root)
        self.client.owned_material_menu = 1
        self.job = Backend.__new__(Backend)
        self.job.out, self.job.client = self.root, self.client
        self.job.request = {'mode':'item', 'target_stack_sizes':{}}
        self.job.profile = {'dimension':'minecraft:overworld', 'depots':[[1,64,1],[2,64,2]]}
        self.job.action = Mock(return_value=nullcontext((self.client,self.root)))
        self.job.stock = lambda:dict(inventory_counts(self.client.status()))
        self.job.prepare_travel = Mock()
        self.job.stage_near_base = Mock()
        self.job.checkpoint = Mock()
        self.job.close_owned_menu = Mock()
        self.job.fetch_packed = Mock()

    def fetch(self, targets):
        with patch('container_access.open_grounded_chest', side_effect=lambda *args,**kw:self.client.status()) as opened:
            result = self.job.fetch(targets)
        return result, opened

    def fill(self, first=28, last=62):
        for slot in range(first,last+1):
            self.client.put(slot,'minecraft:dirt',64)

    def test_exact_sixteen_fills_late_partial_stack_and_preserves_earlier_last_empty_slot(self):
        self.client.put(0,'minecraft:stone',64)
        self.fill(28,61)
        self.client.put(62,'minecraft:stone',48)
        result, opened = self.fetch({'minecraft:stone':64})
        self.assertEqual('done',result['phase'])
        self.assertEqual(48,self.client.menu['slots'][0]['count'])
        self.assertEqual(64,self.client.menu['slots'][62]['count'])
        self.assertEqual(0,self.client.menu['slots'][27]['count'])
        self.assertEqual(1,opened.call_count)
        opened.assert_called_once_with(self.client,[1,64,1],allow_empty=True)
        self.job.close_owned_menu.assert_called_once()
        self.assertEqual({'minecraft:stone':16},json.loads((self.root/'sources.json').read_text())[0]['provided'])

    def test_multiple_targets_share_capacity_without_using_reserved_empty_slot(self):
        self.fill(27,59)
        self.client.put(0,'minecraft:sand',64)
        self.client.put(1,'minecraft:gravel',64)
        self.client.put(2,'minecraft:coal',64)
        result, _ = self.fetch({'minecraft:sand':64,'minecraft:gravel':64,'minecraft:coal':64})
        self.assertEqual('waiting',result['phase'])
        self.assertEqual(128,sum(self.job.stock().get(item,0) for item in ('minecraft:sand','minecraft:gravel','minecraft:coal')))
        self.assertEqual(1,sum(row['count']==0 for row in self.client.status()['inventory']))
        self.assertEqual(1,len(result['missing']))

    def test_full_backpack_can_only_fill_existing_partial_stack(self):
        self.fill(27,62)
        self.client.put(62,'minecraft:gravel',48)
        self.client.put(0,'minecraft:gravel',64)
        self.client.put(1,'minecraft:sand',64)
        result, _ = self.fetch({'minecraft:gravel':128,'minecraft:sand':64})
        self.assertEqual({'minecraft:gravel':64,'minecraft:sand':64},result['missing'])
        self.assertEqual(48,self.client.menu['slots'][0]['count'])
        self.assertEqual(64,self.client.menu['slots'][1]['count'])
        self.assertEqual(64,self.job.stock()['minecraft:gravel'])

    def test_nonstackable_target_uses_actual_source_stack_size(self):
        self.fill(27,60)
        self.client.put(0,'minecraft:diamond_pickaxe',1,max_stack=1)
        self.client.put(1,'minecraft:diamond_pickaxe',1,max_stack=1)
        result, _ = self.fetch({'minecraft:diamond_pickaxe':2})
        self.assertEqual('waiting',result['phase'])
        self.assertEqual(1,self.job.stock()['minecraft:diamond_pickaxe'])
        self.assertEqual(1,sum(row['count']==0 for row in self.client.status()['inventory']))

    def test_missing_source_size_uses_only_requested_registry_mapping(self):
        self.client.put(0,'minecraft:gravel',64)
        original = self.client.status
        def status():
            state = original()
            state['menu']['slots'][0].pop('max_stack',None)
            return state
        self.client.status = status
        self.job.request['target_stack_sizes'] = {'minecraft:gravel':64}
        result, _ = self.fetch({'minecraft:gravel':16})
        self.assertEqual('done',result['phase'])
        self.assertEqual(16,self.job.stock()['minecraft:gravel'])

    def test_unknown_or_conflicting_stack_size_blocks_before_click(self):
        for size in (None,16):
            with self.subTest(size=size):
                self.client.put(0,'minecraft:gravel',64)
                self.job.request['target_stack_sizes'] = {'minecraft:gravel':16} if size == 16 else {}
                original = self.client.status
                if size is None:
                    def status():
                        state = original()
                        state['menu']['slots'][0].pop('max_stack',None)
                        return state
                    self.client.status = status
                with self.assertRaisesRegex(JobBlocked,'堆叠上限'):
                    self.fetch({'minecraft:gravel':16})
                self.assertFalse(self.client.calls)
                self.client.status = original

    def test_food_changes_cannot_confirm_unacknowledged_target_transfer(self):
        self.client.put(0,'minecraft:gravel',64)
        self.client.put(27,'minecraft:bread',8)
        def no_transfer(item,target):
            self.client.menu['slots'][27]['count'] -= 1
        self.client.transfer = Mock(side_effect=no_transfer)
        with patch('container_access.open_grounded_chest',side_effect=lambda *a,**k:self.client.status()) as opened:
            with self.assertRaisesRegex(JobBlocked,'增量未确认'):
                self.job.fetch({'minecraft:gravel':16})
        self.client.transfer.assert_called_once_with('minecraft:gravel',16)
        self.assertEqual(1,opened.call_count)
        self.job.fetch_packed.assert_not_called()

    def test_source_loss_must_match_backpack_gain(self):
        self.client.put(0,'minecraft:stone',64)
        self.client.transfer = Mock(side_effect=lambda item,target:self.client.put(27,item,target))
        with self.assertRaisesRegex(JobBlocked,'出箱数量'):
            self.fetch({'minecraft:stone':16})
        self.client.transfer.assert_called_once()

    def test_changed_menu_cannot_authorize_second_transfer(self):
        self.client.put(0,'minecraft:stone',64)
        def changed(item,target):
            self.client.menu['id'] += 1
        self.client.transfer = Mock(side_effect=changed)
        with self.assertRaisesRegex(JobBlocked,'容器或光标'):
            self.fetch({'minecraft:stone':16})
        self.client.transfer.assert_called_once()

    def test_already_satisfied_single_item_never_travels_or_opens(self):
        self.client.put(27,'minecraft:stone',64)
        result, opened = self.fetch({'minecraft:stone':64})
        self.assertEqual('done',result['phase'])
        opened.assert_not_called()
        self.job.prepare_travel.assert_not_called()
        self.job.fetch_packed.assert_not_called()

    def test_obstructed_chest_uses_real_vertical_scan_and_never_approaches(self):
        self.client.request = Mock(return_value={'blocks':[
            {'pos':[1,64,1],'state':'Block{minecraft:chest}[facing=north]'},
            {'pos':[1,65,1],'state':'Block{minecraft:stone}'},
        ]})
        with self.assertRaisesRegex(RuntimeError,'landing column is obstructed'):
            self.job.fetch({'minecraft:stone':64})
        self.client.request.assert_called_once_with('scan',min=[1,64,1],max=[1,70,1],details=True)
        self.assertFalse(self.client.calls)


if __name__ == '__main__':
    unittest.main()
