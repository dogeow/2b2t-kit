"""Explicit target scopes for the existing material backend's sole client."""
from . import (mineral_pipeline, wood_pipeline, colored_pipeline,
               natural_block_pipeline, mud_pipeline, stripped_wood_pipeline)
from .protocol import JobBlocked

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
    return {'item': item, 'family': module.__name__.rsplit('.', 1)[-1].removesuffix('_pipeline'),
            'target_scope': scope, 'max_target_count': maximum}


def run(backend, item, target_count, out, checkpoint, target_scope):
    family = _route(item)
    module, _, expected_scope, binding, maximum = family
    if target_scope != expected_scope:
        raise ValueError('Expected target_scope=' + expected_scope + ' for ' + item)
    if type(target_count) is not int or not 1 <= target_count <= maximum:
        raise ValueError('Invalid target count for ' + item)
    checkpoint()
    client = backend.ensure_client()
    if client is None or backend.client is not client:
        raise JobBlocked('Pipeline must reuse the backend sole owned client')
    client.material_backend = backend
    setattr(client, binding, backend)
    return module.run(client, backend.profile, item, target_count, out, checkpoint)
