import copy
import unittest
from name_tag_anvil import bind, preview


class NameTagAnvilTests(unittest.TestCase):
    def case(self):
        lease = dict(id='owner', kind='materials', job_session='task', world_session='w')
        empty = dict(item='minecraft:air', count=0)
        state = dict(connected=True, health=20, manual_movement=False, world_session='w',
                     control_revision=4, pos=[1, 2, 3], last_request='open', movement_keys={},
                     supervision_lease=lease, screen='AnvilScreen',
                     inventory=[dict(slot=0, item='minecraft:name_tag', count=1)],
                     menu=dict(type='AnvilMenu', id=7, cursor=empty, slots=[empty]*3))
        reply = dict(phase='done', id='open', world_session='w', control_revision=4,
                     pos=[1, 2, 3], supervision_lease=lease, screen='', menu=dict(id=0, type='InventoryMenu'))
        command = dict(id='command', action='native', op='interact', params=dict(
            pos=[4, 2, 3], face='up', expected_state='Block{minecraft:anvil}[facing=south]'))
        return state, reply, command

    def test_async_window_after_known_interaction_is_owned_without_reopening(self):
        s, r, c = self.case()
        self.assertEqual(bind(s, r, c, [4, 2, 3])['id'], 7)

    def test_changed_control_request_position_or_input_refuses_adoption(self):
        for mutation in ({'manual_movement': True}, {'control_revision': 5},
                         {'last_request': 'other'}, {'pos': [2, 2, 3]}, {'health': 19}):
            s, r, c = self.case(); s.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): bind(s, r, c, [4, 2, 3])
        s, r, c = self.case(); s['menu']['slots'][0] = dict(item='minecraft:name_tag', count=1)
        with self.assertRaises(ValueError): bind(s, r, c, [4, 2, 3])

    def test_preview_rejects_extra_input_expensive_output_and_foreign_window(self):
        tag = dict(item='minecraft:name_tag', count=1)
        s = dict(experience_level=24, menu=dict(type='AnvilMenu', id=7, cursor=dict(count=0),
                 slots=[tag, dict(count=0), tag], anvil_cost=1, anvil_result_may_pickup=True))
        self.assertEqual(preview(s, 7)[1], 1)
        for change in ({'anvil_cost': 2}, {'id': 8}, {'anvil_result_may_pickup': False}):
            bad = copy.deepcopy(s); bad['menu'].update(change)
            with self.assertRaises(ValueError): preview(bad, 7)

class NameTagClickTests(unittest.TestCase):
    def test_queue_allows_only_exact_tag_input_and_witnessed_output(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import Mock
        from village_queue import VillageQueue
        from name_tag_anvil import permitted_click
        s,_,_=NameTagAnvilTests().case();s.update(interface_paused=False,inventory_interface_paused=False)
        empty=dict(item='minecraft:air',count=0);tag=dict(item='minecraft:name_tag',count=1)
        s['menu']['slots']=[empty,empty,empty,tag];s['menu']['material_owned']=False
        cert=dict(type='AnvilMenu',id=7,world_session='w',task_session='task',lease_id='owner',control_revision=4,purpose='name_tag_rename',source_request='open')
        params=dict(menu_id=7,slot=3,kind='quick_move',button=0,expected_item='minecraft:name_tag',expected_count=1,expected_cursor='minecraft:air',expected_cursor_count=0)
        with tempfile.TemporaryDirectory() as d:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(d)/'owner';q.out.mkdir();q.world='w';q.lease=s['supervision_lease'];q.closing_menu=None;q.status=lambda **kw:s;q._dispatch=Mock(return_value={'phase':'done'})
            (q.out/'owned-material-menu.json').write_text(json.dumps(cert))
            q._send('native',op='slot_click',params=params);self.assertEqual(q._dispatch.call_count,1)
            for change in ({'slot':0},{'kind':'pickup'},{'expected_count':2},{'menu_id':8}):
                with self.assertRaisesRegex(RuntimeError,'must finish or close'):q._send('native',op='slot_click',params={**params,**change})
            with self.assertRaisesRegex(RuntimeError,'must finish or close'):q._send('native',op='navigate',params={'target':[1,2,3]})
        s['menu'].update(slots=[tag,empty,tag,empty],anvil_cost=1,anvil_result_may_pickup=True);s['experience_level']=24;p={**params,'slot':2}
        self.assertFalse(permitted_click(s,cert,p))
        cert['ui_name_witness']=dict(text='Kit Iron Farm',menu_id=7,source_request='open')
        self.assertTrue(permitted_click(s,cert,p));s['menu']['anvil_cost']=2;self.assertFalse(permitted_click(s,cert,p))


if __name__ == '__main__': unittest.main()
