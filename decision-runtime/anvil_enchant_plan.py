"""Plan approved maximum-level books into ONE book, then apply it once.

This is a pure planner, not inventory or XP authorization. All prior-work
penalties are explicit inputs from actual evidence. It optimizes the supplied
book instances under the user's book-first constraint, not every possible
equipment/source selection. The live anvil preview must confirm every step.
"""
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from zipfile import ZipFile
import json
import re


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an explicit integer >= {minimum}')
    return value


def levels_to_xp(level):
    """XP required from level zero; not the cost paid at an arbitrary level."""
    _integer(level, 'level')
    if level <= 16:
        return level * level + 6 * level
    if level <= 31:
        return (5 * level * level - 81 * level + 720) // 2
    return (9 * level * level - 325 * level + 4440) // 2


def rules_from_jar(path):
    """Use this installation's built-in definitions rather than a web table."""
    result = {}
    with ZipFile(Path(path)) as archive:
        for name in archive.namelist():
            if not name.startswith('data/minecraft/enchantment/') or not name.endswith('.json'):
                continue
            definition = json.loads(archive.read(name))
            cost = _integer(definition['anvil_cost'], 'anvil_cost', 1)
            maximum = _integer(definition['max_level'], 'max_level', 1)
            key = 'minecraft:' + name.rsplit('/', 1)[1][:-5]
            result[key] = {'book_multiplier': max(1, cost // 2), 'max_level': maximum}
    if not result:
        raise ValueError('No native enchantment definitions in the supplied JAR')
    return result


@dataclass(frozen=True)
class _Plan:
    ref: str
    penalty: int
    levels: int
    xp_from_zero: int
    peak: int
    steps: tuple


def plan_single_book(books, targets, rules, *, item_penalty, max_cost=39,
                     objective='levels'):
    """Return an exact minimum merge tree, or None when no legal tree exists.

    Books may already contain several approved maximum enchantments, including
    overlapping maxima. Creating maxima from lower-level books and combining
    incompatible enchantments are outside this model. ``targets`` must be a caller-approved
    compatible set applicable to the destination item. Missing penalties are
    errors, never silently treated as zero.
    """
    _integer(item_penalty, 'item_penalty')
    _integer(max_cost, 'max_cost', 1)
    if max_cost > 39 or objective not in ('levels', 'xp_from_zero'):
        raise ValueError('Survival cost <=39 and a declared objective required')
    if not isinstance(books, list) or not 1 <= len(books) <= 10:
        raise ValueError('One to ten observed book instances required')
    if not isinstance(targets, dict) or not targets or not isinstance(rules, dict):
        raise ValueError('Explicit approved target enchantments required')
    for name, level in targets.items():
        _integer(level, 'target level', 1)
        rule = rules.get(name, {})
        if rule.get('max_level') != level:
            raise ValueError('Every target must use its native maximum level')
        _integer(rule.get('book_multiplier'), 'book multiplier', 1)

    identifiers = set()
    effects = []
    states = {}
    for i, book in enumerate(books):
        if not isinstance(book, dict):
            raise ValueError('Observed book objects required')
        identifier = book.get('id')
        if (not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_:.#-]{1,128}', identifier)
                or identifier == 'item' or identifier in identifiers):
            raise ValueError('Distinct observed book identifiers required')
        identifiers.add(identifier)
        penalty = _integer(book.get('repair_cost'), 'book repair_cost')
        enchantments = book.get('enchantments')
        if not isinstance(enchantments, dict) or not enchantments:
            raise ValueError('Observed nonempty book enchantments required')
        if any(name not in targets or level != targets[name]
               or type(level) is not int for name, level in enchantments.items()):
            raise ValueError('Only approved maximum enchantments may enter the plan')
        effects.append(dict(enchantments))
        states[1 << i] = {penalty: _Plan(identifier, penalty, 0, 0, 0, ())}

    full = (1 << len(books)) - 1
    merged_effects = {}
    weights = {}
    for mask in range(1, full + 1):
        combined = {}
        for i, enchantments in enumerate(effects):
            if mask & (1 << i):
                combined.update(enchantments)
        merged_effects[mask] = combined
        weights[mask] = sum(level * rules[name]['book_multiplier']
                            for name, level in combined.items())
    if merged_effects[full] != targets:
        raise ValueError('Supplied books do not cover the approved targets')

    def score(plan):
        primary, secondary = ((plan.levels, plan.xp_from_zero) if objective == 'levels'
                              else (plan.xp_from_zero, plan.levels))
        return primary, secondary, plan.peak, plan.ref

    for size in range(2, len(books) + 1):
        for members in combinations(range(len(books)), size):
            mask = sum(1 << i for i in members)
            options = states.setdefault(mask, {})
            left = (mask - 1) & mask
            while left:
                right = mask ^ left
                # Both orientations are enumerated: right-hand enchantments cost XP.
                for a in states.get(left, {}).values():
                    for b in states.get(right, {}).values():
                        cost = a.penalty + b.penalty + weights[right]
                        if cost > max_cost:
                            continue
                        penalty = 2 * max(a.penalty, b.penalty) + 1
                        ref = '(' + a.ref + '+' + b.ref + ')'
                        step = {'operation': 'combine_books', 'left': a.ref, 'right': b.ref,
                                'output': ref, 'cost_levels': cost,
                                'output_repair_cost': penalty,
                                'enchantments': dict(merged_effects[mask])}
                        candidate = _Plan(ref, penalty, a.levels + b.levels + cost,
                                          a.xp_from_zero + b.xp_from_zero + levels_to_xp(cost),
                                          max(a.peak, b.peak, cost), a.steps + b.steps + (step,))
                        if penalty not in options or score(candidate) < score(options[penalty]):
                            options[penalty] = candidate
                left = (left - 1) & mask

    finished = []
    for book in states.get(full, {}).values():
        cost = item_penalty + book.penalty + weights[full]
        if cost <= max_cost:
            step = {'operation': 'apply_finished_book', 'left': 'item', 'right': book.ref,
                    'cost_levels': cost, 'output_repair_cost': 2 * max(item_penalty, book.penalty) + 1}
            finished.append(_Plan(book.ref, book.penalty, book.levels + cost,
                                  book.xp_from_zero + levels_to_xp(cost), max(book.peak, cost),
                                  book.steps + (step,)))
    if not finished:
        return None
    best = min(finished, key=score)
    return {'scope': 'supplied_maximum_books_combined_first_then_one_item_application',
            'objective': objective, 'total_levels': best.levels,
            'xp_if_each_step_starts_from_zero': best.xp_from_zero,
            'maximum_step_levels': best.peak, 'steps': list(best.steps),
            'final_book_enchantments': dict(targets),
            'requires_actual_anvil_preview': True}
