"""Bounded original-source work intent, local to one current controller and projection."""
from contextlib import contextmanager
import math
import time

@contextmanager
def original_source_work(client,key,*,enabled):
    if type(enabled)is not bool:raise ValueError('Thermal intent must be boolean')
    if not enabled:
        yield
        return
    previous=getattr(client,'original_source_thermal_scope',None)
    own={'world':client.world,'task':client.task,'key':key,'until':time.monotonic()+60}
    client.original_source_thermal_scope=own
    try:yield
    finally:
        if getattr(client,'original_source_thermal_scope',None)is own:
            if previous is None:del client.original_source_thermal_scope
            else:client.original_source_thermal_scope=previous

def allows(client,state):
    scope=getattr(client,'original_source_thermal_scope',None)
    if not isinstance(scope,dict)or not isinstance(state,dict):return False
    projection=state.get('projection_selection')
    if not isinstance(projection,dict):return False
    hp=state.get('health');food=state.get('food');deadline=scope.get('until')
    return bool(type(deadline)in(int,float)and math.isfinite(deadline)and time.monotonic()<deadline
        and isinstance(scope.get('world'),str)and bool(scope['world'])
        and isinstance(scope.get('task'),str)and bool(scope['task'])
        and scope['world']==getattr(client,'world',None)==state.get('world_session')
        and scope['task']==getattr(client,'task',None)
        and scope.get('key')and scope['key']==projection.get('key')
        and state.get('model_water_construction_options_protocol')==1
        and state.get('minor_thermal_work_protocol')==1 and state.get('minor_thermal_work_allowed')is True
        and type(hp)in(int,float)and math.isfinite(hp)and 19<=hp<=20
        and type(food)is int and food>=18
        and not state.get('under_water')and not state.get('in_lava'))
