"""Pure local source/geometry/frontier regressions; no game client or RPC."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs import projection_spatial_cache as cache

DIRT='minecraft:dirt'
DIRT_STATE='Block{minecraft:dirt}'


def row(x,y=64,z=0,item=DIRT,state=DIRT_STATE):
    return {'pos':[x,y,z],'state':state,'item':item}


def geometry(expected):
    return {'placement_key':'test-locked-placement','content_hash':cache.native_content_hash(expected),
            'origin':[0,64,0],'rotation':'NONE','mirror':'NONE',
            'bounds':{'min':[min(r['pos'][i] for r in expected) for i in range(3)],
                      'max':[max(r['pos'][i] for r in expected) for i in range(3)]}}


def air(x,y=64,z=0):return {'pos':[x,y,z],'state':'AIR','replaceable':True,'support':False}
def solid(x,y=64,z=0,state=DIRT_STATE):return {'pos':[x,y,z],'state':state,'replaceable':False,'support':True}


def seal(data):
    value={k:v for k,v in data.items() if k!='index_hash'}
    data['index_hash']=hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class ProjectionSpatialCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'index.json'
    def index(self,expected):return cache.build_index(expected,**geometry(expected),total=len(expected))
    def frontier(self):return cache.SupportedFrontier(self.index([row(x) for x in range(3)]),'world-a')

    def test_native_digest_is_lexicographic_world_lines_and_exact_properties(self):
        expected=[row(2,state='Block{minecraft:oak_log}[axis=x]',item='minecraft:oak_log'),row(10)]
        golden='10,64,0\tBlock{minecraft:dirt}\tminecraft:dirt\n2,64,0\tBlock{minecraft:oak_log}[axis=x]\tminecraft:oak_log\n'
        self.assertEqual(hashlib.sha256(golden.encode()).hexdigest(),cache.native_content_hash(expected))
        wrong=copy.deepcopy(expected);wrong[0]['state']='Block{minecraft:oak_log}[axis=y]'
        with self.assertRaises(cache.CacheInvalidated):cache.build_index(wrong,**geometry(expected))

    def test_full_table_rejects_contradictory_hash_duplicates_partial_and_unbounded_input(self):
        expected=[row(0),row(1)]
        for changed in ({'content_hash':'0'*64},{'content_hash':'INVALID'}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):cache.build_index(expected,**(geometry(expected)|changed))
        with self.assertRaises(ValueError):cache.build_index([row(0),row(0)],**geometry(expected))
        with self.assertRaises(ValueError):cache.build_index(expected,**geometry(expected),total=3)
        with self.assertRaises(ValueError):cache.build_index(expected,**geometry(expected),total=True)
        with self.assertRaises(ValueError):cache.build_index([row(0)]*(cache.MAX_CELLS+1),**geometry(expected))
        with self.assertRaises(ValueError):cache.build_index(iter(expected),**geometry(expected))
        invalid=row(True)
        with self.assertRaises(ValueError):cache.native_content_hash([invalid])

    def test_exact_state_boundaries_gaps_y_z_and_items_never_merge_runs(self):
        log='minecraft:stripped_cherry_wood'
        expected=[row(0),row(1),row(3),row(4,y=65),row(4,z=1),
                  row(5,item=log,state='Block{minecraft:stripped_cherry_wood}[axis=y]'),
                  row(6,item=log,state='Block{minecraft:stripped_cherry_wood}[axis=x]')]
        index=self.index(expected)
        self.assertEqual([(0,1,64,0),(3,3,64,0),(4,4,64,1),(4,4,65,0)],
                         [(r.min_x,r.max_x,r.y,r.z) for r in index.x_runs[DIRT]])
        self.assertEqual(['Block{minecraft:stripped_cherry_wood}[axis=y]',
                          'Block{minecraft:stripped_cherry_wood}[axis=x]'],[r.state for r in index.x_runs[log]])
        all_positions=[p for runs in index.x_runs.values() for run in runs for p in run.positions()]
        self.assertEqual(len(expected),len(set(all_positions)));self.assertEqual({tuple(r['pos']) for r in expected},set(all_positions))

    def test_six_neighbor_order_and_block_to_item_variants_are_preserved(self):
        expected=[row(0),row(0,y=65),row(1),row(4,item='minecraft:torch',state='Block{minecraft:wall_torch}[facing=north]'),
                  row(5,item='minecraft:air',state='Block{minecraft:bedrock}')]
        index=self.index(expected)
        self.assertEqual(((0,63,0),(0,65,0),(0,64,-1),(0,64,1),(-1,64,0),(1,64,0)),index.neighbors([0,64,0]))
        neighbors=index.neighbor_cells([0,64,0])
        self.assertEqual((0,65,0),neighbors[1].pos);self.assertEqual((1,64,0),neighbors[5].pos)
        self.assertIsNone(neighbors[0]);self.assertEqual(((4,64,0),),index.by_item['minecraft:torch'])

    def test_persistence_reuses_static_indices_but_never_persists_actual_progress(self):
        expected=[row(0),row(1,state='Block{minecraft:oak_log}[axis=y]',item='minecraft:oak_log')]
        index=self.index(expected);frontier=cache.SupportedFrontier(index,'world-a')
        frontier.observe('world-a',[solid(0)],evidence='server_ack',observed_at=1);index.save(self.path)
        restored=cache.load_index(self.path,**geometry(expected))
        self.assertEqual(index.cells,restored.cells);self.assertEqual(index.by_item,restored.by_item)
        self.assertEqual(index.x_runs,restored.x_runs);self.assertEqual(index.neighbors([0,64,0]),restored.neighbors([0,64,0]))
        fresh=cache.SupportedFrontier(restored,'world-b');self.assertEqual(frozenset(),fresh.observed_matches)
        encoded=json.loads(self.path.read_text());self.assertNotIn('actual',encoded);self.assertNotIn('world_session',encoded)
        with self.assertRaises(TypeError):restored.by_item[DIRT]=()
        with self.assertRaises(AttributeError):restored.scope=index.scope
        with self.assertRaises(AttributeError):fresh.index=index

    def test_key_hash_origin_rotation_mirror_and_bounds_each_invalidate_saved_cache(self):
        expected=[row(0)];self.index(expected).save(self.path)
        changes=({'placement_key':'other'}, {'content_hash':'1'*64}, {'origin':[1,64,0]},
                 {'rotation':'CLOCKWISE_90'}, {'mirror':'FRONT_BACK'},
                 {'bounds':{'min':[-1,64,0],'max':[0,64,0]}})
        for changed in changes:
            with self.subTest(changed=changed),self.assertRaises(cache.CacheInvalidated):cache.load_index(self.path,**(geometry(expected)|changed))
        for changed in changes+({'rotation':'invented'},):
            index=self.index(expected)
            with self.subTest(changed=changed),self.assertRaises(cache.CacheInvalidated):index.assert_scope(**(geometry(expected)|changed))
            with self.assertRaises(cache.CacheInvalidated):index.cell([0,64,0])
            with self.assertRaises(cache.CacheInvalidated):index.assert_scope(**geometry(expected))

    def test_cache_checksum_and_semantic_indices_refuse_tampering_even_when_resealed(self):
        expected=[row(0),row(1)];index=self.index(expected);index.save(self.path)
        good=json.loads(self.path.read_text())
        data=copy.deepcopy(good);data['neighbors'][0][5]=-1;self.path.write_text(json.dumps(data))
        with self.assertRaises(cache.CacheInvalidated):cache.load_index(self.path,**geometry(expected))
        for mutate in (lambda d:d['by_item'][DIRT].reverse(),lambda d:d['neighbors'][0].__setitem__(5,-1),
                       lambda d:d.__setitem__('runs',[[0,0],[1,1]]),lambda d:d.__setitem__('schema',True)):
            data=copy.deepcopy(good);mutate(data);seal(data);self.path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):cache.load_index(self.path,**geometry(expected))

    def test_loaded_file_and_native_model_receipt_are_bounded_and_typed(self):
        expected=[row(0)];model={'model_schema':1,'loaded_chunks_verified':True,'total':1,'expected':expected,**geometry(expected)}
        index=cache.index_from_model(model,origin=[0,64,0],rotation='NONE',mirror='NONE')
        self.assertEqual(expected[0]['state'],index.cells[0].state)
        for changed in ({'model_schema':True},{'loaded_chunks_verified':False},{'total':True},{'total':2}):
            with self.subTest(changed=changed),self.assertRaises(ValueError):cache.index_from_model(model|changed,origin=[0,64,0],rotation='NONE',mirror='NONE')
        self.path.write_bytes(b' '*1025)
        with patch.object(cache,'MAX_FILE_BYTES',1024),self.assertRaises(ValueError):cache.load_index(self.path,**geometry(expected))

    def test_incremental_frontier_uses_only_actual_support_and_reopens_after_removal(self):
        frontier=self.frontier()
        self.assertEqual(frozenset(),frontier.positions())
        delta=frontier.observe('world-a',[air(x) for x in range(3)]+[solid(-1)],evidence='scan',observed_at=1)
        self.assertEqual(frozenset({(0,64,0)}),frontier.positions(DIRT));self.assertEqual(frozenset(),frontier.observed_matches)
        delta=frontier.observe('world-a',[solid(0)],evidence='server_ack',observed_at=2)
        self.assertEqual(frozenset({(0,64,0),(1,64,0)}),delta.affected)
        self.assertEqual(frozenset({(1,64,0)}),frontier.positions());self.assertEqual(frozenset({(0,64,0)}),frontier.observed_matches)
        delta=frontier.observe('world-a',[air(0)],evidence='scan',observed_at=3)
        self.assertEqual(frozenset({(0,64,0)}),delta.added);self.assertEqual(frozenset({(1,64,0)}),delta.removed)
        self.assertEqual(frozenset(),frontier.observed_matches)
        delta=frontier.observe('world-a',[air(0)],evidence='scan',observed_at=4)
        self.assertEqual(frozenset(),delta.changed);self.assertEqual(frozenset(),delta.affected)

    def test_support_flags_change_even_with_same_state_and_omitted_air_stays_unknown(self):
        frontier=self.frontier()
        frontier.observe('world-a',[air(0),solid(-1)],evidence='scan',observed_at=1)
        self.assertIsNone(frontier.actual([1,64,0]));self.assertEqual(frozenset({(0,64,0)}),frontier.positions())
        update=solid(-1);update['support']=False
        delta=frontier.observe('world-a',[update],evidence='scan',observed_at=2)
        self.assertEqual(frozenset({(0,64,0)}),delta.affected);self.assertEqual(frozenset(),frontier.positions())
        self.assertIsNone(frontier.actual([1,64,0]))

    def test_world_change_clears_actual_states_and_rejects_delayed_old_ack(self):
        frontier=self.frontier();static=frontier.index.cells
        frontier.observe('world-a',[solid(0),air(1)],evidence='server_ack',observed_at=10)
        frontier.bind_world('world-b');self.assertIs(static,frontier.index.cells)
        self.assertEqual(frozenset(),frontier.positions());self.assertEqual(frozenset(),frontier.observed_matches)
        self.assertIsNone(frontier.actual([0,64,0]))
        with self.assertRaises(cache.CacheInvalidated):frontier.observe('world-a',[solid(0)],evidence='server_ack',observed_at=11)
        frontier.observe('world-b',[air(0),solid(-1)],evidence='scan',observed_at=1)
        self.assertEqual(frozenset({(0,64,0)}),frontier.positions())

    def test_bad_or_stale_observation_batch_is_atomic_and_cannot_guess_air_support(self):
        frontier=self.frontier();frontier.observe('world-a',[air(0),solid(-1)],evidence='scan',observed_at=1)
        bad_batches=([solid(0),air(50)], [solid(0),solid(0)],
                     [solid(0),{'pos':[1,64,0],'state':'garbage','replaceable':True,'support':False}],
                     [solid(0),{'pos':[1,64,0],'state':'AIR','replaceable':False,'support':True}])
        for updates in bad_batches:
            with self.assertRaises(ValueError):frontier.observe('world-a',updates,evidence='scan',observed_at=2)
            self.assertEqual(frozenset(),frontier.observed_matches);self.assertEqual(frozenset({(0,64,0)}),frontier.positions())
            self.assertEqual('AIR',frontier.actual([0,64,0]).state)
        for evidence,at in (('predicted',2),('scan',1),('scan',0),('scan',True)):
            with self.assertRaises(ValueError):frontier.observe('world-a',[solid(0)],evidence=evidence,observed_at=at)

    def test_state_grammar_does_not_drop_or_duplicate_properties(self):
        for state in ('garbage','Block{minecraft:oak_log}[axis=x,axis=y]','Block{minecraft:air}','AIR'):
            with self.subTest(state=state),self.assertRaises(ValueError):cache.native_content_hash([row(0,state=state)])
        expected=[row(0,item='minecraft:oak_stairs',state='Block{minecraft:oak_stairs}[facing=east,half=top,shape=straight,waterlogged=false]')]
        self.assertEqual(expected[0]['state'],self.index(expected).cells[0].state)


if __name__=='__main__':unittest.main()
