import copy,unittest
from native_wheat_preflight_reconcile import prove,record,HOST_CLASS_SHA256,REASON

class NativeWheatRejectionTests(unittest.TestCase):
    def fixtures(self):
        cells=[[0,63,0]];inventory=[{'slot':0,'item':'minecraft:wheat','count':3},{'slot':1,'item':'minecraft:wheat_seeds','count':8}]
        book={'world_session':'w','cells':cells,'pending':{'operation':'planter_wheat_batch','soils':cells},'complete':False,'inventory_credit':0,'inventory_before':{'minecraft:wheat':3,'minecraft:wheat_seeds':8}}
        reply={'id':'r','phase':'error','detail':REASON,'world_session':'w','time':1}
        event={'request_id':'r','world_session':'w','op':'planter_wheat_batch','phase':'error','detail':REASON,'params':{'soils':cells},'inventory_delta':{},'position_before':[0,64,0],'position_after':[0,64,0],'health_before':20,'health_after':20,'revision_after':5}
        frames=[{'time':n,'connected':True,'world_session':'w','phase':'done','health':20,'manual_movement':False,'planter_active':False,'planter_material_batch':{},'navigating':False,'guard_busy':False,'control_revision':5,'scan_cells_read':2,'scan_total_cells':2,'inventory':copy.deepcopy(inventory),'blocks':[{'pos':[0,63,0],'state':'Block{minecraft:farmland}[moisture=7]'},{'pos':[0,64,0],'state':'Block{minecraft:wheat}[age=7]'}]}for n in (2,3)]
        return book,reply,event,frames
    def test_exact_rejection_is_retained_without_claiming_harvest_or_completion(self):
        book,reply,event,frames=self.fixtures();before=copy.deepcopy(book)
        proof=prove(book,reply,event,frames,HOST_CLASS_SHA256);updated=record(book,proof)
        self.assertEqual(book,before);self.assertIsNone(updated['pending']);self.assertFalse(updated['complete'])
        self.assertEqual(0,updated['inventory_credit']);self.assertEqual(before['pending'],proof['original_pending'])
    def test_unknown_wrong_host_and_mismatched_original_never_resolve(self):
        for change in ('host','reply','event','soils','delta'):
            book,reply,event,frames=self.fixtures();host=HOST_CLASS_SHA256
            if change=='host':host='other'
            elif change=='reply':reply['id']='other'
            elif change=='event':event['op']='mine_block'
            elif change=='soils':event['params']['soils']=[]
            else:event['inventory_delta']={'minecraft:wheat':1}
            with self.assertRaises(RuntimeError):prove(book,reply,event,frames,host)
    def test_partial_changed_active_or_old_field_witness_never_resolves(self):
        for change in ('partial','inventory','crop','active','world','time','revision','manual'):
            book,reply,event,frames=self.fixtures();f=frames[1]
            if change=='partial':f['scan_cells_read']=1
            elif change=='inventory':f['inventory'][0]['count']=4
            elif change=='crop':f['blocks'][1]['state']='Block{minecraft:wheat}[age=0]'
            elif change=='active':f['planter_active']=True
            elif change=='world':f['world_session']='old'
            elif change=='time':f['time']=2
            elif change=='revision':f['control_revision']=6
            else:f['manual_movement']=True
            with self.assertRaises(RuntimeError):prove(book,reply,event,frames,HOST_CLASS_SHA256)
    def test_changed_pending_journal_cannot_be_overwritten(self):
        book,reply,event,frames=self.fixtures();proof=prove(book,reply,event,frames,HOST_CLASS_SHA256)
        book['pending']['soils']=[[1,63,0]]
        with self.assertRaises(RuntimeError):record(book,proof)

if __name__=='__main__':unittest.main()
