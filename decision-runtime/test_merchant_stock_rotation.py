import unittest
from merchant_stock_rotation import StockRotation


class StockRotationTests(unittest.TestCase):
    def test_stock_arriving_at_another_vendor_is_eventually_seen(self):
        policy=StockRotation(('A','B','C'));current='A';seen=[];found=False
        for tick in range(8):
            current=policy.next_slot(current);seen.append(current)
            trades=12 if tick>=3 and current=='B' else 0
            policy.note_batch_result(trades)
            if trades:found=True;break
        self.assertTrue(found)
        self.assertEqual(seen,['B','C','A','A','A','B'])

    def test_full_empty_sweep_waits_locally_but_only_for_bounded_probes(self):
        policy=StockRotation(('A','B','C'),max_idle_probes=1);current='A'
        for wanted in ('B','C','A'):
            current=policy.next_slot(current);self.assertEqual(current,wanted);policy.note_batch_result(0)
        self.assertTrue(policy.holding);self.assertEqual(policy.next_slot(current),'A')
        policy.note_batch_result(0)
        self.assertFalse(policy.holding);self.assertEqual(policy.next_slot(current),'B')

    def test_success_leaves_wait_mode_and_resets_the_empty_sweep(self):
        policy=StockRotation(('A','B'));policy.note_batch_result(0);policy.note_batch_result(0)
        self.assertTrue(policy.holding);policy.note_batch_result(1)
        self.assertFalse(policy.holding);self.assertEqual(policy.next_slot('A'),'B')
        policy.note_batch_result(0);self.assertFalse(policy.holding)

    def test_rejects_unknown_or_nonterminal_counts_without_advancing_policy(self):
        policy=StockRotation(('A','B'));policy.note_batch_result(0)
        for invalid in (True,-1,33,None,1.5):
            with self.subTest(count=invalid),self.assertRaises(ValueError):policy.note_batch_result(invalid)
        self.assertFalse(policy.holding);policy.note_batch_result(0);self.assertTrue(policy.holding)
        with self.assertRaises(ValueError):policy.next_slot('foreign')

    def test_rejects_unbounded_or_ambiguous_configuration(self):
        for slots,probes in ((('A',),2),(('A','A'),2),(['A','B'],2),(('A','B'),0),(('A','B'),6),(('A','B'),True)):
            with self.subTest(slots=slots,probes=probes),self.assertRaises(ValueError):StockRotation(slots,max_idle_probes=probes)


if __name__=='__main__':unittest.main()
