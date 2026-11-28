"""survival_world terrain checks, kept when the model-driven survival bootstrap was removed."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from survival_world import World,shelter,support_footprint

def row(p,name,solid=True,passable=False):
    return {'pos':list(p),'state':'Block{minecraft:'+name+'}','solid':solid,'passable':passable,'fluid':False,'block_entity':False}

def terrain():return [row((x,0,z),'stone') for x in range(-6,7) for z in range(-6,7)]
def state():
    return {'bridge_version':2,'connected':True,'server':'singleplayer','dimension':'minecraft:overworld','game_mode':'survival',
            'world_name':'Trial','world_session':'a','health':20,'food':20,'manual_movement':False,'window_active':True,
            'screen':'','pos':[.5,1,.5],'control_revision':4,'last_request':'old','phase':'done','entities':[],
            'inventory':[{'item':'minecraft:oak_log','count':2}],'menu':{'id':0,'type':'InventoryMenu','cursor':{'count':0},'slots':[]}}

class WorldTests(unittest.TestCase):
    def test_unknown_space_and_pits_cannot_be_walked_into(self):
        rows=[r for r in terrain() if r['pos']!=[1,0,0]]
        w=World(rows,[-6,0,-6],[6,4,6]);paths=w.paths([.5,1,.5])
        self.assertNotIn((1,1,0),paths);self.assertNotIn((7,1,0),paths)
        self.assertIn((2,1,0),paths) # May route around the hole.
    def test_magma_and_water_never_form_walkway(self):
        rows=[r for r in terrain() if r['pos']!=[1,0,0]]+[row((1,0,0),'magma_block'),row((0,1,1),'water',False,True)]
        paths=World(rows,[-6,0,-6],[6,4,6]).paths([.5,1,.5])
        self.assertNotIn((1,1,0),paths);self.assertNotIn((0,1,1),paths)
    def test_player_standing_on_block_edge_recenters_onto_actual_support(self):
        rows=[r for r in terrain() if r['pos']!=[0,0,0]]
        w=World(rows,[-6,0,-6],[6,4,6]);paths=w.paths([.04,1,.5])
        self.assertEqual(w.route(paths,(-1,1,0)),[(-1,1,0)])
        self.assertFalse(w.paths([.5,1,.5]))
    def test_one_block_step_needs_head_clearance(self):
        rows=terrain()+[row((1,1,0),'stone'),row((0,3,0),'stone')]
        w=World(rows,[-1,0,0],[1,4,0])
        self.assertNotIn((1,2,0),w.paths([.5,1,.5]))
    def test_open_door_allows_entry_but_closed_door_does_not(self):
        base=terrain();opened=row((1,1,0),'oak_door');opened['state']+='[open=true]'
        w=World(base+[opened],[-6,0,-6],[6,4,6]);self.assertTrue(w.open((1,1,0)))
        opened['state']=opened['state'].replace('true','false');self.assertFalse(w.open((1,1,0)))
    def test_resource_selection_respects_camp_and_current_footing(self):
        rows=terrain()+[row((2,1,0),'oak_log'),row((-2,1,0),'oak_log')]
        w=World(rows,[-6,0,-6],[6,4,6]);found=w.resource([.5,1,.5],{'oak_log'},{(2,1,0)})
        self.assertEqual(found[0],(-2,1,0))
        self.assertIsNone(w.resource([.5,1,.5],{'oak_log'},{(2,1,0),(-2,1,0)}))
    def test_real_body_straddling_two_blocks_protects_both_supports(self):
        rows=[r for r in terrain() if r['pos']!=[1,0,0]]+[row((1,0,0),'iron_ore')]
        w=World(rows,[-6,-1,-6],[6,4,6])
        self.assertEqual(support_footprint([.98,1,.5]),{(0,0,0),(1,0,0)})
        self.assertEqual(support_footprint([.98,1,.02]),
                         {(0,0,-1),(0,0,0),(1,0,-1),(1,0,0)})
        self.assertIsNone(w.resource([.98,1,.5],{'iron_ore'}))
    def test_resource_cannot_choose_the_only_stance_on_top_of_its_target(self):
        target=(2,1,0);stance=(2,2,0)
        w=World(terrain()+[row(target,'iron_ore')],[-6,-1,-6],[6,4,6])
        # A ledge can expose only its top, reached from a rising route. Even
        # though the ore is visible, standing on it is not a mining stance.
        parents={(0,1,0):None,(1,1,0):(0,1,0),stance:(1,1,0)}
        with patch.object(w,'paths',return_value=parents),patch.object(
                w,'sight',side_effect=lambda feet,block:feet==stance):
            self.assertIsNone(w.resource([.5,1,.5],{'iron_ore'}))
    def test_normal_side_wall_stone_is_still_a_resource(self):
        base=[row(tuple(r['pos']),'dirt') for r in terrain()]
        w=World(base+[row((2,1,0),'stone')],[-6,-1,-6],[6,4,6])
        target,path=w.resource([.5,1,.5],{'stone'})
        self.assertEqual(target,(2,1,0))
        self.assertFalse(any(target in support_footprint([p[0]+.5,p[1],p[2]+.5]) for p in path))
    def test_hut_has_full_roof_and_only_door_opening(self):
        blocks,door=shelter([0,1,0]);self.assertEqual(len(set(blocks)),55)
        self.assertNotIn(door,blocks);self.assertNotIn((0,2,2),blocks)
        self.assertEqual(sum(y==3 for x,y,z in blocks),25)
    def test_resource_columns_are_removed_from_the_top(self):
        w=World(terrain()+[row((2,y,0),'dirt') for y in (1,2,3)],[-6,0,-6],[6,5,6])
        target,path=w.resource([.5,1,.5],{'dirt'})
        self.assertEqual(target,(2,3,0))
    def test_grass_spread_does_not_count_as_a_hole_in_an_earth_shelter(self):
        w=World([row((0,1,0),'grass_block')],[-1,0,-1],[1,3,1])
        self.assertTrue(w.earth((0,1,0)))
        self.assertFalse(w.earth((1,1,0)))
    def test_camp_rejects_an_obstructed_flat_area(self):
        w=World(terrain(),[-6,0,-6],[6,4,6]);self.assertIsNotNone(w.camp([.5,1,.5]))
        w=World(terrain()+[row((x,2,z),'stone') for x in range(-6,7) for z in range(-6,7)],[-6,0,-6],[6,4,6])
        self.assertIsNone(w.camp([.5,1,.5]))


class MiningBridge:
    """Normal native receipts with controllable arrival drift; no live game."""
    def __init__(self,root,rows):
        self.root=Path(root);self.world='Trial';self.origin=[.5,1,.5]
        self.state={**state(),'bridge_version':3,'world_id':'/saves/Trial',
                    'inventory':[{'item':'minecraft:wooden_pickaxe','count':1}]}
        self.rows=list(rows);self.requests=[];self.select_position=None
    def read(self):return self.state
    def close(self):pass
    def wait(self,seconds):pass
    def select(self,item):
        if self.select_position is not None:self.state['pos']=list(self.select_position)
    def request(self,op,**args):
        self.requests.append((op,args))
        if op=='scan':return {**self.state,'blocks':self.rows}
        if op in {'walk','walk_path'}:
            self.state['pos']=list(args['path'][-1] if op=='walk_path' else args['target'])
        if op=='mine_block':
            self.rows=[r for r in self.rows if r['pos']!=args['pos']]
            self.state['inventory'].append({'item':'minecraft:cobblestone','count':1})
        return self.state


if __name__=='__main__':unittest.main()
