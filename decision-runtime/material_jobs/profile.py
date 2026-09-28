"""Per-world material infrastructure. Coordinates are data, never task-specific code."""
import hashlib
import json
import math
from pathlib import Path

from .protocol import JobBlocked, server_key


def profile_path(automation, context):
    scope = server_key(context['server']) + '|' + context['dimension']
    return Path(automation).parent / 'material-profiles' / (hashlib.sha256(scope.encode()).hexdigest()[:20] + '.json')


def point(value):
    return (isinstance(value, list) and len(value) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in value))


def load(automation, context):
    automation = Path(automation)
    path = profile_path(automation, context)
    profile = json.loads(path.read_text()) if path.exists() else {}
    if profile and (server_key(profile.get('server')) != server_key(context['server'])
                    or profile.get('dimension') != context['dimension']):
        raise JobBlocked('材料工位配置属于其他服务器或维度')
    config_path = automation.parent.parent / 'twob2tkit.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    sources = []
    for row in config.get('projectionSupplySources', []):
        if (server_key(row.get('server')) == server_key(context['server'])
                and row.get('dimension') == context['dimension']
                and all(type(row.get(k)) is int for k in ('x', 'y', 'z'))):
            p = [row[k] for k in ('x', 'y', 'z')]
            if p not in sources:
                sources.append(p)
    # An explicit approved subset can avoid stale portable-box records. It must
    # still be registered as an approved supply source in Kit.
    if 'depots' in profile:
        if not all(point(p) and p in sources for p in profile['depots']):
            raise JobBlocked('材料仓库未登记在 Kit 允许取料的仓库中')
    else:
        profile['depots'] = sources
    game = automation.parents[2]
    jar = profile.get('recipe_jar')
    if jar is None:
        candidates = [p for p in game.glob('*.jar') if p.stem == game.name]
        if len(candidates) != 1:
            raise JobBlocked('无法确定当前版本配方文件，请设置材料工位的 recipe_jar')
        jar = str(candidates[0])
    if not Path(jar).is_file():
        raise JobBlocked('当前版本的配方文件不存在')
    if type(profile.get('projection_jev_advice', False)) is not bool:
        raise JobBlocked('投影 Jev 建议开关必须为 true 或 false')
    profile.setdefault('projection_jev_advice', False)
    for key in ('workbench', 'workbench_staging', 'supply_staging', 'park_target', 'ender_chest', 'shulker_pad'):
        if key in profile and not point(profile[key]):
            raise JobBlocked('无效工位坐标：' + key)
    for key in ('depots', 'furnace_positions'):
        if not all(point(p) for p in profile.get(key, [])):
            raise JobBlocked('无效工位坐标列表：' + key)
    profile.update(recipe_jar=jar, profile_file=str(path), server=context['server'], dimension=context['dimension'])
    profile.setdefault('resource_regions', [])
    profile.setdefault('search_radius', 256)
    return profile
