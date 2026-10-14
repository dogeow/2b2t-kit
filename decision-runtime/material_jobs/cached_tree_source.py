"""Prioritize current-world forest hints over a blind local wood frontier."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time

from kit_runtime.journal import write_json
from . import bobby_snow_cache as cache
from .resource_tree_trip import BIOMES, platform_input_ready, run as tree_trip
from .protocol import JobPaused

SPECIES = {'minecraft:spruce_log': 'spruce', 'minecraft:dark_oak_log': 'dark_oak'}


def outside_protected(candidate, boxes):
    x, z = candidate['tile']
    for box in boxes:
        low, high = box.get('min'), box.get('max')
        if (not isinstance(low, list) or not isinstance(high, list)
                or len(low) != 3 or len(high) != 3
                or any(type(v) is not int for v in low + high)):
            return False
        if not (x+95 < low[0] or x-64 > high[0] or z+95 < low[2] or z-64 > high[2]):
            return False
    return True


def locate(client, backend, species, out):
    """Cache parsing has no game actions; the sole owner keeps polling safety."""
    first = client.status()
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(cache.candidates, Path(client.root).parents[2],
                         first['server'], first['dimension'], first['pos'], max_candidates=12,
                         index_path=out/'derived-tree-index.json', biome_filter=BIOMES[species])
    try:
        while not future.done():
            backend.checkpoint()
            client.status()  # Refresh the existing heartbeat during potentially long disk reads.
            time.sleep(.15)
        rows = future.result()
        backend.checkpoint()
        current = client.status()
        if any(current.get(k) != first.get(k) for k in ('world_session', 'server', 'dimension')):
            raise JobPaused('Forest cache planning scope changed; hints discarded')
        return rows
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def acquire(backend, client, item, target, out):
    species = SPECIES.get(item)
    if (species is None or backend.request.get('mode') != 'projection'
            or type(target) is not int or not 1 <= target <= 128):
        return None
    if client is not backend.client:
        raise JobPaused('Cached forest lookup has a different material owner')
    first = client.status()
    if not platform_input_ready(first):
        return None
    out = Path(out)/'cached-tree-source'
    out.mkdir(parents=True, exist_ok=False)
    client.set_progress(phase='按缓存定位木料产地')
    try:
        rows = locate(client, backend, species, out)
    except cache.CacheUnavailable:
        return None
    protected = list(backend.profile.get('protected_regions', [])) + [first['projection_selection']]
    eligible = [r for r in rows if outside_protected(r, protected)]
    write_json(out/'candidates.json', eligible)
    if not eligible:
        return None
    # The shared trip still validates the selected MCA, current live species
    # roots, ordinary native chops, inventory gains and the saved-home return.
    return tree_trip(client.root, backend.request, eligible[0], species, target,
                     out/'trip', backend=backend)
