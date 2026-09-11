import json,tempfile,time,unittest,threading
from pathlib import Path
from unittest.mock import patch
from core import Detector,Store,route,completed,local_advice
from companion import relevant,LogCursor,worker,DEFAULT,FileEvents

def snapshot(active=False,reason='',progress=10,t=100,pos=None,screen='',health=20):
    return {'time':t*1000,'connected':True,'server':'test.invalid','dimension':'minecraft:overworld','pos':pos or [10,64,10],'health':health,'screen':screen,'build_job':{'active':active,'phase':'打印中' if active else '已停止','reason':reason,'matched':progress}}

class DetectorTests(unittest.TestCase):
    def test_boot_does_not_replay_old_stopped_task(self):
        d=Detector();self.assertEqual([],d.observe(snapshot(reason='没有路线'),100));self.assertEqual([],d.observe(snapshot(reason='没有路线',t=101),101))
    def test_terminal_failure_creates_one_event(self):
        d=Detector();d.observe(snapshot(True),100);e=d.observe(snapshot(reason='找不到路线',t=101),101)
        self.assertEqual('needs_help',e[0]['kind']);self.assertEqual('spark',route(e[0]));self.assertEqual([],d.observe(snapshot(reason='找不到路线',t=102),102))
    def test_material_shortage_is_local(self):
        d=Detector();d.observe(snapshot(True),100);e=d.observe(snapshot(reason='待补材料：石英 ×5',t=101),101)[0]
        self.assertEqual('local',route(e));self.assertIn('补料',local_advice(e))
    def test_missing_material_footer_does_not_hide_route_failure(self):
        self.assertEqual('spark',route({'kind':'needs_help','reason':'找不到可通行路线。待补材料：石英 ×5'}))
    def test_manual_stop_never_calls_models(self):
        for reason in ['工具箱停止全部','手动移动接管','界面紧急停止','本地脚本停止']:
            d=Detector();d.observe(snapshot(True),100);e=d.observe(snapshot(reason=reason,t=101),101)[0]
            self.assertEqual('manual_takeover',e['kind']);self.assertEqual('local',route(e))
    def test_no_completion_from_negated_word(self):
        self.assertFalse(completed('未完成：路线错误'));self.assertFalse(completed('无法完成'));self.assertTrue(completed('当前投影范围全部匹配'))
    def test_stationary_printing_progress_is_not_stuck(self):
        d=Detector(10);d.observe(snapshot(True),100)
        self.assertEqual([],d.observe(snapshot(True,progress=11,t=109),109));self.assertEqual([],d.observe(snapshot(True,progress=12,t=118),118))
    def test_motion_or_menu_does_not_trip_stall(self):
        d=Detector(10);d.observe(snapshot(True),100);self.assertEqual([],d.observe(snapshot(True,t=110,pos=[11,64,10]),110))
        self.assertEqual([],d.observe(snapshot(True,t=140,screen='ChestScreen'),140));self.assertEqual([],d.observe(snapshot(True,t=145),145))
    def test_stall_has_stable_dedup_key(self):
        d=Detector(10);d.observe(snapshot(True),100);a=d.observe(snapshot(True,t=111),111)[0];b=d.observe(snapshot(True,t=112),112)[0]
        self.assertEqual(a['fingerprint'],b['fingerprint'])
    def test_same_failure_on_restart_does_not_cost_again(self):
        results=[]
        for t in [100,200]:
            d=Detector();d.observe(snapshot(True,t=t),t);results.append(d.observe(snapshot(reason='相同故障',t=t+1),t+1)[0])
        self.assertEqual(results[0]['fingerprint'],results[1]['fingerprint'])
    def test_disconnect_invalidates_old_world(self):
        d=Detector();d.observe(snapshot(True),100);e=d.observe({'connected':False,'time':101000},101)
        self.assertEqual('disconnected',e[0]['kind']);self.assertEqual('local',route(e[0]))
    def test_danger_is_local_not_a_seven_second_model_wait(self):
        d=Detector();d.observe(snapshot(True),100);e=d.observe(snapshot(True,health=5,t=101),101)
        self.assertEqual('danger',e[0]['kind']);self.assertEqual('local',route(e[0]))

class StoreTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'q.db')
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def test_unique_incident_is_queued_once(self):
        d=Detector(1);d.observe(snapshot(True),100);a=d.observe(snapshot(True,t=102),102)[0]
        self.assertTrue(self.store.put(a));self.assertFalse(self.store.put(a));self.assertEqual(a['id'],self.store.next()[0]['id'])
    def test_budget_reservation_counts_failed_and_inflight_calls(self):
        self.assertTrue(self.store.reserve('spark','a',2,10000));self.assertTrue(self.store.reserve('spark','b',2,10001));self.assertFalse(self.store.reserve('spark','c',2,10002))
        self.assertTrue(self.store.reserve('spark','d',2,14000))
    def test_restart_does_not_resubmit_uncertain_model_request(self):
        d=Detector(1);d.observe(snapshot(True),100);e=d.observe(snapshot(True,t=102),102)[0];self.store.put(e);self.store.processing(e);self.store.recover()
        self.assertIsNone(self.store.next());self.assertEqual({'needs_attention':1},self.store.summary()['events'])
    def test_pause_survives_process_restart(self):
        self.store.set('paused',True);other=Store(Path(self.tmp.name)/'q.db');self.assertTrue(other.setting('paused'));other.db.close()

class AdapterTests(unittest.TestCase):
    def test_log_cursor_only_reads_new_bytes_and_survives_rotation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'borer.log';p.write_text('old failure\n');c=LogCursor(p);self.assertEqual([],c.read());p.write_text('old failure\nnew line\n');self.assertEqual(['new line'],c.read());self.assertEqual([],c.read())
            p.unlink();p.write_text('rotated old\n');self.assertEqual([],c.read())
    def test_old_world_manual_override_or_stale_heartbeat_cancels_model_escalation(self):
        now=time.time();s=snapshot(reason='no route',t=now);e={'kind':'needs_help','module':'builder','snapshot':s}
        self.assertTrue(relevant(e,s));self.assertFalse(relevant(e,snapshot(reason='手动接管',t=now)))
        self.assertFalse(relevant(e,snapshot(reason='no route',t=now-20)));s['dimension']='minecraft:the_nether';self.assertFalse(relevant(e,{**s,'dimension':'minecraft:overworld'}))
    def test_rule_event_uses_zero_models(self):
        self.run_worker(False)
    def test_explicit_unknown_event_routes_spark_then_main(self):
        self.run_worker(True)
    def test_early_protocol_notifications_are_not_lost(self):
        from agents import CodexWorker
        c=CodexWorker('/unused','/tmp','/tmp');c.send=lambda _:None
        c.incoming.put({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'ok'}}})
        c.incoming.put({'id':1,'result':{'ok':True}})
        self.assertTrue(c.rpc('turn/start',{})['ok'])
        self.assertEqual('item/completed',c.message(time.monotonic()+1)['method'])
    def test_model_failure_opens_circuit_and_does_not_spin(self):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);calls=[]
            class Broken:
                def __init__(self,*a,**kw):pass
                def analyze(self,*a):calls.append(1);raise RuntimeError('quota exhausted')
                def close(self):pass
            db=Store(state/'events.sqlite3')
            for i in range(2):db.put({'id':str(i),'created':time.time(),'fingerprint':str(i),'kind':'needs_help','module':'builder','reason':'unknown','snapshot':{},'demo':True})
            db.db.close();stop=threading.Event()
            with patch('companion.CodexWorker',Broken):
                t=threading.Thread(target=worker,args=(state,DEFAULT,stop));t.start();deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    db=Store(state/'events.sqlite3');done=db.summary()['events'].get('needs_attention',0);db.db.close()
                    if done==2:break
                    time.sleep(.03)
                stop.set();t.join(3)
            self.assertEqual(2,done);self.assertEqual(1,len(calls))
    def run_worker(self,model_case):
        with tempfile.TemporaryDirectory() as d:
            state=Path(d);cfg={**DEFAULT,'main_backend':'cli','status_file':str(state/'status.json')};calls=[]
            class FakeWorker:
                def __init__(self,*a,**kw):pass
                def analyze(self,e,model,effort):calls.append(model);return {'answer':{'cause':'cause','next_step':'inspect','confidence':.8,'needs_main_agent':len(calls)==1}}
                def close(self):pass
            e={'id':'a','created':time.time(),'fingerprint':'f','kind':'needs_help' if model_case else 'completed','module':'builder','reason':'unknown failure','snapshot':{},'demo':True}
            store=Store(state/'events.sqlite3');store.put(e);store.db.close();stop=threading.Event()
            with patch('companion.CodexWorker',FakeWorker):
                th=threading.Thread(target=worker,args=(state,cfg,stop));th.start();deadline=time.monotonic()+3
                while not (state/'decisions.jsonl').exists() and time.monotonic()<deadline:time.sleep(.02)
                stop.set();th.join(3)
            self.assertTrue((state/'decisions.jsonl').exists());self.assertEqual(2 if model_case else 0,len(calls))

if __name__=='__main__':unittest.main()
