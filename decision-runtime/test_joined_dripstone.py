import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

from material_jobs import joined_dripstone as m
from material_jobs.protocol import JobBlocked
from test_dry_clay_columns import Fake


def block(y,name,props='',**extra):
    return {'pos':[1,y,3],'state':'Block{minecraft:'+name+'}'+props,
            'solid':name in ('grass_block','dripstone_block'),
            'fluid':name=='water','block_entity':False,**extra}


def pointed(y,direction,thickness):
    return block(y,'pointed_dripstone','[thickness='+thickness+',vertical_direction='+direction+',waterlogged=false]')


def farm():
    return [block(63,'grass_block','[snowy=false]'),block(71,'dripstone_block'),block(72,'water','[level=0]'),
            pointed(70,'down','tip_merge')]+[pointed(y,'up',('base'if y==64 else'frustum'if y==68 else'tip_merge'if y==69 else'middle'))for y in range(64,70)]


class JoinedColumnTests(unittest.TestCase):
    def test_exact_six_lower_segments_preserve_highest_root_water_and_floor(self):
        p=m.column(farm(),[1,70,3],61)
        self.assertEqual(list(range(69,63,-1)),[r['pos'][1]for r in p['upward']])
        self.assertEqual(70,p['root'][1]);self.assertEqual(63,p['floor']['pos'][1])
    def test_gaps_wet_parts_downward_branches_and_protected_floor_are_refused(self):
        for kind in ('gap','wet','downward','container','water'):
            rows=farm()
            if kind=='gap':rows=[r for r in rows if r['pos'][1]!=66]
            if kind=='wet':rows[5]['state']=rows[5]['state'].replace('waterlogged=false','waterlogged=true')
            if kind=='downward':rows[5]['state']=rows[5]['state'].replace('vertical_direction=up','vertical_direction=down')
            if kind=='container':rows[0]['block_entity']=True
            if kind=='water':rows[2]['state']='Block{minecraft:water}[level=1]'
            with self.subTest(kind=kind),self.assertRaises(JobBlocked):m.column(rows,[1,70,3],61)

    def client(self,root,fault=None):
        c=Fake(root);c.pos=[1.5,68.2,2.5];c.counts={'minecraft:pointed_dripstone':2}
        c.blocks={tuple(r['pos']):r for r in farm()};original_status=c.status
        c.status=lambda:{**original_status(),'projection_selection':{'key':'house'}}
        c.start_progress=lambda *a,**k:None;c.set_progress=lambda **k:None;original=c.request
        def request(op,**kw):
            if op!='mine_block':return original(op,**kw)
            c.calls.append((op,kw));c.last='joined-'+str(len(c.calls))
            if fault=='unknown':
                return {'id':c.last,'world_session':c.world,'phase':'done','server_confirmed':True,
                        'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
                        'native_sequence':2,'server_ack_sequence':1}
            if fault=='rejected':
                return {'id':c.last,'world_session':c.world,'op':op,'phase':'waiting','detail':'mining target is occluded',
                        'mining_target':kw['pos'],'server_confirmed':False,'outcome_pending':False,'server_update_seen':False,
                        'native_sequence':-1,'server_ack_sequence':-1}
            c.blocks.pop(tuple(kw['pos']));c.blocks[(1,70,3)]=pointed(70,'down','tip')
            lower=kw['pos'][1]-1
            if (1,lower,3)in c.blocks and lower>=64:c.blocks[(1,lower,3)]=pointed(lower,'up','tip')
            if fault!='no_gain':c.counts['minecraft:pointed_dripstone']+=1
            return {'id':c.last,'world_session':c.world,'phase':'done','server_confirmed':True,
                    'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
                    'native_sequence':2,'server_ack_sequence':2}
        c.request=request;return c

    def execute(self,c,out):
        def move(c,point,*a,**kw):c.pos=list(point);return {'complete':True}
        with patch.object(m,'move_replanning_once',side_effect=move):
            return m.run(c,[1,70,3],61,[1,2],{'min':[-3,60,-3],'max':[5,123,7]},out,lambda:None)

    def test_live_sequence_only_mines_six_upward_blocks_with_real_inventory_credit(self):
        with tempfile.TemporaryDirectory()as d:
            c=self.client(Path(d));result=self.execute(c,Path(d)/'run')
            self.assertTrue(result['complete']);self.assertEqual(6,result['actual_backpack_gain'])
            self.assertEqual(list(range(69,63,-1)),[kw['pos'][1]for op,kw in c.calls if op=='mine_block'])
            self.assertEqual({63,70,71,72},{p[1]for p in c.blocks});self.assertEqual(8,c.counts[m.ITEM])
    def test_unknown_ack_is_durable_and_blocks_a_new_job_without_replay(self):
        with tempfile.TemporaryDirectory()as d:
            c=self.client(Path(d),'unknown')
            with self.assertRaisesRegex(JobBlocked,'unconfirmed'):self.execute(c,Path(d)/'run')
            shared=next((Path(d)/'dripstone-growth-intents').glob('*.json'));old=shared.read_bytes()
            with self.assertRaisesRegex(JobBlocked,'unresolved'):self.execute(c,Path(d)/'again')
            self.assertEqual(old,shared.read_bytes());self.assertEqual(1,len([1 for op,kw in c.calls if op=='mine_block']))
    def test_no_loot_and_known_rejection_never_manufacture_source_credit(self):
        for fault in ('no_gain','rejected'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory()as d:
                c=self.client(Path(d),fault);result=self.execute(c,Path(d)/'run')
                self.assertFalse(result['complete']);self.assertEqual(0,result['resource_credit']);self.assertIsNone(result['pending'])
                self.assertIn((1,70,3),c.blocks);self.assertIn((1,63,3),c.blocks)


if __name__=='__main__':unittest.main()
