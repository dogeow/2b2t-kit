"""Permit independently crafted or verified recovered stock, never an old retry.

The original quarantine remains intact. This is not an old-input retry: the
species, support site, material source and command identity must all differ.
"""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from material_plan import inventory_counts


def validate_identity(state, lease, command, marker, old, certificate):
    item = command.get('item')
    support, stand = command.get('support'), command.get('stand')
    original = old.get('support')
    def point(p):
        return isinstance(p, list) and len(p) == 3 and all(type(n) is int for n in p)
    if (command.get('action') != 'boat_place' or item != 'minecraft:oak_boat'
            or old.get('item') == item or not old.get('item', '').endswith('_boat')
            or not all(point(p) for p in (support, stand, original))
            or math.dist(support, original) < 16 or support == original
            or certificate.get('consumed_by') is not None
            or certificate.get('world_session') != state.get('world_session')
            or certificate.get('task_session') != lease.get('job_session')
            or certificate.get('old_journal_sha256') != marker.get('journal_sha256')
            or certificate.get('support') != support or certificate.get('stand') != stand
            or certificate.get('item') != item
            or type(certificate.get('created_at')) is not int or type(state.get('time')) is not int
            or not 0 <= state['time'] - certificate['created_at'] <= 300000):
        raise RuntimeError('New boat is not independent of the quarantined use')
    expected = command.get('allowed_passengers')
    if expected==[] and certificate.get('allowed_passengers')==[]:
        if (certificate.get('kind')in('recovered','observed_carried','crafted')
                and certificate.get('purpose')==command.get('purpose')=='iron_farm_zombie_capture'
                and state.get('connected')is True and state.get('health')==20
                and state.get('manual_movement')is False and not state.get('screen')
                and lease.get('kind')=='materials' and lease.get('world_session')==state.get('world_session')):
            # This prepares an empty receiver. It grants no authority to load
            # or transport any passenger; the named-target gate owns that step.
            return item
        raise RuntimeError('Empty capture boat needs recovered stock and an explicit healthy same-world purpose')
    if (not isinstance(expected, list) or len(expected) not in (1,2) or len(set(expected))!=len(expected)
            or certificate.get('allowed_passengers') != expected):
        raise RuntimeError('One or two distinct exact untraded transfer candidates are required')
    if len(expected)==2 and not(command.get('purpose')==certificate.get('purpose')=='family_pair_transport'):
        raise RuntimeError('Two passengers require an explicit family pair transport purpose')
    people = {v['uuid']: v for v in state.get('loaded_villagers', {}).get('villagers', [])}
    for uid in expected:
        villager = people.get(uid, {})
        if (villager.get('health') != 20 or villager.get('is_baby') is not False
                or villager.get('villager', {}).get('entity_xp') != 0
                or villager.get('villager', {}).get('level') != 1):
            raise RuntimeError('The new boat candidate is not a witnessed healthy untraded adult')
    return item


def validate(state, lease, command, marker, old, certificate, before, craft_intent, craft, after):
    item=validate_identity(state,lease,command,marker,old,certificate)
    if (craft_intent.get('action') != 'manufacture' or craft_intent.get('targets') != {item: 1}
            or craft.get('complete') is not True
            or any(s.get('world_session') != state['world_session'] for s in (before, after))
            or before.get('phase') not in (None, 'done') or after.get('phase') not in (None, 'done')
            or not before.get('time', 0) < after.get('time', 0) <= certificate['created_at']):
        raise RuntimeError('Fresh boat lacks completed same-world crafting evidence')
    a, b, current = inventory_counts(before), inventory_counts(after), inventory_counts(state)
    expected_stock = a.copy()
    expected_stock['minecraft:oak_planks'] -= 5
    expected_stock[item] += 1
    if (a[item] != 0 or a['minecraft:oak_planks'] < 5 or b[item] != 1
            or +expected_stock != b or current[item] != 1):
        raise RuntimeError('Fresh independent boat stock is not conserved')


