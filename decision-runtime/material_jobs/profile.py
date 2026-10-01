"""Per-world material infrastructure. Coordinates are data, never task-specific code."""
import hashlib
import json
import math
from pathlib import Path
import re

from .protocol import JobBlocked, server_key


def profile_path(automation, context):
    scope = server_key(context['server']) + '|' + context['dimension']
    return Path(automation).parent / 'material-profiles' / (hashlib.sha256(scope.encode()).hexdigest()[:20] + '.json')


def point(value):
    return (isinstance(value, list) and len(value) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in value))


def _block_box(value, *, tall=False):
    if not isinstance(value,dict):return False
    low,high=value.get('min'),value.get('max')
    return (isinstance(low,list) and isinstance(high,list) and len(low)==len(high)==3
            and all(type(v) is int for v in low+high)
            and all(low[i]<=high[i] for i in range(3))
            and -64<=low[1]<=high[1]<=319
            and high[0]-low[0]<=127 and high[2]-low[2]<=127
            and (tall or high[1]-low[1]<=191))


def _validate_profile(profile):
    if not isinstance(profile,dict):
        raise JobBlocked('材料工位配置必须是 JSON 对象')
    if 'schema' in profile and profile['schema']!=1:
        raise JobBlocked('材料工位配置版本不受支持')
    regions=profile.get('resource_regions',[])
    if not isinstance(regions,list):
        raise JobBlocked('资源区域配置必须是列表')
    for region in regions:
        if (not isinstance(region,dict)
                or not isinstance(region.get('item'),str)
                or not re.fullmatch(r'minecraft:[a-z0-9_./-]+',region['item'])
                or not _block_box(region)):
            raise JobBlocked('资源区域需要有效物品和有界整数坐标')
        if 'access_shaft' in region and not _block_box(region['access_shaft'],tall=True):
            raise JobBlocked('资源区域入口竖井坐标无效')
    if 'search_origin' in profile and not point(profile['search_origin']):
        raise JobBlocked('资源搜索起点必须是有限三维坐标')
    radius=profile.get('search_radius',256)
    if type(radius) is not int or not 1<=radius<=384:
        raise JobBlocked('资源搜索半径必须是 1..384 的整数')


def load(automation, context):
    automation = Path(automation)
    path = profile_path(automation, context)
    profile = json.loads(path.read_text()) if path.exists() else {}
    _validate_profile(profile)
    if profile and (server_key(profile.get('server')) != server_key(context['server'])
                    or profile.get('dimension') != context['dimension']):
        raise JobBlocked('材料工位配置属于其他服务器或维度')
    config_path = automation.parent.parent / 'twob2tkit.json'
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    if not isinstance(config,dict):
        raise JobBlocked('Kit 配置必须是 JSON 对象')
    configured_sources=config.get('projectionSupplySources',[])
    if not isinstance(configured_sources,list):
        raise JobBlocked('Kit 允许取料仓库配置必须是列表')
    sources = []
    for row in configured_sources:
        if (not isinstance(row,dict) or not isinstance(row.get('server'),str)
                or not row['server'] or not isinstance(row.get('dimension'),str)
                or not row['dimension'] or any(type(row.get(k)) is not int for k in ('x','y','z'))):
            raise JobBlocked('Kit 允许取料仓库记录损坏')
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
