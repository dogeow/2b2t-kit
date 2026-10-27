"""Recognise a native mining refusal that sent no excavation packet."""

def rejected_without_mining(reply,request_id,world,target):
    return (reply.get('id')==request_id and reply.get('world_session')==world
            and reply.get('op')=='mine_block' and reply.get('mining_target')==target
            and reply.get('phase')=='waiting' and reply.get('detail')=='mining target is occluded'
            and type(reply.get('native_sequence'))is int and reply['native_sequence']==-1
            and type(reply.get('server_ack_sequence'))is int and reply['server_ack_sequence']==-1
            and reply.get('server_update_seen')is False and reply.get('server_confirmed')is False
            and reply.get('outcome_pending')is False)
