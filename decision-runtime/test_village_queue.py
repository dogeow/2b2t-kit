import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from village_queue import VillageQueue

class VillageQueueTests(unittest.TestCase):
    def test_refused_air_observation_accepts_only_bounded_gap_after_released_walk(self):
        import copy
        with tempfile.TemporaryDirectory() as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'}
            (q.out/'plan-001').mkdir();params={'target':[10.2,65,20.4],'arrival':.4,'restore_flight':False}
            old={'action':'native','op':'walk','params':params};done={'id':'walk','phase':'done','world_session':'w','pos':[10,64.875,20]}
            (q.out/'plan-001/intent.json').write_text(json.dumps(old));(q.out/'plan-001/result.json').write_text(json.dumps(done))
            prior={'request_id':'walk','time':100.,'op':'walk','phase':'done','world_session':'w','inventory_delta':{},'health_before':20,'health_after':20,
                   'params':dict(task_session='t',**params),'position_before':[5.2,65,10.4],'position_after':done['pos'],'revision_after':8}
            event={'time':101.4,'position_before':[10.17,64,20.306],'position_after':[10.18,64,20.324],'revision_before':8}
            reply={'pos':event['position_after'],'control_revision':8}
            state={'pos':event['position_after'],'health':20,'control_revision':8,'flight':False,'on_ground':True,'movement_keys':{'forward':False},'velocity':[0,-.0784,0]}
            command={'id':'plan-002','op':'navigate','params':{'air_only':True}}
            self.assertTrue(q._refused_air_after_settled_walk(state,command,event,reply,[prior]))
            for change in ('late','airborne','held','velocity','foreign','inventory','hurt','revision','sideways','big_fall','rise'):
                s,e,r,p=copy.deepcopy([state,event,reply,prior])
                if change=='late':e['time']=104
                if change=='airborne':s['on_ground']=False
                if change=='held':s['movement_keys']['forward']=True
                if change=='velocity':s['velocity']=[.1,0,0]
                if change=='foreign':p['params']['task_session']='other'
                if change=='inventory':p['inventory_delta']={'minecraft:stone':1}
                if change=='hurt':p['health_after']=19
                if change=='revision':p['revision_after']=7
                if change in ('sideways','big_fall','rise'):
                    start={'sideways':[10.5,64,20],'big_fall':[10.17,63.5,20.306],'rise':[10.17,65,20.306]}[change]
                    e['position_before']=start;e['position_after']=start;s['pos']=start;r['pos']=start
                with self.subTest(change=change):self.assertFalse(q._refused_air_after_settled_walk(s,command,e,r,[p]))
    def test_initial_entity_reach_refusal_only_snapshots_unchanged_known_outcome(self):
        for change in (None,'unknown','inventory'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as temporary:
                q=VillageQueue.__new__(VillageQueue);q.out=Path(temporary);q.world='w';q.lease={'job_session':'t'}
                d=q.out/'reach';d.mkdir();(q.out/'control').mkdir()
                command={'id':'reach','action':'native','op':'interact_entity','params':{'entity_id':1,'expected_uuid':'v'}}
                reply={'id':'r','world_session':'w','phase':'error','detail':'Entity out of reach'}
                event={'request_id':'r','world_session':'w','op':'interact_entity','phase':'error','detail':reply['detail'],
                       'inventory_delta':{},'position_before':[1,2,3],'position_after':[1,2,3],
                       'revision_before':3,'revision_after':3,'params':{'task_session':'t'}}
                if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if change=='inventory':event['inventory_delta']={'minecraft:emerald':-1}
                (q.out/'command.json').write_text(json.dumps(command));(d/'result.json').write_text(json.dumps(reply));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
                q.status=lambda:{'last_request':'r'};sent=[];q.native=lambda op:sent.append(op)
                if change:
                    with self.assertRaises(RuntimeError):q.observe_refused_entity_reach()
                    self.assertEqual(sent,[])
                else:q.observe_refused_entity_reach();self.assertEqual(sent,['snapshot'])
    def test_stopped_air_small_vertical_settlement_only_reads_conserved_flying_state(self):
        for change in (None,'stock','flight','fall'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
                q,d,event,state=self.stopped_walk(directory);command=json.loads((q.out/'command.json').read_text());command.update(op='navigate',params={'target':[4,2,3],'air_only':True});reply=json.loads((d/'result.json').read_text());reply.update(detail='air-only path changed; no blocks were excavated',control_revision=8,inventory=[{'item':'minecraft:sugar_cane','count':2,'slot':0}]);event.update(op='navigate',detail=reply['detail']);event['params'].update(command['params']);state.update(health=20,flight=True,manual_movement=False,screen='',pos=[2,1.95,3],inventory=[{'item':'minecraft:sugar_cane','count':2,'slot':0}])
                if change=='stock':state['inventory'][0]['count']=3
                if change=='flight':state['flight']=False
                if change=='fall':state['pos'][1]=1
                (q.out/'command.json').write_text(json.dumps(command));(d/'result.json').write_text(json.dumps(reply));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');sent=[];q.native=lambda op:sent.append(op)
                if change:
                    with self.assertRaises(RuntimeError):q.observe_stopped_air_navigation()
                else:q.observe_stopped_air_navigation()
                self.assertEqual(sent,[]if change else['snapshot'])
    def test_read_only_air_refusal_after_released_half_block_step_requires_settled_original_direction(self):
        import copy
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};(q.out/'plan-001').mkdir()
            params=dict(target=[.4,64,.5],arrival=.08,restore_flight=False)
            old=dict(action='native',op='walk',params=params);done=dict(id='walk',phase='done',world_session='w',pos=[.3923,64.5625,.5002])
            (q.out/'plan-001/intent.json').write_text(json.dumps(old));(q.out/'plan-001/result.json').write_text(json.dumps(done))
            prior=dict(request_id='walk',op='walk',phase='done',world_session='w',inventory_delta={},health_before=20,health_after=20,params=dict(task_session='t',**params),position_before=[1.53,64.5625,.475],position_after=done['pos'],revision_after=8)
            event=dict(position_before=done['pos'],position_after=[-.0999,64,.51105],revision_before=8)
            reply=dict(pos=event['position_after'],control_revision=8)
            state=dict(pos=event['position_after'],health=20,control_revision=8,flight=False,on_ground=True,movement_keys={'forward':False},velocity=[0,0,0])
            command=dict(id='plan-002',op='navigate',params=dict(air_only=True))
            self.assertTrue(q._refused_air_after_settled_walk(state,command,event,reply,[prior]))
            state['velocity']=[0,-.0784000015258789,0]
            self.assertTrue(q._refused_air_after_settled_walk(state,command,event,reply,[prior]))
            for change in ('airborne','held','velocity','rise','far','sideways','reverse'):
                s,e,r=copy.deepcopy([state,event,reply])
                if change=='airborne':s['on_ground']=False
                if change=='held':s['movement_keys']['forward']=True
                if change=='velocity':s['velocity']=[.1,0,0]
                if change in ('rise','far','sideways','reverse'):
                    p={'rise':[-.1,65,.51],'far':[-1,64,.51],'sideways':[-.1,64,1],'reverse':[.8,64,.51]}[change];s['pos']=e['position_after']=r['pos']=p
                with self.subTest(change=change):self.assertFalse(q._refused_air_after_settled_walk(s,command,e,r,[prior]))
    def test_bad_boat_stand_never_consumes_a_certificate_or_dispatches_to_owner(self):
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.index=0
            with self.assertRaises(ValueError):q._dispatch('boat_place',dict(support=[3,63,3],stand=[3,63,2],item='minecraft:oak_boat',independent_stock='must-not-consume'),90,{},False)
            self.assertEqual(q.index,0);self.assertEqual(list(q.out.iterdir()),[])
    def test_boat_argument_refusal_only_observes_proved_unchanged_prior_native_terminal(self):
        for unsafe in (None,'journal','inventory','moved','pending','unknown'):
            with self.subTest(unsafe=unsafe),tempfile.TemporaryDirectory()as directory:
                q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'}
                (q.out/'plan-002').mkdir();(q.out/'plan-001').mkdir();(q.out/'control').mkdir()
                (q.out/'command.json').write_text(json.dumps(dict(id='plan-002',action='boat_place')))
                error=dict(type='ValueError',error='A normal boat, exact same-level support and separate standing floor are required',native_inflight=None,unconfirmed_native_request=None,last_request='r')
                reply=dict(id='r',phase='done',world_session='w',control_revision=8,pos=[1,64,1],inventory=[dict(slot=0,item='minecraft:oak_boat',count=1)])
                state=dict(reply,last_request='r');q.status=lambda:state
                if unsafe=='journal':(q.out/'plan-002/actual-one-boat').mkdir()
                if unsafe=='inventory':state['inventory']=[]
                if unsafe=='moved':state['pos']=[2,64,1]
                if unsafe=='pending':reply['phase']='waiting'
                if unsafe=='unknown':error['unconfirmed_native_request']='r'
                (q.out/'plan-002/error.json').write_text(json.dumps(error));(q.out/'plan-001/intent.json').write_text(json.dumps(dict(action='native',op='navigate')));(q.out/'plan-001/result.json').write_text(json.dumps(reply))
                sent=[];q.native=lambda op:sent.append(op)
                if unsafe:
                    with self.assertRaises(RuntimeError):q.observe_refused_boat_geometry()
                    self.assertEqual(sent,[])
                else:q.observe_refused_boat_geometry();self.assertEqual(sent,['snapshot'])
    def test_boat_approach_recovery_is_read_only_and_refuses_any_possible_boat_input(self):
        for unsafe in (None,'journal','inventory','moved','unknown'):
            with self.subTest(unsafe=unsafe),tempfile.TemporaryDirectory()as directory:
                q,d,event,error,state=self.boat_refusal(directory)
                command=json.loads((q.out/'command.json').read_text());command['stand']=[3,1,1]
                (q.out/'command.json').write_text(json.dumps(command))
                error['error']='No visible collision-free depot approach';event.update(op='approach_block',phase='error');event['params']['pos']=command['stand']
                if unsafe=='journal':(d/'actual-one-boat').mkdir()
                if unsafe=='inventory':event['inventory_delta']={'minecraft:oak_boat':-1}
                if unsafe=='moved':event['position_after']=[2,2,3]
                if unsafe=='unknown':error['unconfirmed_native_request']='unknown'
                (d/'error.json').write_text(json.dumps(error));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
                sent=[];q.native=lambda op:sent.append(op)
                if unsafe:
                    with self.assertRaises(RuntimeError):q.observe_refused_boat_approach()
                    self.assertEqual([],sent)
                else:q.observe_refused_boat_approach();self.assertEqual(['snapshot'],sent)
    def test_workbench_open_transition_only_observes_exact_pending_intent(self):
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.root=q.out;q.world='w';q.lease={'id':'l','kind':'materials','job_session':'j','world_session':'w'};q.closing_menu=None
            command={'id':'open','action':'open_workbench','pos':[1,2,3]};d=q.out/'open';d.mkdir()
            (q.out/'command.json').write_text(json.dumps(command));(d/'intent.json').write_text(json.dumps(command))
            state={'connected':True,'world_session':'w','manual_movement':False,'health':20,'screen':'CraftingScreen','interface_paused':False,'inventory_interface_paused':False,'supervision_lease':q.lease,'menu':{'type':'CraftingMenu','id':3,'cursor':{'count':0},'slots':[{'count':0}]*10}}
            with patch('village_queue.read_fresh',return_value=state),patch('village_queue.require_unlocked'):
                q.status(observing=True)
                with self.assertRaises(RuntimeError):q.status()
            for change in ({'manual_movement':True},{'health':18},{'world_session':'other'},{'supervision_lease':None},{'screen':'InventoryScreen'},{'interface_paused':True}):
                with patch('village_queue.read_fresh',return_value={**state,**change}),patch('village_queue.require_unlocked'),self.assertRaises(RuntimeError):q.status(observing=True)
            for filename in ('error.json','result.json'):
                (d/filename).write_text('{}');self.assertFalse(q._opening_workbench());(d/filename).unlink()
            (d/'intent.json').write_text(json.dumps({**command,'pos':[4,5,6]}));self.assertFalse(q._opening_workbench())
    def test_unconfirmed_boat_keeps_original_journal_and_fences_all_replacement_uses(self):
        from kit_runtime.journal import write_json as real_write
        with tempfile.TemporaryDirectory()as directory:
            parent=Path(directory);out=parent/'owner';out.mkdir();q=VillageQueue.__new__(VillageQueue);q.out=out;q.world='w';q.lease={'job_session':'t'};q.prefix='boat-observe';q.index=0;q.closing_menu=None
            command={'id':'old','action':'boat_place','support':[3,1,3],'item':'minecraft:oak_boat'};real_write(out/'command.json',command);d=out/'old';(d/'actual-one-boat').mkdir(parents=True);(out/'control').mkdir()
            book={'world_session':'w','complete':False,'pending':'place','support':[3,1,3],'item':'minecraft:oak_boat','request_id':'use-old'};real_write(d/'actual-one-boat/place.json',book);original=(d/'actual-one-boat/place.json').read_bytes()
            error={'error':'Original boat input has no conserved two-frame result; retained without replay','native_inflight':None,'unconfirmed_native_request':None,'last_request':'use-old'};real_write(d/'error.json',error)
            event={'request_id':'use-old','world_session':'w','op':'interact','phase':'done','revision_after':8,'params':{'task_session':'t','pos':[3,1,3],'expected_hand':'minecraft:oak_boat'}};(out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
            state={'screen':'','last_request':'use-old','control_revision':8,'hand':{'item':'minecraft:oak_boat'}};q.status=lambda **kw:state;sent=[]
            def owner(path,value):
                real_write(path,value)
                if Path(path).name=='command.json':
                    sent.append(value);new=out/value['id'];new.mkdir();real_write(new/'result.json',{'phase':'done','world_session':'w'})
            with patch('village_queue.write_json',side_effect=owner):q.quarantine_unconfirmed_boat_place()
            self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(original,(d/'actual-one-boat/place.json').read_bytes());self.assertTrue((parent/'unresolved-boat-placement.json').exists())
            for action,params in [('boat_place',{}),('native',{'op':'interact','params':{'expected_hand':'minecraft:oak_boat'}}),('native',{'op':'use_item'})]:
                with self.subTest(action=action,params=params),self.assertRaises(RuntimeError):q._send(action,**params)
            self.assertEqual(1,len(sent))
            old_fence=(parent/'unresolved-boat-placement.json').read_bytes()
            second=out/'second';(second/'actual-one-boat').mkdir(parents=True)
            real_write(out/'command.json',{**command,'id':'second'})
            real_write(second/'actual-one-boat/place.json',{**book,'request_id':'use-second'})
            real_write(second/'error.json',{**error,'last_request':'use-second'})
            (out/'control/events.jsonl').write_text(json.dumps({**event,'request_id':'use-second'})+'\n')
            state['last_request']='use-second'
            with patch('village_queue.write_json',side_effect=owner):q.quarantine_unconfirmed_boat_place()
            self.assertEqual((parent/'unresolved-boat-placement.json').read_bytes(),old_fence)
            self.assertEqual(original,(d/'actual-one-boat/place.json').read_bytes())
            registry=json.loads((parent/'unresolved-boat-placement-additional.json').read_text())
            self.assertEqual(registry['entries'][0]['request_id'],'use-second')
            self.assertEqual([v['op']for v in sent],['snapshot','snapshot'])
            with self.assertRaisesRegex(RuntimeError,'Current-world boat use remains unconfirmed'):
                q._send('boat_place',independent_stock='new-stock-is-not-an-escape')
    def boat_refusal(self,directory):
        q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.prefix='boat-read';q.index=0;q.closing_menu=None
        command={'id':'old','action':'boat_place','support':[3,1,3],'stand':[1,1,3]};(q.out/'command.json').write_text(json.dumps(command));d=q.out/'old';d.mkdir();(q.out/'control').mkdir()
        error={'error':'Boat body space is obstructed','type':'RuntimeError','native_inflight':None,'unconfirmed_native_request':None,'last_request':'scan-old'};(d/'error.json').write_text(json.dumps(error))
        event={'request_id':'scan-old','op':'scan','phase':'done','world_session':'w','params':{'task_session':'t','min':[0,0,2],'max':[4,5,4],'details':True},'position_before':[1,2,3],'position_after':[1,2,3],'inventory_delta':{},'health_before':20,'health_after':20,'revision_before':8,'revision_after':8};(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
        state={'screen':'','last_request':'scan-old','pos':[1,2,3],'control_revision':8};q.status=lambda **kw:state
        return q,d,event,error,state
    def test_exact_boat_space_preflight_only_observes_without_replay_or_erasing_error(self):
        from kit_runtime.journal import write_json as real_write
        with tempfile.TemporaryDirectory()as directory:
            q,d,event,error,state=self.boat_refusal(directory);original=(d/'error.json').read_bytes();sent=[]
            def owner(path,value):
                real_write(path,value)
                if Path(path).name=='command.json':
                    sent.append(value);new=q.out/value['id'];new.mkdir();real_write(new/'result.json',{'phase':'done','world_session':'w'})
            with patch('village_queue.write_json',side_effect=owner):q.observe_boat_space_refusal()
            self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(original,(d/'error.json').read_bytes())
    def test_unknown_boat_or_non_read_preflight_never_authorizes_observation(self):
        for change in ('unknown','journal','moved','revision','inventory','scope','input','world','inflight'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
                q,d,event,error,state=self.boat_refusal(directory)
                if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if change=='journal':(d/'actual-one-boat').mkdir()
                if change=='moved':event['position_after']=[2,2,3]
                if change=='revision':state['control_revision']=9
                if change=='inventory':event['inventory_delta']={'minecraft:oak_boat':-1}
                if change=='scope':event['params']['max']=[4,6,4]
                if change=='input':event['op']='interact'
                if change=='world':event['world_session']='other'
                if change=='inflight':error['native_inflight']='pending'
                (d/'error.json').write_text(json.dumps(error));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
                with self.assertRaises(RuntimeError):q.observe_boat_space_refusal()
                self.assertFalse((q.out/'boat-read-001').exists())
    def stopped_walk(self,directory):
        q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.prefix='walk-observe';q.index=0;q.closing_menu=None
        command={'id':'old','action':'native','op':'walk','params':{'target':[4,2,3],'seconds':12}}
        (q.out/'command.json').write_text(json.dumps(command));d=q.out/'old';d.mkdir();(q.out/'control').mkdir()
        reply={'id':'native-old','world_session':'w','phase':'waiting','detail':'time limit reached; inspect progress before resuming','pos':[2,2,3]};(d/'result.json').write_text(json.dumps(reply))
        event={'request_id':'native-old','world_session':'w','op':'walk','phase':'waiting','detail':reply['detail'],'position_before':[1,2,3],'position_after':[2,2,3],'inventory_delta':{},'health_before':20,'health_after':20,'revision_after':8,'params':{'task_session':'t',**command['params']}}
        (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');state={'last_request':'native-old','pos':[2,2,3],'control_revision':8,'movement_keys':{'forward':False},'supervision_lease':{'revision':8}};q.status=lambda **kw:state
        return q,d,event,state
    def test_changed_air_path_acknowledged_stop_only_reads_actual_partial_position(self):
        for unsafe in (None,'running','held','unknown','moved','scope','inventory'):
            with self.subTest(unsafe=unsafe),tempfile.TemporaryDirectory()as directory:
                q,d,event,state=self.stopped_walk(directory);command=json.loads((q.out/'command.json').read_text());command['op']='navigate';command['params']['air_only']=True
                reply=json.loads((d/'result.json').read_text());reply.update(detail='air-only path changed; no blocks were excavated',control_revision=8)
                event.update(op='navigate',detail=reply['detail']);event['params']['air_only']=True;state.update(health=20,movement_keys={'forward':False})
                if unsafe=='running':reply['phase']='running'
                if unsafe=='held':state['movement_keys']['forward']=True
                if unsafe=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if unsafe=='moved':state['pos']=[9,2,3]
                if unsafe=='scope':event['params']['task_session']='other'
                if unsafe=='inventory':event['inventory_delta']={'minecraft:oak_boat':-1}
                (q.out/'command.json').write_text(json.dumps(command));(d/'result.json').write_text(json.dumps(reply));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');sent=[];q.native=lambda op:sent.append(op)
                if unsafe:
                    with self.assertRaises(RuntimeError):q.observe_stopped_air_navigation()
                    self.assertEqual(sent,[])
                else:q.observe_stopped_air_navigation();self.assertEqual(sent,['snapshot'])
    def test_stopped_partial_walk_observes_original_position_without_replaying(self):
        from kit_runtime.journal import write_json as real_write
        with tempfile.TemporaryDirectory()as directory:
            q,d,event,state=self.stopped_walk(directory);sent=[];original=(d/'result.json').read_bytes()
            def owner(path,value):
                real_write(path,value)
                if Path(path).name=='command.json':
                    sent.append(value);new=q.out/value['id'];new.mkdir();real_write(new/'result.json',{'phase':'done','world_session':'w'})
            with patch('village_queue.write_json',side_effect=owner):q.observe_stopped_walk()
            self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(original,(d/'result.json').read_bytes())
    def test_stopped_walk_unknown_moved_active_or_changed_receipt_never_observes(self):
        for change in ('unknown','position','revision','active','inventory','health','task','target','missing_event'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
                q,d,event,state=self.stopped_walk(directory)
                if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if change=='position':state['pos']=[3,2,3]
                if change=='revision':state['control_revision']=9
                if change=='active':state['movement_keys']['forward']=True
                if change=='inventory':event['inventory_delta']={'minecraft:bread':-1}
                if change=='health':event['health_after']=19
                if change=='task':event['params']['task_session']='other'
                if change=='target':event['params']['target']=[9,2,3]
                (q.out/'control/events.jsonl').write_text(''if change=='missing_event'else json.dumps(event)+'\n')
                with self.assertRaises(RuntimeError):q.observe_stopped_walk()
                self.assertFalse((q.out/'walk-observe-001').exists())
    def test_native_timeout_receipt_before_waiting_status_only_allows_conserved_read(self):
        from kit_runtime.journal import write_json as real_write
        for unsafe in (None,'inventory','airborne','moving','unknown'):
            with self.subTest(unsafe=unsafe),tempfile.TemporaryDirectory()as directory:
                q,d,event,state=self.stopped_walk(directory);reply=json.loads((d/'result.json').read_text())
                reply.update(phase='stopped',detail='脚本任务达到时间上限');event.update(phase=reply['phase'],detail=reply['detail'])
                state.update(phase='waiting',detail='time limit reached; inspect progress before resuming',health=20,on_ground=True,flight=False)
                if unsafe=='inventory':event['inventory_delta']={'minecraft:white_bed':1}
                if unsafe=='airborne':state['on_ground']=False
                if unsafe=='moving':state['movement_keys']['forward']=True
                if unsafe=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                real_write(d/'result.json',reply);(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');sent=[]
                def owner(path,value):
                    real_write(path,value)
                    if Path(path).name=='command.json':
                        sent.append(value);new=q.out/value['id'];new.mkdir();real_write(new/'result.json',{'phase':'done','world_session':'w'})
                with patch('village_queue.write_json',side_effect=owner):
                    if unsafe:
                        with self.assertRaises(RuntimeError):q.observe_stopped_walk()
                    else:q.observe_stopped_walk()
                self.assertEqual([]if unsafe else['snapshot'],[v['op']for v in sent])
    def air_refusal(self,directory):
        q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.prefix='observe';q.index=0;q.closing_menu=None;q.status=lambda **kw:{'screen':'','last_request':'native-old'}
        d=q.out/'old';d.mkdir();(q.out/'control').mkdir();(q.out/'command.json').write_text(json.dumps({'id':'old','action':'native','op':'navigate'}))
        reply={'id':'native-old','world_session':'w','phase':'error','detail':'Air-only navigation requires the current material lease and a loaded clear dry path'}
        (d/'result.json').write_text(json.dumps(reply));event={**reply,'request_id':'native-old','op':'navigate','position_before':[1,2,3],'position_after':[1,2,3],'inventory_delta':{},'revision_before':4,'revision_after':4,'params':{'task_session':'t'}}
        (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,d,event
    def test_unmoved_air_refusal_allows_one_read_without_replaying_navigation(self):
        from kit_runtime.journal import write_json as real_write
        with tempfile.TemporaryDirectory()as directory:
            q,d,event=self.air_refusal(directory);sent=[];original=(d/'result.json').read_bytes()
            def owner(path,value):
                real_write(path,value)
                if Path(path).name=='command.json':
                    sent.append(value);new=q.out/value['id'];new.mkdir();real_write(new/'result.json',{'phase':'done','world_session':'w'})
            with patch('village_queue.write_json',side_effect=owner):q.observe_refused_air_path()
            self.assertEqual([('native','snapshot')],[(v['action'],v['op'])for v in sent]);self.assertEqual(original,(d/'result.json').read_bytes());self.assertIsNone(q._refused_air_read)
    def test_held_item_preflight_only_authorizes_read_and_rejects_inventory_change(self):
        from kit_runtime.journal import write_json as real_write
        for changed in (False,True):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory()as directory:
                q,d,event=self.air_refusal(directory);command={'id':'old','action':'native','op':'interact'}
                real_write(q.out/'command.json',command)
                reply=json.loads((d/'result.json').read_text());reply['detail']='Held item changed';real_write(d/'result.json',reply)
                event.update(op='interact',detail=reply['detail'],inventory_delta={'minecraft:dark_oak_planks':-1}if changed else{})
                (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');sent=[];original=(d/'result.json').read_bytes()
                def owner(path,value):
                    real_write(path,value)
                    if Path(path).name=='command.json':
                        sent.append(value);new=q.out/value['id'];new.mkdir();real_write(new/'result.json',{'phase':'done','world_session':'w'})
                with patch('village_queue.write_json',side_effect=owner):
                    if changed:
                        with self.assertRaises(RuntimeError):q.observe_refused_held_item()
                    else:q.observe_refused_held_item()
                self.assertEqual([]if changed else[('native','snapshot')],[(v['action'],v['op'])for v in sent])
                self.assertEqual(original,(d/'result.json').read_bytes())
    def test_unknown_moved_other_world_or_changed_scope_never_authorizes_air_read(self):
        for change in('unknown','moved','world','revision','task','missing_event'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
                q,d,event=self.air_refusal(directory)
                if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if change=='moved':event['position_after']=[2,2,3]
                if change=='world':event['world_session']='other'
                if change=='revision':event['revision_after']=5
                if change=='task':event['params']['task_session']='other'
                (q.out/'control/events.jsonl').write_text(''if change=='missing_event'else json.dumps(event)+'\n')
                with self.assertRaises(RuntimeError):q.observe_refused_air_path()
                self.assertFalse((q.out/'observe-001').exists())
    def test_missing_drop_can_only_issue_a_read_after_the_exact_known_refusal(self):
        from kit_runtime.journal import write_json as real_write
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.prefix='read';q.index=0;q.closing_menu=None
            state={'screen':'','last_request':'native-old'};q.status=lambda **kw:state
            d=q.out/'old';d.mkdir();(q.out/'command.json').write_text(json.dumps({'id':'old','action':'native','op':'collect_item'}));(d/'result.json').write_text(json.dumps({'phase':'error','detail':'Drop is no longer loaded; observe again','world_session':'w','id':'native-old'}));sent=[]
            def owner(path,value):
                real_write(path,value)
                if Path(path).name=='command.json':
                    sent.append(value);new=q.out/value['id'];new.mkdir();real_write(new/'result.json',{'phase':'done','world_session':'w'})
            with patch('village_queue.write_json',side_effect=owner):q.observe_missing_drop()
            self.assertEqual([(v['action'],v['op'])for v in sent],[('native','snapshot')])
            self.assertIsNone(q._missing_drop_observation)
            self.assertEqual(json.loads((d/'result.json').read_text())['phase'],'error')
    def test_missing_drop_observation_does_not_release_unknown_or_other_world_actions(self):
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.status=lambda:{'last_request':'native-old'}
            d=q.out/'old';d.mkdir();(q.out/'command.json').write_text(json.dumps({'id':'old','action':'native','op':'collect_item'}));reply={'phase':'error','detail':'Drop is no longer loaded; observe again','world_session':'other','id':'native-old'};(d/'result.json').write_text(json.dumps(reply))
            with self.assertRaises(RuntimeError):q.observe_missing_drop()
            reply['world_session']='w';(d/'result.json').write_text(json.dumps(reply));(q.out/'control').mkdir();(q.out/'control/unconfirmed-native-request.json').write_text('{}')
            with self.assertRaises(RuntimeError):q.observe_missing_drop()
            self.assertFalse((q.out/'read-001').exists())
    def test_certified_crafting_recovery_only_returns_exact_cursor_or_ingredients(self):
        q=VillageQueue.__new__(VillageQueue);q._owned_menu=lambda s,**kw:s.get('certified',False)
        rows=[{'item':'minecraft:air','count':0,'max_stack':1}for _ in range(46)]
        rows[1]={'item':'minecraft:white_wool','count':3,'max_stack':64}
        s={'certified':True,'menu':{'type':'CraftingMenu','id':6,'slots':rows,
                                   'cursor':{'item':'minecraft:dark_oak_planks','count':48,'max_stack':64}}}
        p={'menu_id':6,'slot':10,'kind':'pickup','expected_item':'minecraft:air','expected_count':0,
           'expected_cursor':'minecraft:dark_oak_planks','expected_cursor_count':48}
        self.assertTrue(q._craft_return(s,p))
        for changes in({'slot':0},{'expected_cursor_count':47},{'kind':'quick_move'},{'menu_id':7}):
            self.assertFalse(q._craft_return(s,{**p,**changes}))
        self.assertFalse(q._craft_return({**s,'certified':False},p))
        s['menu']['cursor']={'item':'minecraft:air','count':0}
        p={'menu_id':6,'slot':1,'kind':'quick_move','expected_item':'minecraft:white_wool','expected_count':3,
           'expected_cursor':'minecraft:air','expected_cursor_count':0}
        self.assertTrue(q._craft_return(s,p))
        self.assertFalse(q._craft_return(s,{**p,'slot':0}))
    def test_released_lease_is_observable_only_while_waiting_for_pause(self):
        q=VillageQueue.__new__(VillageQueue);q.root=Path('.');q.out=Path('.');q.world='w';q.lease={'id':'l','kind':'materials','job_session':'j','world_session':'w'}
        s={'connected':True,'world_session':'w','manual_movement':False,'health':20,'screen':'','supervision_lease':None}
        with patch('village_queue.read_fresh',return_value=s),patch('village_queue.require_unlocked'):
            q.status(observing=True,allow_released=True)
            for options in ({},{'observing':True},{'allow_released':True}):
                with self.assertRaises(RuntimeError):q.status(**options)
        for change in ({'manual_movement':True},{'health':18},{'world_session':'other'},
                       {'supervision_lease':{**q.lease,'id':'other'}}):
            with patch('village_queue.read_fresh',return_value={**s,**change}),patch('village_queue.require_unlocked'):
                with self.assertRaises(RuntimeError):q.status(observing=True,allow_released=True)
    def test_storage_uses_explicit_sdk_window_binding_without_accepting_manual_or_cursor_changes(self):
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'id':'l','job_session':'j'}
            certificate={'type':'ChestMenu','id':2,'world_session':'w','task_session':'j','lease_id':'l','control_revision':8}
            (q.out/'owned-material-menu.json').write_text(json.dumps(certificate))
            s={'screen':'ContainerScreen','interface_paused':False,'inventory_interface_paused':False,'control_revision':8,'menu':{'type':'ChestMenu','id':2,'cursor':{'count':0}}}
            self.assertTrue(q._owned_menu(s))
            for changes in({'control_revision':9},{'interface_paused':True},{'menu':{**s['menu'],'id':3}}):self.assertFalse(q._owned_menu({**s,**changes}))
            s['menu']['cursor']['count']=1;self.assertFalse(q._owned_menu(s));self.assertTrue(q._owned_menu(s,observing=True))
    def test_pending_storage_is_observation_only_until_sdk_publishes_ownership(self):
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);d=q.out/'open';d.mkdir();(d/'intent.json').write_text('{}');(q.out/'command.json').write_text(json.dumps({'id':'open','action':'open_chest_from_pose'}))
            s={'screen':'ContainerScreen','interface_paused':False,'inventory_interface_paused':False,'menu':{'type':'ChestMenu'}}
            self.assertTrue(q._expected_storage_observation(s));self.assertFalse(q._expected_storage_observation({**s,'screen':'InventoryScreen'}))
            (d/'error.json').write_text('{}');self.assertFalse(q._expected_storage_observation(s))
    def test_pending_recipe_observation_does_not_take_over_manual_inventory(self):
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.root=Path(directory);q.world='w';q.lease={'id':'l','kind':'materials','job_session':'j','world_session':'w'};q.closing_menu=None
            d=q.out/'craft';d.mkdir();(d/'intent.json').write_text('{}');(q.out/'command.json').write_text(json.dumps({'id':'craft','action':'manufacture'}))
            s={'connected':True,'world_session':'w','manual_movement':False,'health':20,'screen':'CraftingScreen','interface_paused':False,'inventory_interface_paused':False,'control_revision':7,'supervision_lease':q.lease,'menu':{'type':'CraftingMenu','id':1,'cursor':{'count':1},'slots':[{'count':0}]*10}}
            with patch('village_queue.read_fresh',return_value=s),patch('village_queue.require_unlocked'):
                q.status(observing=True)
                with self.assertRaises(RuntimeError):q.status()
            for changes in({'screen':'InventoryScreen'},{'interface_paused':True},{'manual_movement':True}):
                with patch('village_queue.read_fresh',return_value={**s,**changes}),patch('village_queue.require_unlocked'),self.assertRaises(RuntimeError):q.status(observing=True)
    def test_audit_window_can_only_be_observed_during_its_known_pending_command(self):
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.root=Path(directory);q.world='w';q.lease={'id':'l','kind':'materials','job_session':'j','world_session':'w'}
            d=q.out/'audit';d.mkdir();(d/'intent.json').write_text('{}');(q.out/'command.json').write_text(json.dumps({'id':'audit','action':'audit_depots'}))
            s={'connected':True,'world_session':'w','manual_movement':False,'health':20,'screen':'ContainerScreen','interface_paused':False,'inventory_interface_paused':False,'supervision_lease':q.lease,'menu':{'type':'ChestMenu','cursor':{'count':0}}}
            with patch('village_queue.read_fresh',return_value=s),patch('village_queue.require_unlocked'):
                q.status(observing=True)
                with self.assertRaises(RuntimeError):q.status()
            for changes in({'interface_paused':True},{'manual_movement':True},{'world_session':'other'}):
                with patch('village_queue.read_fresh',return_value={**s,**changes}),patch('village_queue.require_unlocked'),self.assertRaises(RuntimeError):q.status(observing=True)
            (d/'error.json').write_text('{}')
            with patch('village_queue.read_fresh',return_value=s),patch('village_queue.require_unlocked'),self.assertRaises(RuntimeError):q.status(observing=True)
    def test_only_matching_complete_empty_recipe_menu_may_be_closed(self):
        with tempfile.TemporaryDirectory()as directory:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.root=Path(directory);q.world='w';q.lease={'id':'l','kind':'materials','job_session':'j','world_session':'w'};q.closing_menu=None
            d=q.out/'craft';d.mkdir();(d/'intent.json').write_text('{}');(q.out/'command.json').write_text(json.dumps({'id':'craft','action':'manufacture'}))
            cert={'type':'CraftingMenu','id':1,'world_session':'w','task_session':'j','lease_id':'l','control_revision':7};(d/'result.json').write_text(json.dumps({'complete':True,'owned_menu':cert}))
            s={'connected':True,'world_session':'w','manual_movement':False,'health':20,'screen':'CraftingScreen','interface_paused':False,'inventory_interface_paused':False,'control_revision':7,'supervision_lease':q.lease,'menu':{'type':'CraftingMenu','id':1,'cursor':{'count':0},'slots':[{'count':0}]*10}}
            self.assertTrue(q._completed_workbench(s))
            with patch('village_queue.read_fresh',return_value=s),patch('village_queue.require_unlocked'),self.assertRaisesRegex(RuntimeError,'must close'):
                q.send('native',op='walk')
            self.assertEqual('craft',json.loads((q.out/'command.json').read_text())['id'])
            for field,value in(('id',2),('lease_id','other'),('control_revision',6)):
                (d/'result.json').write_text(json.dumps({'complete':True,'owned_menu':{**cert,field:value}}));self.assertFalse(q._completed_workbench(s))
            (d/'result.json').write_text(json.dumps({'complete':True,'owned_menu':cert}));s['menu']['cursor']['count']=1;self.assertFalse(q._completed_workbench(s))
    def test_a_pending_or_failed_action_cannot_be_overwritten_by_another_plan(self):
        with tempfile.TemporaryDirectory()as temporary:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(temporary);q.world='w';q.prefix='p';q.index=0;q.status=lambda:{}
            (q.out/'command.json').write_text(json.dumps({'id':'original'}));(q.out/'original').mkdir()
            for result,error in ((False,False),(True,True)):
                if result:(q.out/'original/result.json').write_text('{}')
                if error:(q.out/'original/error.json').write_text('{}')
                with self.assertRaises(RuntimeError):q.send('native',op='walk')
                self.assertEqual(json.loads((q.out/'command.json').read_text()),{'id':'original'})
            self.assertFalse((q.out/'p-001').exists())
    def test_pause_after_completed_phase_less_projection_read_stamps_snapshot_before_release(self):
        from kit_runtime.journal import write_json as real_write
        for op in ('projection_audit','projection_model'):
            with self.subTest(op=op),tempfile.TemporaryDirectory()as temporary:
                q=VillageQueue.__new__(VillageQueue);q.out=Path(temporary);q.world='w';q.prefix='p';q.index=0;q.closing_menu=None;q.status=lambda **kw:{'screen':''}
                old=q.out/'read';old.mkdir();original={'world_session':'w',op:{'data':'preserved'}}
                (old/'result.json').write_text(json.dumps(original));(q.out/'command.json').write_text(json.dumps({'id':'read','action':'native','op':op}))
                sent=[]
                def owner(path,value):
                    real_write(path,value)
                    if Path(path).name=='command.json':
                        sent.append(value);d=q.out/value['id'];d.mkdir();real_write(d/'result.json',{'phase':None if value['action']=='native'else'done','world_session':'w'})
                with patch('village_queue.write_json',side_effect=owner):self.assertEqual('done',q.send('pause')['phase'])
                self.assertEqual([('native','snapshot'),('pause',None)],[(x['action'],x.get('op'))for x in sent])
                self.assertEqual(original,json.loads((old/'result.json').read_text()))
    def test_projection_pause_stamp_rejects_a_failed_or_other_world_read_without_new_command(self):
        for failed,world in ((True,'w'),(False,'other')):
            with tempfile.TemporaryDirectory()as temporary:
                q=VillageQueue.__new__(VillageQueue);q.out=Path(temporary);q.world='w';q.prefix='p';q.index=0;q.closing_menu=None;q.status=lambda **kw:{'screen':''}
                d=q.out/'read';d.mkdir();(d/'result.json').write_text(json.dumps({'world_session':world,'projection_audit':{}}));(q.out/'command.json').write_text(json.dumps({'id':'read','action':'native','op':'projection_audit'}))
                if failed:(d/'error.json').write_text('{}')
                with self.assertRaises(RuntimeError):q.send('pause')
                self.assertEqual('read',json.loads((q.out/'command.json').read_text())['id']);self.assertFalse((q.out/'p-001').exists())

if __name__=='__main__':unittest.main()
