"""Observe a goal's health safety exit; never log out, reconnect or clear locks."""
import argparse,os,time,math
from pathlib import Path
from live_snapshot import read_fresh
from kit_runtime.journal import write_json
from safety_interlock import require_unlocked,record_material_health_exit


class ExitWitness:
    def __init__(self,world):
        self.world=world;self.last=None;self.peak=None;self.decline=False;self.owned=False
    def observe(self,state):
        native=(state.get('safety_hold')or{}).get('active')is True
        if not state.get('connected'):
            return self.last if self.owned and (native or self.decline) else None
        if state.get('world_session')!=self.world:return None
        if native and self.owned:return self.last or state
        if state.get('manual_movement'):
            self.last=None;self.peak=None;self.decline=False;return None
        lease=state.get('supervision_lease')or{};hp=state.get('health')
        if (lease.get('kind')not in('materials','parking')or lease.get('world_session')!=self.world
                or type(hp)not in(int,float)or not math.isfinite(hp)):return None
        self.owned=True
        self.peak=hp if self.peak is None else max(self.peak,hp)
        self.decline=hp<self.peak-.0001
        self.last={k:state.get(k)for k in('time','health','pos','server','world_session')}
        return None


def watch(root,out):
    root=Path(root);out=Path(out);out.mkdir(exist_ok=False)
    first=read_fresh(root);require_unlocked(root,first);world=first['world_session'];witness=ExitWitness(world)
    write_json(out/'armed.json',{'pid':os.getpid(),'world_session':world,'live_injury_forces_logout':False,'reconnect_allowed_after_safety_exit':False})
    while True:
        if(out/'stop.json').exists():return
        s=read_fresh(root);evidence=witness.observe(s)
        if evidence is not None:
            reason='用户要求：无法处理或触发保护后安全下线，不自动重连或恢复，等待玩家自行上线操作'
            record_material_health_exit(root,evidence,reason)
            write_json(root/'assistant-control-hold.json',{'active':True,'time':s['time'],'reason':reason,'explicit_user_resume_required':True})
            write_json(out/'health-exit.json',{'evidence':evidence,'native_safety_hold':s.get('safety_hold'),'forced_logout_sent':False,'reconnect_sent':False});return
        if not s.get('connected')or s.get('world_session')!=world:
            write_json(out/'ended.json',{'health_exit_observed':False,'forced_logout_sent':False,'reconnect_sent':False});return
        time.sleep(.05)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();watch(a.root,a.out)