def validate_recovery(state,lease,command,marker,old,certificate,proof,placed,place_intent,recover_intent,recover_reply):
    item=validate_identity(state,lease,command,marker,old,certificate)
    boat=proof.get('boat_before')or{};times=proof.get('boat_removed_two_frames')or[]
    expected=Counter(proof.get('inventory_before')or{});expected[item]+=1;expected['minecraft:lead']+=1
    if(proof.get('complete')is not True or proof.get('pending')is not None
            or proof.get('world_session')!=state.get('world_session')or proof.get('health')!=20
            or proof.get('boat_and_lead_recovered')is not True
            or len(times)<2 or not all(type(t)is int for t in times)or times[-1]<=times[0]
            or boat.get('type')!=item or not boat.get('uuid')
            or (proof.get('inventory_before')or{}).get(item,0)!=0
            or Counter(proof.get('inventory_after')or{})!=+expected
            or inventory_counts(state)[item]!=1
            or placed.get('complete')is not True or placed.get('pending')is not None
            or placed.get('world_session')!=state.get('world_session')
            or placed.get('item')!=item or (placed.get('boat')or{}).get('uuid')!=boat['uuid']
            or place_intent.get('action')!='boat_place'or place_intent.get('item')!=item
            or not place_intent.get('independent_stock')
            or (placed.get('before')or{}).get(item)!=1 or (placed.get('after')or{}).get(item,0)!=0
            or recover_intent.get('action')!='native'or recover_intent.get('op')!='recover_boat'
            or recover_intent.get('params',{}).get('expected_uuid')!=boat['uuid']
            or set(recover_intent.get('params',{}).get('expected_passenger_uuids',[]))!={p['uuid']for p in boat.get('passengers',[])}
            or recover_reply.get('id')!=proof.get('boat_recovery_request')
            or recover_reply.get('world_session')!=state.get('world_session')or recover_reply.get('phase')!='done'):
        raise RuntimeError('Recovered boat lacks exact known placement, removal and item conservation')


def validate_carried(state,lease,command,marker,old,certificate,source):
    """Distinct boat species observed before this owner; no old-result credit."""
    item=validate_identity(state,lease,command,marker,old,certificate)
    if (certificate.get('kind')!='observed_carried' or command.get('allowed_passengers')!=[]
            or source.get('connected')is not True or source.get('health')!=20
            or source.get('manual_movement')is not False or source.get('screen')!=''
            or source.get('supervision_lease')
            or any(source.get(k)!=state.get(k)for k in ('world_session','server','dimension','player_uuid'))
            or type(source.get('time'))is not int or source['time']>certificate['created_at']
            or inventory_counts(source)[item]<1 or inventory_counts(source)[item]!=inventory_counts(state)[item]):
        raise RuntimeError('Carried distinct-species boat is not conserved from the exact pre-owner snapshot')

def authorize(out, state, lease, command, marker):
    out = Path(out).resolve()
    path = Path(command.get('independent_stock', '')).resolve()
    if not path.is_relative_to(out) or not path.is_file():
        raise RuntimeError('Original boat placement is quarantined; no independent stock proof')
    certificate = json.loads(path.read_text())
    original = Path(marker['journal'])
    if hashlib.sha256(original.read_bytes()).hexdigest() != marker['journal_sha256']:
        raise RuntimeError('Original unresolved boat journal changed')
    old = json.loads(original.read_text())
    def result(key, filename='result.json'):
        identity = certificate[key]
        if not isinstance(identity, str) or Path(identity).name != identity or not identity:
            raise RuntimeError('Fresh craft evidence escaped current owner')
        return json.loads((out / identity / filename).read_text())
    if certificate.get('kind')=='observed_carried':
        source=out/'actual-before.json'
        if hashlib.sha256(source.read_bytes()).hexdigest()!=certificate.get('source_sha256'):
            raise RuntimeError('Original pre-owner inventory observation changed')
        validate_carried(state,lease,command,marker,old,certificate,json.loads(source.read_text()))
        return path,certificate
    if certificate.get('kind')=='recovered':
        proof_path=Path(certificate.get('recovery_proof','')).resolve()
        if(not proof_path.is_relative_to(out)or not proof_path.is_file()
                or hashlib.sha256(proof_path.read_bytes()).hexdigest()!=certificate.get('recovery_proof_sha256')):
            raise RuntimeError('Recovered boat evidence escaped current owner or changed')
        validate_recovery(state,lease,command,marker,old,certificate,json.loads(proof_path.read_text()),
                          result('placement_command'),result('placement_command','intent.json'),
                          result('recovery_command','intent.json'),result('recovery_command'))
        return path,certificate
    for key in ('before_command', 'after_command'):
        intent = result(key, 'intent.json')
        if intent.get('action') != 'native' or intent.get('op') != 'snapshot':
            raise RuntimeError('Boat stock evidence is not a read-only snapshot')
    validate(state, lease, command, marker, old, certificate,
             result('before_command'), result('craft_command', 'intent.json'),
             result('craft_command'), result('after_command'))
    return path, certificate
