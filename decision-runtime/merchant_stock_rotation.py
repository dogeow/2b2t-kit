"""Bounded stock polling that never strands other merchants indefinitely.

Decisions only. Fresh ownership, health, UI and transaction receipts remain the
caller's responsibility; a decision does not authorize a game interaction.
"""


class StockRotation:
    def __init__(self, slots, *, max_idle_probes=2):
        if (not isinstance(slots,tuple) or not 2<=len(slots)<=8
                or any(not isinstance(v,str) or not 1<=len(v)<=64 for v in slots)
                or len(set(slots))!=len(slots)
                or type(max_idle_probes) is not int or not 1<=max_idle_probes<=5):
            raise ValueError('Distinct bounded merchant slots and a finite idle probe count required')
        self.slots=slots;self.max_idle_probes=max_idle_probes
        self._empty=0;self._idle=0;self.holding=False

    def next_slot(self,current):
        if current not in self.slots:raise ValueError('Current merchant is outside this rotation')
        return current if self.holding else self.slots[(self.slots.index(current)+1)%len(self.slots)]

    def note_batch_result(self,trades):
        if type(trades) is not int or not 0<=trades<=32:
            raise ValueError('A terminal batch count of zero to 32 trades is required')
        if trades:
            self._empty=0;self._idle=0;self.holding=False
        elif self.holding:
            self._idle+=1
            if self._idle>=self.max_idle_probes:
                self._empty=0;self._idle=0;self.holding=False
        else:
            self._empty+=1
            if self._empty>=len(self.slots):self.holding=True;self._idle=0
