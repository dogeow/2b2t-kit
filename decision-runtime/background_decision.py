"""One read-only model request at a time; only the foreground controller may act."""
from copy import deepcopy
from queue import Queue, Empty
import threading
import time


class DecisionMailbox:
    def __init__(self, clock=time.monotonic):
        self.clock=clock;self.job=None;self.closed=False
    @property
    def busy(self):return self.job is not None
    def submit(self,context,work):
        if self.closed or self.busy:return False
        job={'context':deepcopy(context),'started':self.clock(),'valid':True,'queue':Queue(maxsize=1)}
        self.job=job
        def run():
            try:result={'response':work()}
            except Exception as error:result={'error':error}
            job['queue'].put({**result,'elapsed':self.clock()-job['started']})
        threading.Thread(target=run,name='kit-background-decision',daemon=True).start()
        return True
    def invalidate(self,reason='state changed'):
        if self.job:self.job['valid']=False;self.job['invalid_reason']=reason
    def take(self):
        if not self.job or self.closed:return None
        job=self.job
        try:result=job['queue'].get_nowait()
        except Empty:return None
        self.job=None
        return {**result,'context':job['context'],'valid':job['valid'],
                'invalid_reason':job.get('invalid_reason'), 'age':self.clock()-job['started']}
    def close(self):
        self.closed=True;self.invalidate('controller closed')
