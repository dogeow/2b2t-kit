import unittest

from ocean_gravel_survey import exposed_ocean_gravel


def row(x,y,z,state,solid=True,fluid=False,block_entity=False):
    return {'pos':[x,y,z],'state':state,'solid':solid,'fluid':fluid,
            'block_entity':block_entity}


class OceanGravelSurveyTest(unittest.TestCase):
    def sea_column(self,x=10,z=20,depth=4):
        bottom=62-depth
        rows=[row(x,bottom-1,z,'Block{minecraft:stone}'),
              row(x,bottom,z,'Block{minecraft:gravel}')]
        rows.extend(row(x,y,z,'Block{minecraft:water}[level=0]',False,True)
                    for y in range(bottom+1,63))
        return rows

    def test_shallow_exposed_gravel_and_sloped_neighbor_form_one_patch(self):
        rows=self.sea_column()+self.sea_column(11,20,5)
        found=exposed_ocean_gravel(rows,[10,40,20],[11,70,20])
        self.assertEqual(2,len(found))
        self.assertEqual({2},{item['exposed_patch_size'] for item in found})
        self.assertEqual({4,5},{item['water_depth'] for item in found})

    def test_deep_water_roof_and_lava_are_excluded(self):
        self.assertEqual([],exposed_ocean_gravel(self.sea_column(depth=13),[10,40,20],[10,70,20]))
        roof=self.sea_column()+[row(10,63,20,'Block{minecraft:stone}')]
        self.assertEqual([],exposed_ocean_gravel(roof,[10,40,20],[10,70,20]))
        lava=self.sea_column()+[row(11,59,20,'Block{minecraft:lava}[level=0]',False,True)]
        self.assertEqual([],exposed_ocean_gravel(lava,[10,40,20],[10,70,20]))

    def test_waterlogged_plants_and_flow_are_not_clear_mining_columns(self):
        for obstructing in ('Block{minecraft:kelp_plant}',
                            'Block{minecraft:seagrass}',
                            'Block{minecraft:water}[level=1]'):
            with self.subTest(obstructing=obstructing):
                rows=self.sea_column()
                next(row for row in rows if row['pos']==[10,60,20])['state']=obstructing
                self.assertEqual([],exposed_ocean_gravel(rows,[10,40,20],[10,70,20]))


if __name__=='__main__':unittest.main()
