from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from packed_equipment_batch import take
from test_packed_supplies import EquipmentWithdrawalTest
from test_anvil_enchant_preview import book,empty


class BatchTests(unittest.TestCase):
    def setup_client(self,folder,*,unknown_second=False):
        fixture=EquipmentWithdrawalTest();c=fixture.client(folder)
        c.server='simpcraft.com';c.world='w';c.task='t';c.time=0;c.book_clicks=0
        c.box=[empty(i)for i in range(27)]
        for i,row in enumerate([book('minecraft:efficiency',4),book(),book('minecraft:unbreaking',3),book('minecraft:thorns',3),book('minecraft:unbreaking',3)]):
            c.box[i]={**row,'slot':i}
        c.ender[24]['contains']=deepcopy(c.box[:5]);status=c.status;checked=c.checked
        def current():
            s=status();c.time+=1;s.update(time=c.time,world_session='w',dimension='minecraft:overworld');return s
        c.status=current
        def call(op,**p):
            result=checked(op,**p)
            if op=='slot_click'and c.kind=='ShulkerBoxMenu':
                c.book_clicks+=1
                if unknown_second and c.book_clicks==2:raise RuntimeError('second item outcome unknown')
            return result|{'id':'r-'+str(len(c.actions))}
        c.checked=call
        profile=Path(folder)/'profile.json';profile.write_text(json.dumps({'server':'simpcraft.com','dimension':'minecraft:overworld','ender_chest':fixture.ENDER,'shulker_pad':fixture.PAD}))
        return fixture,c,profile

    def execute(self,folder,*,unknown_second=False,missing=False):
        fixture,c,profile=self.setup_client(folder,unknown_second=unknown_second)
        requests=[book(),book('minecraft:thorns',3),book('minecraft:unbreaking',3),book('minecraft:unbreaking',3)]
        if missing:requests.append(book('minecraft:efficiency',5))
        def block(client,pos):
            if pos==[fixture.PAD[0],fixture.PAD[1]-1,fixture.PAD[2]]:return 'Block{minecraft:grass_block}[snowy=false]'
            return 'Block{minecraft:pink_shulker_box}[facing=up]'if pos==fixture.PAD and client.placed else None
        def opening(client,pos,kind):client.kind=kind;client.menu_id+=1;return client.status()
        def placing(client,*args):
            if args[-1]:args[-1]()
            client.placed=True
            i=next(i for i,r in enumerate(c.inventory)if r['item']==fixture.BOX and r['count'])
            c.inventory[i]=empty(i)
        def returned(client,record,ender,journal):
            client.returned=True;record['stage']='returned';journal.write_text(json.dumps(record))
        with ExitStack()as stack:
            for name,fn in [('block',block),('open_box',opening),('use_with_margin',placing),('recover_and_return',returned)]:
                stack.enter_context(patch('packed_equipment_batch.'+name,side_effect=fn))
            stack.enter_context(patch('packed_equipment_batch.register_cleanup'))
            stack.enter_context(patch('anvil_enchant_preview.time.sleep'))
            if unknown_second or missing:
                with self.assertRaisesRegex(RuntimeError if unknown_second else ValueError,'unknown'if unknown_second else 'complete exact batch'):
                    take(c,profile,24,requests)
                return c,None
            return c,take(c,profile,24,requests)

    def test_different_enchantments_and_duplicate_books_share_one_visit(self):
        with tempfile.TemporaryDirectory()as d:
            c,result=self.execute(d)
            self.assertTrue(result['complete']);self.assertEqual(result['box_visits'],1)
            self.assertEqual(result['exact_items_taken'],4);self.assertEqual(c.book_clicks,4)
            self.assertTrue(c.returned);self.assertEqual(c.box[0]['count'],1)
            self.assertEqual(result['packed_transfer']['taken'],{'minecraft:enchanted_book':4})
            self.assertEqual(len(result['packed_transfer']['item_receipts']),4)
    def test_unknown_middle_click_never_repeats_or_starts_recovery(self):
        with tempfile.TemporaryDirectory()as d:
            c,_=self.execute(d,unknown_second=True)
            self.assertEqual(c.book_clicks,2);self.assertFalse(c.returned)
            record=json.loads((Path(d)/'packed-transfer-active.json').read_text())
            self.assertEqual(record['batch_completed'],1);self.assertEqual(record['pending']['index'],1)
            self.assertFalse(any(op=='recover_shulker'for op,p in c.actions))
    def test_incomplete_source_is_rejected_before_intact_box_withdrawal(self):
        with tempfile.TemporaryDirectory()as d:
            c,_=self.execute(d,missing=True)
            self.assertFalse(any(op=='slot_click'for op,p in c.actions));self.assertFalse(c.returned)


if __name__=='__main__':unittest.main()
