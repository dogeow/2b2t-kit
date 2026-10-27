from copy import deepcopy
from pathlib import Path
import hashlib,json,tempfile,unittest
from bridged_trade_abort import observable,bound_request
from merchant_preflight_abort import DETAIL,settled


def fixture():
    params={'menu_id':24,'slot':2,'kind':'pickup','button':0,'expected_item':'minecraft:emerald','expected_count':1,
            'expected_cursor':'minecraft:air','expected_cursor_count':0,'expected_offers_fingerprint':'old','expected_trade_index':3}
    inv=[{'slot':5,'item':'minecraft:iron_ingot','count':40},{'slot':16,'item':'minecraft:emerald','count':22}]
    slots=[{'item':'minecraft:iron_ingot','count':64},{'item':'minecraft:air','count':0},{'item':'minecraft:emerald','count':1}]
    first={'id':'selected','world_session':'w','inventory':deepcopy(inv),'menu':{'id':24,'slots':deepcopy(slots)}}
    book={'world_session':'w','uuid':'villager','complete':False,'pending':{'op':'slot_click','params':deepcopy(params),'request_id':None},
          'receipts':[first],'before':{'minecraft:iron_ingot':104,'minecraft:emerald':22}}
    command={'id':'outer','action':'native','op':'slot_click','params':deepcopy(params)}
    event={'request_id':'refused','world_session':'w','op':'slot_click','phase':'error','detail':DETAIL,
           'params':dict(params,task_session='task'),'inventory_delta':{},'position_before':[1,64,2],'position_after':[1,64,2],
           'revision_before':3,'revision_after':3,'health_before':20,'health_after':20}
    selection={'request_id':'selected','world_session':'w','op':'merchant_select_trade','phase':'done','inventory_delta':{'minecraft:iron_ingot':-64},
               'params':{'task_session':'task','index':3,'menu_id':24,'expected_villager_uuid':'villager'},'revision_before':3,'revision_after':3,'health_before':20,'health_after':20}
    reply={'id':'refused','phase':'error','detail':DETAIL,'world_session':'w','pos':[1,64,2],'control_revision':3}
    state={'world_session':'w','phase':'error','last_request':'refused','control_revision':3,'pos':[1,64,2],'health':20,'inventory':deepcopy(inv),
           'connected':True,'manual_movement':False,'movement_keys':{},'supervision_lease':{'job_session':'task'},
           'menu':{'type':'MerchantMenu','material_owned':True,'id':24,'cursor':{'count':0},'slots':deepcopy(slots),
                   'merchant':{'owned':True,'owner_task':'task','villager_uuid':'villager'}}}
    return book,command,event,selection,reply,state


class BridgedAbortTests(unittest.TestCase):
    def test_only_exact_unissued_output_with_returnable_payments_is_observable(self):
        self.assertTrue(observable(*fixture(),'w','task'))
        for change in ('debit','delta','selection','cursor','unknown','request','command'):
            book,command,event,selection,reply,state=deepcopy(fixture())
            if change=='debit':state['inventory'][0]['count']-=3
            elif change=='delta':event['inventory_delta']={'minecraft:iron_ingot':-3}
            elif change=='selection':selection['inventory_delta']={'minecraft:iron_ingot':-63}
            elif change=='cursor':state['menu']['cursor']['count']=1
            elif change=='unknown':reply['outcome_pending']=True
            elif change=='request':book['pending']['request_id']='other'
            elif change=='command':command['params']['expected_count']=2
            with self.subTest(change=change):self.assertFalse(observable(book,command,event,selection,reply,state,'w','task'))
    def test_null_legacy_id_requires_immutable_native_binding_and_zero_credit_close_proof(self):
        with tempfile.TemporaryDirectory()as d:
            path=Path(d)/'one-trade.json';book,command,event,selection,reply,state=fixture();path.write_text(json.dumps(book))
            binding={'journal':str(path.resolve()),'original_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'world_session':'w','task_session':'task',
                     'command':command,'refusal':event,'selection':selection,'native_reply':reply,'observed_state':state}
            (path.parent/'native-request-binding.json').write_text(json.dumps(binding));self.assertEqual(bound_request(path,book),'refused')
            proof={'abort_settled':True,'purchase_credit':0,'original_sha256':binding['original_sha256'],'refusal':event,
                   'close_receipt':{'id':'close','phase':'done','world_session':'w'},'close_event':{'request_id':'close','op':'close_menu','phase':'done','world_session':'w','params':{'task_session':'task'}},
                   'world_session':'w','uuid':'villager','settled_frames':[{'time':i,'world_session':'w','health':20,'screen':'','cursor_count':0,'inventory':book['before']}for i in [1,2]]}
            (path.parent/'prepurchase-abort.json').write_text(json.dumps(proof));self.assertTrue(settled(path));self.assertFalse(json.loads(path.read_text())['complete'])
            path.write_text(path.read_text()+' ');self.assertIsNone(bound_request(path,book));self.assertFalse(settled(path))


if __name__=='__main__':unittest.main()
