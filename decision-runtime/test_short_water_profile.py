import copy,json,tempfile,unittest
from pathlib import Path
from projected_source_column import geometry,envelope,place as source_place,refill,SOURCE,AIR
from projected_bent_channel import path_for,scan_bounds,flow_after,place as overflow_place,remove_seed,roof_payload
from test_projected_source_column import fixture,Fake,SupplyFake,change,LOW,WORLD,KEY
HIGH=[12,62,20];PROFILE='four_rows';BOTTOM='Block{minecraft:cobblestone_slab}[type=bottom,waterlogged=false]'

def short_fixture():
    m,f=fixture();m['expected']=[v for v in m['expected']if v['pos'][1]<=62]
    for x in range(10,13):m['expected'].append({'pos':[x,63,20],'state':f'Block{{minecraft:water}}[level={12-x}]'})
    f['blocks']=[v for v in f['blocks']if v['pos'][1]<=62];f.update(scan_cells_read=90,scan_total_cells=90);return m,f

class ShortSourceFake(Fake):
    short_protocol=1
    def status(self):return {**super().status(),'projected_short_source_profile_protocol':self.short_protocol}
    def request(self,op,**params):
        self.params=params;result=super().request(op,**params)
        if op=='bucket_place':result['bucket_water']['source_column_profile']=params.get('source_column_profile')
        return result

class ShortProfileTest(unittest.TestCase):
    def test_short_shape_is_not_silently_accepted_by_legacy_default(self):
        m,f=short_fixture()
        with self.assertRaises(ValueError):envelope(LOW,HIGH)
        p=geometry(m,f,LOW,HIGH,WORLD,profile=PROFILE);self.assertEqual(len(p['source_cells']),12);self.assertEqual(len(p['column_boundary_pins']),35)
        for profile in [True,'five_rows',4]:
            with self.assertRaises(ValueError):envelope(LOW,HIGH,profile=profile)
    def test_short_source_place_uses_its_own_dimensions_metadata_and_receipt(self):
        m,f=short_fixture();c=ShortSourceFake(m,f)
        with tempfile.TemporaryDirectory()as d:result=source_place(c,LOW,HIGH,[10,59,20],[9,59,20],'east',KEY,Path(d)/'one',profile=PROFILE);self.assertTrue(result['complete'])
        self.assertEqual(c.uses,1);self.assertEqual(c.params['source_column_profile'],PROFILE);self.assertEqual(len(c.params['column_boundary_pins']),35)
    def test_old_host_has_zero_input_and_an_undispatched_journal(self):
        m,f=short_fixture();c=ShortSourceFake(m,f);c.short_protocol=0
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'one'
            with self.assertRaises(RuntimeError):source_place(c,LOW,HIGH,[10,59,20],[9,59,20],'east',KEY,out,profile=PROFILE)
            self.assertIs(json.loads((out/'progress.json').read_text())['dispatch_started'],False)
        self.assertEqual(c.uses,0)
    def test_missing_seal_cannot_be_concealed_by_the_smaller_profile(self):
        m,f=short_fixture();change(f,[9,60,20],AIR)
        with self.assertRaises(RuntimeError):geometry(m,f,LOW,HIGH,WORLD,profile=PROFILE)


