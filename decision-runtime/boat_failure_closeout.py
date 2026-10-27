"""Recognize an explicitly failed trip only after known input and safe anchoring.

The original journal bytes remain archived. An abort is never route completion
and cannot be resumed; a later journey needs a new plan and current observations.
"""
from pathlib import Path
import hashlib,json,math

def closed_failed_trip(book,world,uuid,journal):
    try:
        if(book.get('complete')is not False or book.get('pending')is not None or book.get('aborted')is not True
            or book.get('world_session')!=world or book.get('uuid')!=uuid):return False
        root=Path(journal).resolve().parent;closure=book['failure_closeout']
        def evidence(name,sha):
            if not isinstance(name,str)or Path(name).name!=name:raise ValueError('Evidence escaped trip directory')
            p=root/name
            if hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise ValueError('Closeout evidence changed')
            return json.loads(p.read_text())
        old=evidence(closure['original_backup'],closure['original_sha256']);proof=evidence(closure['proof'],closure['proof_sha256']);native=proof['original_native_terminal'];pending=old['pending'];boat=proof['secured_boat']
        return (closure.get('protocol')==1 and old.get('complete')is False and old.get('world_session')==world and old.get('uuid')==uuid
            and pending.get('op')=='navigate'and pending.get('request_id')==native.get('request_id')
            and native.get('phase')=='done'and native.get('op')=='navigate'and native.get('world_session')==world
            and native.get('params',{}).get('target')==pending.get('target')and native.get('inventory_delta')=={}
            and proof.get('complete')is True and proof.get('goal_complete')is False
            and proof.get('classification')=='known_completed_leg_failed_route_safely_anchored'
            and proof.get('world_session')==world and proof.get('original_sha256')==closure['original_sha256']
            and proof.get('unconfirmed_native_request_absent')is True and proof.get('player_health')==20
            and boat.get('uuid')==uuid and boat.get('alive')is True and boat.get('on_ground')is True
            and boat.get('leashed')is True and boat.get('leash_resolved')is True
            and boat.get('leash_holder',{}).get('type')=='minecraft:leash_knot'
            and bool(boat.get('passengers'))and all(p.get('alive')is True and type(p.get('max_health'))in(int,float)
                and math.isfinite(p['max_health'])and p['max_health']>0 and p.get('health')==p['max_health']for p in boat['passengers']))
    except(OSError,ValueError,KeyError,TypeError):return False
