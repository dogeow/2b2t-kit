import unittest

from gravel_harvest import dry_top_gravel, fresh_drops


def block(pos,state):return {'pos':list(pos),'state':state}


class GravelHarvestTest(unittest.TestCase):
    def test_only_dry_exposed_top_is_mined(self):
        p=[10,63,20]
        rows=[block(p,'Block{minecraft:gravel}')]
        self.assertTrue(dry_top_gravel(rows,p))
        self.assertFalse(dry_top_gravel(rows+[block([10,64,20],'Block{minecraft:gravel}')],p))
        self.assertFalse(dry_top_gravel(rows+[block([11,63,20],'Block{minecraft:water}[level=0]')],p))
        self.assertFalse(dry_top_gravel(rows+[block([13,63,20],'Block{minecraft:water}[level=0]')],p))
        self.assertFalse(dry_top_gravel(rows+[block([13,65,20],'Block{minecraft:water}[level=0]')],p))
        self.assertTrue(dry_top_gravel(rows+[block([14,63,20],'Block{minecraft:water}[level=0]')],p))
        waterlogged=block([11,63,20],'Block{minecraft:seagrass}')
        waterlogged['fluid']=True
        self.assertFalse(dry_top_gravel(rows+[waterlogged],p))

    def test_existing_drops_are_not_claimed_as_new_gravel(self):
        p=[10,63,20]
        old={'uuid':'a','type':'minecraft:item','stack':{'item':'minecraft:gravel','count':1},'pos':[10.5,63.5,20.5]}
        new={'uuid':'b','type':'minecraft:item','stack':{'item':'minecraft:gravel','count':1},'pos':[10.7,63.5,20.5]}
        self.assertEqual([new],fresh_drops({'entities':[old]},{'entities':[old,new]},p))


if __name__=='__main__':unittest.main()
