package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class PlacementTravelBarrierTest {
    @Test void proposalAndLocalPredictionAreNotServerConfirmation(){
        var b=new PlacementTravelBarrier<String,String>();b.queued("x","stairs:east");
        b.serverBlock("x","stairs:east");assertFalse(b.settled());
        b.sent("x");assertFalse(b.settled());b.serverBlock("x","stairs:east");assertTrue(b.settled());
    }
    @Test void complexBlockMustMatchItsFullState(){
        var b=new PlacementTravelBarrier<String,String>();b.queued("x","stairs:east:bottom:inner_left");b.sent("x");
        for(String wrong:new String[]{"air","stairs:west:bottom:inner_left","stairs:east:top:inner_left","stairs:east:bottom:straight"}){
            b.serverBlock("x",wrong);assertFalse(b.settled());
        }
        b.serverBlock("x","stairs:east:bottom:inner_left");assertTrue(b.settled());
    }
    @Test void lastBlockConfirmedCannotHideAnEarlierOutstandingAction(){
        var b=new PlacementTravelBarrier<String,String>();
        b.queued("first","slab:top");b.sent("first");b.queued("last","door:lower");b.sent("last");
        b.serverBlock("last","door:lower");assertFalse(b.settled());assertEquals(1,b.pendingCount());
        b.serverBlock("first","slab:top");assertTrue(b.settled());
    }
    @Test void unrelatedServerPacketDoesNotReleasePendingTarget(){
        var b=new PlacementTravelBarrier<String,String>();b.queued("a","quartz");b.sent("a");
        b.serverBlock("b","quartz");assertFalse(b.settled());
    }
    @Test void pauseCancelsOnlyUnsentActions(){
        var b=new PlacementTravelBarrier<String,String>();b.queued("a","quartz");b.sent("a");b.queued("b","quartz");
        b.cancelUnsent();assertEquals(1,b.pendingCount());assertFalse(b.settled());
        b.serverBlock("a","quartz");assertTrue(b.settled());
    }
    @Test void unknownNativeActionKeepsConservativeRetryBehavior(){
        var b=new PlacementTravelBarrier<String,String>();b.queued(null,null);b.cancelUnsent();
        b.queued("a","quartz");b.sent("a");b.serverBlock("a","quartz");assertFalse(b.settled());
    }
}
