"""Compare server quotes without mistaking price changes or new offers for restock."""
from copy import deepcopy


def _stack(row, *, dynamic_count=False):
    data = deepcopy(row.get('stack_data') or {})
    if dynamic_count:
        data.pop('count', None)
    return (row['item'], None if dynamic_count else row['count'], data)


def _identity(offer):
    return (_stack(offer['cost_a'], dynamic_count=True),
            _stack(offer['cost_b']), _stack(offer['result']), offer['max_uses'])


def compare(before, after, *, uuid):
    """Return only uniquely matched, previously used offers whose uses decreased."""
    for quote in (before, after):
        if (quote.get('protocol') != 1 or quote.get('owned') is not True
                or quote.get('villager_uuid') != uuid or quote.get('trader_xp', 0) <= 0
                or quote.get('observation_scope') != 'current_server_received_merchant_menu_not_trade_completion'):
            raise ValueError('Exact locked resident server quotes required')
    if after['trader_xp'] < before['trader_xp']:
        raise ValueError('Resident trade history moved backwards')
    evidence = []
    for old in before['offers']:
        if type(old.get('uses')) is not int or old['uses'] <= 0:
            continue
        identity = _identity(old)
        if sum(_identity(v) == identity for v in before['offers']) != 1:
            continue
        matches = [v for v in after['offers'] if _identity(v) == identity]
        if len(matches) != 1:
            continue
        new = matches[0]
        if type(new.get('uses')) is int and 0 <= new['uses'] < old['uses'] <= old['max_uses']:
            evidence.append({'before': deepcopy(old), 'after': deepcopy(new),
                             'uses_before': old['uses'], 'uses_after': new['uses']})
    return evidence
