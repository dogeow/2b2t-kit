import copy,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from material_jobs.renewable_cactus import harvest_top,plant
from material_jobs.protocol import JobPaused

def block(p,name):
    return {'pos':p,'state':'Block{minecraft:'+name+'}','solid':name!='cactus',
            'fluid':False,'block_entity':False}

class Client:
    world='w';task='task'
    def __init__(self):
        self.count=6;self.pos=[100.5,90.,100.5];self.health=20;self.last='';self.calls=[]
        self.blocks=[block([100,64,100],'sand'),block([100,65,100],'cactus'),block([100,66,100],'cactus')]
    def status(self):
        return {'world_session':'w','server':'test','dimension':'minecraft:overworld','health':self.health,
                'manual_movement':False,'screen':'','guard_busy':False,'pos':self.pos,
                'inventory':[{'slot':0,'item':'minecraft:cactus','count':self.count}]}
    def request(self,op,**kw):
        self.calls.append((op,kw));self.last='request-'+str(len(self.calls))
        if op=='scan':
            lo,hi=kw['min'],kw['max'];n=math.prod(b-a+1 for a,b in zip(lo,hi))
            return {'id':self.last,'world_session':'w','phase':'done','scan_cells_read':n,'scan_total_cells':n,
                    'blocks':[copy.deepcopy(b)for b in self.blocks if all(a<=p<=z for a,p,z in zip(lo,b['pos'],hi))]}
        if op=='mine_block':self.blocks=[b for b in self.blocks if b['pos']!=kw['pos']];self.count+=1
        elif op=='navigate':self.pos=list(kw['target'])
        elif op=='interact':
            x,y,z=kw['pos'];self.blocks.append(block([x,y+1,z],'cactus'));self.count-=1
        elif op!='select_item':raise AssertionError(op)
        return {'id':self.last,'world_session':'w','phase':'done'}
    checked=request

class ContractTest(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.out=Path(t.name);self.c=Client()
        self.profile={'colored_source_regions':[{'item':'minecraft:cactus','authorized':True,'min':[100,66,100],'max':[100,67,100]}]}
        for name,func in [('material_jobs.acquisition._travel',lambda c,p,*a,**kw:setattr(c,'pos',list(p))),
                          ('material_jobs.navigation.lift_for_travel',lambda c:None),
                          ('material_jobs.navigation.settled_state',lambda c,*a,**kw:c.status()),
                          ('container_hand.select_container_hand',lambda c:'minecraft:air')]:
            p=patch(name,side_effect=func);p.start();self.addCleanup(p.stop)
        p=patch('material_jobs.renewable_cactus._protected',return_value=False);p.start();self.addCleanup(p.stop)
    def test_full_side_harvest_accepts_native_void_checkpoint_and_keeps_base(self):
        checkpoint=Mock(return_value=None)
        r=harvest_top(self.c,[100,66,100],self.profile,self.out/'harvest',checkpoint)
        self.assertTrue(r['complete']);self.assertTrue(r['base_retained']);self.assertEqual(7,self.c.count)
        self.assertIn([100,65,100],[b['pos']for b in self.c.blocks]);self.assertEqual(1,sum(op=='mine_block'for op,_ in self.c.calls))
        self.assertGreater(checkpoint.call_count,3)
    def test_side_floor_below_the_work_cell_does_not_require_leaving_the_farm(self):
        # Raised ground at y65 is beside, not inside, the player's y66 body.
        self.c.blocks.extend(block([x,65,z],'stone')for x,z in
                             [(101,100),(99,100),(100,101),(100,99)])
        r=harvest_top(self.c,[100,66,100],self.profile,self.out/'side-floor',Mock(return_value=None))
        self.assertTrue(r['complete']);self.assertTrue(r['base_retained'])
        self.assertAlmostEqual(66.45,r['side_pose'][1])
        self.assertEqual(1,sum(op=='mine_block'for op,_ in self.c.calls))
    def test_checkpoint_manual_exit_still_prevents_every_native_input(self):
        with self.assertRaises(JobPaused):harvest_top(self.c,[100,66,100],self.profile,self.out/'stopped',Mock(side_effect=JobPaused('manual')))
        self.assertEqual([],self.c.calls)
    def test_deferred_farm_also_blocks_direct_kernel_calls_without_native_input(self):
        self.profile['cactus_harvest_paused']=True
        with self.assertRaisesRegex(JobPaused,'deferred'):
            harvest_top(self.c,[100,66,100],self.profile,self.out/'paused',Mock(return_value=None))
        self.assertEqual([],self.c.calls)
        self.assertFalse((self.out/'paused').exists())
    def test_confirmed_removed_top_with_absent_drop_keeps_unresolved_journal_and_zero_credit(self):
        original=self.c.request
        def request(op,**kw):
            reply=original(op,**kw)
            if op=='mine_block':
                self.c.count-=1
                reply.update(mining_target=kw['pos'],server_confirmed=True,native_sequence=9,
                             server_ack_sequence=9,
                             confirmation_scope='single_target_server_block_update_and_native_sequence_ack',
                             entities=[{'uuid':'unreceived','type':'minecraft:item',
                                        'stack':{'item':'minecraft:cactus','count':1},
                                        'pos':[100.5,66.5,100.5]}])
            return reply
        self.c.request=request
        with patch('material_jobs.renewable_cactus.time.monotonic',side_effect=[10,15]):
            r=harvest_top(self.c,[100,66,100],self.profile,self.out/'unreceived',Mock(return_value=None))
        self.assertFalse(r['complete']);self.assertTrue(r['unreceived'])
        self.assertTrue(r['base_retained']);self.assertEqual(0,r['actual_gain'])
        self.assertEqual('unreceived_drop',r['pending']);self.assertFalse(r['pickup_confirmed'])
        self.assertEqual(6,self.c.count)
        with self.assertRaisesRegex(RuntimeError,'not replayed'):
            harvest_top(self.c,[100,66,100],self.profile,self.out/'unreceived',Mock(return_value=None))
    def test_full_planting_also_reads_client_after_void_checkpoint(self):
        self.c.blocks=[block([100,64,100],'sand')]
        r=plant(self.c,[[100,65,100]],self.profile,self.out/'plant',Mock(return_value=None))
        self.assertTrue(r['complete']);self.assertEqual(5,r['remaining'])
        self.assertEqual(1,sum(op=='interact'for op,_ in self.c.calls))

if __name__=='__main__':unittest.main()
