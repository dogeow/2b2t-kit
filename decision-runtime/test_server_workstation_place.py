import unittest,itertools
from types import SimpleNamespace
from unittest.mock import patch
from server_workstation_place import place_lectern

P=[1,2,3];STATE='Block{minecraft:lectern}[facing=north,has_book=false,powered=false]'
class Builder:
    def __init__(self):
        self.q=SimpleNamespace(world='w');self.book={'placed':[]};self.calls=[];self.count=2;self.clock=0;self.mask=False
        self.model={'model_schema':1,'loaded_chunks_verified':True,'loaded_server_chunks_verified':True,'placement_key':'k','expected':[{'pos':P,'item':'minecraft:lectern','state':STATE}]}
        self.reply={'id':'print','phase':'done','world_session':'w','server_confirmed':True,'outcome_pending':False,'confirmation_scope':'current_bounded_mask_distinct_exact_final_server_updates','full_projection_confirmed':False,'bounded_target_count':1,'bounded_targets':[P],'placement_key':'k'}
        self.keep_count=False
    def save(self):pass
    def check(self):
        self.clock+=1
        return {'time':self.clock,'inventory':[{'slot':0,'item':'minecraft:lectern','count':self.count}],
                'professional_printer':{'enabled':False},'projection_batch':{'active':self.mask}}
    def scan(self,a,b):return {'time':self.clock},{tuple(P):{'state':STATE}}
    def n(self,op,**kw):
        self.calls.append((op,kw))
        if op=='projection_model':return {'projection_model':self.model}
        if op=='projection_batch_set':self.mask=True
        if op=='projection_batch_clear':self.mask=False
        if op=='professional_print':
            if not self.keep_count:self.count-=1
            return self.reply
        return {'phase':'done'}

class ServerWorkstationTests(unittest.TestCase):
    def test_exact_single_mask_acknowledgement_and_two_frames_complete(self):
        b=Builder()
        with patch('server_workstation_place.time.sleep'):place_lectern(b,P,{STATE})
        self.assertEqual(1,b.count);self.assertFalse(b.mask);self.assertTrue(b.book['placed'][0]['server_confirmed'])
        self.assertEqual(2,len(b.book['placed'][0]['times']));self.assertNotIn('interact',[v[0]for v in b.calls])
    def test_wrong_or_unloaded_projection_sends_no_placement(self):
        for change in ('position','state','server_chunks','scope'):
            b=Builder()
            if change=='position':b.model['expected'][0]['pos']=[8,2,3]
            if change=='state':b.model['expected'][0]['state']='Block{minecraft:air}'
            if change=='server_chunks':b.model['loaded_server_chunks_verified']=False
            if change=='scope':b.mask=True
            with self.subTest(change=change),self.assertRaises(RuntimeError):place_lectern(b,P,{STATE})
            self.assertNotIn('professional_print',[v[0]for v in b.calls])
    def test_done_without_ack_or_wrong_mask_is_retained_never_retried(self):
        for change in ('ack','target','key'):
            b=Builder()
            if change=='ack':b.reply['server_confirmed']=False
            if change=='target':b.reply['bounded_targets']=[[8,2,3]]
            if change=='key':b.reply['placement_key']='other'
            with self.subTest(change=change),self.assertRaises(RuntimeError):place_lectern(b,P,{STATE})
            self.assertTrue(b.mask);self.assertTrue(b.book['verified_workstation_placements'][0]['pending']);self.assertFalse(b.book['placed'])
            self.assertEqual(1,[v[0]for v in b.calls].count('professional_print'))
    def test_ack_without_inventory_debit_does_not_clear_or_credit(self):
        b=Builder();b.keep_count=True
        with patch('server_workstation_place.time.monotonic',side_effect=itertools.count()),patch('server_workstation_place.time.sleep'),self.assertRaises(RuntimeError):place_lectern(b,P,{STATE})
        self.assertTrue(b.mask);self.assertFalse(b.book['placed'])

if __name__=='__main__':unittest.main()
