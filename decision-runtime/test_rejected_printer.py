import json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from village_queue import VillageQueue
from rejected_printer import conserved_server_rejection

def case():
    inv=[{'slot':0,'item':'minecraft:lectern','count':2}];target=[1,2,3]
    command={'id':'print-002','action':'native','op':'professional_print','params':{'seconds':20}}
    intent={'action':'native','op':'projection_batch_set','params':{'placement_key':'k','positions':[target]}}
    prior={'phase':'done','world_session':'w','control_revision':7,'inventory':inv}
    printer={'enabled':False,'owned':False,'waiting_for_server':False,'server_confirmed':0,'fast_proposals':0,'complex_proposals':1,
        'last_proposal':{'interaction_seen':True,'server_update_seen':True,'interaction_matches_proposal':True,'target':'1, 2, 3','server_update_state':'Block{minecraft:air}','sent_tick':1,'server_update_tick':6}}
    detail='服务器未确认上一格，已停止放置；请检查网络或权限'
    reply={'id':'native','phase':'error','detail':detail,'server_confirmed':False,'outcome_pending':True,'world_session':'w','bounded_targets':[target],'bounded_target_count':1,'placement_key':'k','inventory':inv,'professional_printer':printer,'control_revision':8}
    event={'request_id':'native','op':'professional_print','phase':'error','detail':detail,'world_session':'w','inventory_delta':{},'health_before':20,'health_after':20,'revision_before':7,'revision_after':8,'params':{'task_session':'t'}}
    state={'world_session':'w','last_request':'native','inventory':inv,'professional_printer':deepcopy(printer),'projection_batch':{'active':True,'count':1,'placement_key':'k'},'health':20,'screen':'','control_revision':8,'movement_keys':{'forward':False}}
    return command,reply,intent,prior,event,state

class RejectedPrinterTests(unittest.TestCase):
    def test_only_explicit_negative_server_update_with_conserved_materials_matches(self):
        self.assertTrue(conserved_server_rejection(*case(),'w','t'))
        for change in ('no_update','earlier_update','wrong_state','debit','event_debit','waiting','world','revision','mask','multi'):
            args=list(deepcopy(case()));command,reply,intent,prior,event,state=args
            if change=='no_update':reply['professional_printer']['last_proposal']['server_update_seen']=False
            if change=='earlier_update':reply['professional_printer']['last_proposal']['server_update_tick']=0
            if change=='wrong_state':reply['professional_printer']['last_proposal']['server_update_state']='Block{minecraft:lectern}'
            if change=='debit':state['inventory']=[{'slot':0,'item':'minecraft:lectern','count':1}]
            if change=='event_debit':event['inventory_delta']={'minecraft:lectern':-1}
            if change=='waiting':state['professional_printer']['waiting_for_server']=True
            if change=='world':state['world_session']='other'
            if change=='revision':state['control_revision']=9
            if change=='mask':intent['params']['positions']=[[4,2,3]]
            if change=='multi':reply['bounded_targets'].append([4,2,3])
            with self.subTest(change=change):self.assertFalse(conserved_server_rejection(*args,'w','t'))

    def test_reconciliation_only_reads_and_clears_mask_never_replays_print(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);out=root/'owner';out.mkdir();(out/'control').mkdir();command,reply,intent,prior,event,state=case()
            q=VillageQueue.__new__(VillageQueue);q.out=out;q.world='w';q.lease={'job_session':'t'};q.status=lambda **kw:state
            (out/'command.json').write_text(json.dumps(command))
            for name,i,r in [('print-001',intent,prior),('print-002',command,reply)]:
                d=out/name;d.mkdir();(d/'intent.json').write_text(json.dumps(i));(d/'result.json').write_text(json.dumps(r))
            (out/'control/events.jsonl').write_text(json.dumps(event)+'\n');original=(out/'print-002/result.json').read_bytes();calls=[]
            def native(op,**params):
                calls.append(op)
                if op=='scan':return {'world_session':'w','scan_cells_read':1,'scan_total_cells':1,'blocks':[],
                    'scan_predictions':{'complete':True,'pending_count':0,'pending_positions':[]}}
                return {'id':'cleared','phase':'done'}
            q.native=native;result=q.observe_rejected_printer();self.assertFalse(result['pending']);self.assertEqual(0,result['old_goal_credit'])
            self.assertEqual(['scan','projection_batch_clear'],calls);self.assertEqual(original,(out/'print-002/result.json').read_bytes())

    def test_one_closed_failed_travel_record_is_not_an_active_placement_queue(self):
        args=list(case());args[-1]['professional_printer'].update(travel_pending=1,failure=args[1]['detail'])
        self.assertTrue(conserved_server_rejection(*args,'w','t'))
        args[-1]['professional_printer']['travel_pending']=2
        self.assertFalse(conserved_server_rejection(*args,'w','t'))
        args[-1]['professional_printer'].update(travel_pending=1,failure='')
        self.assertFalse(conserved_server_rejection(*args,'w','t'))

    def test_outstanding_prediction_retains_mask_and_blocks_new_print(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);out=root/'owner';out.mkdir();(out/'control').mkdir();command,reply,intent,prior,event,state=case()
            q=VillageQueue.__new__(VillageQueue);q.out=out;q.world='w';q.lease={'job_session':'t'};q.closing_menu=None;q.status=lambda **kw:state
            (out/'command.json').write_text(json.dumps(command))
            for name,i,r in [('print-001',intent,prior),('print-002',command,reply)]:
                d=out/name;d.mkdir();(d/'intent.json').write_text(json.dumps(i));(d/'result.json').write_text(json.dumps(r))
            (out/'control/events.jsonl').write_text(json.dumps(event)+'\n');calls=[]
            def native(op,**params):
                calls.append(op);return {'world_session':'w','scan_cells_read':1,'scan_total_cells':1,'blocks':[],
                    'scan_predictions':{'complete':True,'pending_count':1,'pending_positions':[[1,2,3]]}}
            q.native=native
            with self.assertRaises(RuntimeError):q.observe_rejected_printer()
            self.assertEqual(['scan'],calls);self.assertTrue(json.loads((root/'retained-printer-outcome.json').read_text())['pending'])
            with self.assertRaisesRegex(RuntimeError,'observation remains pending'):q._send('native',op='professional_print',params={})

if __name__=='__main__':unittest.main()
