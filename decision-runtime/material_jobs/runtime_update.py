"""Load an explicitly staged, verified engine through the existing owned Kit API."""
import hashlib
from pathlib import Path
import re

from kit_runtime.journal import write_json
from .protocol import JobBlocked


def validate(plan):
    if plan is None:return None
    if (not isinstance(plan,dict) or set(plan)!={'version','sha256'}
            or not isinstance(plan['version'],str)
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',plan['version'])
            or not isinstance(plan['sha256'],str)
            or not re.fullmatch(r'[0-9a-f]{64}',plan['sha256'])):
        raise ValueError('Explicit staged engine version and SHA256 are required')
    return dict(plan)


def ensure(client,automation,out,plan):
    plan=validate(plan)
    if plan is None:return
    engine=Path(automation).parent/'runtime/twob2tkit-engine.jar'
    if not engine.is_file() or hashlib.sha256(engine.read_bytes()).hexdigest()!=plan['sha256']:
        raise JobBlocked('待加载引擎与已验证安装文件不一致；未请求热加载')
    before=client.status()
    if before.get('runtime_reload_protocol')!=1 or before.get('runtime_host_api')!=3:
        raise JobBlocked('当前宿主不支持已验证的 API 3 引擎热加载')
    if all(before.get(k)==plan['version'] for k in ('runtime_version','navigation_runtime_version')):
        write_json(Path(out)/'runtime-update.json',{'state':'already_loaded','version':plan['version'],
            'staged_sha256':plan['sha256'],'world_session':client.world,'new_reload_sent':False})
        return
    receipt=client.checked('runtime_reload')
    after=client.status()
    proof={'state':'unverified','version':plan['version'],'staged_sha256':plan['sha256'],
           'world_session':client.world,'before_version':before.get('runtime_version'),
           'after_version':after.get('runtime_version'),'receipt':receipt,'new_reload_sent':True}
    # No repeat after a timeout/unknown result; the normal client retains that receipt.
    if (receipt.get('phase')!='done' or receipt.get('world_session')!=client.world
            or after.get('world_session')!=client.world
            or not all(after.get(k)==plan['version'] for k in ('runtime_version','navigation_runtime_version'))):
        write_json(Path(out)/'runtime-update.json',proof)
        raise JobBlocked('引擎热加载结果未获当前世界核验；保留回执且不重复发送')
    proof['state']='loaded';write_json(Path(out)/'runtime-update.json',proof)
