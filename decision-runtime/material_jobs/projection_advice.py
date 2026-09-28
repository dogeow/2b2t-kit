"""Small, redacted choices for an optional projection material adviser.

Only the local material worker maps these opaque choice IDs back to item
targets. Projection coordinates, placement names, player identity and raw
mismatch rows never enter a model prompt.
"""
import hashlib
import json
import re

from material_plan import quantities


MAX_MATERIAL_CHOICES = 8
ITEM = re.compile(r'minecraft:[a-z0-9_./-]+\Z')


def audit_fingerprint(audit, placement_key, targets):
    """Return an internal full-audit fingerprint, or None if proof is weak."""
    if (not isinstance(audit, dict) or audit.get('audit_schema') != 2
            or audit.get('loaded_chunks_verified') is not True
            or audit.get('placement_key') != placement_key
            or type(audit.get('observed_at')) is not int or audit['observed_at'] <= 0
            or type(audit.get('matched')) is not int
            or type(audit.get('total')) is not int or audit['total'] <= 0
            or not isinstance(audit.get('mismatches'), list)
            or audit['matched'] + len(audit['mismatches']) != audit['total']
            or not isinstance(audit.get('replacement_items'), dict)):
        return None
    try:
        remaining = dict(quantities(audit['replacement_items']))
    except (TypeError, ValueError):
        return None
    if remaining != targets:
        return None
    payload = {key: audit[key] for key in ('placement_key', 'matched', 'total',
                                           'mismatches', 'replacement_items')}
    try:
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                             allow_nan=False).encode('utf-8')
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(encoded).hexdigest()


def material_choices(audit, placement_key, targets, held, ranked_items):
    """Offer at most eight verified material batches plus the safe wait choice."""
    digest = audit_fingerprint(audit, placement_key, targets)
    if digest is None or len(ranked_items) < 2:
        return None
    selected = ranked_items[:MAX_MATERIAL_CHOICES]
    if (len(selected) < 2 or len(set(selected)) != len(selected)
            or any(not isinstance(item, str) or not ITEM.fullmatch(item)
                   or item not in targets or type(targets[item]) is not int
                   or targets[item] <= held.get(item, 0)
                   or type(held.get(item, 0)) is not int or held.get(item, 0) < 0
                   for item in selected)):
        return None
    options = {'wait': 'Pause this material task with native protection active; take no new material action.'}
    mapping = {}
    facts = []
    for index, item in enumerate(selected, 1):
        key = f'supply_{index:02d}'
        missing = targets[item] - held.get(item, 0)
        options[key] = (f'Prepare the next bounded native material batch for {item}; '
                        f'{missing} still needed, {held.get(item, 0)} carried.')
        mapping[key] = item
        facts.append({'item': item, 'remaining': targets[item],
                      'carried': held.get(item, 0), 'deficit': missing})
    scene = {'matched_cells': audit['matched'], 'total_cells': audit['total'],
             'remaining_cells': audit['total'] - audit['matched'],
             'material_choices': facts}
    return {'choices': options, 'mapping': mapping, 'scene': scene,
            'fallback': 'supply_01', 'audit_fingerprint': digest,
            'audit_observed_at': audit['observed_at']}
