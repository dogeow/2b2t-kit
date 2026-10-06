"""Explicit offline evaluation of the configured resident model. No Kit actions."""
import argparse
import json
from pathlib import Path
import statistics
import time
from decisions import choose
from ollama_decision import OllamaDecision


def evaluate(settings, cases, out):
    config=json.loads((settings/'settings.json').read_text())
    out.mkdir(parents=True,exist_ok=False)
    model=OllamaDecision(settings,config)
    rows=[]
    try:
        for case in cases['cases']:
            result=choose(model,case['goal'],case['choices'],{'facts':case['facts']})
            row={'id':case['id'],'family':case['family'],'expected':case['expected'],
                 'choice':result['choice'],'correct':result['choice']==case['expected'],
                 'elapsed_ms':result['elapsed_ms'],'confidence':result['confidence'],'usage':result.get('usage')}
            rows.append(row)
            (out/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
            print('STAGE_EVAL',len(rows),case['id'],row['choice'],row['correct'],round(row['elapsed_ms']),flush=True)
        summary={'model':model.model,'prompt_version':cases['prompt_version'],'cases':len(rows),
                 'correct':sum(row['correct']for row in rows),'families':len({row['family']for row in rows}),
                 'median_ms':statistics.median(row['elapsed_ms']for row in rows),
                 'scope':'offline stage selection only','game_actions_dispatched':False}
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        return summary
    finally:model.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--settings',type=Path,required=True)
    parser.add_argument('--cases',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(evaluate(args.settings,json.loads(args.cases.read_text()),args.out)))
