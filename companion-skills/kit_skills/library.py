"""SkillManager adapted from MineDojo Voyager (MIT, see vendor/voyager).

Retains bounded retrieval and versioned executable/description storage. Replaces
Chroma/remote embeddings with local retrieval and arbitrary JavaScript with Kit DSL.
"""
import json,re,sqlite3,time
from pathlib import Path
from .model import validate,digest

def terms(text):
    text=text.lower();out=set(re.findall(r'[a-z0-9_]+',text))
    for run in re.findall(r'[\u4e00-\u9fff]+',text):
        out.update(run[i:i+2] for i in range(max(1,len(run)-1)))
    return out
class SkillManager:
    def __init__(self,root,retrieval_top_k=5):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.retrieval_top_k=min(5,max(1,retrieval_top_k))
        self.db=sqlite3.connect(self.root/'skills.sqlite3',timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS skills(name TEXT,version INTEGER,hash TEXT UNIQUE,body TEXT,status TEXT,created REAL,PRIMARY KEY(name,version));
        CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY,hash TEXT UNIQUE,skill_hash TEXT,success INTEGER,reason TEXT,body TEXT,created REAL,witness INTEGER);
        CREATE TABLE IF NOT EXISTS lessons(id TEXT PRIMARY KEY,body TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS cursors(name TEXT PRIMARY KEY,value TEXT);
        ''')
    def close(self):self.db.close()
    def add_new_skill(self,info):
        skill=validate(info);h=digest(skill)
        row=self.db.execute('SELECT version,status FROM skills WHERE hash=?',(h,)).fetchone()
        if row:return {'name':skill['name'],'version':row[0],'status':row[1],'hash':h}
        version=self.db.execute('SELECT coalesce(max(version),0)+1 FROM skills WHERE name=?',(skill['name'],)).fetchone()[0]
        self.db.execute('INSERT INTO skills VALUES(?,?,?,?,?,?)',(skill['name'],version,h,json.dumps(skill,ensure_ascii=False),'candidate',time.time()));self.db.commit()
        # Voyager's versioned program/description snapshots, kept together with source evidence.
        folder=self.root/'skill'/'code';folder.mkdir(parents=True,exist_ok=True)
        dumped_program_name=skill['name'] if version==1 else f"{skill['name']}V{version}"
        (folder/(dumped_program_name+'.json')).write_text(json.dumps(skill,ensure_ascii=False,indent=2))
        folder=self.root/'skill'/'description';folder.mkdir(parents=True,exist_ok=True)
        (folder/(dumped_program_name+'.txt')).write_text(skill['description'])
        return {'name':skill['name'],'version':version,'status':'candidate','hash':h}
    def get(self,name,version=None):
        sql='SELECT body,status,hash,version FROM skills WHERE name=?';args=[name]
        if version is not None:sql+=' AND version=?';args.append(version)
        row=self.db.execute(sql+' ORDER BY version DESC LIMIT 1',args).fetchone()
        if not row:raise KeyError(name)
        return {'skill':json.loads(row[0]),'status':row[1],'hash':row[2],'version':row[3]}
    def retrieve_skills(self,query,include_candidates=False):
        rows=self.db.execute('SELECT body,status,hash,version FROM skills ORDER BY version DESC').fetchall()
        candidates=[];q=terms(query);seen=set()
        for body,status,h,v in rows:
            skill=json.loads(body)
            if skill['name'] in seen:continue
            if status!='verified' and not include_candidates:continue
            seen.add(skill['name']);t=terms(skill['name']+' '+skill['description']+' '+' '.join(skill.get('tags',[])))
            score=len(q&t)/max(1,len(q));
            if score:candidates.append({'skill':skill,'status':status,'hash':h,'version':v,'score':score})
        k=min(len(candidates),self.retrieval_top_k)
        return sorted(candidates,key=lambda x:(-x['score'],x['skill']['name']))[:k]
    def record(self,skill,episode,success,reason,observed=False):
        ref=self.add_new_skill(skill);h=digest(episode)
        if not episode.get('id'):raise ValueError('Episode id is required')
        cur=self.db.execute('INSERT OR IGNORE INTO episodes VALUES(?,?,?,?,?,?,?,?)',(episode['id'],h,ref['hash'],int(success),reason,json.dumps(episode,ensure_ascii=False),time.time(),int(observed)))
        count=self.db.execute('SELECT count(*) FROM episodes WHERE skill_hash=? AND success=1 AND witness=1',(ref['hash'],)).fetchone()[0]
        failures=self.db.execute('SELECT count(*) FROM episodes WHERE skill_hash=? AND success=0 AND witness=1',(ref['hash'],)).fetchone()[0]
        # Two separately observed successes; changed program versions never inherit prior acceptance.
        status='verified' if count>=2 and failures==0 else 'candidate'
        self.db.execute('UPDATE skills SET status=? WHERE hash=?',(status,ref['hash']));self.db.commit()
        return {**ref,'status':status,'successful_runs':count,'failed_runs':failures,'new_episode':cur.rowcount==1,'reason':reason}
    def lesson(self,event):
        h=digest(event);self.db.execute('INSERT OR IGNORE INTO lessons VALUES(?,?,?)',(h,json.dumps(event,ensure_ascii=False),time.time()));self.db.commit();return h
    def recent_lessons(self,query='',limit=3):
        q=terms(query);out=[]
        for body,created in self.db.execute('SELECT body,created FROM lessons ORDER BY created DESC LIMIT 100'):
            if q and not q.intersection(terms(body)):continue
            out.append({'time':created,'experience':json.loads(body) if len(body)<=2000 else {'excerpt':body[:2000],'truncated':True}})
            if len(out)>=min(5,limit):break
        return out
    def summary(self):return {'skills':dict(self.db.execute('SELECT status,count(*) FROM skills GROUP BY status')),'episodes':self.db.execute('SELECT count(*) FROM episodes').fetchone()[0],'lessons':self.db.execute('SELECT count(*) FROM lessons').fetchone()[0]}
    def cursor(self,key,default=None):
        r=self.db.execute('SELECT value FROM cursors WHERE name=?',(key,)).fetchone();return json.loads(r[0]) if r else default
    def set_cursor(self,key,value):self.db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?)',(key,json.dumps(value)));self.db.commit()
