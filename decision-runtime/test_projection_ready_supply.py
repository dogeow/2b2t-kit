from collections import Counter
from contextlib import nullcontext
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from material_jobs_backend import Backend
from material_jobs.protocol import JobBlocked


def inventory(counts):
    rows=[]
    for item,n in counts.items():
        while n:
            count=min(n,64);rows.append({'slot':len(rows),'item':item,'count':count,'max_stack':64});n-=count
    rows += [{'slot':slot,'item':'minecraft:air','count':0,'max_stack':1} for slot in range(len(rows),36)]
    return rows


class ChestClient:
    def __init__(self,root,held,chests):
        self.world='w';self.out=root;self.held=Counter(held);self.chests={tuple(p):Counter(stock) for p,stock in chests}
        self.opened=[];self.transfers=[];self.current=None;self.owned_material_menu=None
        self.fail_ack=False;self.mismatch=False
    def open(self,unused,pos,**options):
        assert options.get('allow_empty') is True
        self.current=tuple(pos);self.opened.append(self.current);self.owned_material_menu=len(self.opened)
        return self.status()
    def status(self):
        inv=inventory(self.held)
        s={'connected':True,'world_session':self.world,'inventory':inv,'screen':''}
        if self.current is not None:
            source=[]
            for item,n in self.chests[self.current].items():
                while n:
                    count=min(n,64);source.append({'slot':len(source),'item':item,'count':count,'max_stack':64});n-=count
            source += [{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(len(source),27)]
            s['screen']='ContainerScreen';s['menu']={'id':self.owned_material_menu,'type':'ChestMenu','cursor':{'count':0},
                'slots':source+[{**row,'slot':27+row['slot']} for row in inv]}
        return s
    def transfer(self,item,target):
        self.transfers.append((self.current,item,target))
        amount=min(max(0,target-self.held[item]),self.chests[self.current][item])
        if not self.fail_ack:
            self.held[item]+=amount
            if not self.mismatch:self.chests[self.current][item]-=amount
    def close(self):self.current=None


class ProjectionSupplyTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.deep='minecraft:deepslate_tiles';self.smooth='minecraft:smooth_stone';self.andesite='minecraft:polished_andesite'
        self.client=ChestClient(self.root,{'minecraft:white_concrete':32,'minecraft:hopper':6},
            [([1,64,1],{self.smooth:166,self.andesite:57}),([2,64,2],{})])
        self.job=Backend.__new__(Backend)
        self.job.out=self.root;self.job.client=self.client
        self.job.request={'mode':'projection','projection_key':'ship','target_stack_sizes':{self.deep:64,self.smooth:64,self.andesite:64}}
        self.job.profile={'dimension':'minecraft:overworld','depots':[[1,64,1],[2,64,2]]}
        self.job.audit={'placement_key':'ship','loaded_chunks_verified':True,'kinds':{},
            'replacement_items':{self.deep:625,self.smooth:115,self.andesite:136,'minecraft:white_concrete':8,'minecraft:hopper':6}}
        self.job.audit_dirty=False;self.job.checkpoint=Mock();self.job.stock=Mock(side_effect=lambda:dict(self.client.held))
        self.job.close_owned_menu=self.client.close;self.job.prepare_travel=Mock();self.job.stage_near_base=Mock()
        self.job.action=Mock(return_value=nullcontext((self.client,self.root)));self.job.fetch_packed=Mock()

    def fetch(self):
        with patch('container_access.open_grounded_chest',side_effect=self.client.open):return self.job.fetch({self.deep:128})

    def test_missing_deepslate_does_not_hide_ready_smooth_stone_and_andesite(self):
        result=self.fetch()
        self.assertTrue(result['ready_for_build'])
        self.assertEqual({self.smooth:115,self.andesite:57},result['provided_finished'])
        self.assertEqual(51,self.client.chests[(1,64,1)][self.smooth])
        self.assertEqual(115,self.client.held[self.smooth]);self.assertEqual(57,self.client.held[self.andesite])
        self.assertEqual({self.deep:128},result['missing']);self.job.fetch_packed.assert_not_called()
        self.assertEqual([(1,64,1),(2,64,2)],self.client.opened)

    def test_same_projection_deficit_is_not_a_new_full_depot_sweep(self):
        self.fetch();count=len(self.client.opened)
        with patch('container_access.open_grounded_chest',side_effect=self.client.open):
            self.assertIsNone(self.job.finished_supply_pass(self.client,self.root,{self.deep:128}))
        self.assertEqual(count,len(self.client.opened))

    def test_changed_actual_deficit_allows_a_new_material_replenishment_pass(self):
        self.fetch();self.client.held[self.smooth]=0;self.job.audit['replacement_items'][self.smooth]=0
        with patch('container_access.open_grounded_chest',side_effect=self.client.open):
            result=self.job.finished_supply_pass(self.client,self.root,{self.deep:128})
        self.assertFalse(result['ready_for_build']);self.assertEqual(4,len(self.client.opened))

    def test_depot_hints_alone_do_not_create_backpack_receipt(self):
        for chest in self.client.chests.values():chest.clear()
        self.job.warehouse_hint={self.smooth:999,self.andesite:999}
        result=self.fetch()
        self.assertNotIn('ready_for_build',result);self.assertEqual(0,self.client.held[self.smooth])
        self.assertEqual(0,self.client.held[self.andesite])

    def test_unconfirmed_transfer_is_not_claimed_as_material_progress(self):
        self.client.fail_ack=True
        result=self.fetch()
        self.assertNotIn('ready_for_build',result);self.assertEqual(0,self.client.held[self.smooth])

    def test_source_and_backpack_quantity_mismatch_stops_without_repeating(self):
        self.client.mismatch=True
        with self.assertRaisesRegex(JobBlocked,'出箱数量'):self.fetch()
        self.assertEqual(1,len(self.client.transfers))
        self.assertFalse(json.loads((self.root/'finished-supply-pass.json').read_text())['complete'])

    def test_one_empty_work_slot_is_kept_for_crafting_and_tools(self):
        self.client.held=Counter({'minecraft:stone':33*64})
        result=self.fetch()
        self.assertEqual({self.smooth:115},result['provided_finished'])
        self.assertEqual(1,sum(row['count']==0 for row in self.client.status()['inventory']))

    def test_wrong_or_unloaded_projection_does_not_open_any_chest(self):
        self.job.audit['placement_key']='other'
        with self.assertRaises(JobBlocked):self.fetch()
        self.assertFalse(self.client.opened)
        self.job.audit['placement_key']='ship';self.job.audit['loaded_chunks_verified']=False
        with self.assertRaises(JobBlocked):self.fetch()
        self.assertFalse(self.client.opened)

    def test_receipt_records_only_new_fungible_building_material_not_existing_eight_blocks(self):
        self.client.held[self.smooth]=8
        result=self.fetch()
        self.assertEqual(107,result['provided_finished'][self.smooth])
        self.assertNotIn('minecraft:white_concrete',result['provided_finished'])
        self.assertNotIn('minecraft:hopper',result['provided_finished'])

    def test_single_item_tasks_use_exact_chest_fetch_without_ready_build_credit(self):
        self.job.request['mode']='item';self.client.request=Mock(return_value={'phase':'done'})
        with patch('container_access.open_grounded_chest',side_effect=self.client.open) as open:
            result=self.job.fetch({self.deep:128})
        self.assertEqual(2,open.call_count);self.assertNotIn('ready_for_build',result)
        self.client.request.assert_not_called()


if __name__=='__main__':unittest.main()
