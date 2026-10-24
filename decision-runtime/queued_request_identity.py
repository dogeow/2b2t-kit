"""Recover only a queued operation's witnessed terminal ID after a wrapper error."""
import json


def command_id(queue):
    try:return json.loads((queue.out/'command.json').read_text())['id']
    except(OSError,ValueError,KeyError,AttributeError,TypeError):return None


def terminal_id(queue,op,params,previous):
    try:
        command=json.loads((queue.out/'command.json').read_text());d=queue.out/command['id']
        if (command['id']==previous or command['action']!='native'or command['op']!=op
                or command['params']!=params or json.loads((d/'intent.json').read_text())!=command):return None
        reply=json.loads((d/'result.json').read_text())
        events=[json.loads(v)for v in(queue.out/'control/events.jsonl').read_text().splitlines()]
        event=next(v for v in reversed(events)if v.get('request_id')==reply.get('id'))
        if (reply['world_session']==event['world_session']==queue.world
                and reply['phase']==event['phase']and reply['phase']in('done','error','stopped','waiting')
                and event['op']==op and event['params']['task_session']==queue.lease['job_session']
                and all(event['params'].get(k)==v for k,v in params.items())):return reply['id']
    except(OSError,ValueError,KeyError,AttributeError,TypeError,StopIteration):return None
