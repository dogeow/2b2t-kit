import copy
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from material_jobs_backend import Backend
from material_plan import inventory_counts
from packed_supplies import REQUIRED_FREE_SLOTS,workspace_requirement,PackedWorkspaceRequired


class PackedCapacityTest(unittest.TestCase):
    def setup_job(self, free, *, loose=0, packed=0, before=0):
        inventory=[{'slot':i,'item':'minecraft:diamond_pickaxe','count':1,'max_stack':1} for i in range(36)]
        for i in range(free):inventory[35-i]={'slot':35-i,'item':'minecraft:air','count':0,'max_stack':64}
        if before:inventory[0]={'slot':0,'item':'minecraft:iron_ingot','count':before,'max_stack':64}
        rows=[]
        if loose:rows.append({'slot':0,'item':'minecraft:iron_ingot','count':loose,'max_stack':64})
        if packed:rows.append({'slot':18,'item':'minecraft:shulker_box','count':1,'max_stack':1,
                               'contains':[{'item':'minecraft:iron_ingot','count':packed}]})
        self.state={'inventory':inventory,'menu':{'slots':rows+[{}]*36}}
        client=SimpleNamespace(status=lambda:copy.deepcopy(self.state),checked=Mock(),transfer=Mock())
        job=Backend.__new__(Backend)
        job.profile={'ender_chest':[0,64,0],'shulker_pad':[2,64,0]}
        job.request={'target_stack_sizes':{'minecraft:iron_ingot':64}}
        job.ensure_client=lambda:client
        job.stock=lambda:inventory_counts(self.state)
        return job,client

    def test_loose_material_never_spends_the_last_work_slot(self):
        job,client=self.setup_job(1,loose=64)
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            job.fetch_packed({'minecraft:iron_ingot':64})
        client.transfer.assert_not_called();take.assert_not_called()

    def test_loose_material_can_fill_partial_stack_with_one_free_slot(self):
        job,client=self.setup_job(1,loose=64,before=48)
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box'):
            job.fetch_packed({'minecraft:iron_ingot':64})
        client.transfer.assert_called_once_with('minecraft:iron_ingot',64)

    def test_portable_material_leaves_box_recovery_and_work_slots(self):
        job,client=self.setup_job(3,packed=128)
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            job.fetch_packed({'minecraft:iron_ingot':128})
        take.assert_called_once()
        self.assertEqual({'minecraft:iron_ingot':64},take.call_args.args[4])

    def test_two_free_slots_are_not_filled_before_portable_recovery(self):
        job,client=self.setup_job(2,packed=128)
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            result=job.fetch_packed({'minecraft:iron_ingot':128})
        take.assert_not_called()
        self.assertEqual('waiting',result['phase'])
        self.assertEqual('packed_workspace_required',result['code'])
        self.assertEqual((3,2,1),(result['required_free_slots'],result['free_slots'],result['missing_free_slots']))
        client.checked.assert_called_once_with('close_menu')

    def test_partial_iron_stack_cannot_bypass_three_slot_admission(self):
        for free in (1,2):
            with self.subTest(free=free):
                job,client=self.setup_job(free,packed=28,before=11)
                with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
                    result=job.fetch_packed({'minecraft:iron_ingot':85})
                self.assertEqual('waiting',result['phase']);self.assertEqual(3-free,result['missing_free_slots'])
                self.assertEqual(11,inventory_counts(self.state)['minecraft:iron_ingot'])
                take.assert_not_called();client.transfer.assert_not_called()

    def test_three_slots_admit_one_new_stack_without_reserving_all_three_forever(self):
        job,client=self.setup_job(REQUIRED_FREE_SLOTS,packed=64)
        self.assertIsNone(workspace_requirement(self.state))
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            job.fetch_packed({'minecraft:iron_ingot':64})
        take.assert_called_once()
        self.assertEqual({'minecraft:iron_ingot':64},take.call_args.args[4])

    def test_no_useful_portable_source_does_not_request_unnecessary_workspace(self):
        job,client=self.setup_job(1)
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            self.assertIsNone(job.fetch_packed({'minecraft:iron_ingot':85}))
        take.assert_not_called()

    def test_capacity_change_after_closing_menu_is_rechecked_before_pickup(self):
        job,client=self.setup_job(3,packed=64)
        def close(op):
            self.assertEqual('close_menu',op)
            self.state['inventory'][35]={'slot':35,'item':'minecraft:dirt','count':1,'max_stack':64}
        client.checked.side_effect=close
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            result=job.fetch_packed({'minecraft:iron_ingot':64})
        self.assertEqual('packed_workspace_required',result['code']);self.assertEqual(2,result['free_slots'])
        take.assert_not_called()

    def test_only_pre_pickup_workspace_rejection_becomes_waiting(self):
        job,client=self.setup_job(3,packed=64)
        waiting={'phase':'waiting','code':'packed_workspace_required','required_free_slots':3,
                 'free_slots':2,'missing_free_slots':1,'detail':'one slot became occupied before pickup'}
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)), \
                patch('packed_supplies.take_box',side_effect=PackedWorkspaceRequired(waiting)):
            self.assertEqual(waiting,job.fetch_packed({'minecraft:iron_ingot':64}))
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)), \
                patch('packed_supplies.take_box',side_effect=RuntimeError('uncertain box transfer')):
            with self.assertRaisesRegex(RuntimeError,'uncertain box transfer'):
                job.fetch_packed({'minecraft:iron_ingot':64})

    def test_loose_stock_does_not_spend_required_admission_slots_for_remaining_box(self):
        job,client=self.setup_job(3,loose=64,packed=64)
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            job.fetch_packed({'minecraft:iron_ingot':128})
        client.transfer.assert_not_called()
        take.assert_called_once();self.assertEqual({'minecraft:iron_ingot':64},take.call_args.args[4])

    def test_loose_stock_can_fill_partial_stack_without_spending_admission_slots(self):
        job,client=self.setup_job(3,loose=20,packed=64,before=11)
        def transfer(item,target):
            self.state['inventory'][0]['count']=target
            self.state['menu']['slots'][0]['count']=0
        client.transfer.side_effect=transfer
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            job.fetch_packed({'minecraft:iron_ingot':85})
        client.transfer.assert_called_once_with('minecraft:iron_ingot',31)
        take.assert_called_once();self.assertEqual({'minecraft:iron_ingot':85},take.call_args.args[4])

    def test_fetch_propagates_workspace_receipt_instead_of_generic_missing_materials(self):
        job,client=self.setup_job(2,packed=28,before=11)
        job.profile['depots']=[];job.request['mode']='item'
        job.prepare_travel=Mock();job.stage_near_base=Mock();job.action=Mock(return_value=nullcontext((client,None)))
        with patch('packed_supplies.open_box',return_value=copy.deepcopy(self.state)),patch('packed_supplies.take_box') as take:
            result=job.fetch({'minecraft:iron_ingot':85})
        self.assertEqual('packed_workspace_required',result['code']);self.assertEqual('waiting',result['phase'])
        self.assertEqual({'minecraft:iron_ingot':74},result['missing']);self.assertEqual(1,result['missing_free_slots'])
        take.assert_not_called()

    def test_incomplete_or_duplicate_inventory_is_not_an_empty_backpack(self):
        self.setup_job(3,packed=64)
        for inventory in (self.state['inventory'][:-1],self.state['inventory'][:-1]+[self.state['inventory'][0]]):
            with self.subTest(inventory=inventory):
                result=workspace_requirement({'inventory':inventory})
                self.assertEqual('packed_inventory_unknown',result['code'])
                self.assertIsNone(result['free_slots'])


if __name__=='__main__':unittest.main()
