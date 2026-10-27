import copy,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from test_cactus_checkpoint_contract import Client
from material_jobs.cactus_drop_pickup import recover, UnreceivedCactusDrop

class PickupTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.out=Path(t.name)
        self.c=Client();self.c.pos=[101.5,67.1,100.5]
        self.drop={'uuid':'new-drop','type':'minecraft:item','stack':{'item':'minecraft:cactus','count':1},'pos':[99.65,65.,100.5]}
        self.present=True;old_status=self.c.status
        def status():return{**old_status(),'time':time.time_ns(),'entities':[copy.deepcopy(self.drop)]if self.present else[]}
        self.c.status=status;original=self.c.checked
        def checked(op,**kw):
            r=original(op,**kw)
            if op=='navigate'and kw['target'][1]<66 and kw['target'][0]<100:
                self.c.count=7;self.present=False
            return r
        self.c.checked=checked
        self.receipt={'id':'original-mine','phase':'done','world_session':'w','mining_target':[100,67,100],
            'server_confirmed':True,'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
            'native_sequence':10,'server_ack_sequence':10,'entities':[copy.deepcopy(self.drop)]}
        p=patch('material_jobs.cactus_drop_pickup.settled_state',side_effect=lambda c,*a,**kw:c.status());p.start();self.addCleanup(p.stop)
    def go(self):return recover(self.c,[100,67,100],self.receipt,6,set(),self.out/'pickup',Mock(return_value=None))
    def test_exact_opposite_side_drop_uses_air_column_and_actual_gain_without_mining(self):
        q=self.go();self.assertEqual(7,self.c.count);self.assertEqual(20,q['health'])
        self.assertTrue(all(op in('scan','navigate')for op,_ in self.c.calls))
        self.assertLess(q['pos'][0],100);self.assertFalse(self.present)
        with self.assertRaisesRegex(RuntimeError,'no replay'):self.go()
    def test_unknown_original_mine_never_starts_pickup_motion(self):
        self.receipt['server_ack_sequence']=9
        with self.assertRaisesRegex(RuntimeError,'Unknown cactus mining'):self.go()
        self.assertEqual([],self.c.calls)
    def test_preexisting_item_cannot_be_credited_as_the_new_drop(self):
        with self.assertRaisesRegex(RuntimeError,'identity'):
            recover(self.c,[100,67,100],self.receipt,6,{'new-drop'},self.out/'pickup',Mock(return_value=None))
        self.assertEqual([],self.c.calls)
    def test_confirmed_original_drop_absent_is_unreceived_without_motion_or_credit(self):
        self.present=False
        with self.assertRaises(UnreceivedCactusDrop)as result:self.go()
        self.assertEqual('new-drop',result.exception.uuid)
        self.assertEqual(6,self.c.count);self.assertEqual([],self.c.calls)
        self.assertEqual([],list((self.out/'pickup').glob('*.json')))
    def test_absence_after_unknown_mining_or_inventory_change_cannot_be_retired(self):
        self.present=False;self.receipt['server_confirmed']=False
        with self.assertRaises(RuntimeError)as result:self.go()
        self.assertNotIsInstance(result.exception,UnreceivedCactusDrop)
        self.receipt['server_confirmed']=True;self.c.count=7
        with self.assertRaises(RuntimeError)as result:self.go()
        self.assertNotIsInstance(result.exception,UnreceivedCactusDrop)

if __name__=='__main__':unittest.main()
