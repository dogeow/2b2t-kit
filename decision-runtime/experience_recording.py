"""Record just-observed native transactions in Kit's local skill memory, without a model."""
import json
import sys
from pathlib import Path
from sensitive_data import sanitize
MANAGERS={}

def record_native_transaction(request,before,result,state_root=None):
    if request.get('op') in ('scan','snapshot','projection_audit','scan_trees',
                             'scan_snow_biomes','snow_seed_candidates'):
        return {'status':'observation'}
    # This entry point is called by MaterialClient after matching a native reply.
    # External retrospective documents must use learn_episode (candidate-only) instead.
    if result.get('id')!=request.get('id') or result.get('phase') not in ('done','waiting','error','stopped'):
        return {'status':'unconfirmed'}
    manager=_manager(state_root)
    from kit_skills.learning import learn_transaction
    from kit_skills.kit import compact
    return learn_transaction(manager,sanitize(request),compact(before),
                             compact(sanitize(result)))


def _manager(state_root=None):
    package=Path(__file__).resolve().parents[1]/'companion-skills'
    if package.is_dir() and str(package) not in sys.path:sys.path.insert(0,str(package))
    from kit_skills.library import SkillManager
    root=Path(state_root) if state_root else package/'state';key=str(root.resolve())
    manager=MANAGERS.get(key)
    # Optional recording must not wait ten seconds for a busy observer database.
    if manager is None:manager=MANAGERS[key]=SkillManager(root, lock_timeout=.05)
    return manager


def state_for_backend(backend):
    value=getattr(backend,'profile',{}).get('skill_memory_state')
    if value is not None:
        if not isinstance(value,str) or not value or not Path(value).is_absolute():
            raise ValueError('skill_memory_state must be an absolute local directory')
        return Path(value)
    return Path(backend.root).parent/'skill-memory'


def record_lesson(event,state_root=None):
    """A diagnostic/manual import can never add a witnessed success episode."""
    if not isinstance(event,dict):raise ValueError('A lesson must be an object')
    safe=sanitize(event)
    if len(json.dumps(safe,ensure_ascii=False).encode())>16384:
        raise ValueError('Lesson exceeds bounded local payload size')
    return {'status':'lesson','id':_manager(state_root).lesson(safe)}

def close_recorders():
    for manager in MANAGERS.values():manager.close()
    MANAGERS.clear()
