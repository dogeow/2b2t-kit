"""Resume a guarded game job only after real macOS input has gone quiet."""

import json
import math
import re
import subprocess
import time
from pathlib import Path


def parse_hid_idle_seconds(output):
    match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', output)
    return int(match.group(1)) / 1_000_000_000 if match else None


def mac_hid_idle_seconds():
    result = subprocess.run(['ioreg', '-c', 'IOHIDSystem', '-d', '4'],
                            capture_output=True, text=True, timeout=4)
    return parse_hid_idle_seconds(result.stdout) if result.returncode == 0 else None


def resume_ready(state, expected_world, idle_seconds, stable_seconds, bounds):
    pos = state.get('pos')
    return bool(state.get('connected') and state.get('world_session') == expected_world
                and pos and len(pos) == 3 and pos[1] >= 82
                and bounds[0][0]-12 <= pos[0] <= bounds[0][1]+12
                and bounds[1][0]-12 <= pos[2] <= bounds[1][1]+12
                and state.get('health', 0) >= 19
                and state.get('air_supply', 0) >= 295
                and not state.get('under_water')
                and not state.get('screen')
                and not state.get('manual_movement')
                and not state.get('safety_hold', {}).get('active')
                and idle_seconds is not None and idle_seconds >= 5
                and stable_seconds >= 5)


def wait_for_quiet_player(automation_root, expected_world, bounds,
                          timeout_seconds=180):
    root = Path(automation_root)
    deadline = time.monotonic() + timeout_seconds
    last_pos = None
    stable_since = time.monotonic()
    while time.monotonic() < deadline:
        state = json.loads((root / 'status.json').read_text())
        if time.time() * 1000 - state.get('time', 0) > 3000:
            raise RuntimeError('Game status became stale during manual handoff')
        if (not state.get('connected') or state.get('world_session') != expected_world
                or state.get('health', 0) < 19
                or state.get('safety_hold', {}).get('active')):
            raise RuntimeError('Manual handoff changed world or safety state')
        pos = state.get('pos')
        if (last_pos is None or not pos or
                math.dist(pos, last_pos) > .05):
            stable_since = time.monotonic()
        last_pos = pos
        idle = mac_hid_idle_seconds()
        if resume_ready(state, expected_world, idle,
                        time.monotonic()-stable_since, bounds):
            return state
        time.sleep(.5)
    raise TimeoutError('Player input did not become quiet within the bounded wait')
