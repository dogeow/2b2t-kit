import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from storage_find import find, item_id, match


def snapshot(pos,items,rows=None,**extra):
    return {'server':'simpcraft.com','dimension':'minecraft:overworld','worldId':'','status':'active',
        'x':pos[0],'y':pos[1],'z':pos[2],'blockId':'minecraft:chest','lastSeenEpochMillis':1,
        'items':rows if rows is not None else [{'id':i,'name':i,'count':c}for i,c in items.items()],**extra}


class StorageFindTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();game=Path(self.tmp.name)
        self.root=game/'config/twob2tkit/automation';self.root.mkdir(parents=True)
        self.config=game/'config/twob2tkit.json'
        self.state={'server':'simpcraft.com:25565','dimension':'minecraft:overworld','pos':[0,64,0]}

    def tearDown(self):self.tmp.cleanup()

    def write(self,*records):self.config.write_text(json.dumps({'storageSnapshots':list(records)}))

    def test_lists_current_world_containers_confirmed_and_largest_first(self):
        self.write(snapshot([100,64,0],{'minecraft:iron_ingot':64}),
            snapshot([10,64,0],{'minecraft:iron_ingot':5,'minecraft:coal':3}),
            snapshot([5,64,0],{'minecraft:iron_ingot':32},contentsDirty=True))
        result=find(self.root,['iron_ingot'],self.state)['items']['minecraft:iron_ingot']
        self.assertEqual(101,result['total']);self.assertEqual(69,result['confirmed_total'])
        self.assertEqual([[100,64,0],[10,64,0],[5,64,0]],[h['pos']for h in result['top']])
        self.assertFalse(result['top'][2]['confirmed'])

    def test_ignores_other_servers_dimensions_and_removed_containers(self):
        self.write(snapshot([1,64,0],{'minecraft:diamond':9},server='2b2t.org'),
            snapshot([2,64,0],{'minecraft:diamond':9},dimension='minecraft:the_nether'),
            snapshot([3,64,0],{'minecraft:diamond':9},status='missing'))
        result=find(self.root,['minecraft:diamond'],self.state)['items']['minecraft:diamond']
        self.assertEqual({'total':0,'confirmed_total':0,'packed_total':0,'containers':0,'top':[]},result)

    def test_limit_caps_listed_containers_but_not_totals(self):
        self.write(*[snapshot([i,64,0],{'minecraft:stone':1})for i in range(5)])
        result=find(self.root,['stone'],self.state,limit=2)['items']['minecraft:stone']
        self.assertEqual((5,5,2),(result['total'],result['containers'],len(result['top'])))

    def test_reports_shulker_contents_separately_from_loose_stock(self):
        self.write(snapshot([1,64,0],{'minecraft:blue_shulker_box':2},packedKnown=True,
                packedItems=[{'id':'minecraft:iron_ingot','name':'Iron','count':128}]),
            snapshot([2,64,0],{'minecraft:iron_ingot':4}),
            snapshot([3,64,0],{'minecraft:red_shulker_box':1}))
        out=find(self.root,['iron_ingot'],self.state)
        result=out['items']['minecraft:iron_ingot']
        self.assertEqual((4,128,2),(result['total'],result['packed_total'],result['containers']))
        self.assertEqual([[2,64,0],[1,64,0]],[h['pos']for h in result['top']])
        self.assertEqual(128,result['top'][1]['packed']);self.assertEqual(0,result['top'][1]['count'])
        self.assertEqual(1,out['unknown_shulker_containers'])

    def test_match_finds_enchantments_in_loose_and_packed_items_of_this_world_only(self):
        book={'id':'minecraft:enchanted_book','name':'附魔书','count':2,'searchTerms':'经验修补 mending'}
        self.write(snapshot([1,64,0],{},rows=[book]),
            snapshot([2,64,0],{'minecraft:blue_shulker_box':1},packedItems=[dict(book,count=5)]),
            snapshot([3,64,0],{},rows=[book],server='2b2t.org'),
            snapshot([4,64,0],{},rows=[dict(book,searchTerms='锋利 sharpness')]))
        out=match(self.root,'Mending',self.state)
        self.assertEqual(2,out['containers'])
        self.assertEqual([[1,64,0],[2,64,0]],[h['pos']for h in out['top']])
        self.assertTrue(out['top'][1]['matches'][0]['packed'])
        self.assertEqual('经验修补 mending',out['top'][0]['matches'][0]['enchantments'])

    def test_separate_enchanted_book_rows_are_summed_by_id_and_matched_individually(self):
        rows=[{'id':'minecraft:enchanted_book','name':'附魔书','count':1,'searchTerms':'mending 经验修补'},
              {'id':'minecraft:enchanted_book','name':'附魔书','count':3,'searchTerms':'sharpness 锋利 V'}]
        self.write(snapshot([1,64,0],{},rows=rows))
        self.assertEqual(4,find(self.root,['enchanted_book'],self.state)['items']['minecraft:enchanted_book']['total'])
        matches=match(self.root,'mending',self.state)['top'][0]['matches']
        self.assertEqual([1],[m['count']for m in matches])

    def test_each_container_reports_how_old_its_record_is(self):
        self.write(snapshot([1,64,0],{'minecraft:coal':3},lastSeenEpochMillis=1_000_000))
        hit=find(self.root,['coal'],self.state,now=1_000+7_200)['items']['minecraft:coal']['top'][0]
        self.assertEqual(2.0,hit['age_hours'])

    def test_item_id_accepts_bare_names(self):
        self.assertEqual('minecraft:oak_log',item_id(' Oak_Log '))
        self.assertEqual('minecraft:oak_log',item_id('minecraft:oak_log'))

    def test_cli_offline_lookup_never_reads_live_status_or_sends(self):
        import kit_cli
        self.write(snapshot([1,64,0],{'minecraft:coal':7}))
        out=io.StringIO()
        with patch('kit_cli.live_status')as live,patch('kit_cli.send')as send,contextlib.redirect_stdout(out):
            code=kit_cli.main(['--game-dir',self.tmp.name,'storage','find','--item','coal','--server','simpcraft.com'])
        self.assertEqual(0,code);live.assert_not_called();send.assert_not_called()
        self.assertEqual(7,json.loads(out.getvalue())['items']['minecraft:coal']['total'])


if __name__=='__main__':unittest.main()
