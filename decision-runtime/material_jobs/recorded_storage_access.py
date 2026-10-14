"""Share proved storage geometry with a caller's existing transfer controller.

This is deliberately separate from the inventory-immutable warehouse auditor.
Transfers remain the ordinary MaterialClient.transfer transactions and journals.
"""
from pathlib import Path
import time
from kit_runtime.journal import write_json
from material_storage_index import records
from .acquisition import _safe
from .protocol import JobBlocked


class Access:
    def __init__(self,client,profile,out,checkpoint):
        self.core=client;self.profile=profile;self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True)
        self.checkpoint=checkpoint;self.world=client.world
        self.report={'world_session':self.world,'pending':None,'inventory_immutable':False}
        self.return_points=[];self.in_house=False;self.sequence=0

    def __getattr__(self,name):return getattr(self.core,name)

    def status(self,*args,**kwargs):
        self.checkpoint();q=self.core.status(*args,**kwargs);_safe(q)
        lease=q.get('supervision_lease')or{}
        if (q.get('world_session')!=self.world or lease.get('world_session')!=self.world
                or lease.get('job_session')!=self.core.task or lease.get('kind')!='materials'):
            raise JobBlocked('Recorded storage controller or current world changed')
        return q

    def save(self):write_json(self.out/'access-current.json',self.report)

    def open(self,client,pos,*,allow_empty=False):
        if client is not self.core:raise JobBlocked('Storage access must reuse the original sole client')
        if not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos):
            raise ValueError('Recorded storage requires integer XYZ')
        q=self.status()
        if not any(pos in r.get('aliases',[r.get('pos')])and not r.get('missing')for r in records(client,q)):
            raise JobBlocked('Storage position has no current scoped Kit record')
        from warehouse_audit_cli import _exit_storage,_travel_to,_container,_open_container
        _exit_storage(self,self.profile)
        _travel_to(self,pos,self.status,[])
        identity,state,positions=_container(self,pos)
        opened=_open_container(self,pos,state,self.profile)
        self.sequence+=1
        write_json(self.out/('opened-%02d.json'%self.sequence),{'identity':identity,
            'positions':positions,'state':state,'menu_id':opened['menu']['id'],
            'world_session':self.world,'time':opened['time'],'inventory_credit':0})
        return opened

    def exit(self):
        from warehouse_audit_cli import _exit_storage
        _exit_storage(self,self.profile)


def bind(client,profile,out,checkpoint):
    access=Access(client,profile,out,checkpoint)
    client.registered_depot_opener=access.open
    client.registered_depot_exit=access.exit
    return access
