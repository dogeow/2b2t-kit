import unittest
from unittest.mock import Mock, patch
from librarian_public_quote import open_when_reachable


class PublicQuoteTests(unittest.TestCase):
    def setup_case(self):
        room = Mock(uid='resident')
        room.bounds.return_value = ([0, 0, 0], [1, 3, 4])
        actor = {'uuid': 'resident', 'villager': {'profession': 'minecraft:librarian'},
                 'bounds': {'min': [0, 64, 1], 'max': [1, 66, 2]}}
        room.actor.return_value = actor
        builder = Mock(book={})
        builder.check.return_value = {'pos': [.5, 64, .5]}
        builder.scan.return_value = ({}, {})
        reply = {'time': 100, 'menu': {'merchant': {'villager_uuid': 'resident'}}}
        builder.q.send.return_value = reply
        builder.q.observe_merchant_reach_refusal.return_value = {'id': 'observation'}
        return builder, room, reply

    def test_one_reachable_open_returns_exact_reply(self):
        b, room, reply = self.setup_case()
        self.assertIs(reply, open_when_reachable(b, room, lambda: True))
        self.assertEqual(1, b.q.send.call_count)
        b.q.observe_merchant_reach_refusal.assert_not_called()

    def test_sleeping_or_distant_resident_sends_no_interaction(self):
        for sleeping in (True, False):
            b, room, _ = self.setup_case()
            b.check.return_value = {'pos': [.5, 64, -10]}
            with self.subTest(sleeping=sleeping), patch('librarian_public_quote.time.monotonic', side_effect=[0, .1, 1]), patch('librarian_public_quote.time.sleep'):
                self.assertIsNone(open_when_reachable(b, room, lambda: not sleeping, seconds=.5))
            b.q.send.assert_not_called()

    def test_known_refusal_has_bounded_attempts(self):
        b, room, _ = self.setup_case()
        b.q.send.side_effect = RuntimeError('Entity out of reach')
        with patch('librarian_public_quote.time.sleep'):
            self.assertIsNone(open_when_reachable(b, room, lambda: True))
        self.assertEqual(2, b.q.send.call_count)
        self.assertEqual(2, b.q.observe_merchant_reach_refusal.call_count)

    def test_unknown_outcome_remains_retained_without_retry(self):
        b, room, _ = self.setup_case()
        b.q.send.side_effect = RuntimeError('Interaction uncertain')
        b.q.observe_merchant_reach_refusal.side_effect = RuntimeError('Not a proved refusal')
        with self.assertRaisesRegex(RuntimeError, 'Not a proved refusal'):
            open_when_reachable(b, room, lambda: True)
        self.assertEqual(1, b.q.send.call_count)
        self.assertTrue(b.book['public_quote_admissions'][0]['pending'])

    def test_wrong_merchant_is_not_traded_or_retried(self):
        b, room, reply = self.setup_case()
        reply['menu']['merchant']['villager_uuid'] = 'other'
        with self.assertRaisesRegex(RuntimeError, 'Different merchant'):
            open_when_reachable(b, room, lambda: True)
        self.assertEqual(1, b.q.send.call_count)

    def test_fixed_cell_can_use_explicit_bounded_farther_distance(self):
        b, room, reply = self.setup_case()
        b.check.return_value = {'pos': [.5, 64, -1.89]}
        self.assertIs(reply, open_when_reachable(b, room, lambda: True, distance_limit=2.95))
        for limit in (3, float('nan'), True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                open_when_reachable(b, room, lambda: True, distance_limit=limit)

    def test_waiting_for_profession_does_not_rescan_the_entire_room(self):
        b, room, _ = self.setup_case()
        b.check.return_value['loaded_villagers'] = {'villagers': [
            {'uuid':'resident','villager':{'profession':'minecraft:none'}},
            {'uuid':'neighbour','villager':{'profession':'minecraft:librarian'}}]}
        with patch('librarian_public_quote.time.monotonic', side_effect=[0,.1,.2,1]), patch('librarian_public_quote.time.sleep'):
            self.assertIsNone(open_when_reachable(b,room,lambda:True,seconds=.5))
        b.scan.assert_not_called()
        b.q.send.assert_not_called()
        self.assertEqual(2,b.book['public_quote_wait_counts']['unclaimed'])

    def test_profession_snapshot_still_requires_fresh_scene_before_open(self):
        b, room, reply = self.setup_case()
        b.check.return_value['loaded_villagers'] = {'villagers': [
            {'uuid':'resident','villager':{'profession':'minecraft:librarian'}}]}
        self.assertIs(reply,open_when_reachable(b,room,lambda:True))
        b.scan.assert_called_once()

    def test_distant_fresh_body_yields_to_other_cells_without_scan_loop(self):
        b, room, _ = self.setup_case()
        b.check.return_value['pos'] = [.5, 64, -10]
        with patch('librarian_public_quote.time.sleep') as sleep:
            self.assertIsNone(open_when_reachable(b, room, lambda: True, seconds=30))
        b.scan.assert_called_once()
        b.q.send.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual(1, b.book['public_quote_wait_counts']['out_of_reach'])


if __name__ == '__main__':
    unittest.main()

class QuoteToolReuseTests(unittest.TestCase):
 setup_case=PublicQuoteTests.setup_case
 def test_selected_safe_tool_does_not_need_another_selection_command(self):
  b,room,reply=self.setup_case();b.check.return_value['hand']={'item':'minecraft:netherite_sword'}
  self.assertIs(open_when_reachable(b,room,lambda:True),reply);b.n.assert_not_called();b.q.send.assert_called_once()

class BoundedReachWaitTests(unittest.TestCase):
 setup_case=PublicQuoteTests.setup_case
 def test_wait_hint_does_not_scan_until_resident_approaches(self):
  from copy import deepcopy
  b,r,reply=self.setup_case();near=deepcopy(b.check.return_value);near['loaded_villagers']={'villagers':[{'uuid':'resident','pos':[.5,64,1.5],'villager':{'profession':'minecraft:librarian'}}]};far=deepcopy(near);far['loaded_villagers']['villagers'][0]['pos'][2]=10;b.check.side_effect=[far,near,near]
  with patch('librarian_public_quote.time.sleep'):self.assertIs(reply,open_when_reachable(b,r,lambda:True,wait_for_reach=True))
  b.scan.assert_called_once();b.q.send.assert_called_once()
 def test_fresh_body_still_controls_input_after_near_hint(self):
  b,r,reply=self.setup_case();near=r.actor.return_value;far={'uuid':'resident','villager':{'profession':'minecraft:librarian'},'bounds':{'min':[0,64,10],'max':[1,66,11]}};r.actor.side_effect=[far,near]
  with patch('librarian_public_quote.time.sleep'):self.assertIs(reply,open_when_reachable(b,r,lambda:True,wait_for_reach=True))
  self.assertEqual(2,b.scan.call_count);b.q.send.assert_called_once()
 def test_wait_remains_bounded_and_never_replays_unknown_input(self):
  b,r,_=self.setup_case();b.check.return_value['pos']=[.5,64,-10]
  with patch('librarian_public_quote.time.monotonic',side_effect=[0,.1,.2,1]),patch('librarian_public_quote.time.sleep'):self.assertIsNone(open_when_reachable(b,r,lambda:True,seconds=.5,wait_for_reach=True))
  b.q.send.assert_not_called();b,r,_=self.setup_case();b.q.send.side_effect=RuntimeError('unknown');b.q.observe_merchant_reach_refusal.side_effect=RuntimeError('retained')
  with self.assertRaisesRegex(RuntimeError,'retained'):open_when_reachable(b,r,lambda:True,wait_for_reach=True)
  b.q.send.assert_called_once()