def scene(kind='dry',service_index=0):
    m,f=short_fixture();goals={tuple(v['pos']):v['state']for v in m['expected']};rows={tuple(v['pos']):v for v in f['blocks']}
    def put(p,state,solid=False,entity=False):
        goals[tuple(p)]=state
        if state==AIR:rows.pop(tuple(p),None)
        else:rows[tuple(p)]={'pos':list(p),'state':state,'solid':solid,'fluid':state.startswith('Block{minecraft:water}'),'block_entity':entity}
    for y in range(59,63):
        for x in range(10,13):put([x,y,20],SOURCE)
    path=path_for(LOW,HIGH,profile=PROFILE);levels=None if kind=='dry'else[0,1,-1,-1,-1,-1,-1,-1]if kind=='partial'else[0,0,0,1,2,3,4,5]if kind=='seed'else[0,0,1,2,3,4,5,6]if kind=='middle'else list(range(8))
    for i,p in enumerate(path):
        x,y,z=p;goals[tuple(p)]=f'Block{{minecraft:water}}[level={i}]'
        if levels and levels[i]>=0:rows[tuple(p)]={'pos':p,'state':f'Block{{minecraft:water}}[level={levels[i]}]','solid':False,'fluid':True,'block_entity':False}
        else:rows.pop(tuple(p),None)
        if i>=3:put([x,y-1,z],'Block{minecraft:cobblestone}',True)
        put([x,y+1,z],BOTTOM if i<3 else AIR)
        for q in [(x+1,y,z),(x-1,y,z),(x,y,z+1),(x,y,z-1)]:
            if list(q)not in path:put(q,'Block{minecraft:spruce_trapdoor}[facing=east,half=top,open=false,powered=false,waterlogged=false]'if i==7 and q[2]==z+1 else'Block{minecraft:glass}',True)
    roof=[path[service_index][0],64,path[service_index][2]];rows.pop(tuple(roof),None)
    m['expected']=[{'pos':list(p),'state':v}for p,v in goals.items()];f['blocks']=list(rows.values());return m,f,roof

class ChannelFake:
    task='owner';world=WORLD;last='';uncertain=False;short_protocol=1;collection_protocol=1
    def __init__(self,m,f,mode='place'):self.model=m;self.frame=f;self.mode=mode;self.uses=0;self.tick=1;self.water=1 if mode=='place'else 0;self.empty=1-self.water;self.params={}
    def status(self):
        return {'projected_bent_channel_protocol':1,'projected_bent_channel_seed_protocol':1,'projected_short_source_profile_protocol':self.short_protocol,'projected_bent_collection_protocol':self.collection_protocol,'projected_bent_middle_service_protocol':1,'health':20,'air_supply':300,'screen':'','manual_movement':False,'guard_busy':False,'guard_armed':True,'supervision_lease':{'job_session':self.task},'world_session':WORLD,'hand':{'item':'minecraft:water_bucket'if self.water else'minecraft:bucket','count':1},'inventory':[{'slot':0,'item':'minecraft:water_bucket','count':self.water},{'slot':1,'item':'minecraft:bucket','count':self.empty}]}
    def request(self,op,**params):
        if op=='projection_model':return {'projection_model':self.model}
        self.params=params;self.uses+=1;self.last='use-'+str(self.uses);path=path_for(LOW,HIGH,profile=PROFILE);index=params.get('projected_bent_channel_collect_index',0)
        levels=[0,0,1,2,3,4,5,6]if index==2 else list(range(8))
        if params.get('projected_bent_channel_seed'):levels=[0,0,0,1,2,3,4,5]
        for i,p in enumerate(path):change(self.frame,p,f'Block{{minecraft:water}}[level={levels[i]}]')
        self.water+=1 if op=='bucket_fill'else-1;self.empty+=-1 if op=='bucket_fill'else 1
        a={'request_id':self.last,'world_session':WORLD,'operation':op,'pos':params['pos'],'source_column_profile':params.get('source_column_profile'),'projected_bent_channel':op=='bucket_place','projected_bent_channel_seed':params.get('projected_bent_channel_seed',False),'projected_bent_channel_collect_index':index,'confirmed':not self.uncertain,'unknown_outcome':self.uncertain,'use_count':1,'server_block_confirmed':True,'server_inventory_confirmed':True}
        if 'bent_middle_ceiling'in params:a['bent_middle_ceiling']=params['bent_middle_ceiling']
        return {'id':self.last,'world_session':WORLD,'phase':'waiting'if self.uncertain else'done','bucket_water':a}
    def checked(self,op,**params):
        if op=='select_item':return self.status()
        assert op=='scan';self.tick+=1;lo,hi=params['min'],params['max'];r=copy.deepcopy(self.frame);r['blocks']=[v for v in r['blocks']if all(lo[i]<=v['pos'][i]<=hi[i]for i in range(3))];count=1
        for i in range(3):count*=hi[i]-lo[i]+1
        r.update(scan_cells_read=count,scan_total_cells=count,time=self.tick);return r

