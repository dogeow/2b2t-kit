import unittest
import json
import tempfile
from pathlib import Path
from zipfile import ZipFile
from anvil_enchant_plan import plan_single_book, levels_to_xp, rules_from_jar


def brute(books, weights, item_penalty, cap):
    """Independent enumeration of every ordered tree for tiny fixtures."""
    def trees(indices):
        if len(indices) == 1:
            i = indices[0]
            return [(books[i]['repair_cost'], 0)]
        out = []
        for bits in range(1, (1 << len(indices)) - 1):
            left = tuple(i for n, i in enumerate(indices) if bits & (1 << n))
            right = tuple(i for i in indices if i not in left)
            right_effects = {}
            for i in right:
                right_effects.update(books[i]['enchantments'])
            value = sum(weights[k] * v for k, v in right_effects.items())
            for lp, lc in trees(left):
                for rp, rc in trees(right):
                    cost = lp + rp + value
                    if cost <= cap:
                        out.append((2 * max(lp, rp) + 1, lc + rc + cost))
        return out
    all_effects = {}
    for book in books:
        all_effects.update(book['enchantments'])
    value = sum(weights[k] * v for k, v in all_effects.items())
    legal = [cost + item_penalty + penalty + value
             for penalty, cost in trees(tuple(range(len(books))))
             if item_penalty + penalty + value <= cap]
    return min(legal) if legal else None


class AnvilPlanTests(unittest.TestCase):
    def fixture(self, values=(5, 3, 2), penalties=None):
        penalties = penalties or [0] * len(values)
        rules = {str(i): {'max_level': v, 'book_multiplier': 1} for i, v in enumerate(values)}
        targets = {str(i): v for i, v in enumerate(values)}
        books = [{'id': 'b' + str(i), 'enchantments': {str(i): v}, 'repair_cost': penalties[i]}
                 for i, v in enumerate(values)]
        return books, targets, rules

    def test_three_fresh_books_first_cost_19_not_unrestricted_14(self):
        books, targets, rules = self.fixture()
        plan = plan_single_book(books, targets, rules, item_penalty=0)
        self.assertEqual(19, plan['total_levels'])
        self.assertEqual(13, plan['steps'][-1]['cost_levels'])
        self.assertEqual(['combine_books', 'combine_books', 'apply_finished_book'],
                         [r['operation'] for r in plan['steps']])

    def test_costly_book_on_left_preserves_asymmetric_cost(self):
        books, targets, rules = self.fixture((8, 1))
        plan = plan_single_book(books, targets, rules, item_penalty=0)
        self.assertEqual(('b0', 'b1', 1), tuple(plan['steps'][0][k] for k in ('left', 'right', 'cost_levels')))

    def test_existing_penalties_and_all_ordered_trees_match_independent_oracle(self):
        for values, penalties, item_penalty in [((9, 5, 2, 1), (0, 1, 0, 3), 1),
                                                ((3, 2, 1, 1), (3, 0, 1, 0), 3),
                                                ((12, 6, 4, 3), (0, 0, 0, 0), 0)]:
            books, targets, rules = self.fixture(values, penalties)
            result = plan_single_book(books, targets, rules, item_penalty=item_penalty)
            expected = brute(books, {k: 1 for k in targets}, item_penalty, 39)
            self.assertEqual(expected, result['total_levels'] if result else None)

    def test_40_level_final_application_is_rejected_even_if_book_merges_fit(self):
        books, targets, rules = self.fixture((12, 12, 4, 3, 2))
        self.assertIsNone(plan_single_book(books, targets, rules, item_penalty=0))

    def test_existing_combined_book_is_not_charged_for_historical_merges(self):
        books, targets, rules = self.fixture()
        combined = [{'id': 'already', 'enchantments': targets, 'repair_cost': 3}]
        plan = plan_single_book(combined, targets, rules, item_penalty=0)
        self.assertEqual(13, plan['total_levels'])
        self.assertEqual(1, len(plan['steps']))

    def test_existing_maximum_on_equipment_can_make_book_first_plan_feasible(self):
        # Full leggings: thorns, swift sneak, protection, unbreaking, mending.
        books, targets, rules = self.fixture((12, 12, 4, 3, 2))
        self.assertIsNone(plan_single_book(books, targets, rules, item_penalty=0))
        # An existing Unbreaking III seed needs only the other four books.
        books.pop(3);targets.pop('3')
        plan = plan_single_book(books, targets, rules, item_penalty=0)
        self.assertIsNotNone(plan)
        self.assertLessEqual(plan['maximum_step_levels'], 39)

    def test_book_identifiers_cannot_alias_item_or_a_merge_expression(self):
        for identifier in ['item', '(b1+b2)', 'a+b', '']:
            books, targets, rules = self.fixture()
            books[0]['id'] = identifier
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                plan_single_book(books, targets, rules, item_penalty=0)

    def test_missing_or_invalid_penalties_are_not_assumed_fresh(self):
        for penalty in [None, True, -1]:
            books, targets, rules = self.fixture()
            books[0]['repair_cost'] = penalty
            with self.assertRaises(ValueError):
                plan_single_book(books, targets, rules, item_penalty=0)
        books, targets, rules = self.fixture()
        with self.assertRaises(ValueError):
            plan_single_book(books, targets, rules, item_penalty=None)

    def test_unapproved_lower_or_uncovered_enchantments_are_rejected(self):
        for change in ['extra', 'lower', 'missing', 'duplicate_id']:
            books, targets, rules = self.fixture()
            if change == 'extra': books[0]['enchantments']['foreign'] = 1
            if change == 'lower': books[0]['enchantments']['0'] = 4
            if change == 'missing': books.pop()
            if change == 'duplicate_id': books[0]['id'] = books[1]['id']
            with self.subTest(change=change), self.assertRaises(ValueError):
                plan_single_book(books, targets, rules, item_penalty=0)

    def test_xp_conversion_boundaries_and_objective_scope_are_explicit(self):
        self.assertEqual([0, 352, 394, 1507, 1628], [levels_to_xp(v) for v in [0, 16, 17, 31, 32]])
        books, targets, rules = self.fixture()
        plan = plan_single_book(books, targets, rules, item_penalty=0, objective='xp_from_zero')
        self.assertTrue(plan['requires_actual_anvil_preview'])
        self.assertEqual('xp_from_zero', plan['objective'])

    def test_native_jar_book_multiplier_has_a_minimum_of_one(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'definitions.jar'
            with ZipFile(path, 'w') as z:
                z.writestr('data/minecraft/enchantment/efficiency.json', json.dumps({'anvil_cost': 1, 'max_level': 5}))
                z.writestr('data/minecraft/enchantment/thorns.json', json.dumps({'anvil_cost': 8, 'max_level': 3}))
            rules = rules_from_jar(path)
            self.assertEqual({'book_multiplier': 1, 'max_level': 5}, rules['minecraft:efficiency'])
            self.assertEqual({'book_multiplier': 4, 'max_level': 3}, rules['minecraft:thorns'])


if __name__ == '__main__':
    unittest.main()
