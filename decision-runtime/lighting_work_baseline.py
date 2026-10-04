"""Read retained complete native audits to restrict work, never to credit work."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

from lighting_cli import bounds, risk_counts, scan_cells
from material_jobs.protocol import server_key


class WorkBaselineBlocked(ValueError):
    pass


def identity(state):
    server = state.get('server')
    return {'server': server_key(server) if isinstance(server, str) else None, **{
        key: deepcopy(state.get(key)) for key in
        ('dimension', 'world_session', 'player_uuid', 'game_mode', 'projection_selection')}}


def current_identity(state, expected=None):
    """Require one fresh, idle native parking observation before selecting work."""
    value = identity(state)
    lease, safety = state.get('supervision_lease') or {}, state.get('supervision_safety') or {}
    task, keys = state.get('material_task') or {}, state.get('movement_keys') or {}
    position, anchor = state.get('pos'), lease.get('park_target')
    projection = value['projection_selection']
    if (type(state.get('time')) is not int or not -1000 <= time.time()*1000-state['time'] <= 3000
            or state.get('connected') is not True or state.get('health') != 20 or state.get('food', 0) < 18
            or state.get('manual_movement') is not False or state.get('screen')
            or state.get('under_water') is not False or state.get('game_mode') != 'survival'
            or any(state.get(key) is not True for key in ('flight', 'guard_armed', 'guard_pve_only'))
            or any(not isinstance(value[key], str) or not value[key]
                   for key in ('server', 'dimension', 'world_session', 'player_uuid'))
            or not isinstance(value['projection_selection'], dict)
            or not isinstance(value['projection_selection'].get('key'), str) or not value['projection_selection']['key']
            or any(not isinstance(projection.get(key), list) or len(projection[key]) != 3
                   or any(type(v) is not int for v in projection[key]) for key in ('min', 'max'))
            or type(state.get('control_revision')) is not int
            or lease.get('kind') != 'parking' or any(not isinstance(lease.get(key), str) or not lease[key]
                                                   for key in ('id', 'job_session'))
            or lease.get('world_session') != value['world_session']
            or lease.get('revision') != state['control_revision'] or lease.get('remote_finish') != 'guard'
            or safety.get('action') != 'KEEP_PVE_GUARD' or safety.get('lease') != lease['id']
            or safety.get('job_session') != lease['job_session']
            or not isinstance(position, list) or len(position) != 3
            or not isinstance(anchor, list) or len(anchor) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in position+anchor)
            or math.dist(position, anchor) > .6
            or not keys or any(v is not False for v in keys.values())
            or any(task.get(key) is not False for key in ('occupied', 'process_alive', 'cancelling'))
            or state.get('pending_scan') or state.get('native_task_session')
            or state.get('phase') not in ('parking', 'done', 'waiting', 'stopped', 'error')
            or any(state.get(key) for key in ('navigating', 'native_material_busy', 'printing', 'chopping',
                                            'borer_active', 'planter_active', 'feeder_active', 'fisher_active', 'guard_busy'))
            or any(state.get(key, {}).get('active') for key in ('build_job', 'concrete', 'gravel'))
            or state.get('professional_printer', {}).get('enabled')
            or (state.get('safety_hold') or {}).get('active')
            or expected is not None and value != expected):
        raise WorkBaselineBlocked('Directed work requires fresh same-identity idle native parking')
    return value


def validate(path, profile, original_out, current):
    """All registered regions and their original raw scans must be accounted for."""
    observed = current_identity(current)
    captured = {}

    def read(source, *, lines=False):
        source = Path(source)
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 8*1024*1024:
            raise WorkBaselineBlocked('Bounded retained work-baseline evidence unavailable')
        raw = source.read_bytes()
        captured[source] = raw
        value = [json.loads(row) for row in raw.splitlines() if row.strip()] if lines else json.loads(raw)
        if (lines and any(not isinstance(row, dict) for row in value)
                or not lines and not isinstance(value, dict)):
            raise WorkBaselineBlocked('Retained baseline evidence must contain native JSON objects')
        return value

    path = Path(path).resolve()
    if path == (Path(original_out)/'regions.json').resolve():
        raise WorkBaselineBlocked('Use a retained immutable baseline, not the currently changing journal')
    book = read(path)
    audits, regions = book.get('audits'), profile['regions']
    campaign = book.get('campaign')
    if (type(book.get('schema')) is not int or book['schema'] != 1
            or book.get('profile') != profile or book.get('world_session') != observed['world_session']
            or book.get('pending') is not None or book.get('coverage_complete') is not True
            or book.get('phase') not in ('audited', 'audited_with_remaining_risk')
            or type(book.get('cursor')) is not int or book['cursor'] != len(regions)
            or type(book.get('ai_calls')) is not int or book['ai_calls'] != 0
            or type(campaign) is not int or campaign < 1
            or not isinstance(audits, list) or len(audits) != len(regions)):
        raise WorkBaselineBlocked('Directed work needs the original full same-world/profile audit baseline')
    if observed['server'] != profile['server'] or observed['dimension'] != profile['dimension']:
        raise WorkBaselineBlocked('Current directed-work server/dimension differs')
    selected, counts, directories = [], [], set()
    for index, (audit, region) in enumerate(zip(audits, regions)):
        if (not isinstance(audit, dict) or type(audit.get('region_index')) is not int or audit['region_index'] != index
                or type(audit.get('campaign')) is not int or audit['campaign'] != campaign
                or audit.get('park_native_confirmed') is not True):
            raise WorkBaselineBlocked('Baseline audit indices/campaign/native parking are incomplete')
        directory = Path(audit['directory'])
        if (directory.is_symlink() or directory.parent.name != 'audit-'
                or directory.parent.parent.resolve() != Path(original_out).resolve()
                or directory.resolve() in directories):
            raise WorkBaselineBlocked('Baseline raw scan is outside the original audit journal')
        directories.add(directory.resolve())
        raw = read(directory/'current-region-audit.json')
        final = read(directory/'final-snapshot.json')
        events = read(directory/'events.jsonl', lines=True)
        low, high = bounds(region['min'], region['max'])
        volume = math.prod(b-a+1 for a, b in zip(low, high))
        try:
            host = tuple(int(v) for v in raw.get('kit_version', '').split('.'))
        except (AttributeError, ValueError):
            host = ()
        lease, parked = raw.get('supervision_lease') or {}, final.get('supervision_lease') or {}
        if (host < (2026, 10, 4, 1) or identity(raw) != observed or identity(final) != observed
                or raw.get('connected') is not True or raw.get('phase') != 'done'
                or type(raw.get('id')) is not str or not raw['id']
                or any(type(raw.get(key)) is not int for key in ('control_revision', 'scan_start_revision',
                           'scan_end_revision', 'scan_cells_read', 'scan_total_cells', 'scan_started_at', 'scan_ended_at'))
                or raw['control_revision'] != raw['scan_start_revision'] or raw['control_revision'] != raw['scan_end_revision']
                or raw['scan_cells_read'] != volume or raw['scan_total_cells'] != volume
                or not 0 < raw['scan_started_at'] <= raw['scan_ended_at']
                or audit.get('observed_at') != raw['scan_ended_at']
                or lease.get('kind') != 'materials' or not lease.get('job_session')
                or lease.get('world_session') != observed['world_session'] or lease.get('revision') != raw['control_revision']
                or parked.get('kind') != 'parking' or parked.get('id') != audit.get('parking_lease')
                or parked.get('id') != lease.get('id') or parked.get('job_session') != lease['job_session']
                or parked.get('revision') != final.get('control_revision')
                or final.get('control_revision') != audit.get('control_revision') or final.get('phase') != 'parking'
                or final.get('connected') is not True or final.get('health') != 20):
            raise WorkBaselineBlocked('Complete current-server raw scan or original parking scope differs')
        terminal = [event for event in events if event.get('request_id') == raw['id']]
        if (len(terminal) != 1 or any(event.get('op') not in ('scan', 'snapshot', 'navigate', 'material_session', 'material_job_park')
                or event.get('phase') not in (None, 'done') or event.get('inventory_delta') != {}
                or event.get('world_session') != observed['world_session']
                or event.get('op') == 'navigate' and event.get('params', {}).get('air_only') is not True
                for event in events)):
            raise WorkBaselineBlocked('Original audit has unknown/mutating actions or lacks the exact raw scan receipt')
        event = terminal[0]
        if (event.get('op') != 'scan' or event.get('phase') != 'done'
                or event.get('params', {}).get('min') != list(low) or event.get('params', {}).get('max') != list(high)
                or event.get('params', {}).get('details') is not True
                or event.get('params', {}).get('task_session') != lease['job_session']
                or event.get('revision_before') != raw['control_revision'] or event.get('revision_after') != raw['control_revision']
                or event.get('health_before') != 20 or event.get('health_after') != 20):
            raise WorkBaselineBlocked('Retained scan request bounds, task or revision differ')
        cells = scan_cells(raw, low, high, observed['world_session'])
        for row in cells.values():
            if (any(type(row.get(key)) is not bool for key in ('solid', 'fluid', 'block_entity', 'passable',
                       'replaceable', 'zombie_spawn_floor', 'zombie_block_light_risk'))
                    or any(type(row.get(key)) is not int or not 0 <= row[key] <= 15
                           for key in ('spawn_block_light', 'monster_spawn_block_light_limit'))):
                raise WorkBaselineBlocked('Retained scan lacks complete native lighting details')
            if row['zombie_block_light_risk'] != (row['zombie_spawn_floor']
                    and row['spawn_block_light'] <= row['monster_spawn_block_light_limit']):
                raise WorkBaselineBlocked('Retained scan has contradictory native lighting risk')
        actual = risk_counts(cells, profile['protected'])
        if any(type(audit.get(key)) is not int or audit[key] != value for key, value in actual.items()):
            raise WorkBaselineBlocked('Baseline dark counts differ from the original actual scan')
        counts.append(actual['unprotected_dark_floor'])
        if counts[-1] > 0:
            selected.append(index)
    if any(source.read_bytes() != value for source, value in captured.items()):
        raise WorkBaselineBlocked('Retained baseline/raw evidence changed during validation')
    return {'schema': 1, 'mode': 'all_baseline_unprotected_dark_regions', 'baseline_path': str(path),
            'baseline_sha256': hashlib.sha256(captured[path]).hexdigest(), 'baseline_campaign': campaign,
            'identity': observed, 'selected_indices': selected, 'baseline_dark_counts': counts,
            'complete_baseline_regions': len(regions), 'placement_credit': 0,
            'evidence_sha256': {str(source.resolve()): hashlib.sha256(value).hexdigest() for source, value in captured.items()},
            'final_audit_scope': 'all_registered_regions', 'goal_complete': False}
