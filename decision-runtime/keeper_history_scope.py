"""Bind an immutable paid quote to the same server/account across client world nonces.

This is historical evidence, never a new quote, payment, or native attestation.
The caller must still require the actual loaded healthy adult and paid history.
"""
from pathlib import Path
import hashlib
import json

SCOPE='immutable_paid_quote_and_same_connection_not_new_quote_or_native_attestation'

def connection_scope(state):
    server=state.get('server');dimension=state.get('dimension');account=state.get('account_name')or state.get('player_name')
    if any(not isinstance(v,str)or not v or v.strip()!=v for v in (server,dimension,account)):return None
    return [server.lower().removesuffix(':25565'),dimension,account]

def digest(proof):
    return hashlib.sha256(json.dumps(proof,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def load(base,proof,state):
    try:
        if (proof.get('complete')is not True or proof.get('pending')or proof.get('open_roofs')
                or not isinstance(proof.get('world_session'),str)or not proof['world_session']
                or not isinstance(proof.get('immutable_quote_result'),str)
                or state.get('connected')is not True or connection_scope(state)is None):return None
        base=Path(base).resolve();path=(base/proof['immutable_quote_result']).resolve()
        if not path.is_relative_to(base)or not path.is_file()or path.stat().st_size>2*1024*1024:return None
        raw=path.read_bytes();reply=json.loads(raw);merchant=reply.get('reopened_merchant')or(reply.get('menu')or{}).get('merchant')or reply.get('merchant')
        if (reply.get('world_session')!=proof['world_session']or reply.get('pending')
                or reply.get('phase')not in (None,'done')or reply.get('outcome_pending')is True
                or merchant!=proof['merchant']or merchant.get('protocol')!=1 or merchant.get('owned')is not True
                or merchant.get('villager_uuid')!=proof['keeper_uuid']or merchant.get('trader_xp',0)<=0
                or merchant.get('observation_scope')!='current_server_received_merchant_menu_not_trade_completion'):return None
        for parent in path.parents:
            if parent==base:break
            context=parent/'actual-before.json'
            if not context.is_file()or context.stat().st_size>2*1024*1024:continue
            context_raw=context.read_bytes();original=json.loads(context_raw)
            if(original.get('connected')is True and original.get('world_session')==proof['world_session']
                    and connection_scope(original)==connection_scope(state)):
                return {'scope':SCOPE,'proof_digest':digest(proof),'source_world':proof['world_session'],
                        'current_world':state['world_session'],'connection':connection_scope(state),
                        'keeper_uuid':proof['keeper_uuid'],'immutable_quote_result':str(path.relative_to(base)),
                        'quote_result_sha256':hashlib.sha256(raw).hexdigest(),
                        'original_context':str(context.relative_to(base)),
                        'context_sha256':hashlib.sha256(context_raw).hexdigest()}
    except(OSError,ValueError,KeyError,TypeError):return None
    return None

def matches(certificate,proof,state):
    try:
        return (isinstance(certificate,dict)and certificate.get('scope')==SCOPE
                and certificate['proof_digest']==digest(proof)
                and certificate['source_world']==proof['world_session']
                and certificate['current_world']==state['world_session']
                and certificate['keeper_uuid']==proof['keeper_uuid']
                and connection_scope(state)is not None and certificate['connection']==connection_scope(state))
    except(ValueError,KeyError,TypeError):return False
