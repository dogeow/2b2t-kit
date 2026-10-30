import copy,json,tempfile,unittest
from pathlib import Path
from projected_source_column import AIR,SOURCE,geometry,envelope,source_receipt,observed_after,place,admission_rejected_before_use,SourceAdmissionRejected
LOW=[10,59,20];HIGH=[12,67,20];WORLD='current-world';KEY='locked-fixture'
UP='Block{minecraft:dropper}[facing=up,triggered=false]';GLASS='Block{minecraft:glass}'

def fixture():
    goals={};rows={}
    def add(p,state,solid=False,entity=False):
        rows[tuple(p)]={'pos':list(p),'state':state,'solid':solid,'fluid':state.startswith('Block{minecraft:water}'),'block_entity':entity}
    for y in range(59,68):
        for x in range(10,13):
            p=(x,y,20);goals[p]=SOURCE
            if y<62:add(p,'Block{minecraft:water}[level=8]')
            if y==62:add(p,SOURCE if x!=11 else'Block{minecraft:water}[level=1]')
        for p in [(9,y,20),(13,y,20),*[(x,y,z)for x in range(10,13)for z in [19,21]]]:goals[p]=GLASS;add(p,GLASS,True)
    for x in range(10,13):
        p=(x,58,20);goals[p]=UP.replace('false','true');add(p,UP,True,True)
        goals[(x,68,20)]=f'Block{{minecraft:water}}[level={12-x}]'
    return ({'placement_key':KEY,'content_hash':'fixture','expected':[{'pos':list(p),'state':v}for p,v in goals.items()]},
            {'world_session':WORLD,'phase':'done','scan_cells_read':165,'scan_total_cells':165,'scan_coherent':True,
             'scan_predictions':{'complete':True,'pending_count':0},'blocks':list(rows.values()),'time':1})

def change(frame,p,state):
    rows={tuple(v['pos']):v for v in frame['blocks']};rows[tuple(p)]={'pos':list(p),'state':state,'solid':False,'fluid':state.startswith('Block{minecraft:water}'),'block_entity':False};frame['blocks']=list(rows.values())

def receipt(request,target):
    return {'id':request,'world_session':WORLD,'phase':'done','bucket_water':{'request_id':request,'world_session':WORLD,'operation':'bucket_place','pos':target,
        'projected_source_column':True,'confirmed':True,'unknown_outcome':False,'use_count':1,'server_block_confirmed':True,'server_inventory_confirmed':True,'server_observed_state':SOURCE}}

class Fake:
    task='owner';world=WORLD;last='';protocol=1;uncertain=False
    def __init__(self,model,frame):self.model=model;self.frame=frame;self.calls=[];self.uses=0;self.tick=1
    def status(self):
        return {'projected_source_column_protocol':self.protocol,'health':20,'food':20,'air_supply':300,'world_session':WORLD,
                'screen':'','manual_movement':False,'guard_busy':False,'guard_armed':True,'supervision_lease':{'kind':'materials','job_session':self.task},
                'projection_selection':{'key':KEY},'hand':{'item':'minecraft:water_bucket','count':1},
                'inventory':[{'item':'minecraft:water_bucket','slot':0,'count':1-self.uses},{'item':'minecraft:bucket','slot':1,'count':self.uses}]}
    def request(self,op,**kw):
        self.calls.append(op)
        if op=='projection_model':return {'projection_model':self.model}
        if op=='bucket_place':
            if getattr(self,'reject_before_use',False):
                self.last='one'
                return {'id':'one','world_session':WORLD,'phase':'error','last_bucket_admission_rejection':{
                    'protocol':2,'request_id':'one','world_session':WORLD,'input_sent':False,'material_owner_current':True,
                    'bucket_task_active':False,'active_request_id':'','active_command':'','navigation_active':False}}
            self.uses+=1;self.last='one';change(self.frame,kw['pos'],SOURCE);r=receipt(self.last,kw['pos'])
            if self.uncertain:r['phase']='waiting'
            return r
        raise AssertionError(op)
    def checked(self,op,**kw):
        self.calls.append(op)
        if op=='select_item':return self.status()
        if op=='scan':self.tick+=1;r=copy.deepcopy(self.frame);r['time']=self.tick;return r
        raise AssertionError(op)

