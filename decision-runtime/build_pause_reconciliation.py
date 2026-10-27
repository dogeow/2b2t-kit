"""Accept a refused pause only when the same native job has already settled."""
REJECTION='Build supervision rejected: task, input, cooldown or server queue changed'
def already_settled(reply,state,job):
    build=state.get('build_job')or{};printer=state.get('professional_printer')or{}
    return bool(reply.get('phase')=='error' and reply.get('detail')==REJECTION
        and state.get('connected')is True and not state.get('manual_movement')and not state.get('screen')
        and build.get('session')==job and build.get('active')is False and build.get('queue_settled')is True
        and printer.get('owned')is False and printer.get('waiting_for_server')is False
        and printer.get('travel_pending')==0 and not state.get('navigating')and not state.get('pending_scan'))

def pause_or_observe_completion(client,job):
    import json,time
    reply=client.request('build_control',job_session=job,action='pause_and_report')
    if reply.get('phase')=='done':return
    # Keep the exact original receipt; no retries or second stop command.
    deadline=time.monotonic()+2
    while reply.get('phase')=='error' and reply.get('detail')==REJECTION:
        state=client.status()
        if already_settled(reply,state,job):
            with(client.out/'build-pause-reconciliations.jsonl').open('a')as stream:
                stream.write(json.dumps({'original_reply':reply,'settled_state':state,'request_replayed':False})+'\n')
            return
        if time.monotonic()>=deadline:break
        time.sleep(.1)
    raise RuntimeError(reply.get('detail','Build pause outcome unproved'))
