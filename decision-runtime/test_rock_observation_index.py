import random,unittest
from unittest.mock import patch
from material_jobs import acquisition as a


def reference(rows,low,high,item,allow_cleared=False):
    cells={tuple(r['pos']):r for r in rows};inside=[r for p,r in cells.items()if a.in_box(p,low,high)]
    if any(a.block_id(r) not in a.NATURAL|a.LIGHTS|a.AIR for r in inside):return None
    if any(a.block_id(r)=='minecraft:raw_iron_block'and not a.RAW_IRON_BLOCK_MIN_Y<=r['pos'][1]<=a.RAW_IRON_BLOCK_MAX_Y for r in inside):return None
    buffer=[r for p,r in cells.items()if all(low[i]-(2 if i==1 else 3)<=p[i]<=high[i]+(2 if i==1 else 3)for i in range(3))]
    if any(a._danger(r,True)for r in buffer):return None
    remaining=sum(a.block_id(r)in a.NATURAL for r in inside)
    if allow_cleared and remaining==0:
        if any(r.get('passable')is not True for r in inside):return None
        return {'available':0,'remaining':0}
    if any(not cells.get((x,low[1]-1,z),{}).get('solid')for x in range(low[0],high[0]+1)for z in range(low[2],high[2]+1)):return None
    return {'available':sum(a.block_id(r)in a.ROCK_SOURCES[item]for r in inside),'remaining':remaining}


class RockObservationIndexTest(unittest.TestCase):
    def rows(self):
        return [{'pos':[x,y,z],'state':'Block{minecraft:'+('tuff'if(x+y+z)%3==0 else 'stone')+'}',
                 'solid':True,'fluid':False,'block_entity':False,'passable':False}
                for x in range(-3,10)for y in range(-3,10)for z in range(-3,10)]
    def test_same_natural_hazard_floor_and_empty_results_as_original_checker(self):
        rows=self.rows();rng=random.Random(23)
        for name in [None,'minecraft:water','minecraft:chest','minecraft:raw_iron_block']:
            sample=[dict(r)for r in rows]
            if name:
                sample[rng.randrange(len(sample))].update(state='Block{'+name+'}',fluid=name.endswith('water'),block_entity=name.endswith('chest'))
            for _ in range(12):
                low=[rng.randrange(0,4)for _ in range(3)];high=[v+2 for v in low]
                for clear in [False,True]:
                    self.assertEqual(reference(sample,low,high,'minecraft:tuff',clear),a._rock_observation(sample,low,high,'minecraft:tuff',allow_cleared=clear))
    def test_candidate_trials_share_one_cell_index(self):
        rows=self.rows()
        with patch.object(a,'_rock_observation',wraps=a._rock_observation)as observed:
            a.rock_choice(rows,[0,0,0],[5,5,5],'minecraft:tuff',[0,8,0])
        self.assertGreater(observed.call_count,1)
        indexes=[call.kwargs['cells']for call in observed.call_args_list]
        self.assertTrue(all(value is indexes[0]for value in indexes))
