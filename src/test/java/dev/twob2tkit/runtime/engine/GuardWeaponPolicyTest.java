package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class GuardWeaponPolicyTest {
 @Test void distantHiddenOrdinaryWaterCreeperCannotBlockDryWorkButUnsafeEvidenceDoes(){
  assertTrue(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,true,true,false,false,false,12,2));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(false,true,true,true,false,false,false,20,8));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,false,true,true,false,false,false,20,8));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,false,true,false,false,false,20,8));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,true,false,false,false,false,20,8));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,true,true,true,false,false,20,8));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,true,true,false,true,false,20,8));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,true,true,false,false,true,20,8));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,true,true,false,false,false,11.99,8));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,true,true,false,false,false,20,1.99));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedCreeper(true,true,true,true,false,false,false,Double.NaN,8));
 }
 @Test void aWaterZombieFarBelowCannotBlockDryWorkButTridentAndHitsKeepDefense(){
  assertTrue(GuardWeaponPolicy.harmlessSubmergedMelee(true,true,true,true,false,6));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedMelee(true,true,true,true,false,5.999));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedMelee(true,false,true,true,false,20));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedMelee(true,true,true,true,true,20));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedMelee(true,true,true,false,false,20));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedMelee(false,true,true,true,false,20));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedMelee(true,true,false,true,false,20));
  assertFalse(GuardWeaponPolicy.harmlessSubmergedMelee(true,true,true,true,false,Double.NaN));
 }
 @Test void expiredUnobservedStandaloneFightRetreatsWithoutTreatingAbsenceAsDeath(){
  assertTrue(GuardWeaponPolicy.missingTargetRise(true,true,true,false,0));
  assertFalse(GuardWeaponPolicy.missingTargetRise(false,true,true,false,0));
  assertFalse(GuardWeaponPolicy.missingTargetRise(true,false,true,false,0));
  assertFalse(GuardWeaponPolicy.missingTargetRise(true,true,false,false,0));
  assertFalse(GuardWeaponPolicy.missingTargetRise(true,true,true,true,0));
  assertFalse(GuardWeaponPolicy.missingTargetRise(true,true,true,false,1));
 }
 @Test void unknownTargetsCannotDisengageWithoutTheVerifiedHighClearance(){
  assertTrue(GuardWeaponPolicy.missingTargetDisengage(true,true,false,true,32));
  assertFalse(GuardWeaponPolicy.missingTargetDisengage(true,true,false,true,31.999));
  assertFalse(GuardWeaponPolicy.missingTargetDisengage(true,true,false,true,Double.NaN));
  assertFalse(GuardWeaponPolicy.missingTargetDisengage(true,true,false,true,Double.POSITIVE_INFINITY));
  assertFalse(GuardWeaponPolicy.missingTargetDisengage(false,true,false,true,60));
  assertFalse(GuardWeaponPolicy.missingTargetDisengage(true,false,false,true,60));
  assertFalse(GuardWeaponPolicy.missingTargetDisengage(true,true,true,true,60));
  assertFalse(GuardWeaponPolicy.missingTargetDisengage(true,true,false,false,60));
 }
	@Test void independentZombieFallbackCannotUseGroundSword(){
		assertFalse(GuardWeaponPolicy.groundSwordAllowed(true,true));
		assertTrue(GuardWeaponPolicy.groundSwordAllowed(true,false));
		assertTrue(GuardWeaponPolicy.groundSwordAllowed(false,true));
	}
	@Test void zombieSwordNeedsActualSwordWithThirtyTwoDurability(){
		assertTrue(GuardWeaponPolicy.usableSword(true,32));
		assertFalse(GuardWeaponPolicy.usableSword(true,31));
		assertFalse(GuardWeaponPolicy.usableSword(false,200));
	}
 @Test void heldAndSpareBowsUseTheSameDurabilityReserve(){
  assertFalse(GuardWeaponPolicy.usableBow(true,true,0));assertFalse(GuardWeaponPolicy.usableBow(true,true,7));
  assertTrue(GuardWeaponPolicy.usableBow(true,true,8));assertTrue(GuardWeaponPolicy.usableBow(true,false,0));assertFalse(GuardWeaponPolicy.usableBow(false,false,999));
 }
 @Test void aLowCeilingKeepsTheBowFallbackInsteadOfForcingLogout(){
  assertEquals(GuardWeaponPolicy.Hover.FALLBACK,GuardWeaponPolicy.hover(65,65,false));
  assertEquals(GuardWeaponPolicy.Hover.FALLBACK,GuardWeaponPolicy.hover(67.1,65,false));
  assertEquals(GuardWeaponPolicy.Hover.RISE,GuardWeaponPolicy.hover(65,65,true));
  assertEquals(GuardWeaponPolicy.Hover.HOLD,GuardWeaponPolicy.hover(68,65,false));
  assertEquals(GuardWeaponPolicy.Hover.DESCEND,GuardWeaponPolicy.hover(70,65,true));
 }
 @Test void descentStopsAboveZombieReachAndBrakeProjectionCannotSendUsDown(){
  assertEquals(-.15,GuardWeaponPolicy.hoverVerticalStep(70,70,64),1e-9);
  assertEquals(-.05,GuardWeaponPolicy.hoverVerticalStep(67.15,67.15,64),1e-9);
  assertEquals(0,GuardWeaponPolicy.hoverVerticalStep(67.5,66.8,64),1e-9);
  assertEquals(.15,GuardWeaponPolicy.hoverVerticalStep(65,65,64),1e-9);
  assertEquals(GuardWeaponPolicy.Hover.FALLBACK,GuardWeaponPolicy.hover(70,64,false));
 }
 @Test void ordinaryZombieScopeExcludesConversionCandidatesAndRangedDrowned(){
  for(String type:java.util.List.of("minecraft:zombie","minecraft:husk","minecraft:drowned"))
   assertTrue(GuardWeaponPolicy.ordinaryZombie(type,false));
  for(String type:java.util.List.of("minecraft:zombie_villager","minecraft:zombified_piglin","minecraft:skeleton","minecraft:creeper"))
   assertFalse(GuardWeaponPolicy.ordinaryZombie(type,false));
  assertFalse(GuardWeaponPolicy.ordinaryZombie("minecraft:drowned",true));
 }
 @Test void zombieHoverNeverCommandsADescentIntoMelee(){
  assertTrue(GuardWeaponPolicy.needsRise(64,64));assertTrue(GuardWeaponPolicy.needsRise(66.9,64));
  assertFalse(GuardWeaponPolicy.needsRise(67,64));assertFalse(GuardWeaponPolicy.needsRise(70,64));
 }
	@Test void swordOnlyFromSafeReachableHoverWithNoRangedMob(){
		assertTrue(GuardWeaponPolicy.swordHoverReady(true,true,true,67.1,67.1,64,2.8,3));
		assertFalse(GuardWeaponPolicy.swordHoverReady(true,true,true,66.9,66.9,64,2.8,3));
		assertFalse(GuardWeaponPolicy.swordHoverReady(true,true,true,67.1,66.8,64,2.8,3));
		assertFalse(GuardWeaponPolicy.swordHoverReady(true,true,true,67.5,67.5,64,2.8,3));
		assertFalse(GuardWeaponPolicy.swordHoverReady(true,true,true,67.1,67.1,64,2.81,3));
		assertFalse(GuardWeaponPolicy.swordHoverReady(false,true,true,67.1,67.1,64,2.8,3));
		assertFalse(GuardWeaponPolicy.swordHoverReady(true,false,true,67.1,67.1,64,2.8,3));
		assertFalse(GuardWeaponPolicy.swordHoverReady(true,true,false,67.1,67.1,64,2.8,3));
	}
	@Test void aSkeletonTargetDoesNotSuppressAscentWhenZombieIsAlsoNearby(){
		var threats = java.util.List.of(new GuardWeaponPolicy.Threat(74, false, 3),
			new GuardWeaponPolicy.Threat(75, true, 8));
		assertEquals(7.0, GuardWeaponPolicy.combatRise(74, threats));
		assertEquals(0.0, GuardWeaponPolicy.combatRise(82, threats));
	}
	@Test void distantHostilesDoNotTriggerAnUnnecessaryAscent(){
		assertEquals(0.0, GuardWeaponPolicy.combatRise(74,
			java.util.List.of(new GuardWeaponPolicy.Threat(74, false, 10),
				new GuardWeaponPolicy.Threat(74, true, 13))));
	}
    @Test void blockedAscentAtHealthyStateFallsBackToCombatInsteadOfIdleOrLogout() {
        assertFalse(GuardWeaponPolicy.riseFailureNeedsExit(20));
        assertFalse(GuardWeaponPolicy.riseFailureNeedsExit(14));
        assertTrue(GuardWeaponPolicy.riseFailureNeedsExit(13.9));
    }
}
