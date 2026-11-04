"""Verify observed flushing windows, not just successful source toggles.

Input frames carry monotonically increasing millisecond ``time`` values and a
``sources`` mapping of layer IDs to raw Minecraft air/water states. Sampling
uncertainty is retained: an interval's lower bound uses its first and last
observations, while its upper bound includes the two surrounding transitions.
The first and last partial intervals cannot earn completion credit.
"""
import math
import re

_WATER = re.compile(r'(?:Block\{minecraft:water\}|minecraft:water)\[level=(?:[0-9]|1[0-5])\]')


def _phase(state):
    if state in ('air', 'minecraft:air', 'Block{minecraft:air}'):
        return 'dry'
    if state == 'water' or isinstance(state, str) and _WATER.fullmatch(state):
        return 'wet'
    return 'unknown'


def analyze_clock_trace(frames, *, layers=None, minimum_dry_seconds=20,
                        minimum_wet_seconds=4, maximum_wet_seconds=12,
                        maximum_sample_gap_seconds=1.5, maximum_dry_blip_seconds=2,
                        minimum_wet_intervals=2, minimum_dry_intervals=1):
    """Return conservative per-layer evidence; this never operates the game.

    A passing result concerns only the supplied cells and observed time span.
    It does not prove whole-floor drainage, mob spawning, XP or loot transport.
    Those require separate current-world observations.
    """
    limits = (minimum_dry_seconds, minimum_wet_seconds, maximum_wet_seconds,
              maximum_sample_gap_seconds, maximum_dry_blip_seconds)
    if (any(isinstance(x, bool) or not isinstance(x, (int, float))
            or not math.isfinite(x) or x <= 0 for x in limits)
            or minimum_wet_seconds > maximum_wet_seconds
            or any(type(x) is not int or x < 1
                   for x in (minimum_wet_intervals, minimum_dry_intervals))):
        raise ValueError('Positive timing and interval requirements are required')
    if not isinstance(frames, list) or len(frames) < 3:
        raise ValueError('At least three complete observation frames are required')
    first = frames[0].get('sources') if isinstance(frames[0], dict) else None
    if not isinstance(first, dict) or not first:
        raise ValueError('Every frame must contain the expected source cells')
    expected = tuple(first) if layers is None else tuple(layers)
    if (not expected or len(set(expected)) != len(expected)
            or any(not isinstance(x, str) or not x for x in expected)):
        raise ValueError('Unique nonempty string layer IDs are required')
    times = []
    for frame in frames:
        if (not isinstance(frame, dict) or type(frame.get('time')) is not int
                or not isinstance(frame.get('sources'), dict)
                or any(layer not in frame['sources'] for layer in expected)):
            raise ValueError('Missing source cell or invalid millisecond timestamp')
        if times and frame['time'] <= times[-1]:
            raise ValueError('Frames must have distinct increasing timestamps')
        times.append(frame['time'])
    gaps = [{'after': a, 'before': b, 'seconds': (b-a)/1000}
            for a, b in zip(times, times[1:])
            if b-a > maximum_sample_gap_seconds*1000]
    result = {'passed': False, 'scope': 'supplied_source_cells_only',
              'observed_seconds': (times[-1]-times[0])/1000,
              'sampling_gaps': gaps, 'layers': {}}
    for layer in expected:
        phases = [_phase(frame['sources'][layer]) for frame in frames]
        # Retraction can briefly expose AIR before neighboring flowing water
        # reaches the source cell again. Such a bounded brief AIR gap earns no
        # dry-time credit: conservatively keep the entire tail WET. A sampling
        # gap or unknown cell can never be repaired by this rule.
        blips = []
        i = 1
        while i < len(phases)-1:
            if phases[i] != 'dry' or phases[i-1] != 'wet':
                i += 1
                continue
            j = i
            while j < len(phases) and phases[j] == 'dry':
                j += 1
            span = (times[j]-times[i-1])/1000 if j < len(times) else math.inf
            continuous = all(times[k]-times[k-1] <= maximum_sample_gap_seconds*1000
                             for k in range(i, min(j+1, len(times))))
            if j < len(phases) and phases[j] == 'wet' and continuous and span <= maximum_dry_blip_seconds:
                phases[i:j] = ['wet']*(j-i)
                blips.append({'first_air_at': times[i], 'last_air_at': times[j-1],
                              'upper_seconds': span, 'dry_credit_seconds': 0})
            i = j
        state = None
        first_seen = last_seen = previous_state_last_seen = None
        bounded_start = False
        intervals = []
        unknown = 0
        for frame, phase in zip(frames, phases):
            now = frame['time']
            unknown += phase == 'unknown'
            if last_seen is not None and now-last_seen > maximum_sample_gap_seconds*1000:
                state = None  # No interval can bridge unobserved time.
            if state is None:
                state, first_seen, last_seen = phase, now, now
                bounded_start = False
                continue
            if phase != state:
                if bounded_start and state != 'unknown':
                    intervals.append({'phase': state,
                                      'lower_seconds': (last_seen-first_seen)/1000,
                                      'upper_seconds': (now-previous_state_last_seen)/1000})
                previous_state_last_seen = last_seen
                bounded_start = state != 'unknown' and phase != 'unknown'
                state, first_seen = phase, now
            last_seen = now
        wet = [v for v in intervals if v['phase'] == 'wet']
        dry = [v for v in intervals if v['phase'] == 'dry']
        bad_wet = [v for v in wet if v['lower_seconds'] < minimum_wet_seconds
                   or v['upper_seconds'] > maximum_wet_seconds]
        bad_dry = [v for v in dry if v['lower_seconds'] < minimum_dry_seconds]
        passed = (not unknown and not gaps and not bad_wet and not bad_dry
                  and len(wet) >= minimum_wet_intervals
                  and len(dry) >= minimum_dry_intervals)
        result['layers'][layer] = {'passed': passed, 'unknown_samples': unknown,
                                   'complete_intervals': intervals,
                                   'dry_gaps_treated_as_wet': blips,
                                   'wet_intervals': len(wet), 'dry_intervals': len(dry),
                                   'invalid_wet_intervals': bad_wet,
                                   'short_dry_intervals': bad_dry}
    result['passed'] = all(v['passed'] for v in result['layers'].values())
    return result
