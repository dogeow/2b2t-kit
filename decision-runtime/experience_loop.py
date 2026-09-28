"""Offline, advisory-only experience loop for native Kit evidence.

Only allowlisted categories reach the database or the export. In particular,
Jev's AREA-mining choice is *advice*, not an executed recovery action. This
module never writes to the automation bridge or changes the live game.
"""

import argparse
from collections import deque
import hashlib
import hmac
import io
import json
import math
import os
import secrets
import sqlite3
import time
from pathlib import Path


MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_LINE_BYTES = 16 * 1024
MAX_PAVING_FILES = 2000
MAX_LOG_ROWS = 2000
MAX_EXAMPLES = 10000
MIN_DISTINCT_RUNS = 3
CAUSES = {'aim', 'mine', 'move', 'server_ack', 'pipeline_ack'}
PHASES = {'SURVEY', 'ENTER', 'TRANSFER', 'LOWER_TO_TOP', 'DIG', 'HORIZONTAL',
          'RETURN', 'VERIFY', 'DONE', 'BLOCKED'}
TOOL_CLASSES = {'pickaxe', 'shovel', 'axe', 'mining_tool', 'other', 'empty'}
BLOCK_CLASSES = {'stone', 'ore', 'soil', 'wood', 'liquid', 'protected', 'other', 'none'}
INVENTORY_BANDS = {'full', 'near_full', 'roomy'}
HEALTH_BANDS = {'healthy', 'reduced', 'critical'}
ACKS = {'none', 'pending', 'timeout', 'rejected'}
MINING_CHOICES = {'pause', 'wait_once', 'retry_once', 'rescan'}
MINING_SOURCES = {'jev', 'cache', 'local'}
PAVING_BLOCKERS = {'nearby_entity', 'vertical_pose_unconfirmed',
                   'direct_vertical_pose_lost', 'player_body_after_reposition',
                   'player_body_overlap', 'player_body_after_approach'}
RECOVERY_ACTIONS = {'rescan', 'replan', 'fetch_supply', 'craft_planks',
                    'resume_after_supply'}
MINING_RESULTS = {
    # These are client-side observations after an explicit restart, not a
    # server-acknowledged action receipt; movement could also be manual.
    'post_restart_observed_target_air': 'observed_target_air_after_restart',
    'post_restart_confirmed_column_progress': 'observed_column_progress_after_restart',
    'post_restart_movement_progress': 'observed_movement_after_restart',
    'post_restart_no_confirmed_progress': 'observed_no_progress',
    'post_restart_re_stalled': 'observed_re_stall',
}


def _enum(value, options):
    return value if isinstance(value, str) and value in options else None


def _read_json_lines(path):
    """Read a bounded, complete-line tail of an append-only or rotated log."""
    path = Path(path)
    try:
        if not path.is_file():
            return
        with path.open('rb') as stream:
            size = stream.seek(0, os.SEEK_END)
            offset = max(0, size - MAX_SOURCE_BYTES)
            stream.seek(offset)
            tail = stream.read(MAX_SOURCE_BYTES)
            if offset:
                first_line_end = tail.find(b'\n')
                if first_line_end < 0:
                    return
                tail = tail[first_line_end + 1:]
            if tail and not tail.endswith(b'\n'):
                last_line_end = tail.rfind(b'\n')
                if last_line_end < 0:
                    return
                tail = tail[:last_line_end + 1]
            recent = deque(maxlen=MAX_LOG_ROWS)
            for line in io.BytesIO(tail):
                if len(line) > MAX_LINE_BYTES:
                    continue
                try:
                    row = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(row, dict):
                    recent.append(row)
            yield from recent
    except OSError:
        return  # A rotating or temporarily absent live log is not evidence.


def _block_class(state):
    if not isinstance(state, str) or len(state) > 160:
        return 'other'
    name = state.lower()
    if any(part in name for part in ('gravel', 'sand', 'dirt', 'grass', 'clay')):
        return 'soil'
    if any(part in name for part in ('stone', 'deepslate', 'tuff', 'brick', 'quartz')):
        return 'stone'
    if any(part in name for part in ('log', 'wood', 'plank')):
        return 'wood'
    return 'other'


def _nonnegative_int(value):
    return type(value) is int and 0 <= value <= 1_000_000_000


def _timestamp_ns(value):
    return type(value) is int and 0 < value < 100_000_000_000_000_000_000


