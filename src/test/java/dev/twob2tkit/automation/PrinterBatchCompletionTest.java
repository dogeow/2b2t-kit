package dev.twob2tkit.automation;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PrinterBatchCompletionTest {
    private void ack(PrinterBatchCompletion<String,String> b,String pos,String state){
        b.acknowledge(pos,state,true,true,true);
    }

    @Test void oneMaskTargetFinishesAsSoonAsItsUniqueFinalPacketIsAcknowledged(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("a"));
        assertFalse(b.complete(Set.of("a")));b.queued("a");ack(b,"a","dirt");
        assertTrue(b.complete(Set.of("a")));
    }
    @Test void duplicatePacketsCannotStandInForAnotherTarget(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("a","b"));
        for(int i=0;i<10;i++)ack(b,"a","dirt");
        assertFalse(b.complete(Set.of("a","b")));ack(b,"b","dirt");
        assertTrue(b.complete(Set.of("a","b")));
    }
    @Test void onlyFirstSentTravelAndPacingAcknowledgementsMayCreditTheFinalGoal(){
        for(var flags:List.of(new boolean[]{false,true,true},new boolean[]{true,false,true},
                             new boolean[]{true,true,false})){
            var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("a"));
            b.acknowledge("a","dirt",flags[0],flags[1],flags[2]);
            assertFalse(b.complete(Set.of("a")));
        }
    }
    @Test void anIntermediateOrientationDoesNotCreditAnExactGoal(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("a"));
        b.acknowledge("a","stairs:east:inner_left",true,true,false);
        assertFalse(b.complete(Set.of("a")));
    }
    @Test void laterCorrectionOfEarlierCoordinateRevokesCompletion(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("first","last"));
        ack(b,"first","dirt");b.serverBlock("first","air");ack(b,"last","dirt");
        assertFalse(b.complete(Set.of("first","last")));
    }
    @Test void exactStatesRejectChangesThatLegacyPacingMayAccept(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("a"));
        ack(b,"a","fence:east=true");b.serverBlock("a","fence:east=false");
        assertFalse(b.complete(Set.of("a")));
    }
    @Test void requeuedCoordinateRequiresANewConfirmedAction(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("a"));
        ack(b,"a","dirt");b.queued("a");assertFalse(b.complete(Set.of("a")));
        b.acknowledge("a","dirt",false,false,true);assertFalse(b.complete(Set.of("a")));
        ack(b,"a","dirt");assertTrue(b.complete(Set.of("a")));
    }
    @Test void emptyOrChangedMaskNeverCompletesEarly(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of());
        assertFalse(b.complete(Set.of()));b.begin(Set.of("a"));ack(b,"a","dirt");
        assertFalse(b.complete(Set.of("different")));assertFalse(b.complete(Set.of()));
    }
    @Test void outsideMaskPacketsAndUnsentActionsNeverCoverTheMask(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("a"));
        ack(b,"other","dirt");assertFalse(b.complete(Set.of("a")));
        b.queued("a");b.serverBlock("a","dirt");assertFalse(b.complete(Set.of("a")));
    }
    @Test void nextPrinterSessionCannotReuseOldReceipts(){
        var b=new PrinterBatchCompletion<String,String>();b.begin(Set.of("a"));ack(b,"a","dirt");
        assertTrue(b.complete(Set.of("a")));b.begin(Set.of("a"));assertFalse(b.complete(Set.of("a")));
        b.begin(Set.of());assertFalse(b.complete(Set.of()));
    }
    @Test void malformedTargetSetsAreRejected(){
        var b=new PrinterBatchCompletion<String,String>();
        assertThrows(IllegalArgumentException.class,()->b.begin(List.of("a","a")));
        assertThrows(IllegalArgumentException.class,()->b.begin(null));
    }
}
