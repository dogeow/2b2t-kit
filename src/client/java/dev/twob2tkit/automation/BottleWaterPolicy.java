package dev.twob2tkit.automation;

/** Bottles preserve source water, so no water block-change packet is expected. */
final class BottleWaterPolicy {
    private BottleWaterPolicy() {}
    static int outputSlot(int selected,int count,int firstEmpty) {
        if(selected<0||selected>8||count<1||count>64)return -1;
        return count==1?selected:firstEmpty>=0&&firstEmpty<36&&firstEmpty!=selected?firstEmpty:-1;
    }
    static int inventorySlot(int containerId,int slot,boolean direct) {
        if(direct)return slot>=0&&slot<36?slot:-1;
        if(containerId!=0)return -1;
        return slot>=36&&slot<45?slot-36:slot>=9&&slot<36?slot:-1;
    }
    static boolean exactDelta(int bottlesBefore,int bottlesAfter,int waterBefore,int waterAfter) {
        return bottlesBefore>0&&bottlesAfter>=0&&waterBefore>=0
            &&bottlesAfter==bottlesBefore-1&&waterAfter==waterBefore+1;
    }
    static final class Receipt {
        private boolean sent,handConfirmed,outputConfirmed;
        private long handTick=-1,outputTick=-1;
        void sendOnce(){if(sent)throw new IllegalStateException("Bottle use already sent; no retry allowed");sent=true;}
        void inventory(boolean sameContext,int slot,int hand,int output,boolean applied,boolean expected,long tick){
            if(!sent||!sameContext||!applied)return;
            if(slot==hand){handConfirmed=expected;handTick=expected?tick:-1;}
            if(slot==output){outputConfirmed=expected;outputTick=expected?tick:-1;}
        }
        boolean done(boolean owner,boolean sourceUnchanged,boolean predictionsSettled,boolean exactInventory,long tick){
            return sent&&owner&&sourceUnchanged&&predictionsSettled&&exactInventory&&handConfirmed&&outputConfirmed
                &&handTick>=0&&outputTick>=0&&tick-Math.max(handTick,outputTick)>=8;
        }
        boolean sent(){return sent;}
        boolean handConfirmed(){return handConfirmed;}
        boolean outputConfirmed(){return outputConfirmed;}
    }
}
