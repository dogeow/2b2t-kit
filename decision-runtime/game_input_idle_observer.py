"""Read-only game-specific idle telemetry. Never starts an owner or sends input."""
import argparse,json,os,time
from pathlib import Path
from game_input_idle import GameInputIdle,may_reacquire_without_ui_input
from manual_idle_resume import hardware_idle_seconds
from live_snapshot import read_fresh
from kit_runtime.journal import write_json

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--policy',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--seconds',type=int,default=7200);a=p.parse_args();assert 1<=a.seconds<=43200
 tracker=GameInputIdle();deadline=time.monotonic()+a.seconds
 while time.monotonic()<deadline:
  try:
   s=read_fresh(a.root,wait_seconds=.5);idle=hardware_idle_seconds()if s.get('window_active')is True else None;elapsed=tracker.observe(s,idle,time.monotonic());policy=json.loads(a.policy.read_text());record={'time':s['time'],'observer_pid':os.getpid(),'world_session':s.get('world_session'),'window_active':s.get('window_active'),'manual_movement':s.get('manual_movement'),'game_idle_seconds':elapsed,'can_consider_normal_reacquisition':may_reacquire_without_ui_input(s,policy,elapsed),'no_game_input_sent':True,'does_not_close_interfaces_or_start_controllers':True}
  except (OSError,ValueError,RuntimeError)as error:record={'time':int(time.time()*1000),'observer_pid':os.getpid(),'can_consider_normal_reacquisition':False,'error':str(error),'no_game_input_sent':True}
  write_json(a.out,record);time.sleep(.5)
if __name__=='__main__':main()
