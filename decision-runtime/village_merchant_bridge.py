"""Run refreshed trade logic through the existing village queue and its sole owner."""
class VillageMerchantBridge:
    def __init__(self,queue):
        self.queue=queue;self.root=queue.root;self.world=queue.world;self.task=queue.lease['job_session']
        s=self.status();self.server=s['server'];self.last=s['last_request'];self.out=queue.out
        self.merchant_purchase_hand_pending=False
    def status(self):
        s=self.queue.status(observing=True)
        if s['world_session']!=self.world or s['supervision_lease']['job_session']!=self.task or s['health']!=20:
            raise RuntimeError('Original healthy village owner changed during trade')
        return s
    def checked(self,op,**params):
        if op not in {'merchant_select_trade','slot_click','close_menu','select_item','interact_entity'}:
            raise ValueError('Trade bridge accepts only ordinary merchant interactions')
        from queued_request_identity import command_id,terminal_id
        self.status();previous=command_id(self.queue)
        try:r=self.queue.native(op,**params)
        except BaseException:
            known=terminal_id(self.queue,op,params,previous)
            if known:self.last=known
            raise
        self.last=r['id']
        if r.get('phase')!='done':raise RuntimeError(r.get('detail','Original trade input is not confirmed'))
        return r
    def request(self,op,**params):
        if op!='snapshot':return self.checked(op,**params)
        if params:raise ValueError('Trade snapshot takes no control parameters')
        self.status();r=self.queue.native('snapshot');self.last=r['id']
        if r.get('world_session')!=self.world:raise RuntimeError('Trade observation belongs to another world')
        self.status();return r
