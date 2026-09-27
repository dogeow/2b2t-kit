"""Resume acknowledged furnace batches without reloading ingredients or guessing progress."""
import json
import time
from pathlib import Path

from furnace_batches import collect, distribution, load


def inspect_batch(journal, world, positions, source, output, amount):
    """Read-only preflight, before any restocking or navigation on a resumed run."""
    job = json.loads(Path(journal).read_text())
    if job.get('world_session') != world:
        raise RuntimeError('Reconfirm smelting ownership after a world transition')
    if any(job.get(k) != v for k, v in (('source', source), ('output', output), ('amount', amount))):
        raise RuntimeError('Existing smelting plan differs; do not restart it')
    expected = [(list(pos), n) for pos, n in zip(positions, distribution(amount, len(positions))) if n]
    actual = job.get('furnaces', [])
    if [(e.get('pos'), e.get('amount')) for e in actual] != expected:
        raise RuntimeError('Smelting receipts do not cover the expected bank and quantity')
    if any(e.get('stage') not in ('loaded', 'collected') for e in actual):
        raise RuntimeError('Partially loaded furnace requires inspection; do not restock or replay')
    if job.get('complete') and any(e['stage'] != 'collected' for e in actual):
        raise RuntimeError('Smelting completion lacks collection receipts')
    return job


def load_or_resume(client, positions, source, output, amount, journal):
    if Path(journal).exists():
        return inspect_batch(journal, client.world, positions, source, output, amount)
    return load(client, positions, source, output, amount, journal)


def wait_collect(client, journal, *, maximum=900, initial_delay=0, poll_interval=20):
    """Keep native safety observations live while waiting, never reload a timed-out batch."""
    if maximum <= 0 or initial_delay < 0 or poll_interval <= 0:
        raise ValueError('Smelting wait limits must be positive')
    deadline = time.monotonic() + maximum
    next_check = time.monotonic() + initial_delay
    while True:
        state = client.status()
        if state.get('health', 0) < 19:
            raise RuntimeError('Pause smelting attendance and recover health')
        now = time.monotonic()
        if now >= deadline:
            raise RuntimeError('Smelting is not complete; preserve the furnace journal')
        if now >= next_check:
            if collect(client, journal):
                return
            next_check = time.monotonic() + poll_interval
        time.sleep(.5)
