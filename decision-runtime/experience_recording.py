"""Record just-observed native transactions in Kit's local skill memory, without a model."""
import sys
from pathlib import Path
MANAGERS={}

def record_native_transaction(request,before,result,state_root=None):
    if request.get('op') in ('scan','snapshot','projection_audit','scan_trees'):return {'status':'observation'}
    # This entry point is called by MaterialClient after matching a native reply.
    # External retrospective documents must use learn_episode (candidate-only) instead.
    if result.get('id')!=request.get('id') or result.get('phase') not in ('done','waiting','error','stopped'):
        return {'status':'unconfirmed'}
    package=Path(__file__).resolve().parents[1]/'companion-skills'
    if str(package) not in sys.path:sys.path.insert(0,str(package))
    from kit_skills.library import SkillManager
    from kit_skills.learning import learn_transaction
    from kit_skills.kit import compact
    root=Path(state_root) if state_root else package/'state';key=str(root.resolve())
    manager=MANAGERS.get(key)
    if manager is None:manager=MANAGERS[key]=SkillManager(root)
    return learn_transaction(manager,request,compact(before),compact(result))

def close_recorders():
    for manager in MANAGERS.values():manager.close()
    MANAGERS.clear()
