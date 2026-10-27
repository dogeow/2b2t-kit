import copy,unittest
from unittest.mock import patch
from printer_partial_interval import prove,HOST_HASHES,REASON

class PartialIntervalTests(unittest.TestCase):
    def grass_fixture(self):
        parts=copy.deepcopy(self.fixture());row=parts[2]['mismatches'][-1]
        row.update(actual='Block{minecraft:short_grass}',block_entity=False,fluid=False,neighbors_loaded=True,adjacent_fluid=False)
        for f in parts[3]:f['blocks']=copy.deepcopy(f['blocks'])+[{'pos':row['pos'],'state':row['actual']}]
        return parts
    def test_unchanged_unattempted_grass_does_not_hide_an_unacknowledged_input(self):
        with patch('printer_partial_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':88}):
            proof=prove(*self.grass_fixture(),HOST_HASHES)
            self.assertEqual([[3,64,2]],proof['remaining_unchanged_short_grass'])
            self.assertFalse(proof['original_mask_complete'])
            parts=self.grass_fixture();parts[1]['professional_printer']['fast_proposals']=3
            with self.assertRaises(RuntimeError):prove(*parts,HOST_HASHES)
    def test_changed_or_replaced_grass_and_incomplete_original_observation_are_rejected(self):
        for state in('Block{minecraft:air}','Block{minecraft:dark_oak_planks}'):
            parts=self.grass_fixture();parts[3][0]['blocks'][-1]['state']=state
            with patch('printer_partial_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':88}),self.assertRaises(RuntimeError):prove(*parts,HOST_HASHES)
        parts=self.grass_fixture();parts[2]['mismatches'][-1].pop('neighbors_loaded')
        with patch('printer_partial_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':88}),self.assertRaises(RuntimeError):prove(*parts,HOST_HASHES)
    def fixture(self):
        item='minecraft:dark_oak_planks';state='Block{'+item+'}';positions=[[1,64,2],[2,64,2],[3,64,2]]
        pending={'positions':positions,'item':item,'before':{item:90}}
        p={'fast_proposals':2,'complex_proposals':0,'server_confirmed':2,'enabled':False,'owned':False,'waiting_for_server':False,'travel_pending':0,'failure':'','last_proposal':{'ack_final':True}}
        r={'id':'r','phase':'waiting','detail':REASON,'server_confirmed':False,'outcome_pending':True,'world_session':'w','placement_key':'k','bounded_targets':positions,'bounded_target_count':3,'time':100,'professional_printer':p}
        owner={'id':'l','kind':'materials','job_session':'j','world_session':'w'};r['supervision_lease']=owner
        before={'placement_key':'k','mismatches':[{'pos':v,'kind':'missing','expected':state,'actual':'Block{minecraft:air}'}for v in positions]}
        f={'world_session':'w','connected':True,'health':20,'manual_movement':False,'screen':'','professional_printer':p,'supervision_lease':owner,'projection_selection':{'key':'k'},'menu':{'cursor':{'count':0}},'scan_cells_read':3,'scan_total_cells':3,'blocks':[{'pos':v,'state':state}for v in positions[:2]]}
        return pending,r,before,[{**f,'time':101},{**f,'time':102}]
    def test_partial_mask_is_never_reported_as_whole_completion_or_replayed(self):
        parts=self.fixture()
        with patch('printer_partial_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':88}):proof=prove(*parts,HOST_HASHES)
        self.assertFalse(proof['original_mask_complete']);self.assertFalse(proof['original_request_replayed']);self.assertEqual([[3,64,2]],proof['remaining_current_missing'])
    def test_any_unacknowledged_or_complex_proposal_or_changed_inventory_stays_unresolved(self):
        for changes in({'fast_proposals':3},{'server_confirmed':1},{'complex_proposals':1},{'waiting_for_server':True}):
            parts=copy.deepcopy(self.fixture());parts[1]['professional_printer'].update(changes)
            with patch('printer_partial_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':88}),self.assertRaises(RuntimeError):prove(*parts,HOST_HASHES)
        with patch('printer_partial_interval.inventory_counts',return_value={'minecraft:dark_oak_planks':87}),self.assertRaises(RuntimeError):prove(*self.fixture(),HOST_HASHES)
