import unittest
from librarian_round_robin import choose_ready,keeper_refresh_key
class RoundRobinTest(unittest.TestCase):
 def test_fresh_keeper_candidate_precedes_other_waiting_cells(self):
  self.assertEqual(choose_ready([{'id':'A'},{'id':'B'}],{'A':20,'B':1},'A')['id'],'A')
 def test_preferred_candidate_must_still_be_ready(self):
  self.assertEqual(choose_ready([{'id':'B'}],{},'A')['id'],'B')
 def test_normal_selection_is_least_recent_and_no_ready_is_none(self):
  self.assertEqual(choose_ready([{'id':'A'},{'id':'B'}],{'A':20,'B':1})['id'],'B');self.assertIsNone(choose_ready([],{},'A'))
 def test_refresh_retry_budget_is_per_candidate_generation(self):
  a=keeper_refresh_key('A','mending',{'native_sequence':1});self.assertEqual(a,keeper_refresh_key('A','mending',{'native_sequence':1}));self.assertNotEqual(a,keeper_refresh_key('A','mending',{'native_sequence':2}));self.assertNotEqual(a,keeper_refresh_key('B','mending',{'native_sequence':1}))
