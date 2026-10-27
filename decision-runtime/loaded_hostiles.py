"""Read current live-server hostile entities without scanning terrain or claiming global absence."""
from pathlib import Path
import json,math,time,uuid
SCOPE='current_client_loaded_server_hostile_entities'

def valid(frame,state,now=None):
    try:
        now=int(time.time()*1000)if now is None else now
        if (frame['protocol']!=1 or frame['scope']!=SCOPE or frame['connected']is not True or state['connected']is not True
                or any(frame[k]!=state[k]for k in ('world_session','server','dimension','player_uuid','runtime_version','runtime_generation'))
                or type(frame['runtime_generation'])is not int or type(frame['time'])is not int
                or not 0<=now-frame['time']<=1000 or abs(state['time']-frame['time'])>1000
                or not 0<=frame['world_entered_at']<=frame['time']
                or type(frame['truncated'])is not bool or not isinstance(frame['hostiles'],list)or len(frame['hostiles'])>256
                or frame['equipment_scope']!='current_client_entity_equipment_not_predicted_drops'):return False
        seen=set()
        for row in frame['hostiles']:
            uuid.UUID(row['uuid'])
            if row['uuid']in seen or type(row['id'])is not int: return False
            seen.add(row['uuid'])
            if (not isinstance(row['type'],str)or not row['type'].startswith('minecraft:')
                    or any(type(row[k])is not bool for k in ('alive','hostile','is_baby','has_custom_name','visible','on_fire','in_water'))
                    or row['alive']is not True or row['hostile']is not True
                    or type(row['health'])not in(int,float)or not math.isfinite(row['health'])or row['health']<0):return False
            for point in [row['pos'],row['bounds']['min'],row['bounds']['max']]:
                if not isinstance(point,list)or len(point)!=3 or any(type(n)not in(int,float)or not math.isfinite(n)for n in point):return False
            if any(row['bounds']['min'][i]>=row['bounds']['max'][i]for i in range(3)):return False
            if any(not isinstance(row[k],str)or ':'not in row[k]or len(row[k])>128 for k in ('main_hand','off_hand','head_item')):return False
        return True
    except(KeyError,ValueError,TypeError,AttributeError):return False

def read(root,state,now=None):
    try:
        path=Path(root)/'loaded-hostile-survey.json'
        if path.stat().st_size>1048576:return None
        frame=json.loads(path.read_text())
    except(OSError,ValueError,TypeError):return None
    return frame if valid(frame,state,now)else None
