import unittest

from deep_gravel_survey import deep_candidates,terrain_summary


def row(x,y,z,state,solid=True,fluid=False,block_entity=False):
    return {'pos':[x,y,z],'state':state,'solid':solid,'fluid':fluid,
            'block_entity':block_entity}


class DeepGravelSurveyTest(unittest.TestCase):
    def column(self,depth=12):
        top=70;target=top-depth
        rows=[row(10,top,20,'Block{minecraft:grass_block}'),
              row(10,target,20,'Block{minecraft:gravel}'),
              row(10,target-1,20,'Block{minecraft:stone}')]
        rows.extend(row(10,y,20,'Block{minecraft:dirt}' if y>=top-2 else 'Block{minecraft:stone}')
                    for y in range(target+1,top))
        return rows

    def test_finds_only_sealed_natural_column_at_accepted_depth(self):
        rows=self.column()
        found=deep_candidates(rows,[10,40,20],[10,90,20])
        self.assertEqual(1,len(found))
        self.assertEqual(12,found[0]['depth'])
        self.assertEqual([10,58,20],found[0]['pos'])
        self.assertEqual(12,len(found[0]['cover']))
        self.assertEqual(9,deep_candidates(self.column(9),[10,40,20],[10,90,20])[0]['depth'])
        self.assertEqual([],deep_candidates(self.column(21),[10,40,20],[10,90,20]))
        self.assertEqual([],deep_candidates(self.column(9),[10,40,20],[10,90,20],10,20))
        exposed=[row(10,70,20,'Block{minecraft:gravel}'),
                 row(10,69,20,'Block{minecraft:stone}')]
        self.assertEqual(0,deep_candidates(exposed,[10,40,20],[10,90,20])[0]['depth'])

    def test_rejects_water_cave_and_player_structure(self):
        base=self.column()
        self.assertEqual([],deep_candidates(base+[row(13,60,20,'Block{minecraft:water}',fluid=True)],
                                            [10,40,20],[10,90,20]))
        cave=[r for r in base if r['pos']!=[10,64,20]]
        self.assertEqual([],deep_candidates(cave,[10,40,20],[10,90,20]))
        built=[r if r['pos']!=[10,64,20] else row(10,64,20,'Block{minecraft:stone_bricks}')
               for r in base]
        self.assertEqual([],deep_candidates(built,[10,40,20],[10,90,20]))
        self.assertEqual([],deep_candidates(base+[row(12,69,20,'Block{minecraft:chest}',block_entity=True)],
                                            [10,40,20],[10,90,20]))

    def test_surface_summary_distinguishes_land_and_water_columns(self):
        rows=[row(10,62,20,'Block{minecraft:water}',solid=False,fluid=True),
              row(11,65,20,'Block{minecraft:grass_block}')]
        self.assertEqual({'land_columns':1,'water_columns':1,'other_columns':0,'unloaded_columns':0},
                         terrain_summary(rows,[10,40,20],[11,100,20]))


if __name__=='__main__':unittest.main()
