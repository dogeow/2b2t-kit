import json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
from material_jobs.build_progress import BuildMaterialProgress,phase,acquisition_activity
from material_jobs.build_progress_overlay import overlay
from test_projection_flat_jobs import model,layout_for,audit


class BuildProgressTest(unittest.TestCase):
    def test_acquisition_activity_uses_live_native_state(self):
        state={'world_session':'w','op':'navigate','phase':'done'}
        self.assertEqual('采集',acquisition_activity(state,'minecraft:tuff'))
        state['navigating']=True
        self.assertEqual('巡航',acquisition_activity(state,'minecraft:tuff'))
        state['navigating']=False;state['idle_activity']={'conflicts':['scan','material_lease']}
        self.assertEqual('扫描',acquisition_activity(state,'minecraft:tuff'))
        state['idle_activity']['conflicts']=[]
        state['rock_quarry']={'active':True,'world_session':'w','item':'minecraft:tuff','completion':'clear'}
        self.assertEqual('开路',acquisition_activity(state,'minecraft:tuff'))
        state['rock_quarry']['completion']='collect'
        self.assertEqual('开采',acquisition_activity(state,'minecraft:tuff'))
        state['rock_quarry']['world_session']='old'
        self.assertEqual('采集',acquisition_activity(state,'minecraft:tuff'))
        state['guard_busy']=True
        self.assertEqual('防护',acquisition_activity(state,'minecraft:tuff'))

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.build=self.root/'0001-build';self.build.mkdir();m=model();self.layout=layout_for(m)
        self.request={'mode':'projection','projection_key':'ship','flat_map':{'schema':1,'content_hash':m['content_hash']},'created_at':9000}
        self.status={'state':'building','done':7,'total':18}
        self.state={'world_session':'w','inventory':[{'slot':0,'item':'minecraft:stone','count':3},{'slot':40,'item':'minecraft:stone','count':64}]}
        self.audit=audit(self.layout,dict(list(self.layout.expected.items())[:7]))
        self.audit['material_ledger']={'world_session':'w','verified_windows':3}
        self.write(self.root/'active-operation.json',{'name':'build','directory':str(self.build)})
        self.write(self.build/'flat-model.json',{'world_session':'w','projection_model':m})
        self.write(self.build/'flat-next-batch.json',{'phase':'ready','placement_key':'ship','item':'minecraft:stone','positions':[[3,64,0]]*10})
        self.write(self.root/'projection-latest.json',self.audit);self.reader=BuildMaterialProgress()
    def write(self,p,value):p.write_text(json.dumps(value))
    def read(self):return self.reader.details(self.request,self.status,self.state,self.root)
    def test_current_type_physical_count_stock_and_shortage_exclude_pending_plan(self):
        d=self.read();self.assertEqual((7,18,3,8),(d['done'],d['total'],d['on_hand'],d['shortage']))
        self.assertEqual(phase(d,lambda _: '石头'),'放置 石头7/18 背包3 缺8')
    def test_surplus_does_not_show_negative_gap(self):
        self.state['inventory'][0]['count']=15;self.assertEqual(self.read()['shortage'],0)
    def test_changed_world_foreign_progress_or_nonbuild_does_not_enrich(self):
        self.state['world_session']='other';self.assertIsNone(self.read());self.state['world_session']='w'
        self.status['done']=8;self.assertIsNone(self.read());self.status['done']=7
        self.status['state']='gathering';self.assertIsNone(self.read())
    def test_wrong_ledger_world_and_hash_do_not_become_progress(self):
        self.audit['material_ledger']['world_session']='old';self.write(self.root/'projection-latest.json',self.audit)
        self.assertIsNone(self.read())
    def test_unchanged_ledger_is_cached_instead_of_rescanning_for_each_display_frame(self):
        self.read();layout=next(iter(self.reader.layouts.values()))[1]
        with patch.object(layout,'observed') as observed:
            self.read();self.read();observed.assert_not_called()

    def test_live_display_changes_only_phase_and_preserves_owner_counter_and_journal(self):
        native=self.root/'automation';native.mkdir()
        self.request.update(id='job',context={'world_session':'w'})
        self.status.update(id='job',terminal=False,native_task_session='task',updated_at=10000)
        self.state.update(connected=True,manual_movement=False,time=10000,control_revision=7,
            supervision_lease={'kind':'materials','world_session':'w','job_session':'task','revision':7})
        self.write(self.root/'status.json',self.status);self.write(native/'status.json',self.state)
        hud={'title':'地图施工','active':True,'task_session':'task','world_session':'w',
             'control_revision':7,'done':7,'total':18,'updated_at':10000,'phase':'继续投影建造'}
        self.write(native/'job-progress.json',hud);journal=(self.root/'status.json').read_bytes()
        with patch('material_jobs.build_progress_overlay.time.time',return_value=10):
            self.assertTrue(overlay(self.request,native,self.root,self.reader,lambda _: '石头'))
        result=json.loads((native/'job-progress.json').read_text())
        self.assertEqual(result['phase'],'放置 石头7/18 背包3 缺8')
        for key in ['done','total','updated_at','task_session','control_revision']:self.assertEqual(result[key],hud[key])
        self.assertEqual(journal,(self.root/'status.json').read_bytes());self.assertFalse((native/'request.json').exists())

    def test_wood_discovery_and_crafting_are_distinct_activities(self):
        from material_jobs.projection_spatial_cache import native_content_hash
        m=model()
        for row in m['expected']:row.update(item='minecraft:acacia_planks',state='Block{minecraft:acacia_planks}')
        m['content_hash']=native_content_hash(m['expected']);self.request['flat_map']['content_hash']=m['content_hash'];self.request['id']='job'
        layout=layout_for(m);a=audit(layout,dict(list(layout.expected.items())[:7]));a['material_ledger']={'world_session':'w'}
        self.write(self.root/'projection-latest.json',a);self.write(self.build/'flat-model.json',{'world_session':'w','projection_model':m})
        folder=self.root/'pipelines/wood';folder.mkdir(parents=True)
        self.write(self.root/'active-operation.json',{'name':'fetch','directory':str(self.root/'0002-fetch')})
        self.write(self.root/'inflight.json',{'job_id':'job','operation':'run_pipeline','args':['minecraft:acacia_planks',20,'absolute_backpack_total',str(folder)]})
        self.status['state']='gathering'
        for step,expected in [('discover','找树'),('craft','制作')]:
            self.write(folder/'wood-carried-pipeline.json',{'pending':{'kind':step}})
            self.assertEqual(self.read()['activity'],expected)
    def test_cached_expected_table_can_supply_denominator_before_first_build_but_not_actual_credit(self):
        native=self.root/'automation';native.mkdir();m=model()
        self.write(native/'flat-map-continuation-cache.json',{'schema':1,'native_parking_verified':True,
                   'world_session':'old','model':m,'audit':{'matched':99999}})
        (self.build/'flat-model.json').unlink();self.reader=BuildMaterialProgress(native)
        self.assertEqual(self.read()['done'],7)
        self.assertEqual(self.read()['total'],18)
