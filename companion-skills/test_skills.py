import copy,json,os,tempfile,unittest
from pathlib import Path
from kit_skills.library import SkillManager
from kit_skills.learning import skill_from_request,learn_transaction,learn_episode,propose_from_ai
from kit_skills.model import verify_episode,validate
from kit_skills.kit import KitRecorder,ingest_supervisor
from kit_skills.cli import compile_skill

def state(t=100000,**kw):
    return {'time':t,'connected':True,'server':'simpcraft.com','dimension':'minecraft:overworld','health':20,'pos':[0,64,0],'inventory':[],**kw}
def req(rid='one',op='navigate',**kw):
    return {'id':rid,'op':op,'server':'simpcraft.com','dimension':'minecraft:overworld','site':[0,64,0],**({'target':[2,64,0],'arrival':1,'seconds':20} if op=='navigate' else {}),**kw}
def episode(request=None):
    r=request or req();s=skill_from_request(r)
    before=state();after=state(101000,id=r['id'],phase='done',pos=r.get('target',[0,64,0]))
    params={k:v for k,v in r.items() if k not in {'op','id','server','dimension','site'}}
    return s,{'id':r['id'],'before':before,'after':after,'parameters':params,'actions':[{'request':r,'result':after}]}
class SkillsTest(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.m=SkillManager(self.root/'skills')
    def tearDown(self):self.m.close();self.tmp.cleanup()
    def test_success_claim_without_actual_position_does_not_pass(self):
        s,e=episode();e['after']['pos']=[100,64,100];e['success']=True
        self.assertFalse(verify_episode(s,e)[0])
    def test_different_request_or_world_cannot_supply_evidence(self):
        s,e=episode();e['actions'][0]['result']['id']='other';self.assertFalse(verify_episode(s,e)[0])
        s,e=episode();e['after']['dimension']='minecraft:the_nether';self.assertFalse(verify_episode(s,e)[0])
    def test_ai_imports_never_promote_themselves(self):
        for i in range(3):
            s,e=episode(req(str(i)));result=learn_episode(self.m,{'skill':s,'episode':e})
        self.assertEqual(result['status'],'candidate');self.assertEqual(self.m.retrieve_skills('前往施工点'),[])
    def test_native_two_successes_promote_and_retrieve(self):
        for i in range(2):
            s,e=episode(req(str(i)));r=learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after'])
        self.assertEqual(r['status'],'verified');self.assertEqual(len(self.m.retrieve_skills('前往施工点')),1)
        plan=compile_skill(self.m,s['name'],{'target':[3,64,0],'arrival':1,'seconds':20})
        self.assertEqual(plan['steps'][0]['args']['target'],[3,64,0])
    def test_duplicate_evidence_is_not_two_successes(self):
        s,e=episode();q=e['actions'][0]['request']
        learn_transaction(self.m,q,e['before'],e['after']);r=learn_transaction(self.m,q,e['before'],e['after'])
        self.assertEqual(r['successful_runs'],1);self.assertEqual(r['status'],'candidate')
    def test_changed_skill_is_new_candidate_not_inherited_success(self):
        for i in range(2):
            s,e=episode(req(str(i)));learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after'])
        s['success'][0]['radius']=.1;r=self.m.add_new_skill(s)
        self.assertEqual(r['version'],2);self.assertEqual(r['status'],'candidate')
        with self.assertRaises(ValueError):compile_skill(self.m,s['name'],{'target':[2,64,0],'arrival':1,'seconds':20})
    def test_manual_stop_does_not_turn_into_a_skill_failure(self):
        s,e=episode();e['after'].update(phase='stopped',detail='手动移动接管')
        r=learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after'])
        self.assertEqual(r['status'],'lesson');self.assertEqual(self.m.summary()['episodes'],0)
    def test_print_confirmation_is_batch_success_not_full_house(self):
        s,e=episode(req('print1','professional_print',seconds=5));e['after']['professional_printer']={'server_confirmed':3,'waiting_for_server':False,'failure':'','travel_pending':0,'enabled':False,'owned':False}
        self.assertTrue(verify_episode(s,e)[0]);self.assertIn('不代表整栋',s['description'])
        e['after']['professional_printer']['waiting_for_server']=True;self.assertFalse(verify_episode(s,e)[0])
    def printer_episode(self,rid='printer-case',**changes):
        s,e=episode(req(rid,'professional_print',seconds=3))
        e['after']['professional_printer']={'server_confirmed':6,'waiting_for_server':False,
            'failure':'','travel_pending':0,'enabled':False,'owned':False,
            'fast_proposals':6,'complex_proposals':0,**changes}
        return s,e
    def test_printer_done_with_late_sent_block_is_not_success(self):
        s,e=self.printer_episode(travel_pending=1,fast_proposals=7)
        self.assertEqual('done',e['after']['phase'])
        self.assertFalse(verify_episode(s,e)[0])
    def test_printer_running_failure_or_waiting_flags_prevent_success(self):
        for changes in ({'waiting_for_server':True},{'failure':'server did not confirm'},
                        {'enabled':True},{'owned':True}):
            with self.subTest(changes=changes):
                s,e=self.printer_episode(**changes)
                self.assertFalse(verify_episode(s,e)[0])
    def test_printer_missing_actual_host_fields_is_unknown_not_success(self):
        for key in ('server_confirmed','travel_pending','waiting_for_server','failure','enabled','owned'):
            with self.subTest(key=key):
                s,e=self.printer_episode();del e['after']['professional_printer'][key]
                self.assertFalse(verify_episode(s,e)[0])
    def test_printer_counters_and_stopped_flags_require_actual_json_types(self):
        for changes in ({'server_confirmed':True},{'server_confirmed':6.0},
                        {'travel_pending':False},{'travel_pending':0.0},
                        {'waiting_for_server':0},{'enabled':0},{'owned':0}):
            with self.subTest(changes=changes):
                s,e=self.printer_episode(**changes)
                self.assertFalse(verify_episode(s,e)[0])
    def test_printer_insufficient_and_zero_confirmations_never_succeed(self):
        s,e=self.printer_episode(server_confirmed=3);s['success'][0]['count']=4
        self.assertFalse(verify_episode(s,e)[0])
        e['after']['professional_printer']['server_confirmed']=4
        self.assertTrue(verify_episode(s,e)[0])
        s,e=self.printer_episode(server_confirmed=0)
        self.assertFalse(verify_episode(s,e)[0])
        for count in (0,False,1.0):
            s,e=self.printer_episode();s['success'][0]['count']=count
            self.assertFalse(verify_episode(s,e)[0])
    def test_printer_malformed_status_never_supplies_success(self):
        for status in (None,[],True,'done'):
            with self.subTest(status=status):
                s,e=self.printer_episode();e['after']['professional_printer']=status
                self.assertFalse(verify_episode(s,e)[0])
    def test_two_partial_printer_windows_cannot_promote_a_skill(self):
        for i in range(2):
            s,e=self.printer_episode('pending-print'+str(i),travel_pending=1,fast_proposals=7)
            result=learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after'])
        self.assertEqual('candidate',result['status'])
        self.assertEqual(0,result['successful_runs'])
        self.assertEqual([],self.m.retrieve_skills('打印投影'))
    def test_two_fully_settled_stopped_print_windows_still_promote(self):
        for i in range(2):
            s,e=self.printer_episode('settled-print'+str(i))
            result=learn_transaction(self.m,e['actions'][0]['request'],e['before'],e['after'])
        self.assertEqual('verified',result['status'])
        self.assertEqual(2,result['successful_runs'])
    def test_collection_requires_inventory_not_only_done(self):
        s,e=episode(req('chop1','chop',item='minecraft:oak_log',target_count=16,seconds=60))
        self.assertFalse(verify_episode(s,e)[0]);e['after']['inventory']=[{'slot':0,'item':'minecraft:oak_log','count':16}]
        self.assertTrue(verify_episode(s,e)[0])
    def test_external_code_and_unbounded_actions_are_rejected(self):
        s,e=episode();s['steps'][0]['op']='shell'
        with self.assertRaises(ValueError):propose_from_ai(self.m,s)
        with self.assertRaises(ValueError):episode(req(seconds=10000))
    def test_arbitrary_script_cannot_be_executed_as_a_skill(self):
        s,e=episode();s['steps'][0]={'op':'python','args':{'code':'raise SystemExit()'}}
        with self.assertRaises(ValueError):validate(s)
    def test_file_observer_correlates_pre_state_request_and_reply(self):
        mailbox=self.root/'mailbox';mailbox.mkdir();rec=KitRecorder(mailbox,self.m)
        for i in range(2):
            t=100+i*5;before=state(t*1000);(mailbox/'status.json').write_text(json.dumps(before));rec.poll(t)
            request=req('native'+str(i));p=mailbox/'request.json';p.write_text(json.dumps(request));os.utime(p,(t+.02,t+.02));rec.poll(t+.03)
            after=state((t+1)*1000,id=request['id'],phase='done',pos=request['target']);(mailbox/'status.json').write_text(json.dumps(after));result=rec.poll(t+1)
        self.assertEqual(result[0]['status'],'verified')
    def test_missing_or_stale_before_frame_is_only_a_lesson(self):
        mailbox=self.root/'mailbox';mailbox.mkdir();(mailbox/'status.json').write_text(json.dumps(state()))
        (mailbox/'request.json').write_text(json.dumps(req()));r=KitRecorder(mailbox,self.m)
        self.assertEqual(r.poll(100),[]);self.assertEqual(self.m.summary()['episodes'],0)
        self.assertEqual(r.poll(200),[])
    def test_journal_cursor_and_partial_lines_are_not_double_counted(self):
        p=self.root/'events.jsonl';p.write_text('{"id":1}\n{"id":')
        self.assertEqual(ingest_supervisor(self.m,p),1);self.assertEqual(ingest_supervisor(self.m,p),0)
        with p.open('a') as f:f.write('2}\n')
        self.assertEqual(ingest_supervisor(self.m,p),1);self.assertEqual(self.m.summary()['lessons'],2)
    def test_gui_partial_build_is_a_lesson_not_a_verified_skill(self):
        mailbox=self.root/'gui';mailbox.mkdir();r=KitRecorder(mailbox,self.m)
        (mailbox/'status.json').write_text(json.dumps(state(build_job={'active':True,'matched':10,'total':100})));r.poll(100)
        (mailbox/'status.json').write_text(json.dumps(state(101000,build_job={'active':False,'matched':13,'total':100,'reason':'找不到可通行路线'})));r.poll(101)
        self.assertEqual(self.m.summary()['lessons'],1);self.assertEqual(self.m.summary()['episodes'],0)
    def test_request_id_path_traversal_is_ignored(self):
        mailbox=self.root/'ids';mailbox.mkdir();(mailbox/'status.json').write_text(json.dumps(state()))
        (mailbox/'request.json').write_text(json.dumps(req('../../unexpected')));r=KitRecorder(mailbox,self.m);r.poll(100)
        self.assertEqual(r.pending,{});self.assertEqual(self.m.summary()['episodes'],0)
    def test_read_only_recorder_never_writes_game_directory(self):
        mailbox=self.root/'mailbox';mailbox.mkdir();p=mailbox/'status.json';p.write_text(json.dumps(state()));before={x.name:x.read_bytes() for x in mailbox.iterdir()}
        r=KitRecorder(mailbox,self.m);r.poll(100);r.snapshot()
        self.assertEqual(before,{x.name:x.read_bytes() for x in mailbox.iterdir()})

if __name__=='__main__':unittest.main()
