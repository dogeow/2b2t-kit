package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ConfirmedPlacementPacerTest {
    @Test void plainCubeNeedsSentActionAndServerConfirmationBeforeNextProposal(){
        var p=new ConfirmedPlacementPacer();assertTrue(p.acquire(1,false,true));p.queued(1,true);
        assertFalse(p.acknowledge());assertFalse(p.acquire(30,false,true));p.sent(4);assertTrue(p.acknowledge());
        assertFalse(p.acquire(8,false,true));assertTrue(p.acquire(9,false,true));
    }
    @Test void tenNativeSubticksCannotQueueTwoPlacementsInOneClientTick(){
        var p=new ConfirmedPlacementPacer();int proposals=0;
        for(int sub=0;sub<10;sub++)if(p.acquire(1,false,true)){proposals++;p.queued(1,true);p.sent(1);p.acknowledge();}
        assertEquals(1,proposals);
    }
    @Test void delayedAndMissingAcknowledgementsNeverUnlockTheQueue(){
        for(int delay:new int[]{2,5,15,45}){
            var p=new ConfirmedPlacementPacer();assertTrue(p.acquire(0,false,true));p.queued(0,true);p.sent(2);
            for(int tick=1;tick<delay+2;tick++)assertFalse(p.acquire(tick,false,true));
            p.acknowledge();assertTrue(p.acquire(Math.max(8,delay+2),false,true));
        }
        var p=new ConfirmedPlacementPacer();p.queued(0,true);p.sent(3);assertTrue(p.timedOut(63));assertFalse(p.acquire(100,false,true));
    }
    @Test void conservativeAndComplexPlacementsKeepTwentyTickCadence(){
        var p=new ConfirmedPlacementPacer(false);p.queued(1,true);p.sent(5);p.acknowledge();
        assertFalse(p.acquire(20,false,true));assertTrue(p.acquire(21,false,true));
        p=new ConfirmedPlacementPacer();p.queued(7,false);assertFalse(p.acquire(26,false,true));assertTrue(p.acquire(27,false,true));
    }
    @Test void pauseAndBusyNativeQueueBothBlockNewWork(){
        var p=new ConfirmedPlacementPacer();assertFalse(p.acquire(0,true,true));assertFalse(p.acquire(0,false,false));assertTrue(p.acquire(0,false,true));
        p.queued(0,true);assertTrue(p.cancelUnsent(2));assertFalse(p.awaiting());
        assertTrue(p.acquire(2,false,true));p.queued(2,true);p.sent(5);assertFalse(p.cancelUnsent(6));assertTrue(p.awaiting());p.acknowledge();assertTrue(p.acquire(10,false,true));
    }
    @Test void eachNewTargetRequiresItsOwnAcknowledgement(){
        var p=new ConfirmedPlacementPacer();p.queued(0,true);p.sent(3);p.acknowledge();assertTrue(p.acquire(8,false,true));p.queued(8,true);
        assertFalse(p.acquire(40,false,true));assertFalse(p.acknowledge());p.sent(12);assertTrue(p.acknowledge());assertFalse(p.acknowledge());
    }
    @Test void onlyPropertyFreeNonFallingFullBlocksWithoutBlockEntitiesAccelerate(){
        assertTrue(ConfirmedPlacementPacer.safeSimple(true,true,false,false));
        assertFalse(ConfirmedPlacementPacer.safeSimple(false,true,false,false));
        assertFalse(ConfirmedPlacementPacer.safeSimple(true,false,false,false));
        assertFalse(ConfirmedPlacementPacer.safeSimple(true,true,true,false));
        assertFalse(ConfirmedPlacementPacer.safeSimple(true,true,false,true));
    }
}
