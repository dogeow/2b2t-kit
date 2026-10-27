import unittest
from material_jobs.dripstone_cave_survey import entries


def row(pos,name,**kw):
    return {'pos':pos,'state':'Block{minecraft:'+name+'}','fluid':False,
            'block_entity':False,'solid':True,**kw}


class CaveSurveyTest(unittest.TestCase):
    low=[-4,0,-4]; high=[4,80,4]

    def test_real_cave_target_and_dry_air_entry_are_required(self):
        self.assertEqual([],entries([],self.low,self.high))
        result=entries([row([0,32,0],'dripstone_block')],self.low,self.high)
        self.assertTrue(result)
        self.assertTrue(all(e['target']==[0,32,0] for e in result))
        self.assertEqual(0,result[0]['entry_blocks'])

    def test_protected_material_is_not_a_reason_to_open_a_new_shaft(self):
        self.assertEqual([],entries([row([0,32,0],'dripstone_block')],self.low,self.high,protected={(0,32,0)}))

    def test_wet_or_structural_ceiling_is_never_excavated(self):
        for name,kw in [('water',{'fluid':True}),('chest',{'block_entity':True}),('stone_bricks',{})]:
            with self.subTest(name=name):
                rows=[row([0,32,0],'dripstone_block')]+[row([x,50,z],name,**kw)
                    for x in range(-3,4) for z in range(-3,4)]
                self.assertEqual([],entries(rows,self.low,self.high))

    def test_ordinary_dry_ceiling_produces_top_down_bounded_entry(self):
        rows=[row([0,32,0],'dripstone_block')]+[row([x,y,z],'stone')
            for x in range(-3,4) for z in range(-3,4) for y in range(40,46)]
        result=entries(rows,self.low,self.high)
        self.assertTrue(result)
        self.assertEqual(6,result[0]['entry_blocks'])
        self.assertTrue(all(e['entry_blocks']in(6,7) and e['top']==45 and e['bottom']<40 for e in result))


if __name__=='__main__': unittest.main()
