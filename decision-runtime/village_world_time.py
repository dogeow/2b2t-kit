"""Observe effective client daylight; raw clock modulo is never night evidence.

This is not proof of server spawning, NPC schedules, or mob availability.
A visual time override or missing fresh evidence leaves the period unknown.
"""
from villager_events import read as read_events

def classify(environment,now):
 if not isinstance(environment,dict)or environment.get('scope')!='current_client_world_environment':return None
 observed=environment.get('observed_at');sky=environment.get('sky_darken');dark=environment.get('dark_outside');bright=environment.get('bright_outside')
 if(type(now)is not int or type(observed)is not int or not -1000<=now-observed<=1000
    or environment.get('time_changer_active')is not False
    or type(sky)is not int or not 0<=sky<=15
    or type(dark)is not bool or type(bright)is not bool or dark==bright
    or dark!=(sky>=4)):return None
 return {'period':'dark'if dark else'bright','evidence_scope':'current_client_effective_sky_not_server_spawn_guarantee',
         'observed_at':observed,'sky_darken':sky,'raw_clocks':{k:environment.get(k)for k in('overworld_clock_ticks','default_clock_ticks','game_ticks')}}

def read(root,state):
 frame=read_events(root,state)
 return None if frame is None else classify(frame.get('world_environment'),state['time'])
