"""Current connection binding for inventory and registered portable-cargo work.

The historical resident registry is retained as an attack/health protection set;
this adapter does not claim a new resident census or permit villager construction.
"""
from pathlib import Path
import json
from village_resource_health import check,ProtectedResidentHealthError,record_health_failure


def validate_binding(state,kernel,startup,protected,required,config):
    lease=state.get('supervision_lease')or{}
    if (not config.get('server')or state.get('server','').strip().lower().removesuffix(':25565')!=config['server'].strip().lower().removesuffix(':25565')
            or startup.get('server','').strip().lower().removesuffix(':25565')!=config['server'].strip().lower().removesuffix(':25565')
            or not config.get('dimension')or state.get('dimension')!=config['dimension']or startup.get('dimension')!=config['dimension']
            or not kernel.get('world_session')or state.get('world_session')!=kernel['world_session']
            or startup.get('world_session')!=kernel['world_session']
            or lease.get('world_session')!=kernel['world_session']or lease.get('kind')!='materials'
            or not kernel.get('task_session')or lease.get('job_session')!=kernel['task_session']
            or type(state.get('control_revision'))is not int or lease.get('revision')!=state['control_revision']
            or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
            or not isinstance(required,set)or not required or not required<=protected):
        raise RuntimeError('Current resource connection, owner or full resident protection set changed')

class CurrentResourceScopeMixin:
    def __init__(self,out,root,prefix,proof,resume=False):
        out=Path(out);self._resource_kernel=json.loads((out/'transport-kernel.json').read_text());self._resource_startup=json.loads((out/'actual-before.json').read_text());project=json.loads((out.parent/'project-state.json').read_text());self._resource_config=project['resource_inventory_scope'];self._resource_pads={tuple(p)for p in self._resource_config['pads']};self._resource_supports={(p[0],p[1]-1,p[2])for p in self._resource_pads};ref=(out.parent/project['current_enclosed_population']['proof']).resolve()
        if not ref.is_relative_to(out.parent.resolve()):raise ValueError('Resident reference must belong to this project')
        census=json.loads(ref.read_text());self._resource_required=set(census.get('expected_known_uuids',[]))|{v['uuid']for v in census['boundary_checks'][-1]['roster']};self._resource_reference=ref
        super().__init__(out,root,prefix,proof,resume=resume)
        if hasattr(self,'book'):
            self.book['resource_scope']={'kind':'inventory_and_registered_cargo_only','resident_reference':str(ref),'resident_reference_world':census.get('world_session'),'current_native_world':self._resource_kernel['world_session'],'protected_id_count':len(self.protected_ids),'new_resident_census_claimed':False};self.save()
    def check(self):
        state=self.q.status();validate_binding(state,self._resource_kernel,self._resource_startup,self.protected_ids,self._resource_required,self._resource_config);certificate=None
        try:certificate=json.loads((self.out/'owned-material-menu.json').read_text())
        except(OSError,ValueError):pass
        try:return check(state,self._resource_kernel['world_session'],self.protected_ids,self.home_min,self.home_max,owned_menu=certificate)
        except ProtectedResidentHealthError as error:
            path=record_health_failure(self.out,error)
            if hasattr(self,'book'):self.book['resident_health_failure_proof']=str(path);self.save()
            raise
    def send(self,action,**params):
        if action not in {'open_chest_from_pose','open_shulker','transfer','manufacture','travel_to'}:raise ValueError('Resource-only scope excludes villager and construction operations')
        if action=='travel_to'and(params.get('target')!=self._resource_config['home']or type(params.get('max_radius',4096))is not int or not 0<params.get('max_radius',4096)<=self._resource_config['max_radius']):raise ValueError('Resource travel is restricted to the registered home return')
        return super().send(action,**params)
    def n(self,op,**params):
        if op not in {'scan','navigate','select_item','close_menu','interact','recover_shulker','use_item'}:raise ValueError('Resource-only scope cannot excavate or attack')
        if op=='navigate'and params.get('air_only')is not True:raise ValueError('Resource travel must retain ordinary collision checks')
        if op=='use_item'and params.get('item')not in ('minecraft:cooked_beef','minecraft:cooked_porkchop','minecraft:cooked_chicken','minecraft:cooked_mutton','minecraft:bread'):raise ValueError('Resource recovery only consumes ordinary food')
        if op=='interact'and(not params.get('expected_hand','').endswith('shulker_box')or tuple(params.get('pos',[]))not in self._resource_supports or params.get('face')!='up'):raise ValueError('Resource world interaction only places its portable box')
        if op=='recover_shulker'and tuple(params.get('pos',[]))not in self._resource_pads:raise ValueError('Portable recovery must use a registered pad')
        return super().n(op,**params)
    def place(self,p,support,face,**params):
        if tuple(p)not in self._resource_pads or not params.get('item','').endswith('shulker_box'):raise ValueError('Only temporary cargo boxes may be placed by this role')
        return super().place(p,support,face,**params)
