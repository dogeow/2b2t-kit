package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BottleWaterPolicyTest {
    @Test void singletonReplacesHandEvenWithFullInventoryButStackNeedsSpace(){
        assertEquals(6,BottleWaterPolicy.outputSlot(6,1,-1));
        assertEquals(-1,BottleWaterPolicy.outputSlot(6,2,-1));
        assertEquals(12,BottleWaterPolicy.outputSlot(6,64,12));
        assertEquals(-1,BottleWaterPolicy.outputSlot(6,2,6));
        assertEquals(-1,BottleWaterPolicy.outputSlot(9,1,12));
    }
    @Test void menuSlotsCannotConfirmArmorOffhandOrOtherContainers(){
        assertEquals(6,BottleWaterPolicy.inventorySlot(0,42,false));
        assertEquals(12,BottleWaterPolicy.inventorySlot(0,12,false));
        assertEquals(6,BottleWaterPolicy.inventorySlot(7,6,true));
        assertEquals(-1,BottleWaterPolicy.inventorySlot(1,42,false));
        assertEquals(-1,BottleWaterPolicy.inventorySlot(0,45,false));
        assertEquals(-1,BottleWaterPolicy.inventorySlot(0,4,false));
    }
    @Test void clientPredictionAndStalePacketsCannotCompleteUse(){
        var r=new BottleWaterPolicy.Receipt();
        r.inventory(true,6,6,6,true,true,0);r.sendOnce();
        assertFalse(r.done(true,true,true,true,100));
        r.inventory(false,6,6,6,true,true,1);r.inventory(true,6,6,6,false,true,1);
        assertFalse(r.done(true,true,true,true,100));
        r.inventory(true,6,6,6,true,true,2);
        assertFalse(r.done(true,true,true,true,9));assertTrue(r.done(true,true,true,true,10));
        assertFalse(r.done(false,true,true,true,10));assertFalse(r.done(true,false,true,true,10));
        assertFalse(r.done(true,true,false,true,10));assertFalse(r.done(true,true,true,false,10));
        assertThrows(IllegalStateException.class,r::sendOnce);
    }
    @Test void stackedBottleNeedsBothHandAndWaterServerPacketsAndRejectsCorrections(){
        var r=new BottleWaterPolicy.Receipt();r.sendOnce();r.inventory(true,6,6,12,true,true,1);
        assertFalse(r.done(true,true,true,true,100));r.inventory(true,12,6,12,true,true,2);
        assertTrue(r.done(true,true,true,true,10));r.inventory(true,6,6,12,true,false,11);
        assertFalse(r.done(true,true,true,true,100));
    }
    @Test void onlyOneEmptyBottleBecomesOneWaterBottle(){
        assertTrue(BottleWaterPolicy.exactDelta(1,0,2,3));
        assertFalse(BottleWaterPolicy.exactDelta(1,1,2,3));
        assertFalse(BottleWaterPolicy.exactDelta(2,0,2,3));
        assertFalse(BottleWaterPolicy.exactDelta(1,0,2,4));
    }
}
