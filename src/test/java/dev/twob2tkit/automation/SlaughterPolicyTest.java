package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SlaughterPolicyTest {
    private boolean owned(String task,String world,long revision,long expires,long heartbeat) {
        return SlaughterPolicy.owned(true,task,"farm",world,"world-a","world-a",revision,7,7,expires,heartbeat);
    }
    private boolean safe(boolean ground,boolean busy,boolean held,float health,boolean sweepClear) {
        return SlaughterPolicy.safe(true,busy,false,held,true,health,20,ground,false,false,false,false,true,sweepClear);
    }
    @Test void realCurrentLeaseRequired() {
        assertTrue(owned("farm","world-a",7,5000,10));
        assertFalse(owned("","world-a",7,5000,10));
        assertFalse(owned("other","world-a",7,5000,10));
        assertFalse(owned("farm","old-world",7,5000,10));
        assertFalse(owned("farm","world-a",6,5000,10));
        assertFalse(SlaughterPolicy.owned(false,"farm","farm","world-a","world-a","world-a",7,7,7,5000,10));
    }
    @Test void liveWorldAndLeaseRevisionBothRequired() {
        assertFalse(SlaughterPolicy.owned(true,"farm","farm","world-a","world-a","world-b",7,7,7,5000,10));
        assertFalse(SlaughterPolicy.owned(true,"farm","farm","world-a","world-a","world-a",7,6,7,5000,10));
        assertFalse(SlaughterPolicy.owned(true,"farm","farm","world-a","world-b","world-a",7,7,7,5000,10));
    }
    @Test void expiredOrMissingHeartbeatNeverPermitsAttack() {
        assertFalse(owned("farm","world-a",7,-1,10));
        assertFalse(owned("farm","world-a",7,15001,10));
        assertFalse(owned("farm","world-a",7,5000,15001));
        assertFalse(owned("farm","world-a",7,5000,-1));
        assertTrue(owned("farm","world-a",7,15000,15000));
    }
    @Test void safeAirborneAttackAndNoSweepNeighbourRequired() {
        assertTrue(safe(false,false,false,19,true));
        assertFalse(safe(true,false,false,20,true));
        assertFalse(safe(false,false,false,20,false));
        assertFalse(safe(false,true,false,20,true));
        assertFalse(safe(false,false,true,20,true));
        assertFalse(safe(false,false,false,18.99F,true));
        assertFalse(safe(false,false,false,Float.NaN,true));
    }
    @Test void manualFoodDamageAndOtherControllersOwnPriority() {
        assertFalse(SlaughterPolicy.safe(true,false,true,false,true,20,20,false,false,false,false,false,true,true));
        assertFalse(SlaughterPolicy.safe(true,false,false,false,true,20,20,false,true,false,false,false,true,true));
        assertFalse(SlaughterPolicy.safe(true,false,false,false,true,20,20,false,false,true,false,false,true,true));
        assertFalse(SlaughterPolicy.safe(true,false,false,false,true,20,20,false,false,false,false,true,true,true));
        assertFalse(SlaughterPolicy.safe(true,false,false,false,true,20,20,false,false,false,true,false,true,true));
    }
    @Test void requiresPveProtectionSurvivalFoodAndRealWeapon() {
        assertFalse(SlaughterPolicy.safe(false,false,false,false,true,20,20,false,false,false,false,false,true,true));
        assertFalse(SlaughterPolicy.safe(true,false,false,false,false,20,20,false,false,false,false,false,true,true));
        assertFalse(SlaughterPolicy.safe(true,false,false,false,true,20,7,false,false,false,false,false,true,true));
        assertFalse(SlaughterPolicy.safe(true,false,false,false,true,20,20,false,false,false,false,false,false,true));
    }
    @Test void onlyFourOrdinaryFoodSpecies() {
        for(String species:new String[]{"minecraft:cow","minecraft:sheep","minecraft:pig","minecraft:chicken"})
            assertTrue(SlaughterPolicy.adult(species,true,false,false,false,10));
        for(String species:new String[]{"minecraft:horse","minecraft:wolf","minecraft:player","minecraft:mooshroom","minecraft:zombie"})
            assertFalse(SlaughterPolicy.adult(species,true,false,false,false,10));
    }
    @Test void babyNamedRemovedAndDeadAnimalsAlwaysProtected() {
        assertFalse(SlaughterPolicy.adult("minecraft:cow",true,false,true,false,10));
        assertFalse(SlaughterPolicy.adult("minecraft:cow",true,false,false,true,10));
        assertFalse(SlaughterPolicy.adult("minecraft:cow",true,true,false,false,10));
        assertFalse(SlaughterPolicy.adult("minecraft:cow",false,false,false,false,10));
        assertFalse(SlaughterPolicy.adult("minecraft:cow",true,false,false,false,0));
        assertFalse(SlaughterPolicy.adult("minecraft:cow",true,false,false,false,Float.NaN));
    }
    @Test void cannotReduceReserveBelowFourDefaultOrTwoAbsoluteMinimum() {
        assertEquals(20,SlaughterPolicy.DEFAULT_KEEP);
        assertTrue(SlaughterPolicy.surplus(5,4));
        assertFalse(SlaughterPolicy.surplus(4,4));
        assertFalse(SlaughterPolicy.surplus(3,4));
        assertTrue(SlaughterPolicy.surplus(3,2));
        assertFalse(SlaughterPolicy.surplus(20,1));
        assertFalse(SlaughterPolicy.surplus(20,-1));
    }
    @Test void regionIsBoundedAndCannotOverflowVolume() {
        assertTrue(new SlaughterPolicy.Bounds(0,0,0,31,7,31).valid());
        assertFalse(new SlaughterPolicy.Bounds(0,0,0,31,8,31).valid());
        assertFalse(new SlaughterPolicy.Bounds(0,0,0,32,0,0).valid());
        assertFalse(new SlaughterPolicy.Bounds(1,0,0,0,1,1).valid());
        assertFalse(new SlaughterPolicy.Bounds(Integer.MIN_VALUE,0,0,Integer.MAX_VALUE,0,0).valid());
    }
    @Test void regionUsesActualFiniteAnimalPosition() {
        var b=new SlaughterPolicy.Bounds(10,60,20,12,65,22);
        assertTrue(b.contains(10,60,20));assertTrue(b.contains(12.99,65.99,22.99));
        assertFalse(b.contains(13,65,22));assertFalse(b.contains(10,59.99,20));
        assertFalse(b.contains(Double.NaN,60,20));assertFalse(b.contains(10,Double.POSITIVE_INFINITY,20));
    }
    @Test void identitySightReachAndCooldownAllRequired() {
        assertTrue(SlaughterPolicy.aim(true,true,2.8,3,.95F));
        assertFalse(SlaughterPolicy.aim(false,true,2,3,1));
        assertFalse(SlaughterPolicy.aim(true,false,2,3,1));
        assertFalse(SlaughterPolicy.aim(true,true,2.81,3,1));
        assertFalse(SlaughterPolicy.aim(true,true,2,3,.94F));
        assertFalse(SlaughterPolicy.aim(true,true,Double.NaN,3,1));
        assertFalse(SlaughterPolicy.aim(true,true,2,Double.POSITIVE_INFINITY,1));
        assertFalse(SlaughterPolicy.aim(true,true,2,3,Float.NaN));
    }
}
