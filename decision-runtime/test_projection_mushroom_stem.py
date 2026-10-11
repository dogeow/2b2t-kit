import unittest
from projection_flat_plan import full_block, next_batch
from test_projection_flat_jobs import model,layout_for,state
from material_jobs.projection_spatial_cache import native_content_hash

STEM='minecraft:mushroom_stem'
STATE='Block{minecraft:mushroom_stem}[down=true,east=true,north=true,south=true,up=true,west=true]'


class MushroomStemPlanTests(unittest.TestCase):
    def fixture(self,adjacent=False):
        m=model(width=3,depth=1);m['expected'][1].update(item=STEM,state=STATE)
        if adjacent:m['expected'][2].update(item=STEM,state=STATE)
        m['content_hash']=native_content_hash(m['expected']);layout=layout_for(m)
        s=state(4);s['inventory'][5]['item']=STEM;s['target_stack_sizes']={STEM:64}
        s['projection_mushroom_stem_seed_protocol']=1
        actual={(0,64,0):'Block{minecraft:stone}',(2,64,0):'Block{minecraft:stone}'}if not adjacent else {(0,64,0):'Block{minecraft:stone}'}
        return layout,s,actual
    def test_isolated_stem_is_always_one_native_seed_even_with_real_adjacent_support(self):
        layout,s,actual=self.fixture();plan=next_batch(layout,actual,s)
        self.assertEqual('air_seed',plan['operation']);self.assertEqual([[1,64,0]],plan['positions'])
        self.assertEqual(3,plan['retained_after'])
    def test_old_host_adjacent_stems_and_false_skin_faces_remain_excluded(self):
        layout,s,actual=self.fixture();s.pop('projection_mushroom_stem_seed_protocol')
        self.assertEqual('blocked',next_batch(layout,actual,s)['phase'])
        layout,s,actual=self.fixture(True);self.assertFalse(layout.fillable&layout.single_seed_only)
        self.assertEqual('blocked',next_batch(layout,actual,s)['phase'])
        self.assertFalse(full_block(STATE.replace('north=true','north=false'),STEM))


if __name__=='__main__':unittest.main()