class SourceColumnTest(unittest.TestCase):
    def test_real_fixture_has_27_cells_75_seals_and_two_preserved_sources(self):
        m,f=fixture();p=geometry(m,f,LOW,HIGH,WORLD);self.assertEqual(len(p['source_cells']),27);self.assertEqual(len(p['column_boundary_pins']),75);self.assertEqual(p['preserved_sources'],[[10,62,20],[12,62,20]])
    def test_missing_floor_fails_before_select_or_use(self):
        m,f=fixture();change(f,[11,58,20],'Block{minecraft:water}[level=8]');c=Fake(m,f)
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaisesRegex(RuntimeError,'floor'):place(c,LOW,HIGH,[10,59,20],[9,59,20],'east',KEY,Path(d)/'one')
        self.assertEqual(c.uses,0);self.assertNotIn('select_item',c.calls)
    def test_wrong_floor_or_missing_boundary_is_not_a_sealed_fixture(self):
        for p,s in [([10,58,20],UP.replace('up','north')),([9,63,20],AIR)]:
            m,f=fixture();change(f,p,s)
            with self.assertRaises(RuntimeError):geometry(m,f,LOW,HIGH,WORLD)
    def test_incomplete_scan_stale_world_and_pending_predictions_are_rejected(self):
        for k,v in [('world_session','old'),('scan_cells_read',164),('scan_total_cells',166),('scan_coherent',False)]:
            m,f=fixture();f[k]=v
            with self.assertRaises(RuntimeError):geometry(m,f,LOW,HIGH,WORLD)
        m,f=fixture();f['scan_predictions']['pending_count']=1
        with self.assertRaises(RuntimeError):geometry(m,f,LOW,HIGH,WORLD)
    def test_non_source_model_or_wet_overflow_cannot_be_substituted(self):
        m,f=fixture();m['expected'][0]['state']='Block{minecraft:water}[level=1]'
        with self.assertRaises(RuntimeError):geometry(m,f,LOW,HIGH,WORLD)
        m,f=fixture();change(f,[12,68,20],SOURCE)
        with self.assertRaisesRegex(RuntimeError,'overflow'):geometry(m,f,LOW,HIGH,WORLD)
    def test_only_the_exact_integer_shape_is_supported(self):
        for lo,hi in [([10,59,20],[12,68,20]),([10,59,20],[13,67,20]),([10,59,20],[12,67,21]),([True,59,20],HIGH)]:
            with self.assertRaises(ValueError):envelope(lo,hi)
    def test_post_scan_rejects_lost_source_new_leak_and_new_lava(self):
        m,f=fixture();p=geometry(m,f,LOW,HIGH,WORLD);before={tuple(v['pos']):v['state']for v in f['blocks']};change(f,[10,59,20],SOURCE);lo,hi=envelope(LOW,HIGH)
        self.assertTrue(observed_after(f,WORLD,lo,hi,p,[10,59,20],before))
        for pos,state in [([10,62,20],AIR),([9,59,19],SOURCE),([11,60,20],'Block{minecraft:lava}[level=0]')]:
            bad=copy.deepcopy(f);change(bad,pos,state);self.assertFalse(observed_after(bad,WORLD,lo,hi,p,[10,59,20],before))
    def test_receipt_requires_exact_mode_single_use_and_both_server_confirmations(self):
        r=receipt('one',[10,59,20]);self.assertTrue(source_receipt(r,'one',WORLD,[10,59,20]))
        for k,v in [('server_block_confirmed',False),('server_inventory_confirmed',False),('projected_source_column',False),('operation','bucket_fill'),('use_count',2),('unknown_outcome',True)]:
            bad=copy.deepcopy(r);bad['bucket_water'][k]=v;self.assertFalse(source_receipt(bad,'one',WORLD,[10,59,20]))
    def test_old_running_host_refuses_before_any_request(self):
        m,f=fixture();c=Fake(m,f);c.protocol=0
        with tempfile.TemporaryDirectory()as d:
            with self.assertRaises(RuntimeError):place(c,LOW,HIGH,[10,59,20],[9,59,20],'east',KEY,Path(d)/'one')
        self.assertEqual(c.calls,[])
    def test_one_use_gets_two_fresh_frames(self):
        m,f=fixture();c=Fake(m,f)
        with tempfile.TemporaryDirectory()as d:
            p=place(c,LOW,HIGH,[10,59,20],[9,59,20],'east',KEY,Path(d)/'one');self.assertTrue(p['complete']);self.assertEqual(len(p['observations']),2)
        self.assertEqual(c.uses,1)
    def test_exact_new_admission_refusal_is_not_an_unknown_bucket_use(self):
        d={'protocol':2,'request_id':'one','world_session':WORLD,'input_sent':False,'material_owner_current':True,
           'bucket_task_active':False,'active_request_id':'','active_command':'','navigation_active':False}
        r={'id':'one','world_session':WORLD,'phase':'error','last_bucket_admission_rejection':d}
        self.assertTrue(admission_rejected_before_use(r,'one',WORLD))
        for key,value in [('request_id','old'),('world_session','old'),('input_sent',True),('protocol',1),('bucket_task_active',True),('material_owner_current',False)]:
            bad=copy.deepcopy(r);bad['last_bucket_admission_rejection'][key]=value
            self.assertFalse(admission_rejected_before_use(bad,'one',WORLD))
        r['bucket_water']={'request_id':'old','use_count':1}
        self.assertTrue(admission_rejected_before_use(r,'one',WORLD))
        r['bucket_water']['request_id']='one'
        self.assertFalse(admission_rejected_before_use(r,'one',WORLD))
    def test_structured_no_input_refusal_clears_only_its_pending_use_and_never_retries(self):
        m,f=fixture();c=Fake(m,f);c.reject_before_use=True
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'one'
            with self.assertRaises(SourceAdmissionRejected):place(c,LOW,HIGH,[10,59,20],[9,59,20],'east',KEY,out)
            record=json.loads((out/'progress.json').read_text());self.assertIsNone(record['pending']);self.assertTrue(record['rejected_before_use'])
        self.assertEqual(c.uses,0);self.assertEqual(c.calls.count('bucket_place'),1)
    def test_unknown_use_keeps_original_identity_and_is_never_repeated(self):
        m,f=fixture();c=Fake(m,f);c.uncertain=True
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'one'
            with self.assertRaisesRegex(RuntimeError,'unconfirmed'):place(c,LOW,HIGH,[10,59,20],[9,59,20],'east',KEY,out)
            p=json.loads((out/'progress.json').read_text());self.assertEqual(p['request_id'],'one');self.assertIsNotNone(p['pending'])
        self.assertEqual(c.uses,1)

if __name__=='__main__':unittest.main()
