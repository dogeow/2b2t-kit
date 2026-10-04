"""Known terminal travel may be archived only after independently proved parking."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import kit_cli
from lighting_regions_cli import RegionsWorker,RegionsPaused
import lighting_known_travel_reconcile as module
from potato_farm import ENTITY_SCOPE_AT_SCAN_END
from test_lighting_regions_cli import profile,state


class KnownTravelTests(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);base=root/'retained';base.mkdir();now=int(time.time()*1000)
        world,task,lease,rid='world-a','owned-task','owned-lease','old-navigation'
        original=state()|{'time':now-9000,'player_uuid':'player','game_mode':'survival','kit_version':'2026.10.4.1',
            'projection_selection':{'key':'model','min':[0,64,0],'max':[4,64,4]},
            'phase':'waiting','op':'navigate','id':rid,'last_request':rid,'detail':module.DETAIL,
            'control_revision':8,'pos':[1.5,70,1.5],'velocity':[0,0,0],
            'movement_keys':{'forward':False,'jump':False},'recent_hurt_at':0,'equipment':[],
            'navigating':False,'native_material_busy':False,'guard_busy':False,'pending_scan':None,
            'material_task':{'occupied':False,'process_alive':False,'cancelling':False}}
        original['inventory'][0]={'slot':0,'item':'minecraft:diamond_sword','count':1,'durability':20,'enchantments':[]}
        original['inventory'][1]={'slot':1,'item':'minecraft:torch','count':8}
        original['inventory'][8]={'slot':8,'item':'minecraft:bow','count':1,'durability':20,'enchantments':[]}
        original['supervision_lease']={'id':lease,'job_session':task,'world_session':world,'revision':8,
                                        'kind':'materials','remote_finish':'guard','park_target':[1.5,88,1.5]}
        def frame(stamp,rev=8,kind='materials',pos=None,last=None):
            value=deepcopy(original);value.update(time=stamp,control_revision=rev,
                        pos=list(pos or original['pos']),last_request=last or rid)
            value['inventory'][0]['durability']=19;value['inventory'][8]['durability']=19
            value['supervision_lease'].update(kind=kind,revision=rev)
            return value
        probe_id,column_id,park_id,nav_id='probe-scan','column-scan','park-target','safety-ascent'
        probe_before=frame(now-8000);probe_after=frame(now-7900,last=probe_id)
        before=frame(now-7000,last=probe_id);target=[1.5,88,1.5];position=[1.5,87.9,1.5]
        low,high=[1,-64,1],[1,319,1]
        ground={'pos':[1,63,1],'state':'Block{minecraft:stone}','fluid':False,'passable':False}
        def scan(stamp,scan_id,start):
            value=frame(stamp,last=None);value.update(id=scan_id,phase='done',scan_start_revision=8,
                scan_end_revision=8,scan_cells_read=384,scan_total_cells=384,scan_started_at=start,
                scan_ended_at=stamp,scan_entities=[],scan_entity_scope=ENTITY_SCOPE_AT_SCAN_END,blocks=[ground])
            value['last_request']=None
            value['pending_scan']={'id':scan_id,'world_session':world,'control_revision':8,
                'cells_read':384,'total_cells':384,'reading_complete':False,'reply_write_state':'not_submitted'}
            return value
        probe=scan(now-7950,probe_id,now-8000);column=scan(now-6900,column_id,now-7000)
        park=frame(now-6800,last=park_id);park.update(id=park_id,phase='done',op='material_job_park')
        ascent=frame(now-6000,9,pos=position,last=nav_id);ascent.update(id=nav_id,phase='done')
        ascent['supervision_lease']['park_target']=[1.5,86.9,1.5]  # Native same-owner reanchor is preserved.
        settled=[]
        for stamp in (now-5500,now-5250,now-5000):
            value=deepcopy(ascent);value['time']=stamp;settled.append(value)
        hover=settled[-1];stop_before=deepcopy(hover);stop_before['time']=now-4500
        keep_time=now-3000
        current=frame(now,10,'parking',position,nav_id);current.update(id=nav_id,phase='parking')
        current['supervision_lease'].update(park_target=position,parked_at=keep_time)
        current['supervision_safety']={'lease':lease,'job_session':task,'cause':'heartbeat_lost',
                                     'action':'KEEP_PVE_GUARD','time':keep_time}
        parking=[]
        for stamp in (now-2000,now-1000,now):
            value=deepcopy(current);value['time']=stamp;parking.append(value)
        keep_snapshot=deepcopy(current);keep_snapshot.pop('phase');keep_snapshot.pop('last_request')
        keep_snapshot['time']=keep_time+1;keep_snapshot['supervision_safety']={'lease':'previous-owner'}
        keep={'lease':lease,'job_session':task,'cause':'heartbeat_lost','action':'KEEP_PVE_GUARD',
              'time':keep_time,'snapshot':keep_snapshot,'confirmed':False,'server_survival_verified':False}
        worker=RegionsWorker(root/'automation',profile(),root/'journal',observer=lambda:deepcopy(current))
        directory=worker.out/'batch-'/'00003';directory.mkdir(parents=True)
        params={'task_session':task,'background_ok':True,'target':[1.5,64.5,1.5],
                'arrival':.25,'air_only':True,'seconds':90}
        request={'id':rid,'op':'navigate','world_session':world,'expected_revision':7,
                 'server':original['server'],'dimension':original['dimension'],**params}
        event={'request_id':rid,'world_session':world,'op':'navigate','params':params,'phase':'waiting',
               'detail':module.DETAIL,'revision_before':7,'revision_after':8,'inventory_delta':{},
               'health_before':20,'health_after':20,'position_before':[1.5,88,1.5],
               'position_after':original['pos'],'time':(now-10000)/1000}
        pending={'region_index':0,'mode':'lighting','directory':str(directory),'stage':'travel','travel_stage':'arrival',
                 'world_session':world,'task_session':task,'lease':lease,'error':'Unavailable: 前往资源区的空气航线未确认：'+module.DETAIL,
                 'native_request':{'request_id':rid,'op':'navigate','world_session':world,'task_session':task,
                    'lease_id':lease,'base_revision':7,'expected_revision':8}}
        pending['uncertain_request']=deepcopy(pending['native_request'])
        worker.book.update(world_session=world,campaign=2,cursor=0,dispatch_sequence=3,pending=pending,
            phase='waiting_unresolved',batches=[{'campaign':2,'region_index':1,'placed_verified':3}]);worker.save()
        captured_book=deepcopy(worker.book);worker.book.update(phase='waiting',reason='KeyboardInterrupt: ');worker.save()
        def write(path,value):
            path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(value)+'\n')
        run={'task_session':task,'world_session':world,'complete':False,'placement_key':'model'}
        failure={'op':'navigate','params':params,'detail':module.DETAIL,'terminal_pos':original['pos']}
        originals={'original-regions.json':captured_book,'original-terminal-status.json':original,
                   'original-request.json':request,'original-events.jsonl':event,'original-run-manifest.json':run,
                   'original-movement-failure.json':failure,'original-arrival-height-plan.json':{}}
        for name,value in originals.items():write(base/name,value)
        for name,value in (('events.jsonl',event),('run-manifest-'+task+'.json',run),('movement-failure-'+rid+'.json',failure),('arrival-height-plan.json',{})):
            write(directory/name,value)
        def action(op,rid,params,after=8):
            return {'op':op,'request_id':rid,'world_session':world,'params':{'task_session':task,**params},
                'phase':'done','inventory_delta':{},'health_before':20,'health_after':20,'revision_before':8,'revision_after':after}
        probe_event=action('scan',probe_id,{'min':low,'max':high,'details':True})
        actions=[action('scan',column_id,{'min':low,'max':high,'details':True}),
                 action('material_job_park',park_id,{'park_target':target}),
                 action('navigate',nav_id,{'target':target,'air_only':True},9)]
        probe_dir=base/'column-observation-002';maintenance=base/'owned-ascent-001'
        for name,value in (('before.json',probe_before),('full-body-column-reply.json',probe),('after.json',probe_after),('events.jsonl',probe_event)):
            write(probe_dir/name,value)
        plan={'world_session':world,'task_session':task,'lease':lease,'revision':8,'origin':before['pos'],
              'target':target,'distance':18,'ground_top':64,'ascent_bounds':[[1,70,1],[1,89,1]],'original_request_replayed':False}
        stopped={'signal':'SIGINT','reason':'known_terminal_nonmutating_travel_after_same_owner_vertical_safety_ascent',
                 'pid':12345,'time':now-4000,'request_replayed':False,'original_request_id':rid,
                 'ascent_request_id':nav_id,'world_session':world,'task_session':task,'lease':lease,
                 'command':f'python kit_cli.py lighting resume --out {worker.out}'}
        for name,value in (('before.json',before),('fresh-full-body-column-reply.json',column),
                ('native-park-target-reply.json',park),('native-ascent-reply.json',ascent),('plan.json',plan),
                ('settled-frames.json',settled),('verified-high-hover.json',hover),('before-worker-stop.json',stop_before),
                ('worker-stop.json',stopped),('after-native-parking.json',current),('parking-frames.json',parking),('native-keep-receipt.json',keep)):
            write(maintenance/name,value)
        (maintenance/'events.jsonl').write_text(''.join(json.dumps(value)+'\n'for value in actions))
        write(worker.root/('supervision-receipt-'+lease+'.json'),keep)
        manifest={'world_session':world,'request_id':rid,'original_reply_exists':False,'original_request_replayed':False,
                  'source_directory':str(directory),'files_sha256':{name:hashlib.sha256((base/name).read_bytes()).hexdigest()for name in module.ORIGINAL}}
        write(base/'manifest.json',manifest)
        return worker,base,current,write

    def test_actual_shape_reanchor_scan_residue_false_keep_flags_and_no_credit(self):
        worker,base,current,write=self.fixture();prior=deepcopy(worker.book)
        result=worker.reconcile_known_travel(travel_evidence=base/'manifest.json',process_probe=lambda pid:False)
        self.assertEqual('waiting_resume',result['phase']);self.assertIsNone(result['pending'])
        for key in ('cursor','campaign','dispatch_sequence','batches','audits'):self.assertEqual(prior[key],result[key])
        row=result['pending_reconciliations'][-1]
        self.assertFalse(row['original_navigation_completed']);self.assertFalse(row['region_completed'])
        self.assertFalse(row['request_replayed']);self.assertEqual(0,row['placement_credit'])
        self.assertEqual(2,len(row['defense_tool_wear']));self.assertTrue(row['native_parking_confirmed'])
        self.assertTrue((Path(row['archive'])/'evidence/original-request.json').exists())
        self.assertFalse(result['coverage_complete']);self.assertFalse(result['goal_complete'])

    def assert_refused(self,worker,base):
        original=worker.path.read_bytes();before=deepcopy(worker.book)
        with self.assertRaises((RegionsPaused,ValueError,KeyError,OSError)):
            worker.reconcile_known_travel(travel_evidence=base/'manifest.json',process_probe=lambda pid:False)
        self.assertEqual(original,worker.path.read_bytes());self.assertEqual(before,worker.book)
        self.assertFalse((worker.out/'known-travel-reconciliations').exists())

    def test_unknown_terminal_mailbox_hash_or_original_source_change_refuses(self):
        for change in ('hash','source','status','request','event','failure'):
            with self.subTest(change=change):
                worker,base,current,write=self.fixture();manifest=json.loads((base/'manifest.json').read_text())
                if change=='source':write(Path(worker.book['pending']['directory'])/'arrival-height-plan.json',{'changed':True})
                else:
                    name={'hash':'original-request.json','status':'original-terminal-status.json','request':'original-request.json',
                          'event':'original-events.jsonl','failure':'original-movement-failure.json'}[change]
                    value=json.loads((base/name).read_text())
                    if change=='status':value['last_request']='unknown'
                    elif change=='request':value['expected_revision']=99
                    elif change=='event':value['phase']='done'
                    elif change=='failure':value['terminal_pos']=[0,0,0]
                    else:value['id']='changed'
                    write(base/name,value)
                    if change!='hash':
                        manifest['files_sha256'][name]=hashlib.sha256((base/name).read_bytes()).hexdigest();write(base/'manifest.json',manifest)
                self.assert_refused(worker,base)

    def test_maintenance_unknown_extra_mutation_partial_scan_or_wrong_residue_refuses(self):
        for change in ('partial','residue','old_host','unknown','horizontal','event','inventory','components','occupied_body'):
            with self.subTest(change=change):
                worker,base,current,write=self.fixture();folder=base/'owned-ascent-001'
                name='fresh-full-body-column-reply.json'if change in ('partial','residue','old_host','occupied_body')else'native-ascent-reply.json'
                value=json.loads((folder/name).read_text())
                if change=='partial':value['scan_cells_read']-=1
                elif change=='residue':value['pending_scan']['id']='foreign'
                elif change=='old_host':value['kit_version']='2026.10.4.0'
                elif change=='unknown':value['phase']='waiting'
                elif change=='horizontal':
                    value=json.loads((folder/'plan.json').read_text());value['target'][0]+=1;name='plan.json'
                elif change=='event':
                    with (folder/'events.jsonl').open('a')as f:f.write(json.dumps({'op':'interact'})+'\n')
                elif change=='inventory':value['inventory'][1]['count']-=1
                elif change=='components':value['inventory'][0]['enchantments']=[{'id':'changed'}]
                else:value['blocks'].append({'pos':[1,72,1],'state':'Block{minecraft:oak_planks}','fluid':False,'passable':False})
                if change!='event':write(folder/name,value)
                self.assert_refused(worker,base)

    def test_current_or_native_parking_scope_changes_refuse(self):
        for change in ('world','model','owner','lease','health','pending','mailbox','keep','alive'):
            with self.subTest(change=change):
                worker,base,current,write=self.fixture()
                if change=='world':current['world_session']='other'
                elif change=='model':current['projection_selection']['key']='other'
                elif change=='owner':current['supervision_lease']['job_session']='other'
                elif change=='lease':current['supervision_lease']['id']='other'
                elif change=='health':current['health']=19
                elif change=='pending':current['pending_scan']={}
                elif change=='mailbox':write(worker.root/'request.json',{})
                elif change=='keep':write(worker.root/'supervision-receipt-owned-lease.json',{'action':'KEEP_PVE_GUARD'})
                else:
                    old=worker.path.read_bytes()
                    with self.assertRaises(RegionsPaused):worker.reconcile_known_travel(travel_evidence=base/'manifest.json',process_probe=lambda pid:True)
                    self.assertEqual(old,worker.path.read_bytes());continue
                self.assert_refused(worker,base)

    def test_original_intent_changed_campaign_or_worker_lock_refuses(self):
        for change in ('intent','cursor','batches','lock'):
            with self.subTest(change=change):
                worker,base,current,write=self.fixture()
                if change=='intent':write(worker.root/'lighting-intents/original.json',{'world_session':'world-a','task_session':'owned-task'})
                elif change=='cursor':worker.book['cursor']=1;worker.save()
                elif change=='batches':worker.book['batches'][0]['placed_verified']+=1;worker.save()
                else:
                    with worker.worker_lock():self.assert_refused(worker,base)
                    continue
                self.assert_refused(worker,base)

    def test_cli_exposes_pure_archive_without_resume_or_game_requests(self):
        with patch('lighting_regions_cli.main',return_value=0)as handler:
            self.assertEqual(kit_cli.main(['lighting','reconcile-known-travel','--profile','/tmp/profile',
                '--out','/tmp/original','--travel-evidence','/tmp/manifest.json']),0)
            command=handler.call_args.args[0]
            self.assertEqual('reconcile-known-travel',command[-1]);self.assertIn('--travel-evidence',command)
            self.assertNotIn('resume',command)

    def test_validation_failure_after_second_current_observation_preserves_original(self):
        worker,base,current,write=self.fixture();observe=worker.observer;calls=0
        def changed():
            nonlocal calls
            calls+=1
            if calls==2:current['supervision_lease']['id']='new-owner'
            return observe()
        worker.observer=changed;self.assert_refused(worker,base)


if __name__=='__main__':unittest.main()
