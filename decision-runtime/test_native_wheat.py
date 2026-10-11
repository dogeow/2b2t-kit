import json
import tempfile
import unittest
from pathlib import Path
from collections import Counter
from unittest.mock import Mock, patch
from potato_farm import FarmWait
from material_jobs.native_wheat import run, validate_receipt, unresolved, leave_field

CELLS = [[0,63,0],[1,63,0]]
COUNTS = Counter({'minecraft:wheat':5,'minecraft:wheat_seeds':8})


def receipt():
    return {'phase':'done','world_session':'world','time':10,
            'planter_material_batch':{'protocol':1,'total':2,'grain_before':3,
                'harvest_sent':2,'removed_confirmed':2,'plant_sent':2,'replanted_confirmed':2,
                'cells_server_confirmed':True,'crop_positions':[[0,64,0],[1,64,0]]}}


class NativeWheatTests(unittest.TestCase):
    def test_crop_exit_centers_once_on_observed_farmland_without_resource_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Mock(world='world');c.status.return_value={'pos':[.787,63.9375,.994]}
            c.checked.return_value={'phase':'done'}
            frame={'blocks':[{'pos':[0,63,0],'state':'Block{minecraft:farmland}[moisture=7]',
                               'fluid':False,'block_entity':False},
                              {'pos':[0,64,0],'state':'Block{minecraft:wheat}[age=2]'}]}
            with patch('material_jobs.native_wheat.inventory_counts',return_value=COUNTS), \
                    patch('material_jobs.navigation.settled_state',return_value={'pos':[.5,63.9375,.5]}):
                leave_field(c,{'cells':CELLS},frame,tmp,lambda:None)
            c.checked.assert_called_once_with('walk',target=[.5,63.9375,.5],arrival=.15,seconds=12)
            proof=json.loads((Path(tmp)/'farmland-exit.json').read_text())
            self.assertFalse(proof['pending']);self.assertEqual(proof['inventory_before'],proof['inventory_after'])
            c.checked.reset_mock();frame['blocks'][0]['fluid']=True
            with self.assertRaises(FarmWait):leave_field(c,{'cells':CELLS},frame,tmp,lambda:None)
            c.checked.assert_not_called()

    def test_missing_replant_ack_or_wrong_scope_never_credits_native_ui_counts(self):
        with patch('material_jobs.native_wheat.inventory_counts', return_value=COUNTS):
            validate_receipt(receipt(), CELLS, 3, 'world')
            for key,value in [('cells_server_confirmed',False),('replanted_confirmed',1),
                              ('grain_before',0),('crop_positions',[[2,64,0],[3,64,0]])]:
                bad=receipt();bad['planter_material_batch'][key]=value
                with self.assertRaises(FarmWait):validate_receipt(bad,CELLS,3,'world')
            bad=receipt();bad['world_session']='old'
            with self.assertRaises(FarmWait):validate_receipt(bad,CELLS,3,'world')
        for counts in [Counter({'minecraft:wheat':4,'minecraft:wheat_seeds':8}),
                       Counter({'minecraft:wheat':5,'minecraft:wheat_seeds':3})]:
            with patch('material_jobs.native_wheat.inventory_counts',return_value=counts):
                with self.assertRaises(FarmWait):validate_receipt(receipt(),CELLS,3,'world')

    def test_journal_exists_before_dispatch_and_two_whole_visit_scans_complete_the_visit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);registry=root/'registry.json';registry.write_text('original')
            layout={'cells':CELLS,'scan_min':[0,63,0],'scan_max':[1,64,0]}
            c=Mock(world='world',rev=7);c.status.return_value={'kind':'before','pos':[.5,63.9375,.5]}
            frames=[{'phase':'done','world_session':'world','time':n,'scan_cells_read':4,
                     'scan_total_cells':4,'scan_start_revision':7,'scan_end_revision':7,
                     'blocks':[row for p in CELLS for row in [
                         {'pos':p,'state':'Block{minecraft:farmland}[moisture=7]','fluid':False,'block_entity':False},
                         {'pos':[p[0],64,0],'state':'Block{minecraft:wheat}[age=1]'}]]}
                    for n in [11,12]]
            def dispatch(op,**kw):
                if op=='planter_wheat_batch':
                    self.assertTrue(unresolved(registry));self.assertEqual(CELLS,kw['soils'])
                    return receipt()
                return frames.pop(0)
            c.checked.side_effect=dispatch
            with patch('material_jobs.native_wheat.inventory_counts',
                       side_effect=lambda s:Counter({'minecraft:wheat':3,'minecraft:wheat_seeds':8})
                       if s.get('kind')=='before' else COUNTS):
                result=run(c,registry,layout,CELLS,root/'visit',lambda:None)
            self.assertEqual(2,result['gained']);self.assertFalse(unresolved(registry))
            saved=json.loads((root/'visit/native-wheat-batch.json').read_text())
            self.assertEqual(2,saved['native_receipt']['planter_material_batch']['replanted_confirmed'])
            self.assertEqual(receipt(),json.loads((root/'visit/native-wheat-receipt.json').read_text()))
            self.assertEqual(['planter_wheat_batch','scan','scan'],[v.args[0]for v in c.checked.call_args_list])
            self.assertEqual('original',registry.read_text())

    def test_unknown_native_dispatch_is_retained_and_blocks_every_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);registry=root/'registry.json';registry.write_text('{}')
            c=Mock(world='world');c.checked.side_effect=RuntimeError('unknown')
            layout={'cells':CELLS}
            with patch('material_jobs.native_wheat.inventory_counts',return_value=COUNTS):
                with self.assertRaises(RuntimeError):run(c,registry,layout,CELLS,root/'first',lambda:None)
                with self.assertRaises(FarmWait):run(c,registry,layout,CELLS,root/'second',lambda:None)
            self.assertEqual(1,c.checked.call_count)


if __name__ == '__main__': unittest.main()
