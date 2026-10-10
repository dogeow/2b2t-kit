"""Read-only material HUD: current carried output plus the last verified build count.

The same publisher serves the owning backend and an already-running older worker.
It never creates a lease, dispatches an action, or changes a task journal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

from job_progress import JobProgress
from material_plan import inventory_counts


class ItemNames:
    def __init__(self, automation):
        self.values = {}
        try:
            game = Path(automation).resolve().parents[2]
            version = json.loads((game / (game.name + '.json')).read_text())
            assets = game.parents[1] / 'assets'
            index = json.loads((assets / 'indexes' / (version['assetIndex']['id'] + '.json')).read_text())
            digest = index['objects']['minecraft/lang/zh_cn.json']['hash']
            data = (assets / 'objects' / digest[:2] / digest).read_bytes()
            if hashlib.sha1(data).hexdigest() == digest:
                self.values = json.loads(data)
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            pass  # Unknown names remain honest item IDs; no network fetch.

    def __call__(self, item):
        key = item.replace(':', '.', 1)
        return self.values.get('item.' + key, self.values.get('block.' + key, item))


def quantities_summary(request, status, inflight, state, name):
    """Absolute backpack counts, never depot hints or planned recipe output."""
    mode = request.get('mode')
    phase = status.get('phase') or '准备中'
    item, target, title = None, None, None
    if isinstance(inflight, dict) and inflight.get('job_id') == request.get('id'):
        operation, args = inflight.get('operation'), inflight.get('args', [])
        prefixes = {'run_pipeline': '制作 ', 'acquire': '采集 ', 'fetch': '取料 ',
                    'craft': '制作 ', 'smelt': '熔炼 ', 'harden': '固化 '}
        outputs = inflight.get('output_targets') or {}
        if operation == 'run_pipeline' and isinstance(args, list) and len(args) >= 3:
            # Depot-owned pipelines use another quantity scope; carried stock
            # cannot stand in for a confirmed depot finished-good total.
            if args[2] in ('absolute_backpack', 'absolute_backpack_total'):
                item, target = args[:2]
        elif operation in prefixes and isinstance(outputs, dict) and len(outputs) == 1:
            item, target = next(iter(outputs.items()))
        if isinstance(item, str) and type(target) is int and target > 0:
            title = prefixes[operation] + name(item)
        else:
            item, target = None, None
    if item is None and mode == 'item':
        targets = request.get('targets') or {}
        if len(targets) == 1:
            item, target = next(iter(targets.items()))
            title = '获取 ' + name(item)
    if item is not None and type(target) is int and target > 0:
        done = inventory_counts(state).get(item, 0)
        if mode == 'projection':
            matched, total = status.get('done'), status.get('total')
            if type(matched) is int and type(total) is int and 0 <= matched <= total and total > 0:
                phase = '地图 ' + str(matched) + '/' + str(total)
        return title, done, target, phase
    done, total = status.get('done'), status.get('total')
    if type(done) is not int or type(total) is not int or done < 0 or total < 0:
        return None
    return ('地图施工' if mode == 'projection' else '材料任务'), done, total, phase


class MaterialProgress:
    def __init__(self, request, automation, out, *, name=None):
        self.request, self.root, self.out = request, Path(automation), Path(out)
        self.name = name or ItemNames(automation)
        self.job = None
        self.last_read = 0

    def publish(self, state, *, now=None):
        now = time.time() if now is None else now
        if now - self.last_read < .25:
            return
        self.last_read = now
        try:
            status = json.loads((self.out / 'status.json').read_text())
            pending = self.out / 'inflight.json'
            inflight = json.loads(pending.read_text()) if pending.exists() else None
            context, lease = self.request['context'], state.get('supervision_lease') or {}
            valid = (status.get('id') == self.request['id'] and not status.get('terminal')
                     and status.get('state') != 'paused' and state.get('connected') is True
                     and state.get('manual_movement') is False
                     and state.get('world_session') == context['world_session']
                     and state.get('server', '').lower().removesuffix(':25565') == context['server'].lower().removesuffix(':25565')
                     and state.get('dimension') == context['dimension']
                     and type(state.get('time')) is int and -1000 <= now * 1000 - state['time'] <= 3000
                     and type(status.get('updated_at')) is int and -1000 <= now * 1000 - status['updated_at'] <= 5000
                     and lease.get('kind') == 'materials' and lease.get('world_session') == context['world_session']
                     and lease.get('job_session') == status.get('native_task_session')
                     and bool(status.get('native_task_session'))
                     and type(state.get('control_revision')) is int
                     and lease.get('revision') == state['control_revision'])
            summary = quantities_summary(self.request, status, inflight, state, self.name) if valid else None
            if summary is None:
                self.close()
                return
            title, done, total, phase = summary
            task = lease['job_session']
            if self.job is None or self.job.task != task or self.job.world != state['world_session']:
                self.close()
                self.job = JobProgress(self.root, state['world_session'], task, state['control_revision'], title, total, done)
            self.job.revision, self.job.title, self.job.total = state['control_revision'], title, total
            self.job.update(done=done, phase=phase)
            self.job.publish(state, now)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.close()  # Optional display cannot interrupt actions or safety.

    def close(self):
        if self.job is not None:
            self.job.close()
            self.job = None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--automation', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    request = json.loads(args.request.read_text())
    publisher = MaterialProgress(request, args.automation, args.out)
    try:
        while True:
            try:
                state = json.loads((args.automation / 'status.json').read_text())
                publisher.publish(state)
                status = json.loads((args.out / 'status.json').read_text())
                if status.get('terminal') or state.get('world_session') != request['context']['world_session']:
                    return 0
            except (OSError, ValueError, KeyError, TypeError):
                publisher.close()
            time.sleep(.25)
    finally:
        publisher.close()


if __name__ == '__main__':
    raise SystemExit(main())
