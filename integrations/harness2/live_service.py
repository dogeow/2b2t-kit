"""Single local queue worker for post-execution learning; never controls Minecraft."""
from pathlib import Path
import argparse,fcntl,json,os,time
from live_learning import reflect_live,verify_retrieval
from strategy_loop import LIVE
from minecraft_harness import write

def process(job_path):
 job=json.loads(job_path.read_text())
 if job.get('state')!='pending':return False
 if job.get('kind')!='live_reflection':
  job.update(state='needs_codex_fix',detail='Outside the bounded strategy evaluator; no automatic game retry.');write(job_path,job);return False
 # Bound automatic account usage; failed attempts count and are never retried.
 now=int(time.time()*1000)
 attempts=[]
 for previous in job_path.parent.glob('*'):
  try:record=json.loads(previous.read_text())
  except(OSError,ValueError):continue
  if record.get('kind')=='live_reflection' and now-3600000<record.get('started_at',0)<=now:
   attempts.append(record['started_at'])
 if len(attempts)>=2:
  job.update(detail='等待本地学习调用间隔；每小时最多两次，不影响 Kit 施工。');write(job_path,job);return False
 out=LIVE/'online-feedback'/job['id'];job.update(state='running',worker_pid=os.getpid(),started_at=int(time.time()*1000));write(job_path,job)
 try:
  result=reflect_live(job['acceptance'],out/'reflection');reuse=verify_retrieval(out/'reflection',out/'retrieval');job.update(state='complete',result=str(out/'reflection/live-reflection-result.json'),retrieval=str(out/'retrieval/retrieval-result.json'),entry_created=result['entry_created'],retrieval_verified=reuse.get('verified',False))
 except Exception as error:job.update(state='failed',error=str(error),automatic_retry=False)
 job['finished_at']=int(time.time()*1000);write(job_path,job);return True

def main():
 parser=argparse.ArgumentParser(__doc__);parser.add_argument('--once',action='store_true');args=parser.parse_args();LIVE.mkdir(parents=True,exist_ok=True);lock=(LIVE/'service.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print('EXISTING_LEARNING_WORKER_RETAINED');return
 write(LIVE/'service.json',dict(pid=os.getpid(),scope='local_learning_no_game_controller',started_at=int(time.time()*1000)))
 while True:
  jobs=sorted((LIVE/'review-requests').glob('*'))if(LIVE/'review-requests').exists()else[]
  completed=0
  for path in jobs:
   try:
    if process(path):completed+=1
   except (OSError,ValueError)as error:write(LIVE/'service-error.json',dict(error=str(error),job=path.name))
  if args.once:print('LEARNING_QUEUE_PROCESSED',completed,flush=True);return
  time.sleep(3)
if __name__=='__main__':main()
