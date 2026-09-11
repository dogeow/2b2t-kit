package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PrinterPulseTest {
    private int simulateDelayedServer(boolean gated,int interval){
        int queue=0,subTick=0,placements=0,ackAt=Integer.MAX_VALUE;
        boolean serverUpdated=false;
        for(int tick=0;tick<60;tick++){
            if(tick>=ackAt)serverUpdated=true;
            boolean allow=!gated||PrinterPulse.allowProposal(tick);
            for(int sub=0;sub<10;sub++){
                if(allow&&!serverUpdated&&queue==0)queue=2; // prepare + interact
                if(++subTick%interval==0 && queue>0 && --queue==0){
                    placements++;ackAt=Math.min(ackAt,tick+5);
                }
            }
        }
        return placements;
    }
    @Test void delayedBlockAcknowledgementCannotQueueDuplicatePlacement(){
        assertTrue(simulateDelayedServer(false,12)>1);
        assertEquals(1,simulateDelayedServer(true,12));
        assertEquals(1,simulateDelayedServer(true,40));
    }
    @Test void eachSecondHasOneProposalWindowRegardlessOfFrameRate(){
        for(int start=0;start<100;start++){
            int windows=0;
            for(int t=start;t<start+20;t++)if(PrinterPulse.allowProposal(t))windows++;
            assertEquals(1,windows);
        }
    }
}