def _tail_only(path):
    try:
        return path is not None and Path(path).is_file() and Path(path).stat().st_size > MAX_SOURCE_BYTES
    except OSError:
        return False


class _PavingScanner:
    """One live bounded directory cursor, including newly created world folders."""

    def __init__(self, root):
        self.worlds = os.scandir(root)
        self.cells = None

    def next_entry(self):
        if self.cells is not None:
            try:
                entry = next(self.cells)
            except StopIteration:
                self.cells.close()
                self.cells = None
                return None
            return (Path(entry.path) if entry.name.endswith('.json')
                    and entry.is_file(follow_symlinks=False) else None)
        world = next(self.worlds)
        if world.is_dir(follow_symlinks=False):
            self.cells = os.scandir(world.path)
        return None

    def close(self):
        if self.cells is not None:
            self.cells.close()
            self.cells = None
        self.worlds.close()


class ExperienceStore:
    """Small local SQLite store. Ranking is a report, never a control input."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS examples(
                id TEXT PRIMARY KEY, domain TEXT NOT NULL, context TEXT NOT NULL,
                advised_action TEXT, executed_action TEXT, label TEXT NOT NULL,
                evidence TEXT NOT NULL, run_id TEXT, created_ms INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS examples_context ON examples(domain, context, executed_action);
        ''')
        if self.db.execute("SELECT value FROM metadata WHERE key='salt'").fetchone() is None:
            self.db.execute("INSERT INTO metadata VALUES('salt', ?)", (secrets.token_hex(32),))
            self.db.commit()
        self.salt = bytes.fromhex(self.db.execute(
            "SELECT value FROM metadata WHERE key='salt'").fetchone()[0])
        self._paving_scanners = {}

    def close(self):
        for scanner in self._paving_scanners.values():
            scanner.close()
        self._paving_scanners.clear()
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _opaque(self, text):
        return hmac.new(self.salt, str(text).encode('utf-8'), hashlib.sha256).hexdigest()

    def _insert(self, source, identity, domain, context, advised, executed, label,
                evidence, run=None):
        # All fields except opaque identifiers are composed from fixed local enums.
        encoded = json.dumps(context, sort_keys=True, separators=(',', ':'))
        self.db.execute('''INSERT OR IGNORE INTO examples VALUES(?,?,?,?,?,?,?,?,?)''',
                        (self._opaque(source + '\0' + identity), domain, encoded, advised,
                         executed, label, evidence,
                         self._opaque(source + '\0' + str(run)) if run else None,
                         int(time.time() * 1000)))

    def _finish(self):
        count = self.db.execute('SELECT count(*) FROM examples').fetchone()[0]
        if count > MAX_EXAMPLES:
            self.db.execute('''DELETE FROM examples WHERE id IN
                (SELECT id FROM examples ORDER BY created_ms, id LIMIT ?)''',
                            (count - MAX_EXAMPLES,))
        self.db.commit()

    def count(self):
        return self.db.execute('SELECT count(*) FROM examples').fetchone()[0]

    def ingest_mining(self, path):
        """Pair Kit's prompt/decision/outcome by random decision ID, never by coordinates."""
        groups = {}
        for row in _read_json_lines(path):
            decision_id = row.get('decision_id')
            kind = _enum(row.get('kind'), {'prompt_summary', 'decision', 'outcome'})
            if (not isinstance(decision_id, str) or len(decision_id) > 64
                    or not kind or not isinstance(row.get('data'), dict)):
                continue
            groups.setdefault(decision_id, {})[kind] = row['data']
        before = self.count()
        for decision_id, parts in groups.items():
            if not all(k in parts for k in ('prompt_summary', 'decision', 'outcome')):
                continue
            prompt, decision, outcome = (parts[k] for k in
                                         ('prompt_summary', 'decision', 'outcome'))
            incident = prompt.get('incident')
            if not isinstance(incident, dict):
                continue
            context = {
                'cause': _enum(incident.get('cause'), CAUSES),
                'phase': _enum(incident.get('phase'), PHASES),
                'tool': _enum(incident.get('tool_class'), TOOL_CLASSES),
                'block': _enum(incident.get('block_class'), BLOCK_CLASSES),
                'inventory': _enum(incident.get('inventory_band'), INVENTORY_BANDS),
                'health': _enum(incident.get('health_band'), HEALTH_BANDS),
                'server_ack': _enum(incident.get('server_ack'), ACKS),
                'advice_source': _enum(decision.get('source'), MINING_SOURCES),
            }
            seconds = incident.get('no_progress_seconds')
            if (any(v is None for v in context.values()) or type(seconds) is not int
                    or not 0 <= seconds <= 600):
                continue
            context['stall_seconds_band'] = 'short' if seconds < 10 else 'medium' if seconds < 30 else 'long'
            choice = _enum(decision.get('choice'), MINING_CHOICES)
            if (choice is None or outcome.get('choice') != choice
                    or not isinstance(prompt.get('candidates'), dict)
                    or choice not in prompt['candidates']):
                continue
            result = _enum(outcome.get('outcome'), set(MINING_RESULTS))
            if result is None:
                continue  # Paused, stale, world-changed and incomplete are censored.
            self._insert('mining', decision_id, 'area_mining_stall', context,
                         choice, None, MINING_RESULTS[result], 'native_post_restart_observation')
        self._finish()
        return self.count() - before

    def ingest_paving(self, journal_dir, blocker_log=None):
        """Import confirmed final cells and guard stops; keep raw site/position out."""
        journal_dir = Path(journal_dir) if journal_dir is not None else None
        before = self.count()
        files = []
        if journal_dir is not None and journal_dir.is_dir():
            key = str(journal_dir.resolve())
            scanner = self._paving_scanners.get(key)
            if scanner is None:
                try:
                    scanner = self._paving_scanners[key] = _PavingScanner(journal_dir)
                except OSError:
                    scanner = None
            if scanner is not None:
                # Count every filesystem entry, including non-JSON files and
                # world directories. One invocation never traverses more than
                # this budget; the next watch tick resumes the open iterator.
                for _ in range(MAX_PAVING_FILES):
                    try:
                        candidate = scanner.next_entry()
                    except (StopIteration, OSError):
                        scanner.close()
                        self._paving_scanners.pop(key, None)
                        break
                    if candidate is not None:
                        files.append(candidate)
        for path in files:
            try:
                if path.stat().st_size > MAX_LINE_BYTES:
                    continue
                row = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            if (not isinstance(row, dict) or row.get('schema') != 1
                    or row.get('phase') != 'complete'
                    or not isinstance(row.get('pos'), list)
                    or len(row['pos']) != 3
                    or not all(type(n) is int for n in row['pos'])
                    or not isinstance(row.get('receipts'), list)):
                continue
            receipts = [r for r in row['receipts'] if isinstance(r, dict)]
            phases = [r.get('phase') for r in receipts]
            required = ['mine_intent', 'mined', 'recovered', 'place_intent', 'complete']
            if not all(phase in phases for phase in required):
                continue
            if phases.index('mine_intent') >= phases.index('mined') or phases.index('mined') >= phases.index('recovered') or phases.index('recovered') >= phases.index('place_intent') or phases.index('place_intent') >= phases.index('complete'):
                continue
            if not any(r.get('phase') == 'mined' and r.get('server_air') is True
                       for r in receipts if isinstance(r, dict)):
                continue
            if not any(r.get('phase') == 'recovered' and _nonnegative_int(r.get('inventory_after'))
                       for r in receipts if isinstance(r, dict)):
                continue
            final = receipts[phases.index('complete')]
            if final.get('actual') != row.get('expected') or not _nonnegative_int(final.get('material_after')):
                continue
            context = {'old_block': _block_class(row.get('actual')),
                       'new_block': _block_class(row.get('expected')),
                       'phase': 'complete'}
            source_id = str(path.resolve()) + '\0' + str(row.get('updated_at_ns'))
            self._insert('paving', source_id, 'guarded_paving', context, None,
                         'pave_one', 'verified_complete', 'native_cell_receipts',
                         run=row.get('world_session'))
        if blocker_log is not None:
            for row in _read_json_lines(blocker_log):
                kind = _enum(row.get('kind'), PAVING_BLOCKERS)
                phase = _enum(row.get('journal_phase'), {'recovered', 'mine_intent', 'mined'})
                cell, at = row.get('cell'), row.get('at_ns')
                if (kind is None or phase is None or not isinstance(cell, list)
                        or len(cell) != 3 or not all(type(n) is int for n in cell)
                        or not _timestamp_ns(at)):
                    continue
                context = {'blocker': kind, 'phase': phase,
                           'nearby': 'present' if isinstance(row.get('nearby'), list) and row['nearby'] else 'none'}
                self._insert('paving_blocker', str(at) + ':' + str(cell), 'guarded_paving',
                             context, None, None, 'guard_blocked', 'local_guard_observation')
        self._finish()
        return self.count() - before

    def ingest_build_events(self, path):
        """Executed supervisor recoveries are the only current rankable examples."""
        before = self.count()
        for row in _read_json_lines(path):
            if row.get('kind') != 'recovery_observed':
                continue
            action = _enum(row.get('action'), RECOVERY_ACTIONS)
            job = row.get('job')
            if action is None or not isinstance(job, str) or not 1 <= len(job) <= 128:
                continue
            prior, after = row.get('before'), row.get('after')
            if not isinstance(prior, dict) or not isinstance(after, dict):
                continue
            a, b = prior.get('matched'), after.get('matched')
            if not _nonnegative_int(a) or not _nonnegative_int(b):
                continue
            context = {'stall_kind': 'server_wait' if prior.get('waiting_for_server') is True
                       else 'materials' if prior.get('deficits') else 'navigation' if prior.get('blocked_blocks', 0)
                       else 'placement',
                       'phase': 'inactive' if prior.get('active') is False else 'active'}
            # A supervisor success is acknowledgement plus gain. Check the gain
            # again here; retain no-progress attempts as an uncertainty veto.
            stock_before, stock_after = prior.get('material_stock'), after.get('material_stock')
            stock_gain = (isinstance(stock_before, dict) and isinstance(stock_after, dict)
                          and any(_nonnegative_int(value) and value > stock_before.get(item, 0)
                                  for item, value in stock_after.items()
                                  if _nonnegative_int(stock_before.get(item, 0))))
            supply = after.get('native_supply')
            supply_gain = (isinstance(supply, dict) and supply.get('phase') == 'done'
                           and isinstance(supply.get('taken'), dict)
                           and any(_nonnegative_int(n) and n > 0 for n in supply['taken'].values()))
            gain = (supply_gain if action == 'fetch_supply' else stock_gain if action == 'craft_planks'
                    else b > a)
            success = row.get('success') is True and gain
            label = 'confirmed_progress' if success else 'unresolved_or_no_progress'
            # IDs may contain server/job data: HMAC locally, never export.
            identity = str(row.get('time')) + '\0' + job + '\0' + action
            self._insert('build_recovery', identity, 'projection_recovery', context,
                         None, action, label, 'native_supervisor_receipt' if success else 'no_positive_receipt',
                         run=job)
        self._finish()
        return self.count() - before

    def rankings(self):
        """No live action is returned; sparse, mixed or unsafe evidence abstains."""
        rows = self.db.execute('''SELECT context, executed_action, label, run_id
            FROM examples WHERE domain='projection_recovery' ORDER BY context, executed_action''').fetchall()
        groups = {}
        for context, action, label, run_id in rows:
            group = groups.setdefault((context, action), {'wins': set(), 'uncertain': set()})
            if run_id is None:
                group['uncertain'].add('unknown_run')
            elif label == 'confirmed_progress':
                group['wins'].add(run_id)
            else:
                group['uncertain'].add(run_id)
        results = []
        for (context, action), group in sorted(groups.items()):
            wins, uncertain = group['wins'], group['uncertain']
            ready = len(wins) >= MIN_DISTINCT_RUNS and not uncertain
            results.append({'context': json.loads(context), 'candidate': action,
                            'confirmed_runs': len(wins), 'uncertain_runs': len(uncertain),
                            'status': 'candidate_for_human_review' if ready else 'abstain'})
        results.sort(key=lambda row: (json.dumps(row['context'], sort_keys=True),
                                      row['status'] != 'candidate_for_human_review',
                                      -row['confirmed_runs'], row['candidate']))
        context_rank = {}
        for row in results:
            key = json.dumps(row['context'], sort_keys=True)
            if row['status'] == 'candidate_for_human_review':
                context_rank[key] = context_rank.get(key, 0) + 1
                row['evidence_rank'] = context_rank[key]
            else:
                row['evidence_rank'] = None
        return results

    def export(self, path):
        """Export fixed, deidentified labels; no paths, identifiers, raw logs or time."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.db.execute('''SELECT domain, context, advised_action, executed_action, label, evidence
            FROM examples ORDER BY created_ms, id''').fetchall()
        with path.open('w', encoding='utf-8') as stream:
            for domain, context, advised, executed, label, evidence in rows:
                sample = {'schema': 1, 'domain': domain, 'context': json.loads(context),
                          'advice': advised, 'executed_action': executed,
                          'label': label, 'evidence': evidence,
                          'training_use': 'recovery_candidate' if domain == 'projection_recovery'
                          else 'diagnosis_only', 'advice_caused_outcome': False}
                stream.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + '\n')
        return len(rows)


def ingest_sources(store, mining_log=None, paving_dir=None, paving_blockers=None,
                   build_events=None):
    """One idempotent read-only pass; returns only category counts."""
    result = {'tail_only_sources': [name for name, path in
                                   (('mining_log', mining_log),
                                    ('paving_blockers', paving_blockers),
                                    ('build_events', build_events)) if _tail_only(path)]}
    if mining_log is not None:
        result['area_mining_stalls'] = store.ingest_mining(mining_log)
    if paving_dir is not None or paving_blockers is not None:
        result['guarded_paving'] = store.ingest_paving(paving_dir, paving_blockers)
    if build_events is not None:
        result['projection_recoveries'] = store.ingest_build_events(build_events)
    result['stored'] = store.count()
    return result


def watch_sources(store, sources, *, interval_seconds, cycles, sleep=time.sleep,
                  on_progress=None):
    """Explicit bounded local observation; no callbacks into Minecraft or models."""
    if not 5 <= interval_seconds <= 300 or not 1 <= cycles <= 1440:
        raise ValueError('Watch interval or cycle budget is outside the safe bound')
    added = 0
    previous_tails = None
    for index in range(cycles):
        result = ingest_sources(store, **sources)
        new = sum(result.get(key, 0) for key in
                  ('area_mining_stalls', 'guarded_paving', 'projection_recoveries'))
        added += new
        tails = result['tail_only_sources']
        if (new or (tails and tails != previous_tails)) and on_progress is not None:
            on_progress({'new': new, 'stored': result['stored'], 'tail_only_sources': tails})
        previous_tails = tails
        if index + 1 < cycles:
            sleep(interval_seconds)
    return {'cycles': cycles, 'new': added, 'stored': store.count(),
            'tail_only_sources': previous_tails or []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', required=True, type=Path, help='Explicit local SQLite destination')
    sub = parser.add_subparsers(dest='command', required=True)
    ingest = sub.add_parser('ingest', help='Read local evidence without controlling Minecraft')
    ingest.add_argument('--mining-log', type=Path)
    ingest.add_argument('--paving-dir', type=Path)
    ingest.add_argument('--paving-blockers', type=Path)
    ingest.add_argument('--build-events', type=Path)
    watch = sub.add_parser('watch', help='Explicit, bounded local observation; Ctrl+C stops')
    for option in ('mining-log', 'paving-dir', 'paving-blockers', 'build-events'):
        watch.add_argument('--' + option, type=Path)
    watch.add_argument('--interval-seconds', type=int, default=15)
    watch.add_argument('--minutes', type=int, default=30)
    sub.add_parser('report', help='Show cautious offline candidate rankings')
    export = sub.add_parser('export', help='Write deidentified JSONL labels')
    export.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == 'watch':
        if not 1 <= args.minutes <= 120:
            parser.error('--minutes must be between 1 and 120')
        if not 5 <= args.interval_seconds <= 300:
            parser.error('--interval-seconds must be between 5 and 300')
        sources = {'mining_log': args.mining_log, 'paving_dir': args.paving_dir,
                   'paving_blockers': args.paving_blockers,
                   'build_events': args.build_events}
        if all(path is None for path in sources.values()):
            parser.error('watch requires at least one explicit source')
    with ExperienceStore(args.store) as store:
        if args.command == 'ingest':
            result = ingest_sources(store, args.mining_log, args.paving_dir,
                                    args.paving_blockers, args.build_events)
        elif args.command == 'watch':
            cycles = math.ceil(args.minutes * 60 / args.interval_seconds)
            try:
                result = watch_sources(store, sources, interval_seconds=args.interval_seconds,
                                       cycles=cycles,
                                       on_progress=lambda event: print(json.dumps(event), flush=True))
            except KeyboardInterrupt:
                result = {'stopped': 'user_interrupt', 'stored': store.count()}
        elif args.command == 'report':
            result = {'stored': store.count(), 'rankings': store.rankings()}
        else:
            result = {'exported': store.export(args.output)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
