"""Durable, world-scoped survey history for surface gravel expeditions."""

import json
import time
from pathlib import Path

SCHEMA_VERSION = 1
COMPLETE = {'empty', 'exhausted', 'blocked'}


class SurfaceGravelLedger:
    def __init__(self, path, server, dimension):
        self.path = Path(path)
        self.server = server
        self.dimension = dimension
        if self.path.exists():
            data = json.loads(self.path.read_text())
            if data.get('version') != SCHEMA_VERSION or not isinstance(data.get('entries'), list):
                raise ValueError('Unknown surface gravel route ledger; refusing to overwrite it')
            self.data = data
        else:
            self.data = {'version': SCHEMA_VERSION, 'entries': []}

    def covered(self, low, high, water_buffer):
        """Only skip a tile fully surveyed under at least today's water rule."""
        completed = [entry for entry in self.data['entries']
                     if entry.get('server') == self.server
                     and entry.get('dimension') == self.dimension
                     and entry.get('status') in COMPLETE
                     and (entry.get('status') != 'blocked'
                          or entry.get('retry_after_ms', 0) > int(time.time()*1000))
                     and entry.get('water_buffer', 0) >= water_buffer
                     and entry['low'][1] <= low[1] and entry['high'][1] >= high[1]]
        return bool(completed) and all(
            any(entry['low'][0] <= x <= entry['high'][0]
                and entry['low'][2] <= z <= entry['high'][2] for entry in completed)
            for x in range(low[0], high[0] + 1)
            for z in range(low[2], high[2] + 1))

    def visited_xy(self, low, high):
        """Frontier travel prefers genuinely new XZ ground, even after a policy change."""
        visited=[entry for entry in self.data['entries']
                 if entry.get('server')==self.server and entry.get('dimension')==self.dimension]
        return bool(visited) and all(
            any(entry['low'][0]<=x<=entry['high'][0]
                and entry['low'][2]<=z<=entry['high'][2] for entry in visited)
            for x in range(low[0],high[0]+1)
            for z in range(low[2],high[2]+1))

    def record(self, low, high, water_buffer, status, **facts):
        if status not in {'scanned', 'empty', 'exhausted', 'partial', 'interrupted', 'blocked'}:
            raise ValueError('Invalid surface gravel route status')
        now = int(time.time() * 1000)
        key = (self.server, self.dimension, list(low), list(high), water_buffer)
        previous = next((entry for entry in self.data['entries']
                         if (entry.get('server'), entry.get('dimension'), entry.get('low'),
                             entry.get('high'), entry.get('water_buffer')) == key), None)
        entry = previous if previous is not None else {
            'server': self.server, 'dimension': self.dimension,
            'low': list(low), 'high': list(high), 'water_buffer': water_buffer,
            'first_seen_ms': now,
        }
        entry.update(status=status, updated_ms=now, **facts)
        if previous is None:
            self.data['entries'].append(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + '.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))
        temporary.replace(self.path)
        return entry
