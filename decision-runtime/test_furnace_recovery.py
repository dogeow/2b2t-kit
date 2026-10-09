import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from furnace_recovery import recover


class Client:
    world = 'world'
    def __init__(self, phase='done', confirmed=True):
        self.calls=[]; self.phase=phase; self.confirmed=confirmed
        rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(43)]
        rows[3].update(item='minecraft:diamond_pickaxe',count=1,durability=100,max_stack=1)
        self.state={'time':1,'world_session':'world','empty_furnace_recovery_protocol':1,'inventory':rows,
                    'menu':{'id':11,'type':'FurnaceMenu','cursor':{'item':'minecraft:air','count':0},
                            'slots':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(39)]},
                    'empty_furnace_recovery':{'server_content_seen':True,'server_slots_empty':True,
                                             'pos':[1,64,2],'menu_id':11,'content_serial':1}}
    def status(self): return copy.deepcopy(self.state)
    def request(self, op, **params):
        self.calls.append((op,params))
        if op=='snapshot':return self.status()
        if op=='scan':return {'blocks':[{'state':'Block{minecraft:furnace}[facing=north,lit=false]'}]}
        if op=='mine_block':
            if self.phase=='done'and self.confirmed:self.state['inventory'][8].update(item='minecraft:furnace',count=1,max_stack=64)
            return {'id':'one-mine','phase':self.phase,'server_confirmed':self.confirmed}
        raise AssertionError('Unexpected action '+op)


class FurnaceRecoveryTest(unittest.TestCase):
    def run_recovery(self,c,path):
        with patch('furnace_recovery.snapshot',side_effect=lambda client,p:client.status()):
            return recover(c,[[1,64,2]],path,c.status)
    def test_unknown_or_unconfirmed_removal_retains_one_pending_intent(self):
        for phase,confirmed in [('waiting',False),('done',False)]:
            with tempfile.TemporaryDirectory()as d:
                c=Client(phase,confirmed);out=Path(d)/'new'
                with self.assertRaisesRegex(RuntimeError,'unconfirmed'):self.run_recovery(c,out)
                self.assertEqual(1,sum(op=='mine_block'for op,_ in c.calls))
                self.assertFalse(any(op=='collect_item'for op,_ in c.calls))
                ledger=json.loads((out/'recovery-ledger.json').read_text());self.assertIsNotNone(ledger['pending'])
                self.assertFalse(ledger['complete']);self.assertEqual([],ledger['recovered'])
    def test_real_server_ack_and_exact_inventory_gain_complete_once(self):
        with tempfile.TemporaryDirectory()as d:
            c=Client();result=self.run_recovery(c,Path(d)/'new')
            self.assertTrue(result['complete']);self.assertIsNone(result['pending'])
            self.assertEqual(1,result['recovered'][0]['actual_furnace_count_after'])
            self.assertEqual(1,sum(op=='mine_block'for op,_ in c.calls))
    def test_unsupported_host_rejects_before_any_open_or_action(self):
        with tempfile.TemporaryDirectory()as d:
            c=Client();c.state['empty_furnace_recovery_protocol']=0
            with self.assertRaisesRegex(RuntimeError,'does not support'):self.run_recovery(c,Path(d)/'new')
            self.assertEqual([],c.calls)


if __name__=='__main__':unittest.main()
