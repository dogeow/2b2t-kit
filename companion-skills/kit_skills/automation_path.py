"""Select the live Kit mailbox, including HMCL version-isolated instances."""
import json,time
from pathlib import Path

def resolve_automation(explicit=None,game_root='/Applications/.minecraft',now=None):
    if explicit:return Path(explicit)
    root=Path(game_root);now=time.time() if now is None else now
    candidates=[root/'config/twob2tkit/automation']+list(root.glob('versions/*/config/twob2tkit/automation'))
    observed=[]
    for path in candidates:
        try:
            data=json.loads((path/'status.json').read_text());stamp=data.get('time',0)
            if isinstance(stamp,(int,float)):observed.append((stamp,path))
        except (OSError,ValueError):continue
    fresh=[p for stamp,p in observed if 0<=now*1000-stamp<=10000]
    if len(fresh)>1:raise ValueError('Multiple live Kit clients; specify --automation explicitly')
    if fresh:return fresh[0]
    return max(observed,key=lambda row:row[0])[1] if observed else candidates[0]
