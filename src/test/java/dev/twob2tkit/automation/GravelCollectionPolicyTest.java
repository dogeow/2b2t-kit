package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GravelCollectionPolicyTest {
    @Test void arrivingInsideTheSelectedColumnIsEnoughToStartTheDive(){
        assertTrue(GravelCollectionPolicy.sameColumn(10.14,20.07,10,20));
        assertFalse(GravelCollectionPolicy.sameColumn(9.99,20.07,10,20));
        assertFalse(GravelCollectionPolicy.sameColumn(10.14,21.01,10,20));
    }
    @Test void pickupLeavesRoomForNativeAirFallbackAndRecoversMidDescent(){
        assertEquals(265,GravelCollectionPolicy.pickupStartFloor(218));
        assertEquals(285,GravelCollectionPolicy.pickupStartFloor(270));
        assertTrue(GravelCollectionPolicy.recoverableDescentAirStop(
            "water descent stopped for surface air or health",20));
        assertTrue(GravelCollectionPolicy.recoverableDescentAirStop(
            "Guarded water descent needs clear vertical pickup and full reserve",20));
        assertFalse(GravelCollectionPolicy.recoverableDescentAirStop(
            "water descent stopped for surface air or health",18));
    }
    @Test void validObservedPickupUsesRealAirBudgetAndExpiredCalibrationKeepsFallback(){
        assertEquals(86,GravelCollectionPolicy.pickupStartFloor(71,true));
        assertEquals(265,GravelCollectionPolicy.pickupStartFloor(71,false));
        assertEquals(285,GravelCollectionPolicy.pickupStartFloor(270,true));
        assertEquals(265,GravelCollectionPolicy.pickupStartFloor(0,true));
    }
    @Test void blockGoneInventoryGainedAndDropGoneConfirmPickupWithoutExtraDive(){
        assertTrue(GravelCollectionPolicy.confirmedPickup(true,1,false));
        assertFalse(GravelCollectionPolicy.confirmedPickup(false,1,false));
        assertFalse(GravelCollectionPolicy.confirmedPickup(true,0,false));
        assertFalse(GravelCollectionPolicy.confirmedPickup(true,1,true));
    }
    @Test void onlyNearbyDropsWithAnExactClearPickupColumnMayBeApproached(){
        assertTrue(GravelCollectionPolicy.boundedDropApproach(0,true));
        assertTrue(GravelCollectionPolicy.boundedDropApproach(1.5,true));
        assertFalse(GravelCollectionPolicy.boundedDropApproach(1.5,false));
        assertFalse(GravelCollectionPolicy.boundedDropApproach(2.9251074650605537,true));
        assertFalse(GravelCollectionPolicy.boundedDropApproach(3.676867682403659,true));
        assertFalse(GravelCollectionPolicy.boundedDropApproach(Double.NaN,true));
        assertFalse(GravelCollectionPolicy.boundedDropApproach(-1,true));
    }
    @Test void nativeEntryUsesOnlyTheAuthorizedWorldScope() {
        assertTrue(GravelCollectionPolicy.allowedWorld(true,""));
        assertTrue(GravelCollectionPolicy.allowedWorld(false,"Simpcraft.com:25565"));
        assertTrue(GravelCollectionPolicy.allowedWorld(false,"31.25.11.102:25565"));
        assertFalse(GravelCollectionPolicy.allowedWorld(false,"simpcraft.com.example.org"));
        assertFalse(GravelCollectionPolicy.allowedWorld(false,"another-server.example"));
    }
    @Test void driftingPickupCanUseOnlyBoundedProvedColumnStepsWithExtraAir(){
        assertTrue(GravelCollectionPolicy.boundedPickupRebase(3.676,true,254,86,20,true,0));
        assertTrue(GravelCollectionPolicy.boundedPickupRebase(6,true,126,86,19,true,3));
        assertFalse(GravelCollectionPolicy.boundedPickupRebase(6.01,true,254,86,20,true,0));
        assertFalse(GravelCollectionPolicy.boundedPickupRebase(3.676,false,254,86,20,true,0));
        assertFalse(GravelCollectionPolicy.boundedPickupRebase(3.676,true,125,86,20,true,0));
        assertFalse(GravelCollectionPolicy.boundedPickupRebase(3.676,true,254,86,18,true,0));
        assertFalse(GravelCollectionPolicy.boundedPickupRebase(3.676,true,254,86,20,false,0));
        assertFalse(GravelCollectionPolicy.boundedPickupRebase(3.676,true,254,86,20,true,4));
        assertFalse(GravelCollectionPolicy.boundedPickupRebase(Double.NaN,true,254,86,20,true,0));
    }
    @Test void standingOnTheNextGravelCellCanContinueButFarDropsCannot() {
        assertTrue(GravelCollectionPolicy.reachable(52,51,.2,1.7,4.15));
        assertTrue(GravelCollectionPolicy.reachable(53,51,1.1,2.9,4.15));
        assertFalse(GravelCollectionPolicy.reachable(51.4,51,.2,1.0,4.15));
        assertFalse(GravelCollectionPolicy.reachable(53,51,1.6,3,4.15));
        assertFalse(GravelCollectionPolicy.reachable(55,51,1,4.7,4.15));
    }
    @Test void OnlyInventoryGrowthCountsAndFullBagStopsUnlimitedMode() {
        assertEquals(0,GravelCollectionPolicy.credited(205,205));
        assertEquals(6,GravelCollectionPolicy.credited(205,211));
        assertEquals(0,GravelCollectionPolicy.credited(205,204));
        assertFalse(GravelCollectionPolicy.complete(63,64,64));
        assertTrue(GravelCollectionPolicy.complete(64,64,64));
        assertFalse(GravelCollectionPolicy.complete(128,0,1));
        assertTrue(GravelCollectionPolicy.complete(128,0,0));
    }
    @Test void OnlyUnchangedOccludedMiningCanBeSkippedWithoutEndingTheRun(){
        assertTrue(GravelCollectionPolicy.skipUnstartedMine("mining target is occluded",true,0));
        assertFalse(GravelCollectionPolicy.skipUnstartedMine("mining target is occluded",false,0));
        assertFalse(GravelCollectionPolicy.skipUnstartedMine("mining target is occluded",true,1));
        assertFalse(GravelCollectionPolicy.skipUnstartedMine("server timeout",true,0));
    }
    @Test void pickupRetriesRequireAnObservedDropAndAirAndAreBounded(){
        assertEquals(GravelCollectionPolicy.PickupAction.WAIT,GravelCollectionPolicy.pickupAction(39,0,0,true,true));
        assertEquals(GravelCollectionPolicy.PickupAction.RETRY,GravelCollectionPolicy.pickupAction(40,0,0,true,true));
        assertEquals(GravelCollectionPolicy.PickupAction.WAIT,GravelCollectionPolicy.pickupAction(40,0,0,true,false));
        assertEquals(GravelCollectionPolicy.PickupAction.SKIP,GravelCollectionPolicy.pickupAction(100,2,0,true,true));
        assertEquals(GravelCollectionPolicy.PickupAction.STOP,GravelCollectionPolicy.pickupAction(100,2,2,false,true));
    }
}
