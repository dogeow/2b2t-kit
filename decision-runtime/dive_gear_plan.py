"""Rank observed underwater gear without moving any player item."""

from collections import defaultdict

HELMS = {'minecraft:turtle_helmet', 'minecraft:turtle_shell',
         'minecraft:diamond_helmet', 'minecraft:netherite_helmet'}
BOOTS = {'minecraft:diamond_boots', 'minecraft:netherite_boots'}
SHOVELS = {'minecraft:diamond_shovel', 'minecraft:netherite_shovel'}
BOOK = 'minecraft:enchanted_book'
WATER_POTIONS = {'minecraft:potion', 'minecraft:splash_potion', 'minecraft:lingering_potion'}


def enchantments(row, stored=False):
    key = 'stored_enchantments' if stored else 'enchantments'
    return {entry['id'].rsplit(':', 1)[-1]: entry['level']
            for entry in row.get(key, []) if entry.get('level', 0) > 0}


def score(row, kind):
    ench = enchantments(row)
    durable = row.get('durability', 1) >= 50
    if kind == 'helmet':
        return (10 if ench.get('aqua_affinity') else 0) + 4*ench.get('respiration', 0) \
               + (2 if row['item'] in ('minecraft:turtle_helmet', 'minecraft:turtle_shell') else 0) \
               + (1 if durable else -10)
    if kind == 'boots':
        return 5*ench.get('depth_strider', 0) + (1 if durable else -10)
    if kind == 'shovel':
        return 3*ench.get('efficiency', 0) + (7 if ench.get('silk_touch') else 0) \
               + (1 if durable else -10)
    raise ValueError('Unknown underwater gear type')


def candidates(ender_slots, inventory=(), equipment=None):
    found = []
    equipment = equipment or {}
    for name, row in equipment.items():
        if row.get('count', 0):
            found.append({'source': 'equipped', 'equipment_slot': name, 'item': row})
    for row in inventory:
        if row.get('count', 0) and row.get('slot', 100) < 36:
            found.append({'source': 'inventory', 'slot': row['slot'], 'item': row})
    for outer in ender_slots:
        if outer.get('count') != 1 or not outer.get('item', '').endswith('shulker_box'):
            continue
        for index, item in enumerate(outer.get('contains', [])):
            if item.get('count', 0):
                found.append({'source': 'ender_box', 'ender_slot': outer['slot'],
                              'content_index_hint': index, 'item': item})
    return found


def plan(ender_slots, inventory=(), equipment=None):
    found = candidates(ender_slots, inventory, equipment)
    choices = {}
    for name, allowed in (('helmet', HELMS), ('boots', BOOTS), ('shovel', SHOVELS)):
        options = [entry for entry in found if entry['item']['item'] in allowed]
        choices[name] = max(options, key=lambda entry: score(entry['item'], name), default=None)
        if choices[name] is not None:
            choices[name] = {**choices[name], 'score': score(choices[name]['item'], name)}
    books = defaultdict(list)
    for entry in found:
        if entry['item']['item'] == BOOK:
            for enchantment, level in enchantments(entry['item'], stored=True).items():
                if enchantment in ('respiration', 'aqua_affinity', 'depth_strider',
                                   'efficiency', 'silk_touch', 'unbreaking', 'mending'):
                    books[enchantment].append({**entry, 'level': level})
    potions = [{**entry, 'count': entry['item']['count']} for entry in found
               if entry['item']['item'] in WATER_POTIONS
               and entry['item'].get('water_breathing')]
    scutes = sum(entry['item']['count'] for entry in found
                 if entry['item']['item'] == 'minecraft:turtle_scute')
    return {'best': choices, 'books': dict(books), 'water_breathing_potions': potions,
            'turtle_scutes_observed': scutes}
