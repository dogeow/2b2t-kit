import unittest
from material_jobs.renewable_tall_flower import mother,planting_site

def b(pos,name,state='',solid=False,**kw):
    return {'pos':pos,'state':'Block{minecraft:'+name+'}'+state,
            'solid':solid,'fluid':False,'block_entity':False,**kw}

class TallFlowerTest(unittest.TestCase):
    def rows(self):return [b([0,63,0],'grass_block',solid=True),
        b([0,64,0],'rose_bush','[half=lower]'),b([0,65,0],'rose_bush','[half=upper]')]
    def test_both_live_halves_and_real_soil_are_required(self):
        self.assertIsNotNone(mother(self.rows(),[0,64,0]))
        for rows in (self.rows()[:-1],self.rows()[1:],
                     [b([0,63,0],'sand',solid=True)]+self.rows()[1:]):
            self.assertIsNone(mother(rows,[0,64,0]))
    def test_wrong_upper_half_fluid_building_and_hazard_are_refused(self):
        for extra in (b([1,64,0],'water',fluid=True),b([1,64,0],'chest',block_entity=True),
                      b([1,64,0],'pointed_dripstone'),b([1,64,0],'cobblestone',solid=True)):
            self.assertIsNone(mother(self.rows()+[extra],[0,64,0]))
        self.assertIsNone(mother(self.rows()[:-1]+[b([0,65,0],'rose_bush','[half=lower]')],[0,64,0]))
    def test_natural_foliage_and_other_tall_flowers_are_allowed(self):
        self.assertIsNotNone(mother(self.rows()+[b([1,66,0],'oak_leaves',solid=True),
            b([1,64,1],'lilac','[half=lower]')],[0,64,0]))

    def test_planting_requires_real_soil_and_both_empty_cells(self):
        soil=[b([0,63,0],'grass_block',solid=True)]
        self.assertTrue(planting_site(soil,[0,64,0]))
        for extra in (b([0,64,0],'short_grass'),b([0,65,0],'oak_leaves',solid=True)):
            self.assertFalse(planting_site(soil+[extra],[0,64,0]))
        self.assertFalse(planting_site([],[0,64,0]))
        self.assertFalse(planting_site([b([0,63,0],'grass_block',solid=True,fluid=True)],[0,64,0]))

if __name__=='__main__':unittest.main()
