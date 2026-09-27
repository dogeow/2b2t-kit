import unittest
import json
from collections import Counter
from pathlib import Path
import tempfile
from unittest.mock import patch
from concrete_shelter import plan,dry_anchors,inside_hostiles
import concrete_shelter as shelter


class HatchClient:
    def __init__(self,layout,stock):
        self.layout=layout;self.stock=Counter(stock);self.stock['minecraft:diamond_pickaxe']=1
        self.pos=[layout['stand'][0]+.5,layout['hatch'][1]+2,layout['stand'][2]+.5]
        self.blocks={tuple(p):{'pos':p,'state':'Block{minecraft:cobblestone}','solid':True} for p in layout['blocks']}
        self.blocks[tuple(layout['leaf'])]={'pos':layout['leaf'],'state':'Block{minecraft:oak_leaves}[waterlogged=true]','solid':True}
        self.selected=None;self.actions=[]
    def status(self):
        return {'pos':self.pos,'entities':[],
                'inventory':[{'slot':i,'item':item,'count':count} for i,(item,count) in enumerate(self.stock.items())]}
    def request(self,op,**params):
        assert op=='snapshot';return self.status()
    def checked(self,op,**params):
        self.actions.append((op,params))
        hatch=tuple(self.layout['hatch'])
        if op=='select_item':
            if not self.stock[params['item']]:raise RuntimeError('Missing item:'+params['item'])
            self.selected=params['item']
        elif op=='interact':
            assert params['expected_hand']==self.selected
            self.blocks[hatch]={'pos':list(hatch),'state':'Block{'+self.selected+'}','solid':True}
            self.stock[self.selected]-=1
        elif op=='mine_block':
            assert self.blocks[hatch]['state']==params['expected_state']
            item=self.blocks.pop(hatch)['state'][6:-1];self.stock[item]+=1
        elif op=='navigate':self.pos=list(params['target'])
        else:raise AssertionError(op)
        return {'phase':'done'}


def scan_fixture(client,low,high):
    return {p:row for p,row in client.blocks.items() if all(low[i]<=p[i]<=high[i] for i in range(3))}


def land_fixture(client,block):
    client.pos=[block[0]+.5,block[1]+1,block[2]+.5]

class LayoutTest(unittest.TestCase):
    def test_enemy_inside_room_is_detected_before_descent(self):
        state={'entities':[{'type':'minecraft:zombie','pos':[10.5,63,20.5]},
                           {'type':'minecraft:skeleton','pos':[15,63,20.5]},
                           {'type':'minecraft:pig','pos':[10.5,63,20.5]}]}
        self.assertEqual(['minecraft:zombie'],[e['type'] for e in inside_hostiles(state,[10,63,20])])

    def test_waterlogged_support_is_not_sent_to_dry_approach_api(self):
        rows={(1,62,2):{'state':'Block{minecraft:oak_leaves}[waterlogged=true]','solid':True,'fluid':True},
              (0,63,2):{'state':'Block{minecraft:cobblestone}','solid':True,'fluid':False}}
        self.assertEqual([([0,63,2],'east','Block{minecraft:cobblestone}')],dry_anchors(rows,[1,63,2]))

    def test_work_cells_are_clear_and_hatch_remains_open(self):
        p=plan([10,63,20]);blocks={tuple(v) for v in p['blocks']}
        self.assertNotIn(tuple(p['cell']),blocks);self.assertNotIn(tuple(p['leaf']),blocks);self.assertNotIn(tuple(p['hatch']),blocks)
        for x in (10,11):
            for y in (63,64,65):self.assertNotIn((x,y,20),blocks)
    def test_all_three_wall_levels_enclose_both_work_cells(self):
        p=plan([10,63,20]);blocks={tuple(v) for v in p['blocks']}
        for y in (63,64,65):
            for x in range(9,13):
                for z in (19,21):self.assertIn((x,y,z),blocks)
            for x in (9,12):self.assertIn((x,y,20),blocks)
        self.assertEqual(len(blocks),len(p['blocks']))
    def test_ceiling_has_only_the_designated_exit_hatch(self):
        p=plan([10,63,20]);roof=[v for v in p['blocks'] if v[1]==66]
        self.assertEqual(11,len(roof));self.assertEqual([10,66,20],p['hatch'])

    def test_existing_cobble_deepslate_or_dirt_can_close_and_open_owned_hatch(self):
        for item in shelter.HATCH_ITEMS:
            with self.subTest(item=item),tempfile.TemporaryDirectory() as d:
                layout=plan([10,63,20]);path=Path(d)/'shelter.json'
                path.write_text(json.dumps({'complete':True,'layout':layout,'hatch_owned':False}))
                c=HatchClient(layout,{item:3})
                with patch.object(shelter,'scan',side_effect=scan_fixture), \
                     patch.object(shelter,'land_on_top',side_effect=land_fixture),patch.object(shelter,'light_station'):
                    ledger=shelter.enter_station(c,path)
                    self.assertEqual(item,ledger['hatch_item']);self.assertTrue(ledger['hatch_owned'])
                    self.assertEqual(2,c.stock[item]);self.assertEqual('Block{'+item+'}',c.blocks[tuple(layout['hatch'])]['state'])
                    self.assertEqual(item,json.loads(path.read_text())['hatch_item'])
                    shelter.exit_station(c,ledger)
                self.assertFalse(ledger['hatch_owned']);self.assertNotIn(tuple(layout['hatch']),c.blocks)
                self.assertEqual(3,c.stock[item]);self.assertNotIn(str(path)+'#hatch',c.resource_cleanup)

    def test_hatch_material_choice_uses_backpack_and_never_requires_missing_cobble(self):
        def state(items):return {'inventory':[{'slot':slot,'item':item,'count':count} for slot,item,count in items]}
        self.assertEqual('minecraft:cobbled_deepslate',shelter.choose_hatch_item(state([(0,'minecraft:cobbled_deepslate',3),(1,'minecraft:dirt',16)])))
        self.assertEqual('minecraft:cobblestone',shelter.choose_hatch_item(state([(0,'minecraft:cobbled_deepslate',3),(1,'minecraft:cobblestone',1)])))
        self.assertIsNone(shelter.choose_hatch_item(state([(40,'minecraft:cobblestone',1)])))

    def test_exit_legacy_ledger_defaults_to_cobble_and_changed_or_unowned_hatch_is_preserved(self):
        for recorded,actual,owned,allowed in ((None,'minecraft:cobblestone',True,True),
                ('minecraft:cobbled_deepslate','minecraft:cobblestone',True,False),
                ('minecraft:dirt','minecraft:dirt',False,False),
                ('minecraft:diamond_block','minecraft:diamond_block',True,False)):
            with self.subTest(recorded=recorded,actual=actual,owned=owned),tempfile.TemporaryDirectory() as d:
                layout=plan([10,63,20]);path=Path(d)/'shelter.json';c=HatchClient(layout,{})
                ledger={'path':str(path),'layout':layout,'hatch_owned':owned}
                if recorded is not None:ledger['hatch_item']=recorded
                c.blocks[tuple(layout['hatch'])]={'state':'Block{'+actual+'}','solid':True}
                with patch.object(shelter,'scan',side_effect=scan_fixture):
                    if allowed:shelter.exit_station(c,ledger)
                    else:
                        with self.assertRaisesRegex(RuntimeError,'unowned or changed'):shelter.exit_station(c,ledger)
                        self.assertEqual([],c.actions);self.assertIn(tuple(layout['hatch']),c.blocks)

if __name__=='__main__':unittest.main()
