import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from shallow_gravel import shallow_candidates,open_and_harvest


def row(pos,state,solid=True,fluid=False):
    return {'pos':pos,'state':state,'solid':solid,'fluid':fluid,'block_entity':False}


class ShallowGravelTest(unittest.TestCase):
    def test_one_or_two_natural_soil_layers_above_supported_gravel(self):
        gravel=row([10,62,20],'Block{minecraft:gravel}')
        support=row([10,61,20],'Block{minecraft:stone}')
        dirt=row([10,63,20],'Block{minecraft:dirt}')
        found=shallow_candidates([support,gravel,dirt],[10,62,20],[10,62,20],2,70)
        self.assertEqual(1,len(found));self.assertEqual([dirt['pos']], [x['pos'] for x in found[0]['cover']])
        grass=row([10,64,20],'Block{minecraft:grass_block}[snowy=false]')
        plant=row([10,65,20],'Block{minecraft:short_grass}',solid=False)
        plant['passable']=True
        found=shallow_candidates([support,gravel,dirt,grass,plant],[10,62,20],[10,62,20],2,70)
        self.assertEqual([grass['pos'],dirt['pos']],[x['pos'] for x in found[0]['cover']])

    def test_water_covered_cave_or_player_block_is_not_shallow_surface(self):
        base=[row([10,61,20],'Block{minecraft:stone}'),
              row([10,62,20],'Block{minecraft:gravel}'),
              row([10,63,20],'Block{minecraft:dirt}')]
        self.assertEqual([],shallow_candidates(base+[row([13,63,20],'Block{minecraft:water}',fluid=True)],
                                               [10,62,20],[10,62,20],2,70))
        self.assertEqual([],shallow_candidates(base+[row([10,66,20],'Block{minecraft:stone}')],
                                               [10,62,20],[10,62,20],2,70))
        self.assertEqual([],shallow_candidates(base[:-1]+[row([10,63,20],'Block{minecraft:stone_bricks}')],
                                               [10,62,20],[10,62,20],2,70))

    def test_new_water_near_cover_stops_before_any_mining_action(self):
        class Client:
            calls=[]
            def status(self):
                return {'inventory':[{'item':'minecraft:diamond_shovel','count':1,'durability':500}]}
            def request(self,op,**params):
                self.calls.append(op)
                if op!='scan':raise AssertionError('No approach or mining when water appeared')
                return {'blocks':[row([10,63,20],'Block{minecraft:dirt}'),
                                  row([13,63,20],'Block{minecraft:water}',fluid=True)]}
        candidate={'pos':[10,62,20],'surface_y':63,
                   'cover':[{'pos':[10,63,20],'state':'Block{minecraft:dirt}'}]}
        with tempfile.TemporaryDirectory() as directory:
            result=open_and_harvest(Client(),candidate,Path(directory))
        self.assertEqual('Soil or water buffer changed before break',result['stopped'])

    def test_exact_natural_cover_is_removed_once_before_gravel_harvest(self):
        candidate={'pos':[10,62,20],'surface_y':63,
                   'cover':[{'pos':[10,63,20],'state':'Block{minecraft:dirt}'}]}
        class Client:
            mined=False
            mine_calls=0
            def status(self):
                inventory=[{'slot':i,'item':'minecraft:air','count':0} for i in range(36)]
                inventory[0]={'slot':0,'item':'minecraft:diamond_shovel','count':1,'durability':500}
                if self.mined:inventory[1]={'slot':1,'item':'minecraft:dirt','count':1}
                return {'inventory':inventory,'entities':[]}
            def request(self,op,**params):
                if op=='scan':
                    blocks=[row([10,61,20],'Block{minecraft:stone}'),
                            row([10,62,20],'Block{minecraft:gravel}')]
                    if not self.mined:blocks.append(row([10,63,20],'Block{minecraft:dirt}'))
                    return {'blocks':blocks}
                if op=='approach_block':return {'phase':'done'}
                if op=='mine_block':
                    self.mine_calls+=1;self.mined=True;return {'phase':'done'}
                raise AssertionError(op)
            def checked(self,op,**params):
                if op!='select_item':raise AssertionError(op)
        client=Client()
        with tempfile.TemporaryDirectory() as directory,patch('shallow_gravel.harvest',return_value={'gained':1}) as mine:
            result=open_and_harvest(client,candidate,Path(directory))
        self.assertEqual(1,client.mine_calls)
        self.assertEqual(1,len(result['cover']))
        mine.assert_called_once()


if __name__=='__main__':unittest.main()
