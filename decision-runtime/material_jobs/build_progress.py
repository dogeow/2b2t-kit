"""Display current material counts from the existing model and verified placement ledger."""
from collections import Counter
import json
from pathlib import Path

from material_plan import inventory_counts
from projection_flat_plan import FlatLayout


class BuildMaterialProgress:
    def __init__(self,automation=None):
        self.cache={};self.layouts={};self.counts={};self.automation=Path(automation)if automation is not None else None
    def read(self,path):
        path=Path(path);stamp=(path.stat().st_mtime_ns,path.stat().st_size)
        previous=self.cache.get(path)
        if previous and previous[0]==stamp:return previous[1]
        value=json.loads(path.read_text())
        if stamp!=(path.stat().st_mtime_ns,path.stat().st_size):raise ValueError('Display input changed while reading')
        self.cache[path]=(stamp,value);return value

    def details(self,request,status,state,out):
        if request.get('mode')!='projection' or status.get('state') in ('paused','failed','blocked','completed','cancelled'):return None
        root=Path(out).resolve();operation=self.read(root/'active-operation.json')
        directory=Path(operation.get('directory','')).resolve()
        if directory.parent!=root:return None
        activity=''
        if operation.get('name')=='build' and status.get('state')=='building':
            plan=self.read(directory/'flat-next-batch.json')
            if plan.get('phase')!='ready' or plan.get('placement_key')!=request['projection_key']:return None
            item=plan.get('item');activity='放置'
        else:
            if not (root/'inflight.json').exists():return None
            pending=self.read(root/'inflight.json')
            if pending.get('job_id')!=request.get('id'):return None
            args=pending.get('args',[]);kind=pending.get('operation')
            if kind=='run_pipeline' and len(args)>=4:
                item=args[0];pipeline=Path(args[3]).resolve()
                if root not in pipeline.parents:return None
                if item.endswith('_planks'):
                    book=self.read(pipeline/'wood-carried-pipeline.json');step=(book.get('pending')or{}).get('kind')
                    activity=('砍树' if state.get('chopping') else '找树' if step in ('discover','acquire')
                              else '制作' if step=='craft' else '取料' if step in ('fetch_finished','fetch_logs','fetch_packed') else '准备')
                else:activity='采集' if status.get('state')=='gathering' else '制作'
            else:
                outputs=pending.get('output_targets')or{}
                if len(outputs)!=1:return None
                item=next(iter(outputs));activity={'craft':'制作','smelt':'熔炼','fetch':'取料','harden':'固化','acquire':'采集'}.get(kind,'准备')
        model_path=directory/'flat-model.json'
        if not model_path.exists():
            choices=sorted(root.glob('*-build/flat-model.json'))
            if choices:model_path=choices[0]
            elif self.automation is not None:model_path=self.automation/'flat-map-continuation-cache.json'
            else:return None
        reply=self.read(model_path)
        cached_expected=model_path.name=='flat-map-continuation-cache.json'
        if cached_expected:
            if reply.get('schema')!=1 or reply.get('native_parking_verified') is not True:return None
            model=reply['model']  # Immutable denominator only, never its saved actual audit.
        else:
            if reply.get('world_session')!=state.get('world_session'):return None
            model=reply['projection_model']
        stamp=self.cache[model_path][0]
        if self.layouts.get(model_path,(None,None))[0]!=stamp:
            layout=FlatLayout(model,request['flat_map'])
            self.layouts[model_path]=(stamp,layout,Counter(row['item'] for row in layout.expected.values()))
        layout=self.layouts[model_path][1]
        audit=self.read(root/'projection-latest.json');ledger=audit.get('material_ledger')or{}
        if (layout.key!=request['projection_key'] or audit.get('placement_key')!=layout.key
                or ledger and ledger.get('world_session')!=state.get('world_session')):return None
        if not ledger and audit.get('observed_at',0)<request.get('created_at',0):return None
        signature=(model_path,stamp,self.cache[root/'projection-latest.json'][0])
        if signature not in self.counts:
            layout.observed(audit)  # Only recheck when verified evidence changes.
            missing=Counter(layout.expected[tuple(row['pos'])]['item'] for row in audit['mismatches'])
            self.counts={signature:missing}
        totals=self.layouts[model_path][2];missing=self.counts[signature]
        if item not in totals or audit['matched']!=status.get('done') or audit['total']!=status.get('total'):return None
        held=inventory_counts(state).get(item,0)
        return {'item':item,'done':totals[item]-missing[item],'total':totals[item],
                'on_hand':held,'shortage':max(0,missing[item]-held),'map_done':audit['matched'],
                'map_total':audit['total'],'activity':activity,'source':'verified_physical_ledger'}


def phase(details,name):
    # Put the real activity first so a narrow existing HUD cannot hide it.
    activity=(details.get('activity','')+' ')if details.get('activity')else''
    return (f"{activity}{name(details['item'])}{details['done']}/{details['total']}"
            f" 背包{details['on_hand']} 缺{details['shortage']}")
