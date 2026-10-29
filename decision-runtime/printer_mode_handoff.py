"""Borrow an idle external printer mode through Kit, then respect newer choices."""
import json
import time
import uuid
from pathlib import Path
from live_snapshot import read_fresh
from safety_interlock import require_unlocked
from kit_runtime.journal import write_json


def restoration_target(original,revision,printer):
    current=printer.get('external_mode_revision')
    if type(original)is not bool or type(current)is not int or current<revision:return None
    if current==revision:return original
    latest=printer.get('last_external_enabled')
    return latest if type(latest)is bool else None


def idle_for_mode(state,key):
    return (state.get('connected')is True and state.get('health',0)>=19
        and not state.get('screen')and not state.get('manual_movement')and not state.get('supervision_lease')
        and not state.get('guard_busy')and not state.get('safety_hold',{}).get('active')
        and not state.get('build_job',{}).get('active')and not state.get('professional_printer',{}).get('owned')
        and not state.get('projection_batch',{}).get('active')
        and state.get('projection_selection',{}).get('key')==key
        and not any(state.get(k)for k in ['navigating','borer_active','chopping','fisher_active','planter_active','feeder_active']))


class PrinterModeHandoff:
    def __init__(self,root,out,placement_key,desired_restore=None):
        self.root=Path(root);self.out=Path(out);self.out.mkdir(parents=True,exist_ok=False)
        self.key=placement_key;self.pending=False
        s=read_fresh(self.root);require_unlocked(self.root,s)
        if s.get('printer_mode_handoff_protocol')!=1 or not idle_for_mode(s,self.key):
            raise RuntimeError('Idle native printer handoff unavailable')
        p=s.get('professional_printer')or{}
        if type(p.get('enabled'))is not bool or type(p.get('external_mode_revision'))is not int:
            raise RuntimeError('Exact printer mode and user revision required')
        if desired_restore is not None and type(desired_restore)is not bool:raise ValueError('Boolean restore mode required')
        self.world=s['world_session'];self.revision=p['external_mode_revision']
        self.original=p['enabled']if desired_restore is None else desired_restore
        if desired_restore is not None and self.revision>0 and type(p.get('last_external_enabled'))is bool:
            self.original=p['last_external_enabled']
        write_json(self.out/'before.json',s)
        if p['enabled']:self._set(s,False,'pause')
        write_json(self.out/'token.json',dict(world_session=self.world,placement_key=self.key,
            restore_enabled=self.original,external_revision=self.revision))

    def _set(self,state,enabled,label):
        if self.pending:raise RuntimeError('Original mode request unconfirmed; no repeat')
        p=state['professional_printer'];r=dict(id='printer-mode-'+uuid.uuid4().hex[:12],op='printer_mode',
            site=state['pos'],server=state['server'],dimension=state['dimension'],world_session=state['world_session'],
            expected_revision=state['control_revision'],expires_at=int(time.time()*1000)+8000,
            placement_key=self.key,expected_enabled=p['enabled'],enabled=enabled,
            expected_external_revision=p['external_mode_revision'])
        self.pending=True;write_json(self.out/(label+'-intent.json'),r);write_json(self.root/'request.json',r)
        end=time.monotonic()+10
        while time.monotonic()<end:
            path=self.root/('reply-'+r['id']+'.json')
            if path.exists():
                reply=json.loads(path.read_text());write_json(self.out/(label+'-reply.json'),reply)
                if reply.get('phase')!='done':raise RuntimeError('Native printer handoff rejected: '+str(reply.get('detail')))
                if reply.get('professional_printer',{}).get('enabled')is not enabled:
                    raise RuntimeError('Printer mode not confirmed; no repeat')
                self.pending=False;return reply
            time.sleep(.05)
        raise RuntimeError('Original printer mode request unknown; preserve identity')

    def restore(self,*,safe_to_restore):
        if not safe_to_restore or self.pending:
            result=dict(restored=False,reason='unfinished_service_or_unknown_request')
        else:
            s=read_fresh(self.root)
            if s.get('world_session')!=self.world or not idle_for_mode(s,self.key):
                result=dict(restored=False,reason='new_scope_or_active_control')
            else:
                p=s['professional_printer'];target=restoration_target(self.original,self.revision,p)
                if target is None:result=dict(restored=False,reason='newer_mode_unavailable')
                else:
                    if p['enabled']is not target:self._set(s,target,'restore')
                    result=dict(restored=True,enabled=target,newer_user_choice=p['external_mode_revision']!=self.revision)
        write_json(self.out/'restoration.json',result);return result
