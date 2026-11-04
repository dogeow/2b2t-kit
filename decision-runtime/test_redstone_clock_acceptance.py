import unittest
from redstone_clock_acceptance import analyze_clock_trace, analyze_alternating_trace


def trace(wet=8, dry=43):
    phases = [('air', 10), ('minecraft:water[level=0]', wet), ('air', dry),
              ('Block{minecraft:water}[level=0]', wet), ('Block{minecraft:air}', dry),
              ('minecraft:water[level=0]', wet)]
    rows, now = [], 0
    for state, duration in phases:
        for _ in range(duration*4):
            rows.append({'time': now, 'sources': {'154': state, '181': state}})
            now += 250
    return rows


class ClockAcceptanceTests(unittest.TestCase):
    def test_long_dry_short_flush_passes_for_every_layer(self):
        result = analyze_clock_trace(trace())
        self.assertTrue(result['passed'])
        self.assertEqual(result['layers']['154']['wet_intervals'], 2)
        self.assertEqual(result['layers']['181']['dry_intervals'], 2)
        self.assertEqual(result['scope'], 'supplied_source_cells_only')

    def test_old_fast_clock_fails_even_though_it_toggles_repeatedly(self):
        result = analyze_clock_trace(trace(wet=10, dry=4))
        self.assertFalse(result['passed'])
        self.assertTrue(result['layers']['154']['short_dry_intervals'])

    def test_never_loaded_or_never_triggered_fixture_cannot_pass(self):
        rows = trace()
        for row in rows:
            row['sources'] = {'154': 'air', '181': 'air'}
        self.assertFalse(analyze_clock_trace(rows)['passed'])

    def test_one_unretracted_layer_fails_the_whole_tower(self):
        rows = trace()
        for row in rows:
            row['sources']['181'] = 'water'
        self.assertFalse(analyze_clock_trace(rows)['passed'])

    def test_missing_observations_do_not_earn_a_long_dry_interval(self):
        rows = [v for v in trace() if not 22000 <= v['time'] <= 26000]
        result = analyze_clock_trace(rows)
        self.assertFalse(result['passed'])
        self.assertTrue(result['sampling_gaps'])

    def test_flowing_water_is_not_counted_as_dry(self):
        rows = trace()
        for row in rows:
            if 18000 <= row['time'] < 23000:
                row['sources']['154'] = 'minecraft:water[level=7]'
        result = analyze_clock_trace(rows)
        self.assertFalse(result['passed'])  # The first wet interval exceeds12s.
        self.assertTrue(result['layers']['154']['invalid_wet_intervals'])

    def test_retraction_air_blip_earns_no_extra_dry_interval(self):
        rows = trace()
        for row in rows:
            if 18000 <= row['time'] < 20000:
                row['sources']['154'] = 'minecraft:water[level=7]'
        next(v for v in rows if v['time'] == 18500)['sources']['154'] = 'air'
        result = analyze_clock_trace(rows)
        self.assertTrue(result['passed'])
        layer = result['layers']['154']
        self.assertEqual(layer['wet_intervals'], 2)
        self.assertEqual(layer['dry_intervals'], 2)
        self.assertEqual(layer['dry_gaps_treated_as_wet'][0]['dry_credit_seconds'], 0)

    def test_unknown_state_or_missing_layer_cannot_be_accepted(self):
        rows = trace()
        rows[20]['sources']['154'] = 'other'
        self.assertFalse(analyze_clock_trace(rows)['passed'])
        del rows[20]['sources']['181']
        with self.assertRaises(ValueError):
            analyze_clock_trace(rows)

    def test_partial_first_interval_cannot_earn_completion_credit(self):
        rows = trace()[44:]
        result = analyze_clock_trace(rows)
        self.assertEqual(result['layers']['154']['wet_intervals'], 1)
        self.assertFalse(result['passed'])

    def test_timestamp_and_policy_validation(self):
        rows = trace()
        rows[1]['time'] = rows[0]['time']
        with self.assertRaises(ValueError):
            analyze_clock_trace(rows)
        with self.assertRaises(ValueError):
            analyze_clock_trace(trace(), minimum_dry_seconds=0)
        with self.assertRaises(ValueError):
            analyze_clock_trace(trace(), maximum_sample_gap_seconds=float('nan'))


if __name__ == '__main__':
    unittest.main()


class AlternatingClockAcceptanceTests(unittest.TestCase):
    @staticmethod
    def alternating():
        return [{'time': n*250, 'sources': {
            str(154+3*k): 'water' if (n//100+k)%2 else 'air'
            for k in range(10)}} for n in range(601)]

    def test_alternating_long_windows_pass_in_physical_order(self):
        result = analyze_alternating_trace(self.alternating(), layers=[str(154+3*k)for k in range(10)])
        self.assertTrue(result['passed'])
        self.assertEqual(result['phase_swaps'], 6)

    def test_synchronous_clock_and_wrong_physical_order_fail(self):
        rows = self.alternating()
        for row in rows:
            row['sources']['157'] = row['sources']['154']
        self.assertFalse(analyze_alternating_trace(rows, layers=['154','157'])['passed'])
        self.assertFalse(analyze_alternating_trace(self.alternating(), layers=['154','160','157'])['passed'])

    def test_bounded_propagation_wave_can_swap_but_cannot_stay_synchronous(self):
        rows = self.alternating()
        for start in range(100,600,100):
            rows[start]['sources']['157'] = rows[start]['sources']['154']
        self.assertTrue(analyze_alternating_trace(rows, layers=['154','157'])['passed'])
        for n in range(120,140):
            rows[n]['sources']['157'] = rows[n]['sources']['154']
        self.assertFalse(analyze_alternating_trace(rows, layers=['154','157'])['passed'])

    def test_stationary_short_and_unobserved_windows_fail(self):
        rows = self.alternating()
        self.assertFalse(analyze_alternating_trace(rows[:150], layers=['154','157'])['passed'])
        self.assertFalse(analyze_alternating_trace(rows[:150]+rows[170:], layers=['154','157'])['passed'])
        for row in rows:
            row['sources'] = {'154':'air','157':'water'}
        self.assertFalse(analyze_alternating_trace(rows, layers=['154','157'])['passed'])
