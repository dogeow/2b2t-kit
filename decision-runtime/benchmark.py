"""Paired small Minecraft intent benchmark, with explicit cold/warm timing boundaries."""
import argparse,json,statistics,time
from pathlib import Path
from decisions import provider,question,validated_answer

CHOICES={'yellow':'Walk to the yellow marker.','blue':'Walk to the blue marker.','wait':'Stay still; do not walk anywhere.'}
CASES=[('走到黄色标记。','yellow'),('Go to the blue marker.','blue'),('先别动，我只想看一下。','wait'),
       ('Go to blue, not yellow.','blue'),('Move to the yellow marker and then wait for me.','yellow'),('Stop and wait here.','wait')]

def timed(client,state,questions):
    start=time.perf_counter();r=client.predict(state,questions);ms=(time.perf_counter()-start)*1000
    return {'elapsed_ms':round(ms,3),'answer':validated_answer(r,CHOICES),'usage':r.get('usage',{}),'model':r.get('model')}

def main():
    p=argparse.ArgumentParser();p.add_argument('--provider',choices=['jev','laya'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    started=time.perf_counter();client=provider(a.provider);load=time.perf_counter()-started
    state=lambda goal:{'goal':goal,'scene':{'game':'Minecraft','test_area':'flat safe floor','markers':['yellow','blue']}}
    q=question(CHOICES);result={'provider':a.provider,'load_seconds':round(load,3),'cold':timed(client,state(CASES[0][0]),q),'samples':[]}
    try:
        for _ in range(3 if a.provider=='laya' else 1):timed(client,state(CASES[0][0]),q)
        repeats=8 if a.provider=='laya' else 2
        for _ in range(repeats):
            for goal,expected in CASES:
                row=timed(client,state(goal),q);row.update(goal=goal,expected=expected,correct=row['answer']['choice']==expected);result['samples'].append(row)
        ms=sorted(r['elapsed_ms'] for r in result['samples'])
        result['summary']={'samples':len(ms),'p50_ms':round(statistics.median(ms),3),'p95_ms':ms[min(len(ms)-1,int(len(ms)*.95))],
                           'correct':sum(r['correct'] for r in result['samples']),'min_ms':ms[0],'max_ms':ms[-1]}
        three={**q,'requests_movement':{'type':'noul','instructions':'Does state.goal request walking to a marker?'},
               'language':{'type':'choice','instructions':'Which language is state.goal written in?','criteria':{'Chinese':'Chinese','English':'English'}}}
        result['three_questions']=[timed(client,state(goal),three) for goal,_ in CASES]
        result['three_question_p50_ms']=round(statistics.median(r['elapsed_ms'] for r in result['three_questions']),3)
        if a.provider=='laya':
            import mlx.core as mx
            result['mlx_peak_mib']=round(mx.get_peak_memory()/1024**2,1)
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in result.items() if k not in ['samples','three_questions']},ensure_ascii=False))
    finally:client.close()
if __name__=='__main__':main()
