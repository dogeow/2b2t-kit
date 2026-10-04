"""Explicit target scopes for the existing material backend's sole client."""
from . import (mineral_pipeline, wood_pipeline, colored_pipeline,
               natural_block_pipeline, mud_pipeline, stripped_wood_pipeline)
from .protocol import JobBlocked, fingerprint

CARRIED_SCOPE = 'absolute_backpack_total'

FAMILIES = (
    (mineral_pipeline, mineral_pipeline.ITEMS, 'approved_depot_total', 'mineral_backend', 1_000_000),
    (wood_pipeline, frozenset(wood_pipeline.LOGS) | frozenset(wood_pipeline.PLANKS),
     'approved_depot_total', 'wood_backend', 100_000),
    (colored_pipeline, colored_pipeline.OUTPUTS, 'absolute_backpack', 'colored_backend', 2304),
    (natural_block_pipeline, natural_block_pipeline.OUTPUTS, natural_block_pipeline.TARGET_SCOPE,
     'natural_backend', 2304),
    (mud_pipeline, mud_pipeline.ITEMS, mud_pipeline.TARGET_SCOPE, 'mud_backend', mud_pipeline.MAX_TARGET_COUNT),
    (stripped_wood_pipeline, stripped_wood_pipeline.OUTPUTS, stripped_wood_pipeline.TARGET_SCOPE,
     'stripped_wood_backend', stripped_wood_pipeline.MAX_TARGET_COUNT),
)


def _route(item):
    family = next((row for row in FAMILIES if isinstance(item, str) and item in row[1]), None)
    if family is None:
        raise ValueError('Unsupported material pipeline output: ' + str(item))
    return family


def describe(item):
    """Read the code contract only; no client, inventory or source is inspected."""
    module, _, scope, _, maximum = _route(item)
    result={'item': item, 'family': module.__name__.rsplit('.', 1)[-1].removesuffix('_pipeline'),
            'target_scope': scope, 'max_target_count': maximum}
    if item==mineral_pipeline.IRON or item in wood_pipeline.PLANKS:
        result.update(carried_target_scope=CARRIED_SCOPE,max_carried_target_count=2304)
    return result


def carried_context(backend, client, item, target_count):
    """Pin a carried transaction to the original projection wrapper identity."""
    request=getattr(backend,'request',{})
    context=getattr(backend,'resource_pipeline_context',None)
    if not isinstance(request,dict) or not isinstance(context,dict):return None
    expected={'request_id':request.get('id'),'request_fingerprint':fingerprint(request),
              'projection_key':request.get('projection_key'),'world_session':client.world,
              'item':item,'target_count':target_count,'target_scope':CARRIED_SCOPE}
    bounds=context.get('selection_bounds')
    if (request.get('mode')!='projection' or not expected['request_id'] or not expected['projection_key']
            or request.get('context',{}).get('world_session')!=client.world
            or any(context.get(key)!=value for key,value in expected.items())
            or not isinstance(bounds,dict)
            or any(not isinstance(bounds.get(key),list) or len(bounds[key])!=3
                   or any(type(value)is not int for value in bounds[key]) for key in ('min','max'))
            or any(bounds['min'][i]>bounds['max'][i] for i in range(3))):return None
    return {**expected,'selection_bounds':{key:list(bounds[key]) for key in ('min','max')}}


def run(backend, item, target_count, out, checkpoint, target_scope):
    family = _route(item)
    module, _, expected_scope, binding, maximum = family
    route=describe(item)
    carried=bool(route.get('carried_target_scope') and target_scope==route['carried_target_scope'])
    if target_scope != expected_scope and not carried:
        raise ValueError('Expected target_scope=' + expected_scope + ' for ' + item)
    if carried:maximum=route['max_carried_target_count']
    if type(target_count) is not int or not 1 <= target_count <= maximum:
        raise ValueError('Invalid target count for ' + item)
    checkpoint()
    client = backend.ensure_client()
    if client is None or backend.client is not client:
        raise JobBlocked('Pipeline must reuse the backend sole owned client')
    client.material_backend = backend
    setattr(client, binding, backend)
    worker=module.run_carried if carried else module.run
    return worker(client, backend.profile, item, target_count, out, checkpoint)
