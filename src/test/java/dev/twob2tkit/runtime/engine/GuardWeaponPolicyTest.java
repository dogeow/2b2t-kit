package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class GuardWeaponPolicyTest {
 @Test void heldAndSpareBowsUseTheSameDurabilityReserve(){
  assertFalse(GuardWeaponPolicy.usableBow(true,true,0));assertFalse(GuardWeaponPolicy.usableBow(true,true,7));
  assertTrue(GuardWeaponPolicy.usableBow(true,true,8));assertTrue(GuardWeaponPolicy.usableBow(true,false,0));assertFalse(GuardWeaponPolicy.usableBow(false,false,999));
 }
 @Test void aLowCeilingKeepsTheBowFallbackInsteadOfForcingLogout(){
  assertEquals(GuardWeaponPolicy.Hover.FALLBACK,GuardWeaponPolicy.hover(65,65,false));
  assertEquals(GuardWeaponPolicy.Hover.FALLBACK,GuardWeaponPolicy.hover(67.1,65,false));
  assertEquals(GuardWeaponPolicy.Hover.RISE,GuardWeaponPolicy.hover(65,65,true));
  assertEquals(GuardWeaponPolicy.Hover.HOLD,GuardWeaponPolicy.hover(68,65,false));
  assertEquals(GuardWeaponPolicy.Hover.FALLBACK,GuardWeaponPolicy.hover(70,65,true));
 }
 @Test void zombieHoverNeverCommandsADescentIntoMelee(){
  assertTrue(GuardWeaponPolicy.needsRise(64,64));assertTrue(GuardWeaponPolicy.needsRise(66.9,64));
  assertFalse(GuardWeaponPolicy.needsRise(67,64));assertFalse(GuardWeaponPolicy.needsRise(70,64));
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
}
