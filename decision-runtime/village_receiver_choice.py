"""Seal the empty receiver actually entered, rather than chasing a planned bed."""


def choose(entities, uid, cells):
    for cell in cells:
        lo, hi = cell['min'], cell['max_exclusive']
        front = cell['front_z']
        observed = []
        for actor in entities:
            if actor.get('type') != 'minecraft:villager':
                continue
            box = actor.get('bounds') or {}
            if not all(isinstance(box.get(side), list) and len(box[side]) == 3 for side in ('min', 'max')):
                return None
            if (box['max'][0] > lo[0] and box['min'][0] < hi[0]
                    and box['max'][2] > min(lo[2], front)
                    and box['min'][2] < max(hi[2], front+1)):
                observed.append(actor)
        if len(observed) != 1:
            continue
        actor = observed[0]
        box = actor['bounds']
        if (actor.get('uuid') == uid and actor.get('health') == 20
                and actor.get('alive') is True and actor.get('is_baby') is False
                and all(lo[i] <= box['min'][i] < box['max'][i] <= hi[i] for i in range(3))
                and lo[0]+.01 <= box['min'][0] and box['max'][0] <= hi[0]-.01
                and lo[2]+.01 <= box['min'][2] and box['max'][2] <= hi[2]-.01):
            return cell
    return None