class ShortChannelTest(unittest.TestCase):
    def test_path_and_frame_include_the_low_roof_and_five_west_turn(self):
        p=path_for(LOW,HIGH,profile=PROFILE);self.assertEqual(p[-1],[7,63,22]);self.assertEqual(scan_bounds(LOW,HIGH,PROFILE),([6,58,19],[13,64,23]));self.assertEqual(len(set(map(tuple,p))),8)
        with self.assertRaises(ValueError):roof_payload(PROFILE,[12,64,21],[12,63,20])
    def test_short_pour_carries_one_roof_and_preserves_all12_sources(self):
        m,f,roof=scene();c=ChannelFake(m,f)
        with tempfile.TemporaryDirectory()as d:r=overflow_place(c,LOW,HIGH,KEY,Path(d)/'one',profile=PROFILE,service_ceiling=roof);self.assertTrue(r['complete']);self.assertEqual(r['source_cells_preserved'],12)
        self.assertEqual(c.uses,1);self.assertEqual(c.params['bent_service_ceiling'],roof);self.assertEqual(c.params['source_column_profile'],PROFILE)
    def test_each_collection_has_its_exact_pinned_index_and_then_verifies_the_gradient(self):
        for index,kind in [(2,'seed'),(1,'middle')]:
            m,f,roof=scene(kind,index);c=ChannelFake(m,f,'fill')
            with tempfile.TemporaryDirectory()as d:r=remove_seed(c,LOW,HIGH,KEY,Path(d)/'one',index=index,profile=PROFILE,service_ceiling=roof);self.assertTrue(r['complete'])
            self.assertEqual(c.params['projected_bent_channel_collect_index'],index);self.assertEqual(c.params['bent_service_ceiling'],roof);self.assertEqual(c.uses,1)
    def test_short_seed_uses_the_south_glass_instead_of_waterlogging_the_north_stair(self):
        m,f,roof=scene('partial',2);middle=[11,64,20];change(f,middle,AIR);c=ChannelFake(m,f)
        with tempfile.TemporaryDirectory()as d:r=overflow_place(c,LOW,HIGH,KEY,Path(d)/'one',seed=True,profile=PROFILE,service_ceiling=roof,middle_ceiling=middle);self.assertTrue(r['complete'])
        self.assertEqual(c.params['support'],[10,63,21]);self.assertEqual(c.params['face'],'north');self.assertEqual(c.uses,1)
    def test_shared_middle_roof_stays_open_without_wet_roof_demolition(self):
        m,f,roof=scene();middle=[11,64,20];change(f,middle,AIR);c=ChannelFake(m,f)
        with tempfile.TemporaryDirectory()as d:r=overflow_place(c,LOW,HIGH,KEY,Path(d)/'one',profile=PROFILE,service_ceiling=roof,middle_ceiling=middle);self.assertTrue(r['complete'])
        self.assertEqual(c.params['bent_middle_ceiling'],middle);self.assertEqual(c.uses,1)
        with self.assertRaises(ValueError):roof_payload(PROFILE,roof,[12,63,20],middle_ceiling=[10,64,20],source_origin=[12,63,20])
    def test_wrong_roof_is_a_local_preflight_failure_and_unknown_pour_is_not_retried(self):
        m,f,roof=scene();c=ChannelFake(m,f)
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'one'
            with self.assertRaises(ValueError):overflow_place(c,LOW,HIGH,KEY,out,profile=PROFILE,service_ceiling=[11,64,20])
            self.assertIs(json.loads((out/'progress.json').read_text())['dispatch_started'],False)
        self.assertEqual(c.uses,0)
        c=ChannelFake(m,f);c.uncertain=True
        with tempfile.TemporaryDirectory()as d:
            out=Path(d)/'one'
            with self.assertRaisesRegex(RuntimeError,'unresolved'):overflow_place(c,LOW,HIGH,KEY,out,profile=PROFILE,service_ceiling=roof)
            self.assertIs(json.loads((out/'progress.json').read_text())['dispatch_started'],True)
        self.assertEqual(c.uses,1)

if __name__=='__main__':unittest.main()
