"""Permit a fresh remaining-rock intent only from complete current prediction reads."""
import hashlib
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json
from .protocol import JobBlocked


def verify(client,profile,item,out):
    sources=[r for r in profile.get('resource_regions',[])if r.get('item')==item and r.get('prior_unknown_journal')]
    if not sources:return []
    if client.status().get('scan_prediction_protocol')!=1:
        raise JobBlocked('当前宿主缺少只读预测核验接口，未恢复旧矿区')
    proofs=[]
    for source in sources:
        path=Path(source['prior_unknown_journal'])
        if not path.is_file()or path.stat().st_size>1_000_000:raise JobBlocked('旧采集记录缺失或过大，未恢复')
        raw=path.read_bytes();old=json.loads(raw)
        shaft=source.get('access_shaft')or{}
        if (old.get('schema')!=1 or old.get('item')!=item or source.get('source')!='natural_survey'
                or not any(r.get('min')==source['min']and r.get('max')==source['max']for r in old.get('resource_regions',[]))):
            raise JobBlocked('原矿区与旧记录不一致，未恢复')
        for entry in old.get('visited',{}).values():
            if entry.get('state')!='inflight':continue
            low,high=entry.get('min'),entry.get('max')
            if (not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3
                    or any(type(v)is not int for v in low+high)
                    or not all(shaft['min'][i]<=low[i]<=high[i]<=shaft['max'][i]for i in range(3))):
                raise JobBlocked('旧未知区不在登记竖井内，未恢复')
            reply=client.request('scan',min=low,max=high,details=True,include_predictions=True)
            report=reply.get('scan_predictions')or{};volume=math.prod(high[i]-low[i]+1 for i in range(3))
            proof={'original_journal':str(path),'original_sha256':hashlib.sha256(raw).hexdigest(),
                   'current_world':client.world,'min':low,'max':high,'current_read':reply,
                   'old_action_confirmation_credit':0,'mining_sent':False}
            file=Path(out)/('prior-quarry-current-'+str(len(proofs))+'.json');write_json(file,proof)
            if (reply.get('phase')!='done'or reply.get('world_session')!=client.world
                    or reply.get('scan_cells_read')!=volume or reply.get('scan_total_cells')!=volume
                    or any(reply.get(k)!=client.rev for k in ('scan_start_revision','scan_end_revision','control_revision'))
                    or report.get('protocol')!=1 or report.get('complete')is not True
                    or report.get('pending_count')!=0 or report.get('pending_positions')!=[]
                    or path.read_bytes()!=raw):
                raise JobBlocked('旧未知区当前仍有预测或读取未完整，未重放原挖掘')
            proofs.append(str(file))
    return proofs
