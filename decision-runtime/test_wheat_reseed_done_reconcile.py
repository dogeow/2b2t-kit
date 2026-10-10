import copy
import json
from pathlib import Path
import tempfile
import unittest

from wheat_reseed_done_reconcile import prove,reconcile


class Tests(unittest.TestCase):
    def setUp(self):
        self.pos=[1,64,3];self.low=[0,63,2];self.high=[2,66,4]
        rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(43)]
        rows[0].update(item='minecraft:wheat_seeds',count=10);rows[1].update(item='minecraft:wheat',count=2)
        self.book={'world_session':'world','scope':{'server':'example.test','layout':{'crop':'wheat','harvest_cells':[self.pos]}},
            'cells':{'1,64,3':{'harvest':{'native_mining_confirmed':True,'remaining_count':0}}},
            'pending':{'operation':'plant','pos':self.pos,'expected_state':'Block{minecraft:farmland}[moisture=7]',
                'before_counts':{'minecraft:wheat_seeds':10,'minecraft:wheat':2},'before_inventory':rows,
                'hand_before':{'item':'minecraft:wheat_seeds','count':10},'receipt':{'id':'once','phase':'done','time':10}}}
        self.event={'request_id':'once','op':'interact','phase':'done','world_session':'world',
            'params':{'pos':self.pos,'face':'up','expected_hand':'minecraft:wheat_seeds','expected_state':self.book['pending']['expected_state']},
            'inventory_delta':{'minecraft:wheat_seeds':-1},'revision_before':8,'revision_after':8,
            'position_before':[1.5,65.5,3.5],'position_after':[1.5,65.5,3.5]}
        after=copy.deepcopy(rows);after[0]['count']=9
        self.frames=[]
        for time,age in ((20,1),(21,2)):
            self.frames.append({'phase':'done','world_session':'world','server':'example.test:25565','dimension':'minecraft:overworld',
                'manual_movement':False,'control_revision':9,'scan_start_revision':9,'scan_end_revision':9,
                'scan_cells_read':36,'scan_total_cells':36,'time':time,'inventory':copy.deepcopy(after),
                'blocks':[{'pos':self.pos,'state':'Block{minecraft:farmland}[moisture=7]','fluid':False,'block_entity':False},
                          {'pos':[1,65,3],'state':f'Block{{minecraft:wheat}}[age={age}]','fluid':False,'block_entity':False}]})

    def test_original_done_one_seed_and_two_naturally_grown_frames_prove_without_replay(self):
        p=prove(self.book,[self.event],self.frames,self.low,self.high)
        self.assertEqual([1,2],p['observed_ages']);self.assertEqual(1,p['seed_debit'])
        self.assertFalse(p['new_planting_use_sent']);self.assertFalse(p['server_verified'])

    def test_wrong_receipt_delta_world_missing_crop_or_inventory_cannot_clear_pending(self):
        changes=[lambda b,e,f:b['pending']['receipt'].update(phase='error'),
                 lambda b,e,f:e.update(inventory_delta={}),
                 lambda b,e,f:e['params'].update(pos=[2,64,3]),
                 lambda b,e,f:e.pop('revision_before'),
                 lambda b,e,f:e.update(position_before=None,position_after=None),
                 lambda b,e,f:f[1].update(world_session='other'),
                 lambda b,e,f:f[1].update(time=20),
                 lambda b,e,f:f[1].update(blocks=f[1]['blocks'][:1]),
                 lambda b,e,f:f[1]['inventory'][0].update(count=8),
                 lambda b,e,f:f[1].update(inventory=f[1]['inventory'][:2]),
                 lambda b,e,f:f[1]['blocks'][1].update(state='Block{minecraft:wheat}[age=0]')]
        for change in changes:
            with self.subTest(change=change):
                b,e,f=copy.deepcopy((self.book,self.event,self.frames));change(b,e,f)
                with self.assertRaises(RuntimeError):prove(b,[e],f,self.low,self.high)
        with self.assertRaises(RuntimeError):prove(self.book,[self.event,self.event],self.frames,self.low,self.high)

    def test_archives_original_bytes_and_completes_only_the_proven_bounded_harvest(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);journal=root/'harvest.json';journal.write_text(json.dumps(self.book));before=journal.read_bytes()
            events=root/'events.jsonl';events.write_text(json.dumps(self.event)+'\n')
            paths=[]
            for i,f in enumerate(self.frames):
                p=root/f'frame-{i}.json';p.write_text(json.dumps(f));paths.append(p)
            proof=reconcile(journal,events,paths,root/'proof',low=self.low,high=self.high)
            updated=json.loads(journal.read_text());self.assertTrue(updated['complete']);self.assertIsNone(updated['pending'])
            self.assertTrue(updated['cells']['1,64,3']['replanted']);self.assertEqual(9,updated['seeds_after'])
            self.assertEqual(before,(root/'proof/original-harvest-before.json').read_bytes())
            self.assertFalse(proof['new_planting_use_sent'])
