package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.List;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import static org.junit.jupiter.api.Assertions.*;

class GuardRangedSafetyPolicyTest {
    @Test void tridentIsActualEquipmentNotAnAssumptionAboutAllDrowned(){
        assertFalse(BorerThreats.isRangedCombatType("drowned"));
        assertFalse(BorerThreats.rangedCombatThreat(true,true,"drowned",false,false,false,false));
        assertTrue(BorerThreats.rangedCombatThreat(true,true,"drowned",false,false,true,false));
        assertTrue(BorerThreats.rangedCombatThreat(true,true,"zombie",true,false,false,false));
        assertTrue(BorerThreats.rangedCombatThreat(true,true,"skeleton",false,false,false,false));
        assertFalse(BorerThreats.rangedCombatThreat(false,true,"drowned",false,false,true,false));
        assertFalse(BorerThreats.rangedCombatThreat(true,false,"drowned",false,false,true,false));
        assertTrue(GuardWeaponPolicy.ordinaryZombie("minecraft:drowned",false));
        assertFalse(GuardWeaponPolicy.ordinaryZombie("minecraft:drowned",true));
    }
    @Test void receivedTridentRequiresCurrentExactActualAttackerAndTypedNonEnvironmentalHit(){
        assertTrue(BorerThreats.receivedTrident(true,true,true,true,false,true,true,0));
        assertTrue(BorerThreats.receivedTrident(true,true,true,true,false,true,true,100));
        assertFalse(BorerThreats.receivedTrident(true,true,true,true,false,true,true,101));
        assertFalse(BorerThreats.receivedTrident(true,true,true,true,false,true,true,-1));
        assertFalse(BorerThreats.receivedTrident(false,true,true,true,false,true,true,1));
        assertFalse(BorerThreats.receivedTrident(true,true,true,true,true,true,true,1));
        assertFalse(BorerThreats.receivedTrident(true,true,true,false,false,true,true,1));
        assertFalse(BorerThreats.receivedTrident(true,true,true,true,false,false,true,1));
        assertFalse(BorerThreats.receivedTrident(true,true,true,true,false,true,false,1));
    }
    @Test void actualElevenPointZeroZeroEightDistanceAndFourPointSevenSixFourLowMobGetsRangedMargin(){
        double player=65.74358357727263,mob=60.979248046875,distance=11.007517575315024;
        assertEquals(4.764335530397631,player-mob,1e-9);
        assertEquals(mob+6-player,GuardWeaponPolicy.combatRise(player,List.of(new GuardWeaponPolicy.Threat(mob,true,distance))),1e-9);
        assertEquals(0,GuardWeaponPolicy.combatRise(player,List.of(new GuardWeaponPolicy.Threat(mob,false,distance))));
        assertTrue(GuardWeaponPolicy.safetyRiseNeeded(true,true,true,true,true,true,true,distance));
    }
    @Test void alreadyEngagedUnattackableOrHiddenActualHostileCanRiseWithoutAttackPermission(){
        assertTrue(GuardWeaponPolicy.safetyRiseNeeded(true,true,true,true,false,false,false,11.008));
        assertTrue(GuardWeaponPolicy.safetyRiseNeeded(true,true,true,true,false,false,true,10.1));
        assertFalse(GuardWeaponPolicy.safetyRiseNeeded(true,true,true,true,false,true,true,4));
        assertFalse(GuardWeaponPolicy.safetyRiseNeeded(true,false,true,true,true,false,false,4));
        assertFalse(GuardWeaponPolicy.safetyRiseNeeded(true,true,true,false,true,false,false,4));
        assertFalse(GuardWeaponPolicy.safetyRiseNeeded(false,true,true,true,true,false,false,4));
        assertFalse(GuardWeaponPolicy.safetyRiseNeeded(true,true,true,true,true,false,false,12.01));
        assertFalse(GuardWeaponPolicy.safetyRiseNeeded(true,true,true,true,true,false,false,Double.NaN));
    }
    @Test void fixedPlayerDerivedTargetNeverAddsTwelveAgainForSameEncounter(){
        Object world=new Object();var rise=new GuardWeaponPolicy.SafetyRise();
        assertEquals(12,rise.remaining(world,65,10,true));assertEquals(77,rise.target());
        assertEquals(10,rise.remaining(world,67,11,true));assertEquals(77,rise.target());
        assertEquals(8,rise.remaining(world,69,12,false));assertEquals(77,rise.target());
        assertEquals(0,rise.remaining(world,77,30,true));
        assertEquals(0,rise.remaining(world,65,31,true));assertFalse(rise.active());
    }
    @Test void fixedRiseHasFiniteDeadlineAndARealNewWorldOrExplicitEndResetsIt(){
        Object first=new Object(),second=new Object();var rise=new GuardWeaponPolicy.SafetyRise();
        assertEquals(0,rise.remaining(first,65,0,false));
        assertEquals(12,rise.remaining(first,65,1,true));
        assertEquals(0,rise.remaining(first,65,201,true));assertEquals(0,rise.remaining(first,65,202,true));
        assertEquals(12,rise.remaining(second,65,202,true));
        rise.clear();assertEquals(12,rise.remaining(second,65,203,true));
        assertEquals(0,new GuardWeaponPolicy.SafetyRise().remaining(null,65,1,true));
    }
    @Test void upwardMotionCannotApproachAnAboveGhastOrCreeperAndOriginalHealthThresholdStays(){
        assertFalse(StandaloneCreeperPolicy.riseMovesAway(65,70));
        assertTrue(StandaloneCreeperPolicy.riseMovesAway(65,60));
        assertFalse(GuardWeaponPolicy.riseFailureNeedsExit(20));
        assertFalse(GuardWeaponPolicy.riseFailureNeedsExit(14));
        assertTrue(GuardWeaponPolicy.riseFailureNeedsExit(13.826));
    }
    @Test void actualPlayerPoseVelocityAndEveryBoundingBoundMustBeFiniteAndNondegenerate(){
        assertTrue(GuardWeaponPolicy.finiteVector(new Vec3(0,65,0)));
        assertTrue(GuardWeaponPolicy.finiteVector(Vec3.ZERO));
        assertFalse(GuardWeaponPolicy.finiteVector(null));
        assertFalse(GuardWeaponPolicy.finiteVector(new Vec3(Double.NaN,0,0)));
        assertFalse(GuardWeaponPolicy.finiteVector(new Vec3(0,Double.POSITIVE_INFINITY,0)));
        assertFalse(GuardWeaponPolicy.finiteVector(new Vec3(0,0,Double.NEGATIVE_INFINITY)));
        double[] bounds={-.3,65,-.3,.3,66.8,.3};
        assertTrue(GuardWeaponPolicy.finiteBox(new AABB(bounds[0],bounds[1],bounds[2],bounds[3],bounds[4],bounds[5])));
        for(int i=0;i<6;i++){
            var invalid=bounds.clone();invalid[i]=Double.NaN;
            assertFalse(GuardWeaponPolicy.finiteBox(new AABB(invalid[0],invalid[1],invalid[2],invalid[3],invalid[4],invalid[5])),"bound "+i);
        }
        assertFalse(GuardWeaponPolicy.finiteBox(new AABB(0,65,0,0,67,1)));
        assertFalse(GuardWeaponPolicy.finiteBox(null));
    }
    @Test void farAboveActualHostilesOutsideTheEntireRiseDangerRadiusDoNotActAsCeilings(){
        var swept=new AABB(-.3,65,-.3,.3,78.95,.3);
        var thirtyBlocksBeside=new AABB(29.7,72,-.3,30.3,74,.3);
        var farAbove=new AABB(-.5,100,-.5,.5,102,.5);
        assertTrue(GuardWeaponPolicy.riseThreatClear(65,72,swept,thirtyBlocksBeside,12));
        assertTrue(GuardWeaponPolicy.riseThreatClear(65,100,swept,farAbove,12));
        var nearAbove=new AABB(7.7,72,-.3,8.3,74,.3);
        assertFalse(GuardWeaponPolicy.riseThreatClear(65,72,swept,nearAbove,9));
        assertTrue(GuardWeaponPolicy.riseThreatClear(65,72,swept,nearAbove,6));
        assertFalse(GuardWeaponPolicy.riseThreatClear(65,72,swept,nearAbove,12));
    }
    @Test void bodyIntersectionNearbyAboveAndUnknownBoundsAlwaysRefuseTheAscent(){
        var swept=new AABB(-.3,65,-.3,.3,78.95,.3);
        assertFalse(GuardWeaponPolicy.riseThreatClear(65,64,swept,new AABB(-.2,64,-.2,.2,65.8,.2),9));
        assertFalse(GuardWeaponPolicy.riseThreatClear(65,84,swept,new AABB(-.3,84,-.3,.3,86,.3),6));
        assertTrue(GuardWeaponPolicy.riseThreatClear(65,60,swept,new AABB(2,60,2,2.6,61.8,2.6),12));
        assertFalse(GuardWeaponPolicy.riseThreatClear(65,100,swept,new AABB(Double.NaN,100,0,1,102,1),12));
        assertFalse(GuardWeaponPolicy.riseThreatClear(65,100,swept,new AABB(0,100,0,1,Double.POSITIVE_INFINITY,1),12));
        assertFalse(GuardWeaponPolicy.riseThreatClear(65,Double.NaN,swept,new AABB(30,100,0,31,102,1),12));
    }
}
