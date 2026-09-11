"""Atomic display projection for the game UI; no action, account, or raw episode data."""
import json,os,time
from pathlib import Path

DEFAULT=Path.home()/'.minecraft-kit/skills/catalog.json'
TITLES={'collect_logs':'采集原木','walk_to_worksite':'步行到施工点','navigate_to_worksite':'飞行到施工点','print_nearby_batch':'局部投影打印'}

def export_catalog(manager,path=DEFAULT,now=None):
    now=time.time() if now is None else now
    rows=manager.db.execute('''
    SELECT s.name,s.version,s.status,s.body,s.hash,
      coalesce(e.successes,0),coalesce(e.failures,0),coalesce(e.last_verified,0)
    FROM skills s JOIN (SELECT name,max(version) version FROM skills GROUP BY name) latest
      ON s.name=latest.name AND s.version=latest.version
    LEFT JOIN (SELECT skill_hash,sum(CASE WHEN success=1 AND witness=1 THEN 1 ELSE 0 END) successes,
      sum(CASE WHEN success=0 AND witness=1 THEN 1 ELSE 0 END) failures,
      max(CASE WHEN success=1 AND witness=1 THEN created ELSE 0 END) last_verified
      FROM episodes GROUP BY skill_hash) e ON e.skill_hash=s.hash
    ORDER BY s.name''').fetchall()
    entries=[]
    for name,version,status,body,h,successes,failures,last in rows:
        s=json.loads(body)
        title=s.get('title')
        if not isinstance(title,str) or not title.strip():title=TITLES.get(name,name.replace('_',' '))
        entries.append({'name':name,'title':title[:160],'version':version,'status':status,
          'description':s['description'],'successful_runs':successes,'failed_runs':failures,
          'last_verified_ms':int(last*1000),'origin':'observed' if successes+failures else 'candidate',
          'parameters':s.get('parameters',{}),'preconditions':s.get('preconditions',{}),
          'steps':s['steps'],'success':s['success'],'tags':s.get('tags',[])})
    payload={'schema':1,'updated_ms':int(now*1000),'source':'kit_skill_library','skills':entries}
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.'+str(os.getpid())+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')));tmp.replace(p)
    return len(entries)
