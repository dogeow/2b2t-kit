"""One-screen read-only summary of the running Kit for people and agents.

status.json carries ~100 keys, most of them protocol flags. This keeps what is needed to decide
the next step: is the game connected, where and how healthy is the player, what is running, and
whether the installed jars are newer than the ones the game actually loaded (restart needed).
"""
import json
from pathlib import Path
import re
import time
import zipfile

STALE_SECONDS = 3


def _installed_kit_version(game_dir):
    jars = sorted(Path(game_dir, 'mods').glob('twob2tkit-*.jar'))
    if len(jars) != 1:
        return None, len(jars)
    match = re.fullmatch(r'twob2tkit-(.+)\.jar', jars[0].name)
    return (match.group(1) if match else None), 1


def _installed_engine_version(game_dir):
    path = Path(game_dir, 'config/twob2tkit/runtime/twob2tkit-engine.jar')
    try:
        with zipfile.ZipFile(path) as jar:
            for line in jar.read('META-INF/MANIFEST.MF').decode('utf-8', 'replace').splitlines():
                if line.startswith('twob2tkit-Engine-Version:'):
                    return line.split(':', 1)[1].strip()
    except (OSError, KeyError, zipfile.BadZipFile):
        pass
    return None


def _pick(value, *keys):
    return {k: value[k] for k in keys if isinstance(value, dict) and k in value}


def summarize(game_dir, state, now=None):
    now = time.time() if now is None else now
    age = round(now - state.get('time', 0) / 1000, 1)
    kit, mod_jars = _installed_kit_version(game_dir)
    engine = _installed_engine_version(game_dir)
    out = {
        'age_seconds': age,
        'live': age <= STALE_SECONDS,
        'connected': bool(state.get('connected')),
        'screen': state.get('screen'),
        'game_paused': state.get('game_paused'),
        'versions': {
            'kit_running': state.get('kit_version'), 'kit_installed': kit,
            'engine_running': state.get('runtime_version'), 'engine_installed': engine,
        },
        'request': _pick(state, 'phase', 'op', 'detail'),
        'manual_movement': state.get('manual_movement'),
    }
    notes = []
    if not out['live']:
        notes.append('状态文件已过期：游戏可能没开或卡住，下面是最后一次记录')
    if mod_jars != 1:
        notes.append(f'mods 目录里有 {mod_jars} 个 Kit 主包，应只保留一个')
    if kit and state.get('kit_version') and kit != state.get('kit_version'):
        notes.append('已安装的主包与运行中的不同：需要完整重启游戏')
    if engine and state.get('runtime_version') and engine != state.get('runtime_version'):
        notes.append('已安装的引擎与运行中的不同：/twob2tkit reload 或重启后生效')
    if out['connected']:
        out['player'] = _pick(state, 'server', 'dimension', 'pos', 'health', 'food', 'air_supply', 'game_mode')
        out['recent_hurt'] = _pick(state, 'recent_attacker', 'recent_hurt_at')
        if state.get('recent_hurt_at'):
            out['recent_hurt']['seconds_ago'] = max(0, round(now - state['recent_hurt_at'] / 1000))
    job = state.get('material_job')
    if isinstance(job, dict) and (job.get('active') or job.get('phase')):
        out['material_job'] = _pick(job, 'active', 'title', 'done', 'total', 'phase')
    task = state.get('material_task')
    if isinstance(task, dict) and task.get('state') not in (None, '', 'done', 'idle'):
        out['material_task'] = _pick(task, 'id', 'state', 'detail', 'done', 'total')
        state_name, job_id = task.get('state'), task.get('id', '')
        # Mirrors MaterialJobProtocol: only "paused" can be resumed; blocked/failed/cancelled are terminal.
        if state_name == 'paused':
            notes.append(f'材料任务已暂停：确认安全后可 kit_cli.py materials resume --job-id {job_id}')
        elif state_name in ('blocked', 'failed'):
            notes.append('材料任务已终止（' + ('需要处理' if state_name == 'blocked' else '已停止')
                         + '）：先读 detail 处理原因，再新建任务；终止的任务不能 resume')
    idle = state.get('idle_activity')
    if isinstance(idle, dict) and idle.get('busy'):
        out['idle_activity'] = idle
    hold = state.get('safety_hold')
    if isinstance(hold, dict) and hold.get('active'):
        out['safety_hold'] = _pick(hold, 'reason', 'health', 'escape_result')
        notes.append('安全锁生效中：先处理安全锁，不要继续下达动作')
    if state.get('player_dead'):
        notes.append('角色已死亡')
    out['notes'] = notes
    return out


def read_status(root):
    return json.loads(Path(root, 'status.json').read_text())
