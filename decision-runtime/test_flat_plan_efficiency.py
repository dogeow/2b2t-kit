import unittest
from unittest.mock import patch
from projection_flat_plan import FlatLayout,next_batch
from projection_patch_plan import connected_mask
from material_jobs.projection_spatial_cache import native_content_hash
from projection_flat_backend import planned_stack_in_hand

class FlatEfficiencyTests(unittest.TestCase):
    def fixture(self,width=10,depth=8):
        expected=[{'pos':[x,64,z],'item':'minecraft:stone','state':'Block{minecraft:stone}'}
                  for x in range(width)for z in range(depth)]
        digest=native_content_hash(expected)
        layout=FlatLayout({'model_schema':1,'content_hash':digest,'loaded_chunks_verified':True,
            'loaded_server_chunks_verified':True,'placement_key':'map','bounds':{'min':[0,64,0],
            'max':[width-1,64,depth-1]},'total':len(expected),'expected':expected},{'schema':1,'content_hash':digest})
        rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(43)]
        rows[0]={'slot':0,'item':'minecraft:stone','count':64,'max_stack':64}
        return layout,{'pos':[2,66.75,3],'inventory':rows,'projection_selection':{'key':'map'}}

    def test_a_four_by_four_hole_crossing_the_grid_uses_one_central_stop(self):
        import math
        layout,snapshot=self.fixture()
        hole={(x,64,z)for x in range(3,7)for z in range(2,6)}
        actual={p:r['state']for p,r in layout.expected.items()if p not in hole}
        plan=next_batch(layout,actual,snapshot)
        self.assertEqual(hole,set(map(tuple,plan['positions'])))
        self.assertEqual([5,65.75,4],plan['station'])
        eye=[plan['station'][0],plan['station'][1]+1.62,plan['station'][2]]
        self.assertTrue(all(math.dist(eye,[x+.5,y+1,z+.5])<4.5 for x,y,z in hole))
        # Printer anchors can require a side-face click, below the block top.
        # Keep every edge of the centered four-by-four mask within reach too.
        for x,y,z in hole:
            for hit in ([x+.5,y+.05,z],[x+.5,y+.05,z+1],
                        [x,y+.05,z+.5],[x+1,y+.05,z+.5]):
                self.assertLess(math.dist(eye,hit),4.25)
        self.assertLessEqual(plan['patch_max'][0]-plan['patch_min'][0],3)
        self.assertEqual(48,plan['retained_after'])

    def test_a_sparse_offset_hole_uses_its_own_middle_not_the_grid_edge(self):
        layout,snapshot=self.fixture()
        hole={(3,64,3),(4,64,3),(3,64,4),(4,64,4)}
        actual={p:r['state']for p,r in layout.expected.items()if p not in hole}
        plan=next_batch(layout,actual,snapshot)
        self.assertEqual(hole,set(map(tuple,plan['positions'])))
        self.assertEqual([4,65.75,4],plan['station'])

    def test_many_distant_correct_cells_never_expand_each_small_mask_input(self):
        expected=[{'pos':[x,64,z],'item':'minecraft:stone','state':'Block{minecraft:stone}'}
                  for x in range(128)for z in range(128)]
        digest=native_content_hash(expected)
        model={'model_schema':1,'content_hash':digest,'loaded_chunks_verified':True,
               'loaded_server_chunks_verified':True,'placement_key':'map','bounds':{'min':[0,64,0],
               'max':[127,64,127]},'total':len(expected),'expected':expected}
        layout=FlatLayout(model,{'schema':1,'content_hash':digest})
        actual={tuple(r['pos']):r['state']for r in expected if r['pos'][0]%4!=1 or r['pos'][2]%4!=1}
        rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(43)]
        rows[0]={'slot':0,'item':'minecraft:stone','count':64,'max_stack':64}
        snapshot={'pos':[2,66.75,2],'inventory':rows,'projection_selection':{'key':'map'}}
        def bounded(missing,correct,*args,**kwargs):
            self.assertLessEqual(len(missing),16);self.assertLessEqual(len(correct),36)
            return connected_mask(missing,correct,*args,**kwargs)
        with patch('projection_flat_plan.connected_mask',side_effect=bounded):
            result=next_batch(layout,actual,snapshot)
        self.assertEqual([[1,64,1]],result['positions']);self.assertTrue(result['planning_only'])
        self.assertEqual(0,result['placement_credit'])

    def test_only_full_current_plain_hand_metadata_skips_a_redundant_select(self):
        row={'slot':5,'item':'minecraft:stone','count':32,'max_stack':64}
        state={'selected_slot':5,'inventory':[row],'hand':{k:row[k]for k in ('item','count','max_stack')}}
        plan={'slot':5,'item':'minecraft:stone'}
        self.assertTrue(planned_stack_in_hand(state,plan,16))
        self.assertFalse(planned_stack_in_hand({**state,'selected_slot':4},plan,16))
        self.assertFalse(planned_stack_in_hand({**state,'hand':{'item':'minecraft:stone'}},plan,16))
        self.assertFalse(planned_stack_in_hand(state,plan,31))
        self.assertFalse(planned_stack_in_hand({**state,'inventory':[{**row,'custom_name':'reserved'}]},plan,16))

if __name__=='__main__':unittest.main()
