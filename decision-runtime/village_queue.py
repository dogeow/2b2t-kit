"""Sequence bounded plans through the already running sole village action owner.

This planner writes only that owner's workspace mailbox. It never acquires a
second Minecraft lease or writes the native game request mailbox.
"""
from pathlib import Path
import fcntl,json,time,hashlib
from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from safety_interlock import require_unlocked

WORKSTATIONS=frozenset('minecraft:'+name for name in(
    'lectern','composter','fletching_table','blast_furnace','smoker','barrel',
    'grindstone','smithing_table','stonecutter','cauldron','loom','cartography_table','brewing_stand'))

def require_mailbox_owner(out,state):
    """A registered mailbox must belong to the currently retained native owner."""
    path=Path(out)/'transport-kernel.json'
    if not path.exists():return
    identity=json.loads(path.read_text());lease=state.get('supervision_lease')or{}
    if(identity.get('world_session')!=state.get('world_session')
            or identity.get('task_session')!=lease.get('job_session')):
        raise RuntimeError('Village mailbox belongs to a different native owner; no command queued')

class VillageQueue:
    def __init__(self,out,root,prefix):
        self.out=Path(out);self.root=Path(root);self.prefix=prefix;self.index=0;self.closing_menu=None
        self.lock=(self.out/'planner.lock').open('a');fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        q=read_fresh(self.root);self.world=q['world_session'];self.lease=dict(q.get('supervision_lease')or{})
        if self.lease.get('kind')!='materials':raise RuntimeError('Original village owner is unavailable')
        require_mailbox_owner(self.out,q)
        self.status(observing=True)
        from action_efficiency import ActionEfficiency
        self.efficiency=ActionEfficiency(self.out,prefix,self.world)
    def close(self):self.lock.close()
    def observe_sleeping_merchant_timeout(self):
        return self.observe_idle_merchant_timeout()
    def observe_paid_lock_reopen_timeout(self):
        """Keep the completed trade; observe only its settled failed reopen."""
        from sleeping_merchant_observation import observable_paid_reopen
        from villager_events import read
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No exact paid lock reopen terminal')
        error=json.loads((d/'error.json').read_text());scope=d/'actual-one-wanted-lock'
        lock=json.loads((scope/'lock-wanted.json').read_text());opening=json.loads((scope/'reopened/open.json').read_text())
        purchase=json.loads((scope/'purchase/one-trade.json').read_text())
        if purchase!=lock.get('purchase'):raise RuntimeError('Original purchase receipts differ')
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==error.get('last_request')),None)
        host=self.root.parents[2]/'mods'/('twob2tkit-'+state['kit_version']+'.jar')
        host_sha256=hashlib.sha256(host.read_bytes()).hexdigest()
        if not observable_paid_reopen(command,error,lock,opening,event,state,read(self.root,state),self.world,self.lease['job_session'],host_sha256):
            raise RuntimeError('Paid trade or nested opening remains unresolved; no replay')
        self._sleeping_merchant_read=command['id']
        try:return self.native('snapshot')
        finally:self._sleeping_merchant_read=None
    def observe_idle_merchant_timeout(self):
        """Snapshot a known idle trader interaction; no repeated opening."""
        from sleeping_merchant_observation import observable
        from villager_events import read
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No known sleeping merchant terminal')
        error=json.loads((d/'error.json').read_text());opening=json.loads((d/'actual-normal-merchant-open/open.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None);flags=read(self.root,state)
        if not observable(command,error,opening,event,state,flags,self.world,self.lease['job_session']):raise RuntimeError('Merchant interaction or ownership remains unresolved')
        self._sleeping_merchant_read=command['id']
        try:return self.native('snapshot')
        finally:self._sleeping_merchant_read=None
    def observe_merchant_reach_refusal(self):
        """Snapshot a pinned pre-input range refusal; never repeat its opening."""
        from sleeping_merchant_observation import observable_reach
        from villager_events import read
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No known merchant range refusal')
        error=json.loads((d/'error.json').read_text());opening=json.loads((d/'actual-normal-merchant-open/open.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None);flags=read(self.root,state)
        host=self.root.parents[2]/'mods'/('twob2tkit-'+state['kit_version']+'.jar')
        if not observable_reach(command,error,opening,event,state,flags,self.world,self.lease['job_session'],hashlib.sha256(host.read_bytes()).hexdigest()):raise RuntimeError('Merchant opening is not a proved pre-input range refusal')
        self._sleeping_merchant_read=command['id']
        try:return self.native('snapshot')
        finally:self._sleeping_merchant_read=None
    def observe_workbench_approach_refusal(self):
        """Only snapshot the exact unmoved workbench-route refusal."""
        from workbench_approach_observation import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No workbench pre-use route refusal')
        error=json.loads((d/'error.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        if not observable(command,error,event,state,self.world,self.lease['job_session']):raise RuntimeError('Workbench use or ownership is not settled')
        self._workbench_route_read=command['id']
        try:return self.native('snapshot')
        finally:self._workbench_route_read=None
    def observe_unopened_anvil_preview(self):
        """Read-only settlement of one proved pre-window face refusal, never a retry."""
        from anvil_preview_refusal import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No exact unopened-anvil refusal to observe')
        error=json.loads((d/'error.json').read_text());path=d/'actual-zero-xp-anvil-preview/preview.json';book=json.loads(path.read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        request=error.get('last_request');reply=json.loads((self.root/('reply-'+str(request)+'.json')).read_text())
        if not observable(command,error,book,event,reply,state,self.world,self.lease['job_session']):
            raise RuntimeError('Anvil input/window outcome is not a proved initial face refusal')
        self._anvil_preview_open_read=command['id']
        try:result=self.native('snapshot')
        finally:self._anvil_preview_open_read=None
        write_json(self.out/'anvil-preview-open-refusal-observation.json',{
            'complete':True,'world_session':self.world,'original_command':command,
            'original_preview_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'native_refusal':request,'read_only_snapshot':result['id'],
            'input_moves':0,'output_clicks':0,'original_request_replayed':False})
        return result
    def observe_collected_packed_box(self):
        """Snapshot a conserved carried box, never repeat mining or collection."""
        from collected_packed_observation import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No known terminal portable-box recovery to observe')
        error=json.loads((d/'error.json').read_text());path=self.out/'control/packed-transfer-active.json';record=json.loads(path.read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        reply=json.loads((self.root/('reply-'+error['last_request']+'.json')).read_text())
        if not observable(command,error,record,event,reply,state,self.world,self.lease['job_session']):
            raise RuntimeError('Original portable-box contents or native outcome remain unresolved')
        self._packed_collected_read=command['id']
        try:result=self.native('snapshot')
        finally:self._packed_collected_read=None
        write_json(self.out/'collected-packed-box-observation.json',{'complete':True,'original_command':command,
                   'original_journal_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                   'snapshot_id':result['id'],'original_requests_replayed':False,'box_return_still_required':True})
        return result
    def observe_unstarted_food_air_refusal(self,expected_bread):
        """Observe an exact unmoved approach refusal; send no food or retry."""
        from food_approach_observation import unmoved_air_refusal
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No exact unstarted food air refusal')
        error=json.loads((d/'error.json').read_text());book=json.loads((d/'feeding.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        if not unmoved_air_refusal(command,error,book,event,state,self.world,self.lease['job_session'],expected_bread):raise RuntimeError('Food or movement outcome remains unresolved')
        self._food_pose_stop_read=command['id']
        try:return self.native('snapshot')
        finally:self._food_pose_stop_read=None
    def observe_food_approach_stop(self,expected_bread):
        """Snapshot a known stopped walk before this feeding command sent Q."""
        from food_approach_observation import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No known stopped food approach')
        error=json.loads((d/'error.json').read_text());book=json.loads((d/'feeding.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        if not observable(command,error,book,event,state,self.world,self.lease['job_session'],expected_bread):raise RuntimeError('Food approach or inventory remains unresolved')
        self._food_pose_stop_read=command['id']
        try:return self.native('snapshot')
        finally:self._food_pose_stop_read=None
    def observe_uncredited_founder_food_debit(self):
        """Read a settled one-bread debit; no collector credit or Q replay."""
        from uncredited_food_observation import settled
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No settled uncredited food debit')
        error=json.loads((d/'error.json').read_text());book=json.loads((d/'feeding.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        if not settled(command,error,book,events,state,self.world,self.lease['job_session']):raise RuntimeError('Food input or quantity is still unresolved')
        self._uncredited_food_read=command['id']
        try:return self.native('snapshot')
        finally:self._uncredited_food_read=None
    def observe_recoverable_founder_food(self):
        """Only snapshot a still-loaded exact uncollected bread; no food credit."""
        from uncredited_food_observation import settled
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No known retained recoverable food')
        error=json.loads((d/'error.json').read_text());book=json.loads((d/'feeding.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        if not settled(command,error,book,events,state,self.world,self.lease['job_session'],recoverable=True):raise RuntimeError('Exact ground bread or stopped ownership not verified')
        self._uncredited_food_read=command['id']
        try:return self.native('snapshot')
        finally:self._uncredited_food_read=None
    def observe_accounted_founder_food_budget(self):
        """Only snapshot a settled fully accounted budget; preserve unmet quotas."""
        from feeding_budget_observation import accounted_budget
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(d/'error.json').exists()or not(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No known completed food budget')
        result=json.loads((d/'result.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        if not accounted_budget(command,result,events,state,self.world,self.lease['job_session']):raise RuntimeError('Original food budget remains unresolved')
        self._food_budget_read=command['id']
        try:return self.native('snapshot')
        finally:self._food_budget_read=None
    def observe_unstarted_feeding_enclosure(self):
        """Only snapshot a failed containment scan with no food intent or debit."""
        from unstarted_feeding_enclosure import observable
        state=self.status(observing=True);command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('Original enclosure refusal is not an unstarted food command')
        error=json.loads((d/'error.json').read_text());book=json.loads((d/'feeding.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((v for v in reversed(events)if v.get('request_id')==error.get('last_request')),None)
        if not observable(command,error,book,event,state,self.world,self.lease['job_session']):
            raise RuntimeError('Food delivery or its original ownership remains unresolved')
        self._food_guard_read=command['id']
        try:return self.native('snapshot')
        finally:self._food_guard_read=None
    def observe_rejected_founder_food_guard(self):
        """Snapshot a pinned before-Q rejection without editing or replaying food."""
        from food_guard_observation import rejected_without_q
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('Original feeding action has no known pre-Q refusal')
        error=json.loads((d/'error.json').read_text());feeding=json.loads((d/'feeding.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        host=self.root.parents[2]/'mods'/('twob2tkit-'+state['kit_version']+'.jar')
        if not rejected_without_q(command,error,feeding,event,state,self.world,self.lease['job_session'],hashlib.sha256(host.read_bytes()).hexdigest(),prior_events=events):
            raise RuntimeError('Food input or ownership is not proved unchanged at the pinned before-Q guard')
        self._food_guard_read=command['id']
        try:return self.native('snapshot')
        finally:self._food_guard_read=None
    def observe_unsupported_readonly_native(self):
        """Observe an exact project pre-dispatch rejection, never retry its op."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if (command.get('action')!='native' or command.get('op')!='scan_snow_biomes'
                or not(d/'error.json').exists() or (d/'result.json').exists()
                or (self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No exact unsupported read-only project rejection')
        error=json.loads((d/'error.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        last=events[-1]if events else{}
        if (error.get('error')!='Native operation is outside this village project'
                or error.get('type')!='ValueError'
                or 'native_inflight'not in error or error['native_inflight']is not None
                or 'unconfirmed_native_request'not in error or error['unconfirmed_native_request']is not None
                or error.get('last_request')!=state.get('last_request')
                or last.get('request_id')!=state.get('last_request')or last.get('phase')!='done'
                or last.get('world_session')!=self.world
                or last.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or last.get('revision_after')!=state.get('control_revision')
                or last.get('position_after')!=state.get('pos')
                or state.get('phase')!='done'or state.get('navigating')or state.get('native_material_busy')):
            raise RuntimeError('Unsupported read may have dispatched or current ownership moved')
        self._unsupported_readonly_read=command['id']
        try:return self.native('snapshot')
        finally:self._unsupported_readonly_read=None
    def observe_deferred_defense_navigation(self):
        """Only snapshot a movement rejected before native dispatch by defense."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(command.get('action')!='native'or command.get('op')!='navigate'
                or not(d/'error.json').exists()or(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No exact pre-dispatch defense navigation wait')
        error=json.loads((d/'error.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];last=events[-1]if events else{}
        if(error.get('error')!='Defense remains busy'or error.get('type')!='RuntimeError'
                or 'native_inflight'not in error or error['native_inflight']is not None
                or 'unconfirmed_native_request'not in error or error['unconfirmed_native_request']is not None
                or error.get('last_request')!=state.get('last_request')
                or last.get('request_id')!=state.get('last_request')or last.get('phase')!='done'
                or last.get('world_session')!=self.world
                or last.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or last.get('revision_after')!=state.get('control_revision')or last.get('position_after')!=state.get('pos')
                or state.get('health')!=20 or state.get('phase')!='done'
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or not isinstance(state.get('movement_keys'),dict)or any(state['movement_keys'].values())):
            raise RuntimeError('Deferred movement is not proved unissued at the same healthy terminal')
        self._defense_wait_read=command['id']
        try:return self.native('snapshot')
        finally:self._defense_wait_read=None
    def return_refused_storage_cursor(self):
        """One new safe placement of a known pickup; never repeat the failed transfer."""
        from storage_cursor_refusal import return_plan
        state=self.status(observing=True);command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(not self._owned_menu(state,observing=True)or not(d/'error.json').exists()
           or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No owned known rejected storage remainder')
        error=json.loads((d/'error.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        plan=return_plan(command,error,state,events,self.world,self.lease['job_session'])
        if plan is None:raise RuntimeError('Storage cursor pickup or input-free rejection is not proved')
        self._storage_cursor_return=(command['id'],plan)
        try:return self.native('slot_click',**plan)
        finally:self._storage_cursor_return=None
    def observe_full_storage_transfer(self):
        """Observe a conserved partial deposit; never repeat its clicks."""
        from full_transfer_reconciliation import full_deposit
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);prior=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if(not(d/'error.json').exists()or(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()
                or not(prior/'result.json').exists()or not self._owned_menu(state)):
            raise RuntimeError('No known owned partial full-container transfer')
        error=json.loads((d/'error.json').read_text());before=json.loads((prior/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        proof=full_deposit(command,error,before,state,events,self.world,self.lease['job_session'])
        if proof is None:raise RuntimeError('Partial transfer is not conserved and known; no recovery input')
        self._full_transfer_read=command['id']
        try:return dict(proof=proof,observation=self.native('snapshot'))
        finally:self._full_transfer_read=None
    def observe_unstarted_full_storage_deposit(self):
        """Observe a proved zero-input full chest refusal; never repeat a deposit."""
        from full_transfer_reconciliation import unstarted_full_deposit
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);prior=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if (not(d/'error.json').exists() or(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()
                or not(prior/'result.json').exists() or not self._owned_menu(state)):
            raise RuntimeError('No exact unstarted full chest deposit')
        error=json.loads((d/'error.json').read_text());intent=json.loads((prior/'intent.json').read_text())
        receipt=json.loads((prior/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        proof=unstarted_full_deposit(command,error,intent,receipt,state,events[-1],self.world,self.lease['job_session'])
        if proof is None:raise RuntimeError('Zero input and full destination are not proved')
        self._full_transfer_read=command['id']
        try:return dict(proof=proof,observation=self.native('snapshot'))
        finally:self._full_transfer_read=None
    def observe_partial_iron_quick_refusal(self):
        """Read only an exact retained iron withdrawal; do not retry its refused slot."""
        from storage_quick_refusal import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);prior=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if(not(d/'error.json').exists()or(d/'result.json').exists()or not(prior/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()or not self._owned_menu(state)):
            raise RuntimeError('No owned known partial iron quick-move refusal')
        error=json.loads((d/'error.json').read_text());before=json.loads((prior/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==error['last_request']),None)
        reply=json.loads((self.root/('reply-'+error['last_request']+'.json')).read_text())
        if not observable(command,error,before,event,reply,state,self.world,self.lease['job_session']):
            raise RuntimeError('Partial iron withdrawal or native refusal remains unconfirmed')
        self._iron_quick_read=command['id']
        try:return self.native('snapshot')
        finally:self._iron_quick_read=None
    def observe_storage_corridor_refusal(self):
        """Read an entry-path rejection only if no chest use/transfer was sent."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);prior=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if(command.get('action')!='exchange'or not(d/'error.json').exists()or(d/'result.json').exists()
                or not(prior/'result.json').exists()or(prior/'error.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No exact input-free storage corridor rejection')
        error=json.loads((d/'error.json').read_text());baseline=json.loads((prior/'result.json').read_text())
        intent=json.loads((prior/'intent.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        start=next((i for i,e in enumerate(events)if e.get('request_id')==baseline.get('id')),None)
        segment=events[start+1:]if start is not None else[];last=segment[-1]if segment else{}
        if(error.get('error')!='Original storage return body corridor changed; no movement sent'
                or error.get('type')!='StockBlocked'or error.get('native_inflight')is not None
                or error.get('unconfirmed_native_request')is not None
                or intent.get('action')!='native'or intent.get('op')!='scan'or baseline.get('phase')!='done'
                or baseline.get('world_session')!=self.world or not segment
                or inventory_counts(baseline)!=inventory_counts(state)
                or any(e.get('op')not in('scan','snapshot','navigate','walk','approach_block','select_item','look')
                       or e.get('phase')!='done'or e.get('world_session')!=self.world
                       or e.get('inventory_delta')!={}or e.get('params',{}).get('task_session')!=self.lease.get('job_session')for e in segment)
                or last.get('request_id')!=error.get('last_request')or last.get('request_id')!=state.get('last_request')
                or last.get('revision_after')!=state.get('control_revision')or last.get('position_after')!=state.get('pos')
                or state.get('screen')!=''or state.get('health')!=20 or state.get('navigating')or state.get('pending_scan')):
            raise RuntimeError('Storage may already have opened or transferred; original attempt remains fenced')
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_empty_workbench_inventory_wait(self):
        """Observe a certified empty grid after a known inventory-capacity stop."""
        from material_plan import inventory_counts
        state=self.status(observing=True);command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(command.get('action')!='manufacture'or(d/'error.json').exists()or not(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No settled workbench capacity result')
        reply=json.loads((d/'result.json').read_text());m=state.get('menu')or{};steps=reply.get('steps')or[]
        counts=inventory_counts(state);remaining={i:n-counts[i]for i,n in command.get('targets',{}).items()if counts[i]<n}
        certificate=json.loads((self.out/'owned-material-menu.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];last=events[-1]if events else{}
        if(reply.get('complete')is not False or not remaining or remaining!=reply.get('remaining_targets')
                or not steps or not any(v.get('state')=='waiting_for_inventory_space'for v in steps)
                or any(v.get('state')not in('crafted','waiting_for_inventory_space')for v in steps)
                or reply.get('owned_menu')!=certificate or not self._owned_menu(state)
                or m.get('type')!='CraftingMenu'or m.get('cursor',{}).get('count')!=0
                or len(m.get('slots',[]))<10 or any(v.get('count')!=0 for v in m['slots'][:10])
                or last.get('request_id')!=state.get('last_request')or last.get('phase')!='done'
                or last.get('world_session')!=self.world or last.get('revision_after')!=state.get('control_revision')
                or last.get('params',{}).get('task_session')!=self.lease.get('job_session')):
            raise RuntimeError('Workbench still has an unknown grid, cursor, or ownership outcome')
        self._empty_workbench_read=command['id']
        try:return self.native('snapshot')
        finally:self._empty_workbench_read=None
    def observe_unchanged_roofed_storage(self):
        """Observe a roof survey refusal after travel, with no container input."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        if not(previous/'result.json').exists():
            # The first command of a new planner follows another prefix (often
            # the owner's initial raw snapshot), rather than a fictitious -000.
            indices={e.get('request_id'):i for i,e in enumerate(events)};candidates=[]
            for path in self.out.glob('*/result.json'):
                if path.parent==d or(path.parent/'error.json').exists():continue
                value=json.loads(path.read_text());index=indices.get(value.get('id'))
                if index is not None and index<len(events)-1:candidates.append((index,path.parent))
            if candidates:previous=max(candidates,key=lambda v:v[0])[1]
        if (command.get('action')!='exchange'or len(command.get('positions',[]))!=1
                or not(d/'error.json').exists()or(d/'result.json').exists()
                or not(previous/'result.json').exists()or(previous/'error.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Roof survey has no known input-free storage refusal')
        error=json.loads((d/'error.json').read_text());prior=json.loads((previous/'result.json').read_text());pos=command['positions'][0]
        start=next((i for i,e in enumerate(events)if e.get('request_id')==prior.get('id')),None)
        segment=events[start+1:]if start is not None else[];last=segment[-1]if segment else{}
        raw_snapshot=(start is not None and prior.get('phase')is None and prior.get('connected')is True
                      and events[start].get('op')=='snapshot'and events[start].get('world_session')==self.world
                      and events[start].get('params',{}).get('task_session')==self.lease.get('job_session'))
        if (error.get('error')!='Roofed storage needs a local registered house entry route; preserve the structure'
                or error.get('type')!='StockBlocked'or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or not(prior.get('phase')=='done'or raw_snapshot)or prior.get('world_session')!=self.world
                or inventory_counts(prior)!=inventory_counts(state)or not segment
                or any(e.get('op')not in('scan','snapshot','navigate','walk','approach_block','select_item','look')
                       or e.get('phase')!='done'or e.get('world_session')!=self.world
                       or e.get('params',{}).get('task_session')!=self.lease.get('job_session')for e in segment)
                or last.get('op')!='scan'or last.get('params',{}).get('min')!=pos
                or last.get('params',{}).get('max')!=[pos[0],pos[1]+6,pos[2]]
                or last.get('request_id')!=error.get('last_request')or last.get('request_id')!=state.get('last_request')
                or last.get('revision_after')!=state.get('control_revision')or last.get('position_after')!=state.get('pos')
                or state.get('screen')!=''or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Roofed storage may have dispatched a non-observation input')
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_zero_proposal_printer(self):
        """Only snapshot an exact conserved zero-input interval, preserving its receipt."""
        from zero_proposal_printer import conserved
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);prior_dir=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if((d/'error.json').exists()or not(d/'result.json').exists()or not(prior_dir/'result.json').exists()
                or(prior_dir/'error.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No exact zero-proposal printer terminal')
        reply=json.loads((d/'result.json').read_text());prior=json.loads((prior_dir/'result.json').read_text());intent=json.loads((prior_dir/'intent.json').read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]if events else{}
        if not conserved(command,reply,intent,prior,event,state,self.world,self.lease['job_session']):
            raise RuntimeError('Printer may have sent input; original interval remains fenced')
        self._settled_print_read=command['id']
        try:return self.native('snapshot')
        finally:self._settled_print_read=None
    def observe_settled_partial_printer(self):
        """Read a stopped bounded printer with every dispatched proposal acknowledged.

        This grants observation only, never completion credit or a printer retry.
        """
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if ((d/'error.json').exists()or not(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Printer has no known stopped interval')
        reply=json.loads((d/'result.json').read_text());p=state.get('professional_printer')or{};mask=state.get('projection_batch')or{}
        targets=reply.get('bounded_targets')or[];count=p.get('server_confirmed')
        if (command.get('action')!='native'or command.get('op')!='professional_print'
                or reply.get('phase')!='waiting'or reply.get('detail')!='printer interval ended without complete current bounded-mask server confirmation'
                or reply.get('world_session')!=self.world or reply.get('id')!=state.get('last_request')
                or reply.get('control_revision')!=state.get('control_revision')
                or p.get('enabled')is not False or p.get('owned')is not False
                or p.get('waiting_for_server')is not False or p.get('travel_pending')!=0
                or p.get('failure')or p.get('complex_proposals')!=0
                or type(count)is not int or not 0<count<len(targets)or p.get('fast_proposals')!=count
                or len(set(map(tuple,targets)))!=len(targets)or reply.get('bounded_target_count')!=len(targets)
                or not mask.get('active')or mask.get('count')!=len(targets)
                or mask.get('placement_key')!=reply.get('placement_key')or mask.get('task_session')!=self.lease.get('job_session')
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Stopped printer still has an unconfirmed input or changed scope')
        self._settled_print_read=command['id']
        try:return self.native('snapshot')
        finally:self._settled_print_read=None
    def observe_stopped_projection_stage(self):
        from projection_stage_reconciliation import preview,reconcile
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists() or (d/'result.json').exists() or (self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No stopped projection error receipt')
        error=json.loads((d/'error.json').read_text());stage=json.loads((d/'stage.json').read_text());model=json.loads((d/'native-model.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        bounds=preview(command,error,stage,model,state,events[-1],self.world,self.lease['job_session'])
        path=self.out/'unresolved-projection-stage.json';record=dict(pending=True,command=command['id'],world_session=self.world);write_json(path,record)
        self._projection_stage_read=command['id']
        try:frame=self.native('scan',min=bounds['min'],max=bounds['max'],details=True,include_predictions=True)
        finally:self._projection_stage_read=None
        proof=reconcile(stage,model,frame,self.status());record.update(pending=False,proof=proof,scan_id=frame['id']);write_json(path,record)
        return dict(proof=proof,scene=frame)
    def observe_refused_merchant_purchase(self):
        """Observe one exact native refusal before its output click was dispatched."""
        from merchant_preflight_abort import observable
        state=self.status(observing=True);command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No known merchant pre-purchase refusal')
        error=json.loads((d/'error.json').read_text());book=json.loads((d/'actual-one-trade/one-trade.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        first=book.get('receipts',[{}])[0];selection=next((e for e in reversed(events)if e.get('request_id')==first.get('id')),None)
        if not event or not selection or not observable(command,error,book,state,event,selection,self.world,self.lease['job_session']):
            raise RuntimeError('Merchant purchase is not proved refused before dispatch')
        self._merchant_abort_read=command['id']
        try:return self.native('snapshot')
        finally:self._merchant_abort_read=None
    def observe_refused_bridged_purchase(self,path):
        """Bind a known no-packet primitive refusal to its original external trade journal."""
        from bridged_trade_abort import observable
        path=Path(path).resolve();state=self.status(observing=True)
        if not path.is_relative_to(self.out.resolve()):raise RuntimeError('Bridge journal escaped this owner')
        scope=hashlib.sha256((state['server'].lower().removesuffix(':25565')+'|minecraft:overworld').encode()).hexdigest()[:20]
        pointer=json.loads((self.root/'merchant-trades'/scope/'active.json').read_text())
        if Path(pointer['journal']).resolve()!=path:raise RuntimeError('Bridge journal is not the active original transaction')
        command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(d/'error.json').exists()or not(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No exact terminal bridged purchase refusal')
        source=path.read_bytes();book=json.loads(source);reply=json.loads((d/'result.json').read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==reply.get('id')),None)
        selection=next((v for v in reversed(events)if v.get('request_id')==(book.get('receipts')or[{}])[0].get('id')),None)
        if not observable(book,command,event,selection,reply,state,self.world,self.lease['job_session']):
            raise RuntimeError('Bridged output was not a proved unissued purchase')
        binding={'journal':str(path),'original_sha256':hashlib.sha256(source).hexdigest(),'world_session':self.world,
                 'task_session':self.lease['job_session'],'command':command,'refusal':event,'selection':selection,
                 'native_reply':reply,'observed_state':state,'purchase_credit':0}
        destination=path.parent/'native-request-binding.json'
        if destination.exists():raise RuntimeError('Existing request binding must not be overwritten')
        self._bridged_abort_read=command['id']
        try:result=self.native('snapshot')
        finally:self._bridged_abort_read=None
        binding['read_only_snapshot_id']=result['id'];write_json(destination,binding);return binding
    def observe_refused_selection_registry(self):
        """Snapshot the unresolved-registry preflight only after proving the old selection unissued."""
        from merchant_preflight_abort import selection_was_unissued
        from villager_trading import combined
        from collections import Counter
        state=self.status(observing=True);command=json.loads((self.out/'command.json').read_text());d=self.out/command['id'];error=json.loads((d/'error.json').read_text());server=state['server'].lower().removesuffix(':25565');scope=hashlib.sha256((server+'|minecraft:overworld').encode()).hexdigest()[:20];path=Path(json.loads((self.root/'merchant-trades'/scope/'active.json').read_text())['journal']).resolve()
        if not path.is_relative_to(self.out.resolve()):raise RuntimeError('Original merchant journal outside this owner')
        book=json.loads(path.read_text());old_error=json.loads((path.parents[1]/'error.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];refusal=next(v for v in reversed(events)if v.get('request_id')==book['pending']['request_id']);last=next(v for v in reversed(events)if v.get('request_id')==error.get('last_request'));menu=state.get('menu')or{};merchant=menu.get('merchant')or{}
        if(command.get('action')!='merchant_buy_one'or error.get('error')!='Original merchant transaction is unresolved; no new purchase or replay'
           or(d/'actual-one-trade/one-trade.json').exists()or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None or(self.out/'control/unconfirmed-native-request.json').exists()
           or not selection_was_unissued(book,old_error,refusal,self.world,self.lease['job_session'])or error.get('last_request')!=state.get('last_request')
           or last.get('phase')!='done'or last.get('world_session')!=self.world or last.get('params',{}).get('task_session')!=self.lease['job_session']
           or menu.get('type')!='MerchantMenu'or menu.get('material_owned')is not True or merchant.get('owned')is not True or merchant.get('owner_task')!=self.lease['job_session']or merchant.get('villager_uuid')!=book['uuid']
           or menu.get('cursor',{}).get('count')!=0 or any(v['count']for v in menu['slots'][:3])or combined(state)!=Counter(book['before'])):raise RuntimeError('Registry refusal is not a proved empty no-packet selection abort')
        self._merchant_abort_read=command['id']
        try:return self.native('snapshot')
        finally:self._merchant_abort_read=None
    def observe_refused_merchant_selection(self):
        """Read only an exact no-packet selection refusal; no selection or purchase is replayed."""
        from merchant_preflight_abort import observable_selection
        state=self.status(observing=True);command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('No exact refused merchant selection')
        error=json.loads((d/'error.json').read_text());book=json.loads((d/'actual-one-trade/one-trade.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((v for v in reversed(events)if v.get('request_id')==error.get('last_request')),None)
        if not event or not observable_selection(command,error,book,state,event,self.world,self.lease['job_session']):raise RuntimeError('Selection or payment outcome remains unresolved; no retry')
        self._merchant_abort_read=command['id']
        try:return self.native('snapshot')
        finally:self._merchant_abort_read=None
    def observe_consumed_merchant_opening(self):
        """Only observe a completed first purchase and a refused repeated opening."""
        from consumed_merchant_quote import observable
        state=self.status(observing=True);command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists():raise RuntimeError('No known repeated-opening refusal')
        error=json.loads((d/'error.json').read_text());server=state['server'].lower().removesuffix(':25565');scope=hashlib.sha256((server+'|minecraft:overworld').encode()).hexdigest()[:20]
        pointer=json.loads((self.root/'merchant-trades'/scope/'active.json').read_text());path=Path(pointer['journal']).resolve()
        if not path.is_relative_to(self.out.resolve()):raise RuntimeError('Prior transaction is outside the original controller')
        previous=json.loads(path.read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]if events else{}
        if not observable(command,error,previous,state,event,self.world,self.lease['job_session'],journal_exists=(d/'actual-one-trade/one-trade.json').exists(),unknown_exists=(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Repeated-opening refusal is not a conserved completed prior transaction')
        self._merchant_abort_read=command['id']
        try:return self.native('snapshot')
        finally:self._merchant_abort_read=None
    def observe_unstarted_trade_workspace(self):
        """Observe the ordinary capacity check before a trade journal or selection exists."""
        state=self.status(observing=True);command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==error.get('last_request')),None)
        from trade_workspace_observation import observable
        if not observable(command,error,state,event,self.world,self.lease['job_session'],
                journal_exists=(d/'actual-one-trade/one-trade.json').exists(),
                unknown_exists=(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Trade capacity refusal is not a proved before-selection terminal')
        self._merchant_abort_read=command['id']
        try:return self.native('snapshot')
        finally:self._merchant_abort_read=None
    def observe_unstarted_harness_log_failure(self):
        """Only snapshot a passive finder log failure with its prior scan still exact."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No retained passive Harness log failure')
        error=json.loads((d/'error.json').read_text());path=Path(command['plan']).resolve()
        if not path.is_relative_to(self.out.resolve()):raise RuntimeError('Original owner plan required')
        plan=json.loads(path.read_text());prior=json.loads((self.root/('reply-'+error['last_request']+'.json')).read_text())
        request=json.loads((self.root/'request.json').read_text())
        if(command.get('action')!='harness_iron_stage'or plan.get('decision',{}).get('action')!='find_zombie'
                or plan.get('world_session')!=self.world or plan.get('task_session')!=self.lease['job_session']
                or error.get('type')!='FileNotFoundError'or '.loaded-hostiles.json-'not in error.get('error','')
                or(d/'surface-observation').exists()or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or error['last_request']!=plan.get('fresh_scan_id')or prior.get('id')!=error['last_request']
                or request.get('id')!=error['last_request']or prior.get('id')!=state.get('last_request')
                or prior.get('world_session')!=self.world or prior.get('phase')!='done'
                or prior.get('control_revision')!=state.get('control_revision')or prior.get('pos')!=state.get('pos')
                or inventory_counts(prior)!=inventory_counts(state)or state.get('screen')or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Passive finder is not proved to have stopped before native dispatch')
        self._harness_output_read=command['id']
        try:return self.native('snapshot')
        finally:self._harness_output_read=None
    def observe_partial_depot_audit(self):
        """Snapshot the exact read-only audit terminal; preserve its partial journal."""
        from depot_audit_observation import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No retained partial depot audit')
        error=json.loads((d/'error.json').read_text());prefix,number=command['id'].rsplit('-',1)
        previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        intent=json.loads((previous/'intent.json').read_text());prior=json.loads((previous/'result.json').read_text())
        if intent.get('action')!='native' or intent.get('op')!='scan':raise RuntimeError('Audit lacks its preceding inventory baseline')
        candidates=[]
        for path in (self.out/'control').glob('depot-audit-*.json'):
            partial=json.loads(path.read_text())
            if path.stat().st_mtime>=(d/'intent.json').stat().st_mtime:candidates.append((path,partial))
        if len(candidates)!=1:raise RuntimeError('Exact partial audit journal is ambiguous')
        path,partial=candidates[0];events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        if not event or not observable(command,error,partial,prior,state,event,self.world,self.lease['job_session']):
            raise RuntimeError('Partial audit has unresolved input or changed inventory')
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_missing_storage_record(self,prior_native_result=None):
        """Observe a refused first depot access with the prior native receipt intact."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if prior_native_result is not None:
            source=Path(prior_native_result).resolve()
            if source.name!='result.json' or not source.is_relative_to(self.out.resolve()) or source.parent==d.resolve():
                raise RuntimeError('Exact prior native result in this same controller required')
            previous=source.parent
        if (command.get('action')not in('exchange','audit_depots')or not(d/'error.json').exists()or(d/'result.json').exists()
                or not(previous/'result.json').exists()or(previous/'error.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Missing depot record has no unchanged prior native terminal')
        error=json.loads((d/'error.json').read_text());prior=json.loads((previous/'result.json').read_text());intent=json.loads((previous/'intent.json').read_text())
        if (error.get('error')!='Storage position has no current scoped Kit record'
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or intent.get('action')!='native'or prior.get('phase')!='done'
                or prior.get('world_session')!=self.world or prior.get('id')!=error.get('last_request')
                or prior.get('id')!=state.get('last_request')or prior.get('control_revision')!=state.get('control_revision')
                or prior.get('pos')!=state.get('pos')or inventory_counts(prior)!=inventory_counts(state)
                or state.get('screen')!=''or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Depot record refusal is not proved input-free')
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_unstarted_fixed_tree_landing(self):
        """Observe a proved local landing refusal before native chopping or walking."""
        import math
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists() or(d/'result.json').exists() or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No exact fixed-tree landing preflight')
        error=json.loads((d/'error.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1];pos=state['pos'];y=round(pos[1]);params=event.get('params')or{}
        low=[math.floor(pos[0]-.31),y-1,math.floor(pos[2]-.31)];high=[math.floor(pos[0]+.31),y+1,math.floor(pos[2]+.31)]
        if (command.get('action')!='native' or command.get('op')!='chop'
            or not all(k in(command.get('params')or{})for k in('tree_root','tree_min','tree_max'))
            or error.get('error')not in('固定树正常落地需要完整干燥自然地面','固定树落地身体空间存在方块，未发送走路')
            or error.get('type')!='JobBlocked' or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
            or error.get('last_request')!=state.get('last_request') or event.get('request_id')!=state.get('last_request')
            or event.get('op')!='scan' or event.get('phase')!='done' or event.get('world_session')!=self.world
            or params.get('task_session')!=self.lease['job_session'] or params.get('min')!=low or params.get('max')!=high
            or event.get('position_after')!=pos or event.get('revision_after')!=state.get('control_revision')
            or event.get('inventory_delta') or state.get('health')!=20 or state.get('screen')!=''
            or state.get('chopping') or state.get('navigating') or state.get('pending_scan') or state.get('native_material_busy')):
            raise RuntimeError('Fixed-tree no-input landing outcome is not proved')
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_unstarted_fixed_tree_selection(self):
        """Observe the exact native fixed-tree validation stop, never replay it."""
        from fixed_tree_preflight_refusal import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());directory=self.out/command['id']
        if((directory/'error.json').exists()or not(directory/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()):raise RuntimeError('No known fixed-tree validation terminal')
        reply=json.loads((directory/'result.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]
        if not observable(command,reply,event,state,self.world,self.lease['job_session']):raise RuntimeError('Fixed-tree validation outcome is not proved unchanged and idle')
        self._fixed_tree_selection_read=command['id']
        try:return self.native('snapshot')
        finally:self._fixed_tree_selection_read=None
    def observe_settled_stopped_chop(self):
        """Read a fully acknowledged idle tree stop; never resume or replay the chop."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if (command.get('action')!='native' or command.get('op')!='chop' or not(d/'result.json').exists()
                or(d/'error.json').exists() or not(previous/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):raise RuntimeError('No exact acknowledged idle tree stop')
        result=json.loads((d/'result.json').read_text());before=json.loads((previous/'result.json').read_text());intent=json.loads((previous/'intent.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]
        if (result.get('phase')!='stopped' or result.get('detail')!='chopper stopped'
                or result.get('world_session')!=self.world or before.get('world_session')!=self.world
                or result.get('id')!=state.get('last_request') or event.get('request_id')!=state.get('last_request')
                or event.get('op')!='chop' or event.get('phase')!='stopped' or event.get('inventory_delta')
                or event.get('world_session')!=self.world or(event.get('params')or{}).get('task_session')!=self.lease['job_session']
                or intent.get('action')!='native' or intent.get('op')!='scan' or before.get('phase')!='done'
                or inventory_counts(before)!=inventory_counts(state) or inventory_counts(result)!=inventory_counts(state)
                or before.get('pos')!=result.get('pos') or result.get('pos')!=state.get('pos')
                or result.get('control_revision')!=state.get('control_revision') or state.get('health')!=20
                or state.get('screen')!='' or state.get('chopping') or state.get('navigating')
                or state.get('chopper_remaining') or state.get('chopper_platforms') or state.get('pending_scan')
                or state.get('native_material_busy')):raise RuntimeError('Tree stop still has work, stock or control ambiguity')
        self._stopped_chop_read=command['id']
        try:return self.native('snapshot')
        finally:self._stopped_chop_read=None
    def shulker_storage_click(self,**params):
        """Move exactly one witnessed box through an SDK-owned storage window."""
        from shulker_storage_click import permitted,signature
        deadline=time.monotonic()+3;observed=[]
        while True:
            state=self.status(observing=True)
            if state.get('health')!=20 or state.get('menu',{}).get('id')!=params.get('menu_id'):
                raise RuntimeError('Shulker window or healthy player changed before any click')
            ready=self._owned_menu(state,observing=True)and permitted(state,params,self.world,self.lease['job_session'])
            if ready:
                if not observed or state['time']>observed[-1]:observed.append(state['time'])
                if len(observed)>=2:break
            else:observed=[]
            if time.monotonic()>deadline:raise RuntimeError('Exact owned shulker pickup or empty-slot return required')
            time.sleep(.05)
        self._shulker_storage_click=signature(state,params,self.world)
        try:return self.native('slot_click',**params)
        finally:self._shulker_storage_click=None
    def observe_acknowledged_empty_shulker(self,menu_id):
        """Read an already-open native-owned empty box after a nonempty-content timeout."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No retained empty-shulker opening timeout')
        error=json.loads((d/'error.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1];menu=state.get('menu')or{}
        index=next((i for i in range(len(events)-1,-1,-1)if events[i].get('op')=='interact'and(events[i].get('params')or{}).get('pos')==command.get('pos')),None)
        origin=events[index]if index is not None else{};tail=events[index+1:]if index is not None else[]
        if (command.get('action')!='open_shulker'or error.get('error')!='Chest opening was not acknowledged'
            or error.get('type')!='RuntimeError'or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
            or error.get('last_request')!=state.get('last_request')or event.get('request_id')!=state.get('last_request')
            or origin.get('phase')!='done'or origin.get('world_session')!=self.world
            or any(v.get('op')!='snapshot'or v.get('phase')not in(None,'done')or v.get('world_session')!=self.world
                   or(v.get('params')or{}).get('task_session')!=self.lease['job_session']or v.get('inventory_delta')for v in tail)
            or(event.get('params')or{}).get('task_session')!=self.lease['job_session']
            or(origin.get('params')or{}).get('task_session')!=self.lease['job_session']or event.get('inventory_delta')
            or state.get('health')!=20 or state.get('screen')!='ShulkerBoxScreen'
            or menu.get('type')!='ShulkerBoxMenu'or menu.get('id')!=menu_id or type(menu_id)is not int or menu_id<=0
            or menu.get('material_owned')is not True or len(menu.get('slots',[]))!=63
            or menu.get('cursor',{}).get('count')!=0 or any(v.get('count')for v in menu['slots'][:27])
            or state.get('navigating')or state.get('pending_scan')or state.get('native_material_busy')):
            raise RuntimeError('Original native-owned empty window is not fully witnessed')
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_partial_missing_storage_record(self):
        """Read after completed depot visits; do not replay or complete the failed exchange."""
        from partial_depot_record_observation import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if (not(d/'error.json').exists()or(d/'result.json').exists()
                or not(previous/'result.json').exists()or(previous/'error.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No completed prefix before a missing depot record')
        error=json.loads((d/'error.json').read_text());baseline=json.loads((previous/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==error.get('last_request')),None)
        visits=[json.loads(line)for line in(self.out/'control/depot-exchanges.jsonl').read_text().splitlines()]
        visits=[v for v in visits if baseline['time']<v.get('at_ms',0)<=state['time']]
        if not observable(command,error,baseline,visits,event,state,self.world,self.lease['job_session']):
            raise RuntimeError('Depot prefix or its final native terminal remains unproved')
        write_json(self.out/(command['id']+'-completed-prefix-observation.json'),{
            'original_command':command,'completed_visits':visits,'original_error':error,
            'partial_inventory':dict(__import__('material_plan').inventory_counts(state)),
            'original_exchange_complete':False,'original_request_replayed':False})
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def close_unloaded_occupied_furnace(self):
        """Close an inspected occupied furnace without moving any of its items."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if command.get('action')!='smelt_material'or not(d/'result.json').exists()or(d/'error.json').exists()or not(d/'smelting.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No known occupied-furnace preflight to close')
        result=json.loads((d/'result.json').read_text());book=json.loads((d/'smelting.json').read_text());menu=state.get('menu')or{}
        if(result.get('phase')!='blocked'or result.get('detail')!='指定熔炉有未处理物品，请先收回或选择空炉'
                or book.get('world_session')!=self.world or book.get('batches')!=[]or book.get('complete')is not False
                or state.get('screen')!='FurnaceScreen'or menu.get('type')!='FurnaceMenu'or menu.get('material_owned')is not True
                or menu.get('cursor',{}).get('count')!=0 or state.get('health')!=20 or state.get('manual_movement')is not False):
            raise RuntimeError('Furnace loading, ownership, or cursor remains unresolved')
        self._unloaded_furnace_close=command['id']
        try:return self.native('close_menu')
        finally:self._unloaded_furnace_close=None
    def observe_unstarted_smelting_recipe(self):
        """Observe a recipe-validation refusal before any furnace manifest or input."""
        from material_jobs.processing import _recipe
        from material_jobs.protocol import JobBlocked
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if command.get('action')!='smelt_material'or not(d/'result.json').exists()or(d/'error.json').exists()or(d/'smelting.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('Smelting preparation is not a proved input-free refusal')
        result=json.loads((d/'result.json').read_text());message='配方不是当前游戏可验证的普通 1:1 熔炼配方'
        if result.get('phase')!='blocked'or result.get('detail')!=message:raise RuntimeError('Different processing outcome must remain retained')
        try:_recipe(command['recipe'],json.loads(Path(command['profile']).read_text()))
        except JobBlocked as error:
            if str(error)!=message:raise
        else:raise RuntimeError('Original recipe is no longer a proved validation refusal')
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]if events else{}
        if(event.get('request_id')!=state.get('last_request')or event.get('phase')!='done'
                or event.get('world_session')!=self.world or event.get('params',{}).get('task_session')!=self.lease['job_session']
                or event.get('revision_after')!=state.get('control_revision')
                or (state.get('menu')or{}).get('cursor',{}).get('count')!=0
                or any(v.get('count')for v in (state.get('menu')or{}).get('slots',[])[:5])
                or state.get('health')!=20 or state.get('manual_movement')is not False or state.get('screen')!=''
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Processing owner or prior close is not an idle unchanged terminal')
        write_json(self.out/(command['id']+'-unstarted-recipe-observation.json'),{'original_command':command,'original_result':result,'furnace_input_dispatched':False,'old_request_replayed':False})
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_storage_profile_refusal(self):
        """Snapshot an exact pre-adapter profile refusal; never run its exchange again."""
        from storage_profile_refusal import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No exact storage-profile refusal to observe')
        error=json.loads((d/'error.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        if not observable(command,error,event,state,self.world,self.lease['job_session']):
            raise RuntimeError('Storage adapter or current owner remains unresolved')
        write_json(self.out/(command['id']+'-profile-refusal-observation.json'),{'original_command':command,'original_error':error,'storage_adapter_started':False,'old_request_replayed':False})
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_unstarted_storage_access(self):
        """Preserve settled preparation, without retrying an unregistered storage route."""
        from unstarted_storage_access import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if(not(d/'error.json').exists()or(d/'result.json').exists()
                or not(previous/'result.json').exists()or(previous/'error.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Storage entry has no retained exact terminal')
        error=json.loads((d/'error.json').read_text());baseline=json.loads((previous/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        start=next((i for i,v in enumerate(events)if v.get('request_id')==baseline.get('id')),None)
        segment=events[start+1:]if start is not None else[]
        if not observable(command,error,baseline,segment,state,self.world,self.lease['job_session']):
            raise RuntimeError('Storage preparation or possible container input remains unresolved')
        write_json(self.out/(command['id']+'-unstarted-storage-observation.json'),{
            'original_command':command,'original_error':error,'completed_preparation':segment,
            'container_access_credit':0,'original_request_replayed':False})
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_bed_entity_refusal(self):
        """Observe the initial bed scene refusal, before any placement input."""
        return self._observe_bed_preflight_refusal('An entity intersects the new bed; no placement')
    def observe_bed_space_refusal(self):
        """Only read a bed's initial blocked body/floor survey, never replay use."""
        return self._observe_bed_preflight_refusal('Bed halves and standing cell need empty body space over dry solid floors')
    def _bed_scan_after_settled_walk(self,state,command,event,events):
        """Recognise a small completed landing during the initial read-only scan."""
        try:
            prefix,number=command['id'].rsplit('-',1);p=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
            old=json.loads((p/'intent.json').read_text());done=json.loads((p/'result.json').read_text());before=event['position_before'];after=event['position_after'];target=old['params']['target']
            previous=next(e for e in events if e.get('request_id')==done.get('id'))
            return (old.get('action')=='native'and old.get('op')=='walk'and old['params'].get('restore_flight')is False
                    and done.get('phase')=='done'and done.get('world_session')==self.world
                    and previous.get('op')=='walk'and previous.get('phase')=='done'and previous.get('world_session')==self.world
                    and previous.get('params',{}).get('task_session')==self.lease.get('job_session')
                    and all(previous.get('params',{}).get(k)==v for k,v in old.get('params',{}).items())
                    and previous.get('position_after')==done.get('pos')==before
                    and previous.get('revision_after')==event.get('revision_before')==event.get('revision_after')==state.get('control_revision')
                    and previous.get('health_before')==previous.get('health_after')==state.get('health')==20
                    and previous.get('inventory_delta')=={}and state.get('on_ground')is True and state.get('flight')is False
                    and isinstance(state.get('movement_keys'),dict)and not any(state['movement_keys'].values())
                    and state.get('pos')==after and -.25<=after[1]-before[1]<=0
                    and abs(after[0]-before[0])<1e-6 and abs(after[2]-before[2])<1e-6
                    and abs(after[1]-target[1])<.02 and all(abs(after[i]-target[i])<.3 for i in [0,2]))
        except(OSError,ValueError,TypeError,KeyError,StopIteration):return False
    def _observe_bed_preflight_refusal(self,expected_error):
        from village_beds import cells
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if (command.get('action')!='place_bed' or not(d/'error.json').exists()
                or(d/'result.json').exists()or(d/'actual-directional-bed').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Bed refusal has no input-free initial scene')
        error=json.loads((d/'error.json').read_text());foot=command.get('foot');head,stand=cells(foot,command.get('facing'))
        low=[min(foot[i],head[i],stand[i])-1 for i in range(3)];high=[max(foot[i],head[i],stand[i])+1 for i in range(3)];low[1]=foot[1]-1;high[1]=foot[1]+2
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        if (error.get('error')!=expected_error
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or error.get('last_request')!=state.get('last_request')
                or not event or event.get('op')!='scan'or event.get('phase')!='done'
                or event.get('params',{}).get('min')!=low or event.get('params',{}).get('max')!=high
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('world_session')!=self.world or event.get('revision_after')!=state.get('control_revision')
                or(event.get('position_before')!=event.get('position_after')
                   and not self._bed_scan_after_settled_walk(state,command,event,events))or event.get('inventory_delta')!={}
                or event.get('health_before')!=20 or event.get('health_after')!=20
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Bed refusal lacks its exact scan-only terminal')
        self._bed_entity_read=command['id']
        try:return self.native('snapshot')
        finally:self._bed_entity_read=None
    def observe_exchange_shortage(self):
        """Observe a settled partial exchange without replaying its transfers."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if (command.get('action')!='exchange' or (d/'error.json').exists()
                or not(d/'result.json').exists() or (self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Exchange shortage has no known terminal')
        reply=json.loads((d/'result.json').read_text());visited=reply.get('visited')or[]
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==state.get('last_request')),None)
        remaining=reply.get('remaining_withdraw')or{}
        held=inventory_counts(state)
        expected_withdraw={k:n-held[k]for k,n in command.get('withdraw',{}).items()if held[k]<n}
        expected_deposit={k:held[k]-n for k,n in command.get('deposit',{}).items()if held[k]>n}
        positive=lambda counts:{k:v for k,v in counts.items()if k!='minecraft:air'and v>0}
        closed_terminal=event is not None and event.get('op')=='close_menu'
        # Recorded indoor storage closes the box before walking back outside.
        # Accept that completed, inventory-immutable exit only for a snapshot.
        walked_terminal=False
        import math
        end_position=(event or{}).get('position_after');position=state.get('pos')
        settled_exit=(all(isinstance(p,list)and len(p)==3
                          and all(type(v)in(int,float)and math.isfinite(v)for v in p)
                          for p in (end_position,position))
                      and math.hypot(end_position[0]-position[0],end_position[2]-position[2])<=.5
                      and 0<=end_position[1]-position[1]<=1)
        if(event and command.get('profile') and settled_exit
                and (event.get('op')=='walk' and state.get('on_ground')is True and state.get('flight')is False
                     or event.get('op')=='navigate' and event.get('params',{}).get('air_only')is True
                     and state.get('flight')is True)
                and isinstance(state.get('movement_keys'),dict)and not any(state['movement_keys'].values())):
            index=events.index(event)
            close=next((i for i in range(index-1,-1,-1)if events[i].get('op')=='close_menu'),None)
            walked_terminal=(close is not None and all(
                e.get('phase')=='done'and e.get('world_session')==self.world
                and e.get('params',{}).get('task_session')==self.lease.get('job_session')
                and e.get('inventory_delta')=={}and e.get('health_after')==20
                for e in events[close:index+1]))
        if (reply.get('complete')is not False or reply.get('remaining_deposit')!=expected_deposit
                or remaining!=expected_withdraw or not(remaining or expected_deposit)
                or any(type(v)is not int or v<=0 for v in remaining.values())
                or any(k not in command.get('withdraw',{})for k in remaining)
                or not visited or positive(visited[-1].get('after',{}))!=positive(inventory_counts(state))
                or not event or not(closed_terminal or walked_terminal)or event.get('phase')!='done'
                or event.get('world_session')!=self.world or event.get('revision_after')!=state.get('control_revision')
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('inventory_delta')!={} or event.get('health_after')!=20
                or state.get('screen')!=''or state.get('health')!=20 or state.get('manual_movement')is not False
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Exchange shortage is not an idle conserved terminal')
        self._exchange_shortage_read=command['id']
        try:return self.native('snapshot')
        finally:self._exchange_shortage_read=None
    def observe_indoor_stand_refusal(self):
        """Observe a documented chest preflight that sent no interaction."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text());proof=json.loads((self.out/'control/indoor-stand-refusal.json').read_text());old=proof.get('state',{})
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        if(command.get('action')!='open_chest_from_pose'or error.get('error')!='Indoor chest registered grounded pose or controller changed; no interaction'
                or proof.get('interaction_sent')is not False or proof.get('pose')!=command.get('pose')or proof.get('pos')!=command.get('pos')
                or old.get('world_session')!=self.world or old.get('control_revision')!=state.get('control_revision')
                or old.get('supervision_lease')!=state.get('supervision_lease')
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or(self.out/'control/unconfirmed-native-request.json').exists()or(d/'result.json').exists()
                or not event or event.get('op')not in('scan','snapshot','walk','navigate')or event.get('phase')not in(None,'done')
                or event.get('world_session')!=self.world or error.get('last_request')!=state.get('last_request')
                or event.get('revision_after')!=state.get('control_revision')
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or state.get('pending_scan')or state.get('navigating')or state.get('native_material_busy')):
            raise RuntimeError('Indoor opening lacks exact no-interaction preflight evidence')
        self._indoor_stand_read=command['id']
        try:return self.native('snapshot')
        finally:self._indoor_stand_read=None
    def observe_brewer_pose_refusal(self):
        """Only read a brewing pose check rejected before scan or interaction."""
        from brewer_preflight_observation import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);prior=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if not(d/'error.json').exists()or(d/'result.json').exists()or not(prior/'result.json').exists()or(prior/'error.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No settled pre-input brewer pose refusal')
        error=json.loads((d/'error.json').read_text());baseline=json.loads((prior/'result.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        if not observable(command,error,baseline,events[-1]if events else None,state,self.world,self.lease['job_session']):
            raise RuntimeError('Brewer pose refusal is not an unchanged no-input terminal')
        write_json(self.out/(command['id']+'-pre-input-pose-observation.json'),{'original_command':command,'original_error':error,'brewer_opened':False,'original_request_replayed':False})
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_container_kind_scan_refusal(self):
        """Retain a completed one-cell scan that rejected a wrong container kind."""
        from storage_kind_refusal import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No settled container kind refusal')
        error=json.loads((d/'error.json').read_text())
        prefix,number=command['id'].rsplit('-',1);previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        baseline=json.loads((previous/'result.json').read_text())
        reply=json.loads((self.root/('reply-'+str(error.get('last_request'))+'.json')).read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        if not observable(command,error,baseline,reply,events[-1]if events else None,state,self.world,self.lease['job_session']):
            raise RuntimeError('Container kind refusal lacks an unchanged read-only terminal')
        write_json(self.out/(command['id']+'-kind-scan-observation.json'),{'original_command':command,'original_error':error,
            'scan_reply':reply,'container_access_credit':0,'original_request_replayed':False})
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_storage_schema_refusal(self):
        """Read an invalid top-face plan rejected before its first native call."""
        from storage_schema_refusal import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1)
        previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if(not(d/'error.json').exists()or(d/'result.json').exists()
                or not(previous/'result.json').exists()or(previous/'error.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Storage schema refusal has no settled predecessor')
        error=json.loads((d/'error.json').read_text());baseline=json.loads((previous/'result.json').read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=events[-1]if events else None
        if not observable(command,error,baseline,event,state,self.world,self.lease['job_session']):
            raise RuntimeError('Storage schema refusal has possible native input or changed state')
        write_json(self.out/(command['id']+'-schema-refusal-observation.json'),{
            'original_command':command,'original_error':error,'container_access_credit':0,'original_request_replayed':False})
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def observe_refused_storage_face(self):
        """Read a container plan's initial face rejection, before item use."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(command.get('action')!='open_chest_from_pose'or not(d/'error.json').exists()
                or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No exact failed storage face plan')
        error=json.loads((d/'error.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==error.get('last_request')),None)
        if(error.get('error')!='Target interaction face is occluded or out of reach'
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or not event or event.get('op')!='interact'or event.get('phase')!='error'or event.get('detail')!=error['error']
                or event.get('world_session')!=self.world or event.get('request_id')!=state.get('last_request')
                or event.get('position_before')!=event.get('position_after')or event.get('position_after')!=state.get('pos')
                or event.get('inventory_delta')!={}or event.get('health_before')!=20 or event.get('health_after')!=20
                or event.get('revision_before')!=event.get('revision_after')or event.get('revision_after')!=state.get('control_revision')
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('params',{}).get('pos')!=command.get('pos')or event.get('params',{}).get('face')!=command.get('face')
                or event.get('params',{}).get('expected_hand')!='minecraft:netherite_sword'
                or state.get('screen')!=''or state.get('health')!=20 or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Storage face rejection is not an unchanged input-free terminal')
        self._storage_record_read=command['id']
        try:return self.native('snapshot')
        finally:self._storage_record_read=None
    def quarantine_unconfirmed_boat_place(self):
        """Retain the unresolved placement and observe; prohibit further boat use."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text());path=d/'actual-one-boat/place.json';book=json.loads(path.read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==book.get('request_id')),None)
        if(command.get('action')!='boat_place'or error.get('error')!='Original boat input has no conserved two-frame result; retained without replay'
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or(self.out/'control/unconfirmed-native-request.json').exists()or(d/'result.json').exists()
                or book.get('complete')is not False or book.get('pending')!='place'
                or book.get('world_session')!=self.world or book.get('support')!=command.get('support')
                or book.get('item')!=command.get('item')or not book.get('item','').endswith('_boat')
                or not event or event.get('op')!='interact'or event.get('phase')!='done'
                or event.get('world_session')!=self.world
                or book.get('request_id')!=error.get('last_request')or book.get('request_id')!=state.get('last_request')
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('params',{}).get('pos')!=book['support']
                or event.get('params',{}).get('expected_hand')!=book['item']
                or event.get('revision_after')!=state.get('control_revision')
                or state.get('navigating')or state.get('pending_scan')or state.get('native_material_busy')):
            raise RuntimeError('Unconfirmed boat placement lacks its exact known native terminal')
        marker={'world_session':self.world,'journal':str(path.resolve()),'journal_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'request_id':book['request_id'],'original_request_replayed':False,'outcome_unresolved':True}
        fence=self.out.parent/'unresolved-boat-placement.json'
        if fence.exists()and json.loads(fence.read_text())!=marker:
            registry=self.out.parent/'unresolved-boat-placement-additional.json'
            data=json.loads(registry.read_text())if registry.exists()else{'schema':1,'entries':[]}
            if data.get('schema')!=1 or not isinstance(data.get('entries'),list):raise RuntimeError('Invalid retained boat registry')
            found=[r for r in data['entries']if r.get('request_id')==marker['request_id']]
            if found and found!=[marker]:raise RuntimeError('Original retained boat entry changed')
            if not found:data['entries'].append(marker)
            write_json(registry,data)
        else:write_json(fence,marker)
        self._boat_outcome_read=command['id']
        try:return self.native('snapshot')
        finally:self._boat_outcome_read=None
    def observe_retained_boat_guard(self):
        """Observe a persistent placement guard; keep its original intent intact."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(not(d/'error.json').exists()or(d/'result.json').exists()or(d/'actual-one-boat').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No input-free retained boat guard')
        error=json.loads((d/'error.json').read_text());prefix,number=command['id'].rsplit('-',1);prior=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        before=json.loads((prior/'result.json').read_text());intent=json.loads((prior/'intent.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];last=events[-1]
        if(command.get('action')!='boat_place'or error.get('type')!='RuntimeError'
           or error.get('error')!='Original boat intent is unresolved; no repeated input'
           or 'native_inflight'not in error or error['native_inflight']is not None
           or 'unconfirmed_native_request'not in error or error['unconfirmed_native_request']is not None
           or intent.get('action')!='native'or intent.get('op')!='snapshot'or before.get('phase')not in(None,'done')
           or before.get('world_session')!=self.world or before.get('id')!=error.get('last_request')
           or error.get('last_request')!=state.get('last_request')or before.get('pos')!=state.get('pos')
           or inventory_counts(before)!=inventory_counts(state)
           or last.get('op')!='snapshot'or last.get('phase')not in(None,'done')or last.get('world_session')!=self.world
           or last.get('request_id')!=state.get('last_request')or last.get('revision_after')!=state.get('control_revision')
           or last.get('params',{}).get('task_session')!=self.lease.get('job_session')):
            raise RuntimeError('Retained boat guard may have dispatched or ownership changed')
        self._retained_boat_guard_read=command['id']
        try:return self.native('snapshot')
        finally:self._retained_boat_guard_read=None
    def observe_boat_space_refusal(self):
        """Observe the exact scan-only boat preflight; no placement was sent."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text())
        support=command.get('support');stand=command.get('stand')
        if(command.get('action')!='boat_place'or not all(isinstance(p,list)and len(p)==3 and all(type(v)is int for v in p)for p in(support,stand))
                or error.get('error')!='Boat body space is obstructed'or error.get('type')!='RuntimeError'
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or(d/'result.json').exists()or(d/'actual-one-boat').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Boat placement is not an exact input-free space refusal')
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
        low=[min(support[i],stand[i])-1 for i in range(3)]
        high=[max(support[i],stand[i])+1 for i in range(3)];high[1]=support[1]+4
        if(not event or event.get('op')!='scan'or event.get('phase')!='done'
                or event.get('world_session')!=self.world or error.get('last_request')!=state.get('last_request')
                or event.get('params',{}).get('min')!=low or event.get('params',{}).get('max')!=high
                or event.get('params',{}).get('details')is not True
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('position_before')!=event.get('position_after')or event.get('position_after')!=state.get('pos')
                or event.get('inventory_delta')!={}or event.get('health_before')!=20 or event.get('health_after')!=20
                or type(event.get('revision_before'))is not int or event.get('revision_before')!=event.get('revision_after')
                or event.get('revision_after')!=state.get('control_revision')
                or state.get('navigating')or state.get('pending_scan')or state.get('native_material_busy')):
            raise RuntimeError('Original boat refusal lacks the exact idle scan evidence')
        self._boat_space_read=command['id']
        try:return self.native('snapshot')
        finally:self._boat_space_read=None
    def observe_refused_boat_approach(self):
        """Read a boat's failed ground approach before its placement journal exists."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=events[-1]if events else{}
        if(command.get('action')!='boat_place' or(d/'result.json').exists()or(d/'actual-one-boat').exists()
                or error.get('error')!='No visible collision-free depot approach'
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or(self.out/'control/unconfirmed-native-request.json').exists()
                or event.get('op')!='approach_block'or event.get('phase')!='error'
                or event.get('request_id')!=error.get('last_request')or event.get('request_id')!=state.get('last_request')
                or event.get('world_session')!=self.world
                or event.get('params',{}).get('pos')!=command.get('stand')
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('position_before')!=event.get('position_after')or event.get('position_after')!=state.get('pos')
                or event.get('inventory_delta')!={}or event.get('revision_before')!=event.get('revision_after')
                or event.get('revision_after')!=state.get('control_revision')
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Boat approach has no proved unchanged input-free placement preflight')
        self._boat_space_read=command['id']
        try:return self.native('snapshot')
        finally:self._boat_space_read=None
    def observe_refused_boat_face(self):
        """Observe a boat use rejected before any interaction; never replay it."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text());path=d/'actual-one-boat/place.json';book=json.loads(path.read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]
        from boat_face_refusal import observable
        if not observable(command,error,book,event,state,self.world,self.lease['job_session'],dict(inventory_counts(state))):
            raise RuntimeError('Boat face refusal has no conserved pre-input evidence')
        if(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('Boat face refusal has an unresolved native outcome')
        self._boat_space_read=command['id']
        try:frame=self.native('snapshot')
        finally:self._boat_space_read=None
        write_json(d/'face-refusal-observation.json',{'original_journal_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'observation_request':frame.get('id'),'placement_credit':0,'original_request_replayed':False})
        return frame
    def observe_refused_boat_geometry(self):
        """Observe a pure argument refusal before the worker dispatched anything."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text());prefix,number=command['id'].rsplit('-',1)
        prior=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        intent=json.loads((prior/'intent.json').read_text());reply=json.loads((prior/'result.json').read_text())
        if(command.get('action')!='boat_place'or error.get('type')!='ValueError'
                or error.get('error')!='A normal boat, exact same-level support and separate standing floor are required'
                or(d/'actual-one-boat').exists()or(d/'result.json').exists()or(prior/'error.json').exists()
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or(self.out/'control/unconfirmed-native-request.json').exists()
                or intent.get('action')!='native'or intent.get('op')!='navigate'or reply.get('phase')!='done'
                or reply.get('id')!=error.get('last_request')or reply.get('id')!=state.get('last_request')
                or reply.get('world_session')!=self.world or reply.get('pos')!=state.get('pos')
                or reply.get('control_revision')!=state.get('control_revision')or inventory_counts(reply)!=inventory_counts(state)
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Boat argument refusal is not proved input-free and unchanged')
        self._boat_space_read=command['id']
        try:return self.native('snapshot')
        finally:self._boat_space_read=None
    def observe_unstarted_runtime_artifact_refusal(self,previous_id,installed_sha256):
        """Only observe missing artifact arguments before installation or native dispatch."""
        from material_plan import inventory_counts
        if not isinstance(previous_id,str)or Path(previous_id).name!=previous_id:raise ValueError('Exact prior queue command required')
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id'];prior_dir=self.out/previous_id
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No untouched runtime artifact refusal')
        error=json.loads((d/'error.json').read_text());intent=json.loads((prior_dir/'intent.json').read_text());prior=json.loads((prior_dir/'result.json').read_text())
        installed=self.root.parent/'runtime/twob2tkit-engine.jar'
        if(command.get('action')!='hot_runtime_update'or 'sha256'in command or 'version'in command
                or error.get('type')!='KeyError'or error.get('error')!="'sha256'"
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or intent.get('action')!='native'or(prior_dir/'error.json').exists()or prior.get('phase')!='done'
                or prior.get('id')!=error.get('last_request')or prior.get('id')!=state.get('last_request')
                or prior.get('world_session')!=self.world or prior.get('pos')!=state.get('pos')
                or prior.get('control_revision')!=state.get('control_revision')or inventory_counts(prior)!=inventory_counts(state)
                or state.get('screen')or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or hashlib.sha256(installed.read_bytes()).hexdigest()!=installed_sha256):
            raise RuntimeError('Runtime artifact installation or native outcome is not proved untouched')
        self._deferred_reload_read=command['id']
        try:return self.native('snapshot')
        finally:self._deferred_reload_read=None
    def observe_acknowledged_runtime_version_mismatch(self,before_generation,restored_sha256):
        """The reload ACK is retained even when SDK version verification failed."""
        from runtime_version_observation import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if not(d/'error.json').exists()or(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('No known acknowledged runtime version mismatch')
        error=json.loads((d/'error.json').read_text());reply_path=self.root/('reply-'+str(error.get('last_request'))+'.json')
        # Consumed replies may be retired; the unchanged native status retains the same exact ACK identity.
        reply=json.loads((reply_path if reply_path.exists()else self.root/'status.json').read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        if(not observable(command,error,reply,events[-1]if events else None,state,self.world,self.lease['job_session'],before_generation)
                or hashlib.sha256((self.root.parent/'runtime/twob2tkit-engine.jar').read_bytes()).hexdigest()!=restored_sha256):
            raise RuntimeError('Runtime ACK, continuity, or restored fallback is unproved')
        write_json(self.out/(command['id']+'-acknowledged-version-mismatch.json'),{
            'original_command':command,'original_error':error,'native_reply':reply,'sdk_version_check_passed':False,
            'restored_on_disk_sha256':restored_sha256,'original_request_replayed':False})
        self._deferred_reload_read=command['id']
        try:return self.native('snapshot')
        finally:self._deferred_reload_read=None
    def observe_missing_hot_update_metadata(self):
        """Only observe an artifact-inspection KeyError before installation starts."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());directory=self.out/command['id'];error=json.loads((directory/'error.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]
        if(command.get('action')!='hot_runtime_update'or 'sha256'in command
            or error.get('type')!='KeyError'or error.get('error')!="'sha256'"
            or "command['sha256']"not in error.get('traceback','')or 'village_project.py'not in error.get('traceback','')
            or(directory/'result.json').exists()or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
            or(self.out/'control/unconfirmed-native-request.json').exists()
            or error.get('last_request')!=state.get('last_request')or event.get('request_id')!=state.get('last_request')
            or event.get('phase')!='done'or event.get('world_session')!=self.world
            or event.get('params',{}).get('task_session')!=self.lease['job_session']
            or event.get('revision_after')!=state.get('control_revision')or event.get('position_after')!=state.get('pos')
            or state.get('health')!=20 or state.get('guard_busy')or state.get('screen')or state.get('manual_movement')):
            raise RuntimeError('Hot-update metadata refusal is not a proved input-free preflight')
        self._deferred_reload_read=command['id']
        try:return self.native('snapshot')
        finally:self._deferred_reload_read=None
    def observe_deferred_runtime_reload(self):
        """Read after the SDK waited for defense without dispatching a reload."""
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id'];error=json.loads((d/'error.json').read_text());prefix,number=command['id'].rsplit('-',1);prior=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)));intent=json.loads((prior/'intent.json').read_text());reply=json.loads((prior/'result.json').read_text())
        if(command.get('action')!='hot_runtime_update'or error.get('error')!='Defense remains busy'
                or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or(d/'result.json').exists()or(prior/'error.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()
                or intent.get('action')!='native'or intent.get('op')!='walk'or reply.get('phase')!='done'
                or reply.get('id')!=error.get('last_request')or reply.get('id')!=state.get('last_request')
                or reply.get('world_session')!=self.world or reply.get('control_revision')!=state.get('control_revision')
                or inventory_counts(reply)!=inventory_counts(state)or state.get('health')!=20
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Runtime update was not a proved pre-dispatch defense wait')
        self._deferred_reload_read=command['id']
        try:return self.native('snapshot')
        finally:self._deferred_reload_read=None
    def observe_stopped_walk(self):
        """Read a confirmed halted walk at its final position; never retry it."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if((d/'error.json').exists()or not(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Original walk outcome is not confirmed')
        reply=json.loads((d/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==reply.get('id')),None)
        from settled_drop_walk import conserved_coast
        settled_coast=False
        if conserved_coast(reply,state):
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline:
                fresh=self.status()
                if(fresh.get('time')!=state.get('time')and fresh.get('pos')==state.get('pos')
                        and conserved_coast(reply,fresh)):
                    state=fresh;settled_coast=True;break
                time.sleep(.05)
        timed_out_before_waiting=(reply.get('phase')=='stopped'and reply.get('detail')=='脚本任务达到时间上限'
                                 and state.get('phase')=='waiting'
                                 and state.get('detail')=='time limit reached; inspect progress before resuming'
                                 and state.get('health')==20 and state.get('on_ground')is True and state.get('flight')is False)
        ordinary_stop=(reply.get('phase')=='waiting'and reply.get('detail')in(
                       'time limit reached; inspect progress before resuming','unsafe drop ahead; choose another walking waypoint'))
        if(command.get('action')!='native'or command.get('op')!='walk'
                or not(ordinary_stop or timed_out_before_waiting)
                or reply.get('world_session')!=self.world or reply.get('id')!=state.get('last_request')
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or not isinstance(state.get('movement_keys'),dict)or any(state['movement_keys'].values())
                or not event or event.get('op')!='walk'or event.get('phase')!=reply.get('phase')
                or event.get('detail')!=reply['detail']or event.get('world_session')!=self.world
                or event.get('inventory_delta')!={}or event.get('health_before')!=20 or event.get('health_after')!=20
                or event.get('position_after')!=reply.get('pos')or(reply.get('pos')!=state.get('pos')and not settled_coast)
                or type(event.get('revision_after'))is not int or event['revision_after']!=state.get('control_revision')
                or(state.get('supervision_lease')or{}).get('revision')!=event['revision_after']
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or any(event.get('params',{}).get(k)!=v for k,v in command.get('params',{}).items())):
            raise RuntimeError('Walk is not an exact healthy stopped native terminal')
        self._stopped_walk_read=command['id']
        try:return self.native('snapshot')
        finally:self._stopped_walk_read=None
    def observe_stopped_pickup_walk(self,item,amount):
        """Only snapshot a known aborted walk with one conserved passive pickup."""
        from material_plan import inventory_counts
        if not isinstance(item,str)or not item.startswith('minecraft:')or type(amount)is not int or not 1<=amount<=64:
            raise ValueError('Exact positive pickup required')
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if((d/'error.json').exists()or not(d/'result.json').exists()or(previous/'error.json').exists()
                or not(previous/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Pickup walk has no known native terminal')
        reply=json.loads((d/'result.json').read_text());prior=json.loads((previous/'result.json').read_text());intent=json.loads((previous/'intent.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==reply.get('id')),None)
        expected=inventory_counts(prior);expected[item]+=amount;before=reply.get('pos');after=state.get('pos')
        settled=(isinstance(before,list)and isinstance(after,list)and len(before)==len(after)==3
                 and all(type(v)in(int,float)and __import__('math').isfinite(v)for v in before+after)
                 and -.25<=after[1]-before[1]<=0 and all(abs(after[i]-before[i])<=.15 for i in(0,2)))
        if(command.get('action')!='native'or command.get('op')!='walk'
                or reply.get('phase')!='stopped'or reply.get('detail')!='脚本任务达到时间上限'
                or reply.get('world_session')!=self.world or reply.get('id')!=state.get('last_request')
                or state.get('phase')!='waiting'or state.get('detail')!='time limit reached; inspect progress before resuming'
                or state.get('health')!=20 or state.get('screen')!=''or state.get('on_ground')is not True or state.get('flight')is not False
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or not isinstance(state.get('movement_keys'),dict)or any(state['movement_keys'].values())or not settled
                or intent.get('action')!='native'or intent.get('op')not in('scan','snapshot')or prior.get('phase')!='done'
                or prior.get('world_session')!=self.world or not event or event.get('op')!='walk'
                or event.get('phase')!=reply['phase']or event.get('detail')!=reply['detail']or event.get('world_session')!=self.world
                or event.get('position_before')!=prior.get('pos')or event.get('position_after')!=before
                or event.get('inventory_delta')!={item:amount}or inventory_counts(reply)!=expected or inventory_counts(state)!=expected
                or event.get('health_before')!=20 or event.get('health_after')!=20
                or event.get('revision_before')!=prior.get('control_revision')
                or type(event.get('revision_after'))is not int or event['revision_after']!=reply.get('control_revision')
                or event['revision_after']!=state.get('control_revision')or(state.get('supervision_lease')or{}).get('revision')!=event['revision_after']
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or any(event.get('params',{}).get(k)!=v for k,v in command.get('params',{}).items())):
            raise RuntimeError('Stopped pickup walk is not a conserved healthy idle terminal')
        self._stopped_pickup_read=command['id']
        try:return self.native('snapshot')
        finally:self._stopped_pickup_read=None
    def observe_unstarted_occluded_mine(self):
        """Observe an occluded face only when no mining packet was started."""
        from unstarted_mining import rejected_without_mining
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if((d/'error.json').exists()or not(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Mining outcome is not a known unstarted refusal')
        reply=json.loads((d/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==reply.get('id')),None)
        if(command.get('action')!='native'or command.get('op')!='mine_block'
                or not rejected_without_mining(reply,state.get('last_request'),self.world,command.get('params',{}).get('pos'))
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or not event or event.get('op')!='mine_block'or event.get('phase')!='waiting'
                or event.get('detail')!=reply['detail']or event.get('world_session')!=self.world
                or event.get('inventory_delta')!={}or event.get('health_before')!=20 or event.get('health_after')!=20
                or event.get('position_before')!=event.get('position_after')or event.get('position_after')!=state.get('pos')
                or reply.get('pos')!=state.get('pos')or event.get('revision_after')!=state.get('control_revision')
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or any(event.get('params',{}).get(k)!=v for k,v in command.get('params',{}).items())):
            raise RuntimeError('Mining may have started or its ownership changed')
        self._unstarted_mine_read=command['id']
        try:return self.native('snapshot')
        finally:self._unstarted_mine_read=None
    def observe_refused_air_path(self):
        """Observe one exact zero-movement navigation refusal; never retry it."""
        return self._observe_refused_input('navigate','Air-only navigation requires the current material lease and a loaded clear dry path','_refused_air_read')
    def observe_refused_worksite_navigation(self):
        """Read the host's stopped, unmoved site rejection; never widen its bounds.

        This rejection occurs after stopWorkForScript, so the retained material
        revision advances by two even though no navigation was started.
        """
        state=self.status();command=json.loads((self.out/'command.json').read_text())
        directory=self.out/command['id']
        if((directory/'error.json').exists()or not(directory/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Worksite navigation has no known refusal')
        reply=json.loads((directory/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=events[-1]if events else{}
        if(state.get('health')!=20 or state.get('manual_movement')is not False
                or state.get('phase')!='error' or state.get('screen')
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or command.get('action')!='native'or command.get('op')!='navigate'
                or command.get('params',{}).get('air_only')is not True
                or reply.get('phase')!='error'or reply.get('detail')!='Target outside worksite'
                or reply.get('world_session')!=self.world or reply.get('id')!=state.get('last_request')
                or event.get('request_id')!=reply.get('id')or event.get('world_session')!=self.world
                or event.get('op')!='navigate'or event.get('phase')!='error'
                or event.get('detail')!=reply['detail']or event.get('inventory_delta')!={}
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or any(event.get('params',{}).get(k)!=v for k,v in command['params'].items())
                or state.get('pos')!=reply.get('pos')or state.get('pos')!=event.get('position_before')
                or state.get('pos')!=event.get('position_after')
                or type(event.get('revision_before'))is not int
                or event.get('revision_after')!=event['revision_before']+2
                or state.get('control_revision')!=event.get('revision_after')
                or reply.get('control_revision')!=state.get('control_revision')
                or not isinstance(state.get('movement_keys'),dict)or any(state['movement_keys'].values())):
            raise RuntimeError('Worksite refusal is not a stationary healthy terminal')
        self._refused_air_read=command['id']
        try:return self.native('snapshot')
        finally:self._refused_air_read=None
    def observe_recovered_air_injury(self):
        """Snapshot a known stopped route after full protected recovery; never retry it."""
        from recovered_air_injury import observable
        from safety_interlock import require_unlocked
        state=self.status();require_unlocked(self.root,state)
        command=json.loads((self.out/'command.json').read_text());directory=self.out/command['id']
        if(directory/'error.json').exists()or not(directory/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('Navigation outcome is not known; no recovered observation')
        reply=json.loads((directory/'result.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]if events else{}
        if not observable(command,reply,event,state,self.world,self.lease['job_session']):raise RuntimeError('Stopped injury route is not fully recovered and still owned')
        self._recovered_air_injury_read=command['id']
        try:return self.native('snapshot')
        finally:self._recovered_air_injury_read=None
    def observe_stopped_air_navigation(self):
        """Read an acknowledged navigation stop at its actual partial position."""
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(d/'error.json').exists()or not(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():raise RuntimeError('Air navigation has no known terminal')
        reply=json.loads((d/'result.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]if events else{}
        from material_plan import inventory_counts
        import math
        a,b=reply.get('pos'),state.get('pos')
        from stopped_air_observation import guard_rise,incidental_drops
        settled=(isinstance(a,list)and isinstance(b,list)and len(a)==len(b)==3
                 and all(type(v)in(int,float)and math.isfinite(v)for v in a+b)
                 and math.hypot(a[0]-b[0],a[2]-b[2])<=.05
                 and (0<=a[1]-b[1]<=.1 or guard_rise(reply,event,state))
                 and state.get('flight')is True and state.get('manual_movement')is False and state.get('screen')==''
                 and isinstance(reply.get('inventory'),list)and isinstance(state.get('inventory'),list)
                 and (inventory_counts(reply)==inventory_counts(state)
                      or guard_rise(reply,event,state)and incidental_drops(reply,state)))
        if(command.get('action')!='native'or command.get('op')!='navigate'or command.get('params',{}).get('air_only')is not True
                or reply.get('phase')!='waiting'or reply.get('detail')!='air-only path changed; no blocks were excavated'
                or reply.get('id')!=state.get('last_request')or reply.get('world_session')!=self.world
                or reply.get('control_revision')!=state.get('control_revision')or(reply.get('pos')!=state.get('pos')and not settled)
                or event.get('request_id')!=reply.get('id')or event.get('op')!='navigate'or event.get('phase')!='waiting'
                or event.get('world_session')!=self.world or event.get('position_after')!=reply.get('pos')
                or event.get('revision_after')!=state.get('control_revision')or event.get('inventory_delta')!={}
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('params',{}).get('target')!=command['params'].get('target')
                or state.get('health')!=20 or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or not isinstance(state.get('movement_keys'),dict)or any(state['movement_keys'].values())):
            raise RuntimeError('Navigation has no proved stopped partial position; no replay')
        self._stopped_air_read=command['id']
        try:return self.native('snapshot')
        finally:self._stopped_air_read=None
    def observe_stopped_air_pickup(self,expected_uuid):
        """Only snapshot a conserved single-source pickup during the settled route."""
        from stopped_air_pickup import observable
        from villager_events import read
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);p=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if((d/'error.json').exists()or not(d/'result.json').exists()or not(p/'result.json').exists()
                or(p/'error.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Stopped pickup has no known adjacent snapshot and route terminal')
        reply=json.loads((d/'result.json').read_text());prior=json.loads((p/'result.json').read_text());previous=json.loads((p/'intent.json').read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((v for v in reversed(events)if v.get('request_id')==reply.get('id')),None)
        if not event or not observable(command,reply,previous,prior,event,state,read(self.root,state),self.world,self.lease['job_session'],expected_uuid):
            raise RuntimeError('Stopped air route lacks its exact original player pickup proof; no replay')
        self._stopped_air_read=command['id']
        try:return self.native('snapshot')
        finally:self._stopped_air_read=None
    def observe_refused_scan_volume(self):
        """Only observe an exact rejected read, retaining its original receipt."""
        return self._observe_refused_input('scan','Invalid scan volume','_scan_volume_read')
    def observe_unloaded_scan(self):
        """Retain an incomplete unloaded read and send only a new snapshot."""
        from unloaded_scan_observation import observable
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if((d/'error.json').exists()or not(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No known terminal unloaded scan')
        reply=json.loads((d/'result.json').read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==reply.get('id')),None)
        if not event or not observable(command,reply,event,state,self.world,self.lease['job_session']):
            raise RuntimeError('Unloaded scan lacks conserved read-only evidence')
        self._partial_scan_read=command['id']
        try:return self.native('snapshot')
        finally:self._partial_scan_read=None
    def observe_refused_towing_air_path(self):
        """Observe an exact nested zero-input refusal, retaining its original leg."""
        from boat_towing import known_air_preflight
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text());path=d/'actual-villager-towing/tow.json';book=json.loads(path.read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==state.get('last_request')),None)
        pending=book.get('pending')or{}
        if(command.get('action')!='tow_villager_boat'or error.get('error')!='Original towing leg did not complete; retain it without replay'
                or (d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()
                or not known_air_preflight(book,state,state,error)or state.get('health')!=20
                or state.get('navigating')or any((state.get('movement_keys')or{}).values())
                or not event or event.get('op')!='navigate'or event.get('phase')!='error'
                or event.get('detail')!=state.get('detail')or event.get('world_session')!=self.world
                or event.get('position_before')!=event.get('position_after')or event.get('position_after')!=state.get('pos')
                or event.get('inventory_delta')!={}or event.get('revision_before')!=event.get('revision_after')
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('params',{}).get('target')!=pending.get('target')):
            raise RuntimeError('Towing leg is not a proven unchanged pre-dispatch refusal')
        original_hash=hashlib.sha256(path.read_bytes()).hexdigest();self._towing_refusal_read=command['id']
        try:frame=self.native('snapshot')
        finally:self._towing_refusal_read=None
        if frame.get('world_session')!=self.world or frame.get('pos')!=state['pos']or frame.get('health')!=20:
            raise RuntimeError('Refused towing observation changed; preserve the original pending leg')
        book.setdefault('refused_legs',[]).append({'original_pending':pending,'native_event':event,'journal_before_sha256':original_hash,
                                                'observation_id':frame.get('id'),'movement_credit':0,'original_request_replayed':False})
        book['pending']=None;write_json(path,book)
        return {'complete':True,'proof':str(path),'movement_credit':0,'observation':frame}
    def observe_stopped_towing_health_change(self):
        """Observe a completed native leg followed by a cargo-health abort.

        The original trip remains failed; this grants no transport resume.
        """
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        error=json.loads((d/'error.json').read_text());journal=Path(command.get('resume')or d/'actual-villager-towing/tow.json').resolve()
        if not journal.is_relative_to(self.out.resolve()):raise RuntimeError('Towing health journal escaped current owner')
        book=json.loads(journal.read_text());pending=book.get('pending')or{}
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=events[-1]if events else{}
        if(command.get('action')!='tow_villager_boat'or error.get('error')!='Founder health changed after the original towing leg'
                or(d/'result.json').exists()or error.get('native_inflight')is not None or error.get('unconfirmed_native_request')is not None
                or(self.out/'control/unconfirmed-native-request.json').exists()or pending.get('op')!='navigate'
                or pending.get('request_id')!=error.get('last_request')or pending.get('request_id')!=state.get('last_request')
                or event.get('request_id')!=state.get('last_request')or event.get('op')!='navigate'or event.get('phase')!='done'
                or event.get('world_session')!=self.world or book.get('world_session')!=self.world
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
                or event.get('position_after')!=state.get('pos')or event.get('revision_after')!=state.get('control_revision')
                or event.get('inventory_delta')!={}or state.get('health')!=20 or state.get('navigating')
                or state.get('native_material_busy')or state.get('pending_scan')or any((state.get('movement_keys')or{}).values())):
            raise RuntimeError('Cargo-health abort lacks a known stopped native terminal')
        self._towing_refusal_read=command['id']
        try:return self.native('snapshot')
        finally:self._towing_refusal_read=None
    def observe_refused_air_seed(self):
        """Read an exact seed admission refusal; never retry its placement."""
        state=self.status()
        if state.get('health')!=20 or state.get('manual_movement')is not False or state.get('screen'):
            raise RuntimeError('Seed admission observation requires healthy unchanged input ownership')
        return self._observe_refused_input('projection_air_seed','Air seed requires the current healthy idle guarded material lease','_refused_face_read')
    def observe_refused_interaction_face(self):
        """Observe a rejected initial face check before rotation or item use."""
        return self._observe_refused_input('interact','Target interaction face is occluded or out of reach','_refused_face_read')
    def observe_refused_entity_reach(self):
        """Read a known initial entity ray refusal; no interaction retry."""
        command=json.loads((self.out/'command.json').read_text())
        reply=json.loads((self.out/command['id']/'result.json').read_text())
        if reply.get('detail')not in('Entity out of reach','Entity is occluded'):
            raise RuntimeError('Entity interaction is not a known pre-input reach refusal')
        return self._observe_refused_input('interact_entity',reply['detail'],'_refused_face_read')
    def observe_sleeping_bridged_opening(self,path):
        """Observe a terminal sleeping-adult menu wait; never repeat its entity use."""
        from sleeping_merchant_observation import observable_bridged
        from villager_events import read
        path=Path(path).resolve();state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if(not path.is_relative_to(self.out.resolve())or(d/'error.json').exists()or not(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):raise RuntimeError('No known bridged opening wait')
        opening=json.loads(path.read_text());reply=json.loads((d/'result.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==reply.get('id')),None)
        if not observable_bridged(command,opening,event,reply,state,read(self.root,state),self.world,self.lease['job_session']):
            raise RuntimeError('Original entity use/menu outcome remains unresolved')
        self._sleeping_bridge_read=command['id']
        try:return self.native('snapshot')
        finally:self._sleeping_bridge_read=None
    def observe_refused_held_item(self):
        """Read a hand mismatch rejected before rotation, placement or use."""
        return self._observe_refused_input('interact','Held item changed','_refused_face_read')
    def observe_refused_bucket_face(self):
        """Only observe an exact bucket-place ray rejection with no state delta."""
        return self._observe_refused_input('bucket_place','Bucket support face is occluded or outside normal reach','_refused_face_read')
    def observe_refused_bucket_occupancy(self):
        """Observe occupancy refusal only; it never retries a bucket use."""
        return self._observe_refused_input('bucket_place','Bucket target contains a currently loaded entity','_refused_face_read')
    def observe_controlled_release_decoration_refusal(self):
        """Only observe a refused controlled release; never bypass its flood gate."""
        command=json.loads((self.out/'command.json').read_text())
        if command.get('params',{}).get('controlled_water_release')is not True:
            raise RuntimeError('No explicitly scoped controlled water request')
        return self._observe_refused_input('mine_block','Controlled release cannot replace decorations or waterlog blocks','_refused_face_read')
    def observe_controlled_release_containment_refusal(self):
        """Read a flood-containment refusal; retain the dam and the native gate."""
        command=json.loads((self.out/'command.json').read_text())
        if command.get('params',{}).get('controlled_water_release')is not True:
            raise RuntimeError('No explicitly scoped controlled water request')
        return self._observe_refused_input('mine_block','Released water could escape the declared enclosure','_refused_face_read')
    def observe_refused_collection_approach(self):
        """Observe a collector rejected before a supported approach was started."""
        return self._observe_refused_input('collect_item','No visible collision-free depot approach','_refused_face_read')
    def observe_refused_collection_path(self):
        """Only observe an unchanged collector path refusal; never replay it."""
        return self._observe_refused_input('collect_item','No loaded collision-free route to this depot; no ceiling is broken','_refused_face_read',phases=('waiting',))
    def observe_refused_mining_reach(self):
        """Only observe the exact unmoved mining reach preflight rejection."""
        return self._observe_refused_input('mine_block','Mining target out of reach','_refused_face_read')
    def observe_stopped_lectern_mining(self,*,allow_unacknowledged_readback=False):
        """Read only the target twice, retaining a persistent mutation fence."""
        from stopped_lectern_mining import preview,reconcile
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id'];path=self.out/'lectern-mining-readback.json'
        prior=json.loads(path.read_text())if path.exists()else None
        if(prior and(prior.get('pending')is not False or prior.get('original_command',{}).get('id')==command['id']))or(d/'error.json').exists()or not(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('Original lectern readback must be retained; no replay')
        reply=json.loads((d/'result.json').read_text());events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((v for v in reversed(events)if v.get('request_id')==reply.get('id')),None)
        marker=preview(command,reply,event,state,self.world,self.lease['job_session'],
                       allow_unacknowledged_readback=allow_unacknowledged_readback)
        # Reading an unacknowledged stop never retires its native claim. Keep the
        # same target fenced across future controller handoffs as well.
        project_path=self.out.parent/'project-state.json'
        if project_path.exists():
            project=json.loads(project_path.read_text());targets=project.setdefault('protected_pending_excavation_targets',[])
            if not any(v.get('world_session')==self.world and v.get('pos')==marker['target']and v.get('native_claim_not_cleared')is True for v in targets):
                targets.append({'world_session':self.world,'pos':marker['target'],'native_claim_not_cleared':True,
                                'original_request':reply['id'],'proof':str(path.relative_to(self.out.parent))})
                write_json(project_path,project)
        if prior:
            archive=self.out/'lectern-mining-readbacks';archive.mkdir(exist_ok=True)
            write_json(archive/(hashlib.sha256(json.dumps(prior,sort_keys=True).encode()).hexdigest()+'.json'),prior)
        write_json(path,marker);self._stopped_lectern_read=command['id']
        try:
            frames=[];states=[]
            for _ in range(2):
                frames.append(self.native('scan',min=marker['target'],max=marker['target'],details=True,include_predictions=True));states.append(self.status());time.sleep(.15)
            result=reconcile(marker,frames,states);write_json(path,result);return result
        finally:self._stopped_lectern_read=None
    def observe_refused_lectern_reset(self):
        """Read the initial policy error; tick-time mining stops stay fenced."""
        command=json.loads((self.out/'command.json').read_text());params=command.get('params')or{}
        if(params.get('reset_empty_lectern')is not True or not params.get('expected_villager_uuid')
                or not params.get('expected_quote_opening')or not params.get('expected_offers_fingerprint')
                or not str(params.get('expected_state','')).startswith('Block{minecraft:lectern}')
                or 'has_book=false'not in params['expected_state']):
            raise RuntimeError('No exact empty lectern preflight intent')
        return self._observe_refused_input('mine_block','Lectern reset requires an empty lectern beside the same freshly quoted untraded librarian without a requested book','_lectern_preflight_read')
    def observe_refused_excavation_claim(self):
        """Observe a native begin refusal; retain the older target claim."""
        return self._observe_refused_input('mine_block','An earlier excavation at this target is unconfirmed; no retry sent','_refused_face_read')
    def observe_protected_empty_lectern(self):
        """Observe a default container-protection refusal; grant no mining permission."""
        command=json.loads((self.out/'command.json').read_text());p=command.get('params')or{}
        if (p.get('reset_empty_lectern')not in(None,False)
                or not str(p.get('expected_state','')).startswith('Block{minecraft:lectern}')
                or 'has_book=false'not in p['expected_state']
                or not all(p.get(k)for k in('expected_villager_uuid','expected_quote_opening','expected_offers_fingerprint'))):
            raise RuntimeError('No exact quoted empty lectern without its reset opt-in')
        return self._observe_refused_input('mine_block','Block entities and containers are protected','_refused_face_read')
    def observe_rejected_printer(self):
        """Reconcile one air acknowledgement without awarding old print credit."""
        from rejected_printer import conserved_server_rejection
        from material_plan import inventory_counts
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        prefix,number=command['id'].rsplit('-',1);p=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
        if((d/'error.json').exists()or not(d/'result.json').exists()or not(p/'result.json').exists()
                or(p/'error.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Printer rejection has no exact native terminal')
        reply=json.loads((d/'result.json').read_text());prior=json.loads((p/'result.json').read_text());intent=json.loads((p/'intent.json').read_text())
        events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((v for v in reversed(events)if v.get('request_id')==reply.get('id')),None)
        if not conserved_server_rejection(command,reply,intent,prior,event,state,self.world,self.lease['job_session']):
            raise RuntimeError('No conserved explicit negative server acknowledgement; original print remains fenced')
        path=self.out.parent/'retained-printer-outcome.json';old=json.loads(path.read_text())if path.exists()else{}
        if old.get('pending'):raise RuntimeError('Original rejection observation is still pending')
        history=old.get('history',[])
        if old:history.append({k:v for k,v in old.items()if k!='history'})
        target=reply['bounded_targets'][0];record={'pending':True,'request_id':reply['id'],'world_session':self.world,'target':target,
            'source':str(d/'result.json'),'source_sha256':hashlib.sha256((d/'result.json').read_bytes()).hexdigest(),'history':history,'old_goal_credit':0}
        write_json(path,record);self._rejected_print_read=command['id']
        try:frame=self.native('scan',min=target,max=target,details=True,include_predictions=True)
        finally:self._rejected_print_read=None
        prediction=frame.get('scan_predictions')or{};current=self.status()
        if(frame.get('world_session')!=self.world or frame.get('scan_cells_read')!=1 or frame.get('scan_total_cells')!=1
                or frame.get('blocks')!=[]or prediction.get('complete')is not True or prediction.get('pending_count')!=0
                or prediction.get('pending_positions')!=[]or inventory_counts(current)!=inventory_counts(prior)):
            raise RuntimeError('Current rejected-print state is not settled; retain the original mask')
        cleared=self.native('projection_batch_clear',placement_key=reply['placement_key'])
        record.update(pending=False,classification='server_air_update_and_conserved_inventory_current_predictions_settled',observation=frame,
                      cleared_mask_request=cleared.get('id'),original_request_not_replayed=True)
        write_json(path,record);return record
    def _refused_air_after_settled_walk(self,state,command,event,reply,events):
        """Recognise bounded walk inertia before the native air-path preflight.

        The bridge rejects this exact error before stopWorkForScript/active.
        This permits observation only, without treating drift as navigation.
        """
        import math
        try:
            prefix,number=command['id'].rsplit('-',1)
            previous=self.out/(prefix+'-'+str(int(number)-1).zfill(len(number)))
            old=json.loads((previous/'intent.json').read_text());done=json.loads((previous/'result.json').read_text())
            prior=next(e for e in events if e.get('request_id')==done.get('id'))
            distance=lambda a,b:math.dist(a,b)
            start,end=event['position_before'],event['position_after'];target=old['params']['target'];origin=prior['position_before']
            dx,dz=end[0]-start[0],end[2]-start[2];wx,wz=target[0]-origin[0],target[2]-origin[2];length=math.hypot(wx,wz)
            flat=(abs(end[1]-start[1])<.01 and distance(end,start)<=.35 and distance(state['pos'],start)<=.35)
            # The walk reply can precede the next request's input snapshot.
            # Account for a bounded, grounded landing in that interval, too;
            # this still authorizes only the exact refusal's read-only snapshot.
            landed=prior['position_after'];gx,gz=start[0]-landed[0],start[2]-landed[2]
            between=(landed!=start and old['params'].get('restore_flight') is False and state.get('on_ground') is True
                     and prior['position_after']==done.get('pos') and length>0
                     and 0<=event['time']-prior['time']<=3
                     and -1.0<=start[1]-landed[1]<=0 and math.hypot(gx,gz)<=.45
                     and math.hypot(start[0]-target[0],start[2]-target[2])<=.45
                     and abs(start[1]-target[1])<=1.05
                     and gx*wx+gz*wz>=0 and abs(gx*wz-gz*wx)/length<=.08
                     and state.get('pos')==end==reply.get('pos')
                     and isinstance(state.get('velocity'),list) and len(state['velocity'])==3
                     and math.hypot(state['velocity'][0],state['velocity'][2])<.03
                     and -.085<=state['velocity'][1]<=.01)
            # Acknowledged walking can release at a boat/bed edge, before
            # gravity completes the half-block step. It is still only a read:
            # exact target height, released controls and settled velocity are
            # required, with drift along the original walking direction.
            step=(old['params'].get('restore_flight')is False and state.get('on_ground')is True
                  and -.65<=end[1]-start[1]<=-.1 and math.hypot(dx,dz)<=.65
                  and math.hypot(start[0]-target[0],start[2]-target[2])<=.15
                  and abs(end[1]-target[1])<.025 and length>0
                  and dx*wx+dz*wz>=0 and abs(dx*wz-dz*wx)/length<=.08
                  and state.get('pos')==end==reply.get('pos')
                  and isinstance(state.get('velocity'),list)and len(state['velocity'])==3
                  and math.hypot(state['velocity'][0],state['velocity'][2])<.03
                  and -.085<=state['velocity'][1]<=.01)
            return (command.get('op')=='navigate'and command.get('params',{}).get('air_only')is True
                    and old.get('action')=='native'and old.get('op')=='walk'and done.get('phase')=='done'
                    and done.get('world_session')==self.world and prior.get('op')=='walk'and prior.get('phase')=='done'
                    and prior.get('world_session')==self.world and prior.get('inventory_delta')=={}
                    and prior.get('health_before')==prior.get('health_after')==state.get('health')==20
                    and prior.get('params',{}).get('task_session')==self.lease.get('job_session')
                    and all(prior.get('params',{}).get(k)==v for k,v in old.get('params',{}).items())
                    and (prior.get('position_after')==event.get('position_before')==done.get('pos') or between)
                    and prior.get('revision_after')==event.get('revision_before')==state.get('control_revision')
                    and reply.get('control_revision')==state.get('control_revision')
                    and state.get('flight')is False and isinstance(state.get('movement_keys'),dict)
                    and not any(state['movement_keys'].values())
                    and(flat or step)
                    and distance(state['pos'],reply['pos'])<=.1)
        except(OSError,ValueError,TypeError,KeyError,StopIteration):return False
    def _observe_refused_input(self,op,detail,marker,*,phases=('error',)):
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if((d/'error.json').exists()or not(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('No confirmed air-path refusal available')
        reply=json.loads((d/'result.json').read_text())
        events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
        event=next((e for e in reversed(events)if e.get('request_id')==reply.get('id')),None)
        if(command.get('action')!='native'or command.get('op')!=op
                or reply.get('phase')not in phases or reply.get('detail')!=detail
                or reply.get('world_session')!=self.world or reply.get('id')!=state.get('last_request')
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
                or not event or event.get('world_session')!=self.world or event.get('op')!=op
                or event.get('phase')!=reply.get('phase')or event.get('detail')!=reply['detail']
                or event.get('inventory_delta')!={}or not isinstance(event.get('position_before'),list)
                or len(event['position_before'])!=3
                or(event.get('position_before')!=event.get('position_after')
                   and not(op=='navigate'and self._refused_air_after_settled_walk(state,command,event,reply,events)))
                or type(event.get('revision_before'))is not int or event.get('revision_before')!=event.get('revision_after')
                or event.get('params',{}).get('task_session')!=self.lease.get('job_session')):
            raise RuntimeError('Air-path outcome is not an exact unmoved preflight refusal')
        setattr(self,marker,command['id'])
        try:return self.native('snapshot')
        finally:setattr(self,marker,None)
    def observe_unconfirmed_pickup_terminal(self):
        """Observe a known settled collector without crediting or replaying pickup."""
        import math
        state=self.status();command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
        if (d/'error.json').exists()or not(d/'result.json').exists()or(self.out/'control/unconfirmed-native-request.json').exists():
            raise RuntimeError('Original collector has no confirmed terminal')
        reply=json.loads((d/'result.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==reply.get('id')),None)
        if(command.get('action')!='native'or command.get('op')!='collect_item'
           or reply.get('phase')!='waiting'or reply.get('detail')!='Drop pickup not confirmed at the reached position'
           or reply.get('id')!=state.get('last_request')or reply.get('world_session')!=self.world
           or not event or event.get('world_session')!=self.world or event.get('op')!='collect_item'
           or event.get('phase')!='waiting'or event.get('detail')!=reply['detail']or event.get('inventory_delta')!={}
           or event.get('health_before')!=20 or event.get('health_after')!=20 or state.get('health')!=20
           or event.get('params',{}).get('task_session')!=self.lease.get('job_session')
           or event.get('revision_after')!=state.get('control_revision')or reply.get('control_revision')!=state.get('control_revision')
           or event.get('position_after')!=reply.get('pos')or not isinstance(state.get('pos'),list)
           or not isinstance(reply.get('pos'),list)or len(reply['pos'])!=3 or len(state['pos'])!=3
           or any(type(v)not in(int,float)or not math.isfinite(v)for v in state['pos']+reply['pos'])
           or math.dist(state['pos'],reply['pos'])>.1 or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')
           or not isinstance(state.get('movement_keys'),dict)or any(state['movement_keys'].values())):
            raise RuntimeError('Collector is not the same healthy settled known terminal')
        self._pickup_terminal_read=command['id']
        try:return self.native('snapshot')
        finally:self._pickup_terminal_read=None
    def observe_missing_drop(self):
        """Read after this exact collector refusal, without replaying collection.

        This does not assert pickup success. The caller must independently
        reconcile inventory and the vanished UUID before resolving its intent.
        """
        state=self.status();old=json.loads((self.out/'command.json').read_text());d=self.out/old['id']
        if((d/'error.json').exists()or not(d/'result.json').exists()
                or(self.out/'control/unconfirmed-native-request.json').exists()):
            raise RuntimeError('Original collector has no known terminal; no recovery observation')
        reply=json.loads((d/'result.json').read_text())
        if(old.get('action')!='native'or old.get('op')!='collect_item'or reply.get('phase')!='error'
                or reply.get('detail')!='Drop is no longer loaded; observe again'
                or reply.get('world_session')!=self.world or reply.get('id')!=state.get('last_request')
                or state.get('navigating')or state.get('native_material_busy')or state.get('pending_scan')):
            raise RuntimeError('Collector refusal is not the exact current idle world; no next request')
        self._missing_drop_observation=old['id']
        try:return self.native('snapshot')
        finally:self._missing_drop_observation=None
    def _workbench(self,q):
        m=q.get('menu')or{}
        return (q.get('screen')=='CraftingScreen'and m.get('type')=='CraftingMenu'and type(m.get('id'))is int and m['id']>0
                and q.get('interface_paused')is False and q.get('inventory_interface_paused')is False)
    def _owned_menu(self,q,*,observing=False):
        if not q.get('screen')or q.get('interface_paused')is not False or q.get('inventory_interface_paused')is not False:return False
        m=q.get('menu')or{}
        try:certificate=json.loads((self.out/'owned-material-menu.json').read_text())
        except(OSError,ValueError):return False
        return (certificate.get('type')==m.get('type')and type(m.get('id'))is int and m['id']>0
                and certificate.get('id')==m['id']and certificate.get('world_session')==self.world
                and certificate.get('task_session')==self.lease.get('job_session')and certificate.get('lease_id')==self.lease.get('id')
                and certificate.get('control_revision')==q.get('control_revision')
                and(observing or m.get('cursor',{}).get('count')==0))
    def _name_tag_click(self,state,params):
        try:certificate=json.loads((self.out/'owned-material-menu.json').read_text())
        except(OSError,ValueError):return False
        from name_tag_anvil import permitted_click
        return self._owned_menu(state) and permitted_click(state,certificate,params)
    def _opening_brewer(self,q):
        if q.get('screen')!='BrewingStandScreen'or q.get('menu',{}).get('type')!='BrewingStandMenu':return False
        try:
            command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
            return(command.get('action')=='open_brewing_stand'and(d/'intent.json').exists()
                   and not(d/'error.json').exists()and not(d/'result.json').exists()
                   and json.loads((d/'intent.json').read_text())==command)
        except(OSError,ValueError,KeyError):return False
    def _opening_planned_anvil(self,q):
        """Observe only a pending typed opening before its SDK certificate is published."""
        menu=q.get('menu')or{}
        if (q.get('screen')!='AnvilScreen' or menu.get('type')!='AnvilMenu'
                or type(menu.get('id'))is not int or menu['id']<=0
                or q.get('interface_paused')is not False or q.get('inventory_interface_paused')is not False
                or len(menu.get('slots',[]))!=39 or menu.get('cursor',{}).get('count')!=0
                or any(row.get('count')!=0 for row in menu['slots'][:3])):return False
        try:
            command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
            kind=command.get('action')
            if kind not in('anvil_enchant_preview','anvil_enchant_combine'):return False
            filename=('actual-zero-xp-anvil-preview/preview.json'if kind=='anvil_enchant_preview'
                      else'actual-one-planned-anvil-output/combine.json')
            book=json.loads((d/filename).read_text())
            return (not(d/'error.json').exists()and not(d/'result.json').exists()
                    and json.loads((d/'intent.json').read_text())==command
                    and book.get('world_session')==self.world and book.get('task_session')==self.lease.get('job_session')
                    and book.get('anvil')==command['pos'] and book.get('output_clicks')==0
                    and book.get('pending')in('open_owned_anvil',{'stage':'open_owned_anvil'}))
        except(OSError,ValueError,KeyError,TypeError):return False
    def _expected_storage_observation(self,q):
        if((q.get('screen'),(q.get('menu')or{}).get('type'))not in(('ContainerScreen','ChestMenu'),('ShulkerBoxScreen','ShulkerBoxMenu'))
                or q.get('interface_paused')is not False or q.get('inventory_interface_paused')is not False):return False
        try:
            command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
            return command.get('action')in('open_chest_from_pose','exchange','audit_depots','open_shulker','take_packed_materials','take_packed_equipment')and(d/'intent.json').exists()and not(d/'error.json').exists()
        except(OSError,ValueError,KeyError):return False
    def _manufacture_command(self):
        try:
            command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
            if command.get('action')=='manufacture'and(d/'intent.json').exists()and not(d/'error.json').exists():return d
        except(OSError,ValueError,KeyError):pass
        return None
    def _opening_workbench(self):
        """Observe our pending opener until the SDK publishes window ownership."""
        try:
            command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
            pos=command.get('pos')
            return (command.get('action')=='open_workbench'and isinstance(pos,list)
                    and len(pos)==3 and all(type(v)is int for v in pos)
                    and not(d/'error.json').exists()and not(d/'result.json').exists()
                    and json.loads((d/'intent.json').read_text())==command)
        except(OSError,ValueError,KeyError,TypeError):return False
    def _smelting_observation(self,q):
        """Only observe the SDK's pending furnace action, never adopt its menu."""
        if q.get('screen')!='FurnaceScreen'or q.get('menu',{}).get('type')!='FurnaceMenu':return False
        try:
            command=json.loads((self.out/'command.json').read_text());d=self.out/command['id']
            return (command.get('action')=='smelt_material'and(d/'intent.json').exists()
                    and not(d/'error.json').exists()and not(d/'result.json').exists()
                    and json.loads((d/'intent.json').read_text())==command)
        except(OSError,ValueError,KeyError,TypeError):return False
    def _completed_workbench(self,q):
        if not self._workbench(q):return False
        d=self._manufacture_command()
        if d is None:return False
        try:result=json.loads((d/'result.json').read_text())
        except(OSError,ValueError):return False
        m=q['menu'];certificate=result.get('owned_menu')or{}
        return (result.get('complete')is True and certificate.get('type')=='CraftingMenu'and certificate.get('id')==m['id']
                and certificate.get('world_session')==self.world and certificate.get('task_session')==self.lease.get('job_session')
                and certificate.get('lease_id')==self.lease.get('id')and certificate.get('control_revision')==q.get('control_revision')
                and m.get('cursor',{}).get('count')==0 and len(m.get('slots',[]))>=10
                and all(row.get('count')==0 for row in m['slots'][:10]))
    def _craft_return(self,state,params):
        """Only return a certified cursor or ingredient grid; never take output."""
        m=state.get('menu')or{}
        if not self._owned_menu(state,observing=True)or m.get('type')!='CraftingMenu':return False
        rows=m.get('slots')or[];cursor=m.get('cursor')or{};slot=params.get('slot')
        if(len(rows)!=46 or type(slot)is not int or not 0<=slot<len(rows)or params.get('menu_id')!=m.get('id')
                or params.get('expected_item')!=rows[slot].get('item')or params.get('expected_count')!=rows[slot].get('count')
                or params.get('expected_cursor')!=(cursor.get('item')if cursor.get('count')else'minecraft:air')
                or params.get('expected_cursor_count')!=cursor.get('count')or params.get('button',0)!=0):return False
        if cursor.get('count',0)>0:
            target=rows[slot]
            return (slot>=len(rows)-36 and params.get('kind')=='pickup'
                    and(target.get('count')==0 or target.get('item')==cursor.get('item'))
                    and target.get('count',0)+cursor['count']<=(target.get('max_stack',64)if target.get('count')else cursor.get('max_stack',64)))
        return 1<=slot<=9 and rows[slot].get('count',0)>0 and params.get('kind')=='quick_move'
    def status(self,*,observing=False,allow_released=False):
        q=read_fresh(self.root);require_unlocked(self.root,q);lease=q.get('supervision_lease')or{}
        owned_screen=not q.get('screen')or q.get('menu',{}).get('material_owned')or self._completed_workbench(q)or self._owned_menu(q,observing=observing)
        if observing:
            from owned_furnace_origin import pending_observation
            owned_screen=owned_screen or self._expected_storage_observation(q)or self._smelting_observation(q)or self._opening_brewer(q)or self._opening_planned_anvil(q)or pending_observation(self,q)
        if observing and self._workbench(q):
            owned_screen=owned_screen or self._manufacture_command()is not None or self._opening_workbench() or getattr(self,'closing_menu',None)==q['menu']['id']
        if(q.get('connected')is not True or q.get('world_session')!=self.world or q.get('manual_movement')
                or q.get('health',0)<19 or not owned_screen
                or (not(observing and allow_released and not lease)
                    and any(lease.get(k)!=self.lease.get(k)for k in ('id','kind','job_session','world_session')))):
            raise RuntimeError('Village plan lost its original healthy native owner; no next command')
        return q
    def send(self,action,*,seconds=90,**params):
        started=time.monotonic();result=None;error=None
        try:
            result=self._send(action,seconds=seconds,**params)
            return result
        except Exception as exc:
            error=repr(exc)
            raise
        finally:
            # Telemetry failure must never mask a native receipt or authorize a
            # retry of an action whose outcome is unknown.
            try:
                monitor=getattr(self,'efficiency',None)
                if monitor is not None:monitor.record(action,params,started,time.monotonic(),result,error)
            except Exception:pass
    def _send(self,action,*,seconds=90,**params):
        retained_targets=self.out.parent/'project-state.json'
        if action=='native'and params.get('op')=='mine_block'and retained_targets.exists():
            pending=json.loads(retained_targets.read_text()).get('protected_pending_excavation_targets',[])
            if any(v.get('world_session')==self.world and v.get('native_claim_not_cleared')is True
                   and v.get('pos')==(params.get('params')or{}).get('pos')for v in pending):
                raise RuntimeError('Project retains this native excavation claim; new owners cannot retry it')
        readback_path=self.out/'lectern-mining-readback.json'
        readback=json.loads(readback_path.read_text())if readback_path.exists()else{}
        readback_observation=False
        if(readback and readback.get('world_session')==self.world and action=='native'
                and params.get('op')=='mine_block'and(params.get('params')or{}).get('pos')==readback.get('target')):
            raise RuntimeError('Native excavation claim remains fenced at this target; readback grants no retry')
        if readback.get('pending'):
            from stopped_lectern_mining import read_allowed
            if(getattr(self,'_stopped_lectern_read',None)!=readback['original_command']['id']
                    or not read_allowed(readback,action,params)):
                raise RuntimeError('Lectern abort requires conserved readback; mutations remain fenced')
            readback_observation=True
        retained_stage=self.out/'unresolved-projection-stage.json'
        if retained_stage.exists() and json.loads(retained_stage.read_text()).get('pending'):
            if not(action=='native' and params.get('op')in('scan','snapshot')):
                raise RuntimeError('Projection stage needs conserved prediction-free observation before further inputs')
        fence=self.out.parent/'unresolved-boat-placement.json'
        marker=json.loads(fence.read_text())if fence.exists()else{}
        returning=action=='native'and params.get('op')=='slot_click'
        state=self.status(observing=True)if returning else self.status();old=self.out/'command.json'
        transport_hold=self.out.parent/'village-transport-safety-hold.json'
        if action=='tow_villager_boat'and transport_hold.exists():
            hold=json.loads(transport_hold.read_text())
            if hold.get('active')is True:
                raise RuntimeError('Village transport safety hold: verify repaired passenger clearance and safety return before using this controller')
        extra=self.out.parent/'unresolved-boat-placement-additional.json'
        if extra.exists():
            entries=json.loads(extra.read_text())['entries'];native=params.get('params')or{}
            boat_use=action=='boat_place'or action=='native'and(params.get('op')=='interact'and str(native.get('expected_hand','')).endswith('_boat')or params.get('op')=='use_item'and str(state.get('hand',{}).get('item','')).endswith('_boat'))
            if boat_use and any(r.get('world_session')==self.world and r.get('outcome_unresolved')is True for r in entries):
                raise RuntimeError('Current-world boat use remains unconfirmed; observe its original journal before any new boat placement')
        retained_print=self.out.parent/'retained-printer-outcome.json'
        if retained_print.exists()and json.loads(retained_print.read_text()).get('pending'):
            native=params.get('params')or{}
            if(action=='native'and(params.get('op')in('professional_print','projection_batch_set')
                    or params.get('op')=='interact'and native.get('expected_hand',state.get('hand',{}).get('item'))=='minecraft:lectern')):
                raise RuntimeError('Original printer observation remains pending; no workstation placement')
        project=self.out.parent/'project-state.json'
        configuration=json.loads(project.read_text())if project.exists()else{}
        from pending_placement_claim import guard as guard_pending_placement
        guard_pending_placement(configuration,self.world,action,params)
        gate=configuration.get('workstation_installation_gate',{})
        # A reset must be restorable before its first destructive input. Use
        # the same current-world assignment guard as workstation placement.
        resetting_lectern=(action=='native'and params.get('op')=='mine_block'
                           and(params.get('params')or{}).get('reset_empty_lectern')is True)
        if gate.get('adult_assignment_bounds')is not None:
            native=params.get('params')or{}
            installing=(resetting_lectern or action=='native'and(params.get('op')=='interact'and native.get('expected_hand',state.get('hand',{}).get('item'))in WORKSTATIONS
                         or params.get('op')=='professional_print'and state.get('hand',{}).get('item')in WORKSTATIONS))
            if action=='build_village_stage':installing=any(row.get('item')in WORKSTATIONS for row in json.loads(Path(params['table']).read_text()).get('expected',[]))
            if installing:
                from village_assignment_guard import wait_for_containment
                area=configuration.get('active_village_bounds',{});low=area.get('min',[760977,63,797786]);high=area.get('max',[761036,76,797818])
                state,missing=wait_for_containment(self.status,gate,{'min':low,'max_exclusive':[v+1 for v in high]},state)
                if missing:raise RuntimeError('Contain current grown or displaced villagers before installing a workstation: '+','.join(missing))
        if gate.get('new_workstations_prohibited_until_gate_passes')and not gate.get('all_contained_verified'):
            native=params.get('params')or{}
            placing=(resetting_lectern or action=='native'and(params.get('op')=='interact'and
                     native.get('expected_hand',state.get('hand',{}).get('item'))in WORKSTATIONS
                     or params.get('op')=='professional_print'and state.get('hand',{}).get('item')in WORKSTATIONS))
            if action=='build_village_stage':
                table=json.loads(Path(params['table']).read_text())
                placing=any(row.get('item')in WORKSTATIONS for row in table.get('expected',[]))
            if placing:raise RuntimeError('Contain all village residents in cells before installing any new workstation')
        if marker.get('outcome_unresolved')and(action=='boat_place'or action=='native'and
                (params.get('op')=='interact'and str((params.get('params')or{}).get('expected_hand','')).endswith('_boat')
                 or params.get('op')=='use_item'and str(state.get('hand',{}).get('item','')).endswith('_boat'))):
            if action!='boat_place'or not params.get('independent_stock'):
                raise RuntimeError('Original boat placement is quarantined; no replacement use or retry')
            from independent_boat_stock import authorize
            authorize(self.out,state,self.lease,{'action':action,**params},marker)
        retained=self.out.parent/'unresolved-lectern-placement-870.json'
        if retained.exists():
            placement=json.loads(retained.read_text());native=params.get('params')or{}
            if(placement.get('outcome_unresolved')and action=='native'and params.get('op')=='interact'
                    and native.get('expected_hand',state.get('hand',{}).get('item'))=='minecraft:lectern'):
                clicked=native.get('pos');delta={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'west':(-1,0,0),'east':(1,0,0)}.get(native.get('face'))
                if not isinstance(clicked,list)or len(clicked)!=3 or delta is None:
                    raise RuntimeError('Exact lectern placement target required while an outcome is retained')
                if placement.get('target')in(clicked,[clicked[i]+delta[i]for i in range(3)]):
                    raise RuntimeError('Original lectern placement is unresolved; do not replace or replay its target')
        craft_return=returning and self._craft_return(state,params.get('params')or{})
        if returning and state.get('screen')=='CraftingScreen'and not craft_return:
            raise RuntimeError('Owned crafting recovery only returns exact cursor or grid ingredients')
        if(action=='native'and params.get('op')=='close_menu'and(state.get('menu')or{}).get('type')=='CraftingMenu'
                and(len(state['menu'].get('slots',[]))<10 or any(v.get('count')!=0 for v in state['menu']['slots'][:10]))):
            raise RuntimeError('Workbench grid still contains items; preserve it before closing')
        cleanup=self._completed_workbench(state)
        if cleanup and not(action=='manufacture'or action=='native'and params.get('op')=='close_menu'):
            raise RuntimeError('Completed owned workbench must close before another village action')
        if self._owned_menu(state)and not state.get('menu',{}).get('material_owned'):
            kind=state['menu']['type']
            from shulker_storage_click import signature
            box_click=(action=='native'and params.get('op')=='slot_click'
                       and getattr(self,'_shulker_storage_click',None)==signature(state,params.get('params')or{},self.world))
            permitted=(action=='transfer'and kind in('ChestMenu','ShulkerBoxMenu')or action=='manufacture'and kind=='CraftingMenu'
                       or action=='native'and(params.get('op')in('close_menu','scan','snapshot')or craft_return
                          or box_click
                          or params.get('op')=='slot_click'and getattr(self,'_furnace_glass_click',None)is not None
                             and self._furnace_glass_click==__import__('furnace_glass_click').signature(state,params.get('params')or{},self.world)
                          or params.get('op')=='slot_click'and self._name_tag_click(state,params.get('params')or{})))
            if not permitted:raise RuntimeError('Owned storage/workbench must finish or close before world actions')
        if old.exists():
            previous_command=json.loads(old.read_text());previous=previous_command['id'];directory=self.out/previous
            if not(directory/'result.json').exists()or(directory/'error.json').exists():
                cursor_return=getattr(self,'_storage_cursor_return',None) or getattr(self,'_anvil_input_return',None)
                if(cursor_return and previous==cursor_return[0]and action=='native'and params.get('op')=='slot_click'
                   and params.get('params')==cursor_return[1]):
                    return self._dispatch(action,params,seconds,state,cleanup)
                if(action=='native'and params.get('op')=='scan'
                        and getattr(self,'_projection_stage_read',None)==previous
                        and params.get('params',{}).get('include_predictions')is True):
                    return self._dispatch(action,params,seconds,state,cleanup)
                if(action=='native'and params.get('op')=='snapshot'
                        and previous in (getattr(self,'_sleeping_merchant_read',None),getattr(self,'_food_guard_read',None),getattr(self,'_uncredited_food_read',None),getattr(self,'_food_pose_stop_read',None),getattr(self,'_workbench_route_read',None),getattr(self,'_boat_space_read',None),getattr(self,'_boat_outcome_read',None),getattr(self,'_retained_boat_guard_read',None),getattr(self,'_indoor_stand_read',None),getattr(self,'_bed_entity_read',None),getattr(self,'_storage_record_read',None),getattr(self,'_merchant_abort_read',None),getattr(self,'_harness_output_read',None),getattr(self,'_towing_refusal_read',None),getattr(self,'_deferred_reload_read',None),getattr(self,'_unsupported_readonly_read',None),getattr(self,'_defense_wait_read',None),getattr(self,'_full_transfer_read',None),getattr(self,'_anvil_preview_open_read',None),getattr(self,'_packed_collected_read',None),getattr(self,'_iron_quick_read',None))):
                    return self._dispatch(action,params,seconds,state,cleanup)
                if action=='pause'and previous_command.get('action')=='feed_village_founders'and(directory/'error.json').exists()and(directory/'feeding.json').exists()and not(self.out/'control/unconfirmed-native-request.json').exists():
                    from failed_food_release import allowed
                    error=json.loads((directory/'error.json').read_text());book=json.loads((directory/'feeding.json').read_text());events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()];event=next((e for e in reversed(events)if e.get('request_id')==error.get('last_request')),None)
                    if allowed(action,previous_command,error,book,event,state,self.world,self.lease['job_session']):return self._dispatch(action,params,seconds,state,cleanup)
                raise RuntimeError('Original queued action is still pending or failed; never overwrite it')
            previous_result=json.loads((directory/'result.json').read_text())
            stopped_air_pause=False
            if(action=='pause'and previous_command.get('action')=='native'and previous_command.get('op')=='navigate'
                    and previous_result.get('phase')=='waiting'and previous_result.get('detail')=='air-only path changed; no blocks were excavated'):
                from air_stop_pause import allowed
                events=[json.loads(line)for line in(self.out/'control/events.jsonl').read_text().splitlines()]
                event=next((e for e in reversed(events)if e.get('request_id')==previous_result.get('id')),None)
                stopped_air_pause=event is not None and allowed(action,previous_command,previous_result,state,event,self.world,self.lease['job_session'],(self.out/'control/unconfirmed-native-request.json').exists())

            refused_air_read=(action=='native'and params.get('op')=='snapshot'
                              and getattr(self,'_refused_air_read',None)==previous
                              and previous_command.get('op')=='navigate'
                              and previous_result.get('phase')=='error'
                              and previous_result.get('id')==state.get('last_request')
                              and previous_result.get('world_session')==self.world
                              and not(self.out/'control/unconfirmed-native-request.json').exists())
            stopped_air_read=(action=='native'and params.get('op')=='snapshot'
                              and getattr(self,'_stopped_air_read',None)==previous
                              and previous_command.get('op')=='navigate'and previous_result.get('phase')=='waiting'
                              and previous_result.get('detail')=='air-only path changed; no blocks were excavated'
                              and previous_result.get('id')==state.get('last_request')and previous_result.get('world_session')==self.world)
            if(action=='native'and params.get('op')=='snapshot'and getattr(self,'_recovered_air_injury_read',None)==previous):
                from recovered_air_injury import observable
                events=[json.loads(v)for v in(self.out/'control/events.jsonl').read_text().splitlines()]
                stopped_air_read=observable(previous_command,previous_result,events[-1]if events else{},state,self.world,self.lease['job_session']) and not(self.out/'control/unconfirmed-native-request.json').exists()
            missing_drop_read=(action=='native'and params.get('op')=='snapshot'
                               and getattr(self,'_missing_drop_observation',None)==previous
                               and previous_command.get('action')=='native'and previous_command.get('op')=='collect_item'
                               and previous_result.get('phase')=='error'
                               and previous_result.get('detail')=='Drop is no longer loaded; observe again'
                               and previous_result.get('world_session')==self.world
                               and previous_result.get('id')==state.get('last_request')
                               and not(self.out/'control/unconfirmed-native-request.json').exists())
            food_budget_read=(action=='native'and params.get('op')=='snapshot'
                              and getattr(self,'_food_budget_read',None)==previous
                              and previous_command.get('action')=='feed_village_founders'
                              and previous_result.get('complete')is False and previous_result.get('pending')is None
                              and previous_result.get('pending_food')is None and previous_result.get('world_session')==self.world)
            pickup_terminal_read=(action=='native'and params.get('op')=='snapshot'
                                  and getattr(self,'_pickup_terminal_read',None)==previous
                                  and previous_command.get('action')=='native'and previous_command.get('op')=='collect_item'
                                  and previous_result.get('phase')=='waiting'
                                  and previous_result.get('detail')=='Drop pickup not confirmed at the reached position'
                                  and previous_result.get('world_session')==self.world
                                  and previous_result.get('id')==state.get('last_request')
                                  and not(self.out/'control/unconfirmed-native-request.json').exists())
            stopped_walk_read=(action=='native'and params.get('op')=='snapshot'
                               and previous_command.get('op')=='walk'
                               and(getattr(self,'_stopped_walk_read',None)==previous and(previous_result.get('phase')=='waiting'
                                      or previous_result.get('phase')=='stopped'and previous_result.get('detail')=='脚本任务达到时间上限')
                                   or getattr(self,'_stopped_pickup_read',None)==previous and previous_result.get('phase')=='stopped'
                                      and previous_result.get('detail')=='脚本任务达到时间上限')
                               and previous_result.get('id')==state.get('last_request')
                               and previous_result.get('world_session')==self.world
                               and not(self.out/'control/unconfirmed-native-request.json').exists())
            refused_face_read=(action=='native'and params.get('op')=='snapshot'
                               and getattr(self,'_refused_face_read',None)==previous
                               and (previous_result.get('phase')=='error'and previous_command.get('op')!='collect_item'
                                    or previous_result.get('phase')=='waiting'and previous_command.get('op')=='collect_item'
                                    or previous_result.get('phase')=='error'and previous_command.get('op')=='collect_item'and previous_result.get('detail')=='No visible collision-free depot approach')
                               and (previous_command.get('op'),previous_result.get('detail')) in (
                                   ('projection_air_seed','Air seed requires the current healthy idle guarded material lease'),
                                   ('interact','Target interaction face is occluded or out of reach'),
                                   ('interact','Held item changed'),
                                   ('interact_entity','Entity out of reach'),
                                   ('interact_entity','Entity is occluded'),
                                   ('bucket_place','Bucket support face is occluded or outside normal reach'),
                                   ('bucket_place','Bucket target contains a currently loaded entity'),
                                   ('mine_block','Mining target out of reach'),
                                   ('mine_block','An earlier excavation at this target is unconfirmed; no retry sent'),
                                   ('mine_block','Block entities and containers are protected'),
                                   ('mine_block','Controlled release cannot replace decorations or waterlog blocks'),
                                   ('mine_block','Released water could escape the declared enclosure'),
                                   ('collect_item','No loaded collision-free route to this depot; no ceiling is broken'),
                                   ('collect_item','No visible collision-free depot approach'))
                               and previous_result.get('id')==state.get('last_request')
                               and previous_result.get('world_session')==self.world
                               and not(self.out/'control/unconfirmed-native-request.json').exists())
            sleeping_bridge_read=(action=='native'and params.get('op')=='snapshot'
                                  and getattr(self,'_sleeping_bridge_read',None)==previous
                                  and previous_command.get('op')=='interact_entity'and previous_result.get('phase')=='waiting'
                                  and previous_result.get('detail')=='original processing menu not observed; block use is not repeated'
                                  and previous_result.get('id')==state.get('last_request')and previous_result.get('world_session')==self.world
                                  and not(self.out/'control/unconfirmed-native-request.json').exists())
            bridged_abort_read=(action=='native'and params.get('op')=='snapshot'
                                and getattr(self,'_bridged_abort_read',None)==previous
                                and previous_command.get('action')=='native'and previous_command.get('op')=='slot_click'
                                and previous_result.get('phase')=='error'
                                and previous_result.get('detail')=='Merchant owner, exact offers, selection or stock changed; no packet sent'
                                and previous_result.get('id')==state.get('last_request')and previous_result.get('world_session')==self.world
                                and not(self.out/'control/unconfirmed-native-request.json').exists())
            scan_volume_read=(action=='native'and params.get('op')=='snapshot'
                              and getattr(self,'_scan_volume_read',None)==previous
                              and previous_command.get('op')=='scan'and previous_result.get('phase')=='error'
                              and previous_result.get('detail')=='Invalid scan volume'
                              and previous_result.get('id')==state.get('last_request')
                              and previous_result.get('world_session')==self.world
                              and not(self.out/'control/unconfirmed-native-request.json').exists())
            unloaded_furnace_close=(action=='native'and params.get('op')=='close_menu'
                                   and getattr(self,'_unloaded_furnace_close',None)==previous
                                   and previous_command.get('action')=='smelt_material')
            unstarted_processing_read=(action=='native'and params.get('op')=='snapshot'
                                       and getattr(self,'_storage_record_read',None)==previous
                                       and previous_command.get('action')=='smelt_material')
            exchange_shortage_read=(action=='native'and params.get('op')=='snapshot'
                                    and getattr(self,'_exchange_shortage_read',None)==previous
                                    and previous_command.get('action')=='exchange')
            settled_print_read=(action=='native'and params.get('op')=='snapshot'
                                and getattr(self,'_settled_print_read',None)==previous
                                and previous_command.get('op')=='professional_print')
            empty_workbench_read=(action=='native'and params.get('op')=='snapshot'
                                  and getattr(self,'_empty_workbench_read',None)==previous
                                  and previous_command.get('action')=='manufacture')
            unstarted_mine_read=(action=='native'and params.get('op')=='snapshot'
                                 and getattr(self,'_unstarted_mine_read',None)==previous
                                 and previous_command.get('op')=='mine_block')
            lectern_preflight_read=(action=='native'and params.get('op')=='snapshot'
                                   and getattr(self,'_lectern_preflight_read',None)==previous
                                   and previous_command.get('op')=='mine_block'and previous_result.get('phase')=='error'
                                   and previous_result.get('detail')=='Lectern reset requires an empty lectern beside the same freshly quoted untraded librarian without a requested book')
            rejected_print_read=(action=='native'and params.get('op')=='scan'and getattr(self,'_rejected_print_read',None)==previous
                                 and previous_command.get('op')=='professional_print'and previous_result.get('phase')=='error'
                                 and (params.get('params')or{}).get('include_predictions')is True
                                 and previous_result.get('bounded_targets')==[(params.get('params')or{}).get('min')]
                                 and (params.get('params')or{}).get('min')==(params.get('params')or{}).get('max'))
            partial_scan_read=(action=='native'and params.get('op')=='snapshot'
                               and getattr(self,'_partial_scan_read',None)==previous
                               and previous_command.get('op')=='scan'and previous_result.get('phase')=='waiting')
            stopped_chop_read=(action=='native'and params.get('op')=='snapshot'
                               and getattr(self,'_stopped_chop_read',None)==previous
                               and previous_command.get('action')=='native'and previous_command.get('op')=='chop'
                               and previous_result.get('phase')=='stopped'and previous_result.get('detail')=='chopper stopped'
                               and previous_result.get('id')==state.get('last_request')and previous_result.get('world_session')==self.world
                               and not(self.out/'control/unconfirmed-native-request.json').exists())
            fixed_tree_selection_read=(action=='native'and params.get('op')=='snapshot'
                               and getattr(self,'_fixed_tree_selection_read',None)==previous
                               and previous_command.get('action')=='native'and previous_command.get('op')=='chop'
                               and previous_result.get('phase')=='stopped'and previous_result.get('detail')=='脚本参数无效'
                               and previous_result.get('id')==state.get('last_request')and previous_result.get('world_session')==self.world
                               and not(self.out/'control/unconfirmed-native-request.json').exists())
            readback_observation=(readback_observation and previous_command==readback['original_command'])
            if not(readback_observation or stopped_air_pause or food_budget_read or pickup_terminal_read or missing_drop_read or refused_air_read or stopped_air_read or stopped_walk_read or exchange_shortage_read or unstarted_processing_read or unloaded_furnace_close or refused_face_read or bridged_abort_read or sleeping_bridge_read or scan_volume_read or settled_print_read or empty_workbench_read or unstarted_mine_read or lectern_preflight_read or rejected_print_read or partial_scan_read or stopped_chop_read or fixed_tree_selection_read)and(previous_result.get('phase')not in(None,'done')or previous_result.get('complete')is False):
                raise RuntimeError('Original queued result is not complete; no new plan command')
            # Immediate projection reads return data without a DONE phase. The
            # retained native owner deliberately requires an exact terminal for
            # release; establish that with a read-only snapshot, never by
            # relaxing its outcome fence or retrying a world input.
            previous_op=previous_command.get('op')
            if(action=='pause'and previous_command.get('action')=='native'
                    and previous_op in('projection_audit','projection_model')
                    and previous_result.get('phase')is None
                    and isinstance(previous_result.get(previous_op),dict)):
                if previous_result.get('world_session')!=self.world:
                    raise RuntimeError('Projection read belongs to another world; no release or snapshot')
                self.native('snapshot')
                return self.send(action,seconds=seconds,**params)
        return self._dispatch(action,params,seconds,state,cleanup)
    def _dispatch(self,action,params,seconds,state,cleanup):
        if action=='boat_place':
            from boat_transport import validate_placement_geometry
            validate_placement_geometry(params.get('support'),params.get('stand'),params.get('item'))
        old=self.out/'command.json'
        self.index+=1;identity=f'{self.prefix}-{self.index:03d}'
        if(self.out/identity).exists():raise RuntimeError('Original plan command identity already exists; no replay')
        command={'id':identity,'action':action,**params}
        if action=='boat_place'and params.get('independent_stock'):
            from independent_boat_stock import authorize
            marker=json.loads((self.out.parent/'unresolved-boat-placement.json').read_text())
            certificate_path,certificate=authorize(self.out,state,self.lease,command,marker)
            certificate['consumed_by']=identity
            write_json(certificate_path,certificate)
        if cleanup:self.closing_menu=state['menu']['id']
        write_json(old,command)
        write_json(self.out/(self.prefix+'-planner-current.json'),{'command':command,'complete':False})
        deadline=time.monotonic()+seconds
        while True:
            # A successful pause releases the lease before its disk receipt is
            # published. Observe that interval without authorizing any new work.
            self.status(observing=True,allow_released=action=='pause');directory=self.out/identity;failure=directory/'error.json';result=directory/'result.json'
            if failure.exists():raise RuntimeError('Original village action retained: '+json.loads(failure.read_text()).get('error','unknown'))
            if result.exists():
                value=json.loads(result.read_text())
                if(value.get('phase')not in(None,'done')or value.get('complete')is False):
                    raise RuntimeError('Original village action did not complete: '+str(value.get('detail',value.get('remaining_targets'))))
                write_json(self.out/(self.prefix+'-planner-current.json'),{'command':command,'complete':True})
                self.closing_menu=None;return value
            if time.monotonic()>deadline:raise RuntimeError('Original queued action has no result; no replay or next command')
            time.sleep(.1)
    def native(self,op,**params):return self.send('native',op=op,params=params)
