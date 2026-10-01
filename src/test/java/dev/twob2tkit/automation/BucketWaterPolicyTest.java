package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BucketWaterPolicyTest {
    private static BucketWaterPolicy.Receipt ready() {
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();
        r.block(true,true,true,"water0",true,10);r.inventory(true,true,true,true,11);return r;
    }
    @Test void waterOnlySingletonHands(){
        assertTrue(BucketWaterPolicy.allowedHand(BucketWaterPolicy.Mode.FILL,"minecraft:bucket",1));
        assertTrue(BucketWaterPolicy.allowedHand(BucketWaterPolicy.Mode.PLACE,"minecraft:water_bucket",1));
        assertFalse(BucketWaterPolicy.allowedHand(BucketWaterPolicy.Mode.FILL,"minecraft:bucket",2));
        assertFalse(BucketWaterPolicy.allowedHand(BucketWaterPolicy.Mode.PLACE,"minecraft:lava_bucket",1));
        assertFalse(BucketWaterPolicy.allowedHand(BucketWaterPolicy.Mode.FILL,"minecraft:water_bucket",1));
    }
    @Test void exactConservationBothDirections(){
        assertTrue(BucketWaterPolicy.exactDelta(BucketWaterPolicy.Mode.FILL,3,2,2,3));
        assertTrue(BucketWaterPolicy.exactDelta(BucketWaterPolicy.Mode.PLACE,3,2,4,1));
        assertFalse(BucketWaterPolicy.exactDelta(BucketWaterPolicy.Mode.FILL,3,2,3,3));
        assertFalse(BucketWaterPolicy.exactDelta(BucketWaterPolicy.Mode.FILL,3,2,1,4));
        assertFalse(BucketWaterPolicy.exactDelta(BucketWaterPolicy.Mode.PLACE,1,-1,2,0));
    }
    @Test void exactInventoryPacketCoordinates(){
        assertTrue(BucketWaterPolicy.selectedPacketSlot(4,0,40,false));
        assertTrue(BucketWaterPolicy.selectedPacketSlot(4,0,4,true));
        assertFalse(BucketWaterPolicy.selectedPacketSlot(4,5,40,false));
        assertFalse(BucketWaterPolicy.selectedPacketSlot(4,0,4,false));
        assertFalse(BucketWaterPolicy.selectedPacketSlot(4,0,39,false));
        assertFalse(BucketWaterPolicy.selectedPacketSlot(9,0,45,false));
    }
    @Test void onlyRealPlainSourceWater(){
        assertTrue(BucketWaterPolicy.source(true,true,0,false));
        assertFalse(BucketWaterPolicy.source(true,false,1,false));
        assertFalse(BucketWaterPolicy.source(false,true,0,false));
        assertFalse(BucketWaterPolicy.source(true,true,0,true));
        assertFalse(BucketWaterPolicy.source(true,true,8,false));
    }
    @Test void filledBucketAcceptsRemovedFlowingOrRegeneratedPlainWaterSource(){
        assertTrue(BucketWaterPolicy.fillResult(true,false));
        assertTrue(BucketWaterPolicy.fillResult(false,true));
        assertFalse(BucketWaterPolicy.fillResult(false,false));
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();
        r.block(true,true,true,"water0",true,10);r.inventory(true,true,true,true,11);
        assertTrue(r.done(true,true,true,19));
    }
    @Test void holeMustBeEmptyContainedAndNonEvaporating(){
        assertTrue(BucketWaterPolicy.boundedHole(true,true,false,true,4,false));
        assertFalse(BucketWaterPolicy.boundedHole(false,true,false,true,4,false));
        assertFalse(BucketWaterPolicy.boundedHole(true,false,false,true,4,false));
        assertFalse(BucketWaterPolicy.boundedHole(true,true,true,true,4,false));
        assertFalse(BucketWaterPolicy.boundedHole(true,true,false,false,4,false));
        assertFalse(BucketWaterPolicy.boundedHole(true,true,false,true,3,false));
        assertFalse(BucketWaterPolicy.boundedHole(true,true,false,true,4,true));
    }
    @Test void predictionsAndInventoryCountsAloneCannotComplete(){
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();assertFalse(r.done(true,true,true,500));
    }
    @Test void serverBlockWithoutInventoryCannotComplete(){
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();r.block(true,true,true,"air",true,10);assertFalse(r.done(true,true,true,100));
    }
    @Test void serverInventoryWithoutBlockCannotComplete(){
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();r.inventory(true,true,true,true,10);assertFalse(r.done(true,true,true,100));
    }
    @Test void bothPacketsAndEightTicksComplete(){
        var r=ready();assertFalse(r.done(true,true,true,18));assertTrue(r.done(true,true,true,19));
    }
    @Test void packetOrderMayBeReversed(){
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();r.inventory(true,true,true,true,10);r.block(true,true,true,"air",true,11);
        assertTrue(r.done(true,true,true,19));
    }
    @Test void packetBeforeUseIsIgnored(){
        var r=new BucketWaterPolicy.Receipt();r.block(true,true,true,"air",true,10);r.inventory(true,true,true,true,11);r.sendOnce();
        assertFalse(r.done(true,true,true,100));assertFalse(r.blockSeen());assertFalse(r.inventorySeen());
    }
    @Test void oldConnectionAndDifferentCellAreIgnored(){
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();r.block(false,true,true,"air",true,10);r.block(true,false,true,"air",true,10);
        r.inventory(false,true,true,true,10);assertFalse(r.done(true,true,true,100));assertFalse(r.blockSeen());assertFalse(r.inventorySeen());
    }
    @Test void wrongBucketSlotIsIgnored(){
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();r.block(true,true,true,"air",true,10);r.inventory(true,false,true,true,11);
        assertFalse(r.done(true,true,true,100));assertFalse(r.inventorySeen());
    }
    @Test void rawCorrectiveBlockInvalidatesEarlierPositiveReceipt(){
        var r=ready();r.block(true,true,true,"air",false,12);assertFalse(r.done(true,true,true,100));
        assertTrue(r.blockSeen());assertFalse(r.blockConfirmed());assertEquals("air",r.blockState());
    }
    @Test void lateInventoryCorrectionInvalidatesConversion(){
        var r=ready();r.inventory(true,true,true,false,12);assertFalse(r.done(true,true,true,100));assertFalse(r.inventoryConfirmed());
    }
    @Test void worldOwnershipPredictionOrCountsCannotBeBypassed(){
        var r=ready();assertFalse(r.done(false,true,true,100));assertFalse(r.done(true,false,true,100));assertFalse(r.done(true,true,false,100));
    }
    @Test void uncertainUseCannotBeSentAgain(){
        var r=new BucketWaterPolicy.Receipt();r.sendOnce();assertThrows(IllegalStateException.class,r::sendOnce);
    }
}
