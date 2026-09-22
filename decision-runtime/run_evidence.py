"""Small reproducible run metadata and observed deltas, never credentials or game commands."""
import hashlib,json,time
from pathlib import Path

def inventory(snapshot):
    values={}
    for row in snapshot.get('inventory',[]):
        if 0<=row.get('slot',-1)<36 and row.get('count',0)>0:
            values[row['item']]=values.get(row['item'],0)+row['count']
    return values

def observed_delta(before,after):
    a,b=inventory(before),inventory(after)
    return {'position_before':before.get('pos'),'position_after':after.get('pos'),
            'health_before':before.get('health'),'health_after':after.get('health'),
            'inventory_delta':{item:b.get(item,0)-a.get(item,0) for item in sorted(a.keys()|b.keys()) if b.get(item,0)!=a.get(item,0)},
            'revision_before':before.get('control_revision'),'revision_after':after.get('control_revision')}

def write_manifest(out,task,snapshot):
    source=Path(__file__).parent
    files=('material_client.py','material_manufacture.py','craft_grid.py','craft_recipe.py','craft_recovery.py',
           'goal_workflow.py','projection_terrain.py','projection_access.py','ground_pickup.py','work_access.py','drop_collection.py')
    data={'schema':1,'task_session':task,'created_at':int(time.time()*1000),
          'kit_version':snapshot.get('kit_version'),'game_mode':snapshot.get('game_mode'),'difficulty':snapshot.get('difficulty'),
          'dimension':snapshot.get('dimension'),'world_session':snapshot.get('world_session'),
          'server_hash':hashlib.sha256(str(snapshot.get('server')).encode()).hexdigest()[:16],
          'placement_key':snapshot.get('projection_selection',{}).get('key'),
          'executor':'deterministic native Kit material workflow','complete':False,
          'source_sha256':{name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in files if (source/name).exists()}}
    path=Path(out)/('run-manifest-'+task+'.json');path.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    return data
