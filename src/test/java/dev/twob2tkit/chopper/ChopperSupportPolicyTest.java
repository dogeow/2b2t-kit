package dev.twob2tkit.chopper;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChopperSupportPolicyTest {
	@Test void aPredictedDirtBlockCannotReleaseFlightBeforeServerAcknowledgement(){
		for(int i=1;i<=50;i++)assertEquals(ChopperSupportPolicy.Confirmation.WAIT,ChopperSupportPolicy.placement(true,true,i));
		assertEquals(ChopperSupportPolicy.Confirmation.STAND,ChopperSupportPolicy.placement(false,true,51));
	}
	@Test void rejectedOrMissingConfirmationStopsInsteadOfRepeatingJumps(){
		assertEquals(ChopperSupportPolicy.Confirmation.WAIT,ChopperSupportPolicy.placement(false,false,2));
		assertEquals(ChopperSupportPolicy.Confirmation.STOP,ChopperSupportPolicy.placement(false,false,30));
		assertEquals(ChopperSupportPolicy.Confirmation.STOP,ChopperSupportPolicy.placement(true,true,161));
	}
	@Test void cleanupProtectsOriginalAndManuallyReplacedBlocksAndUnsafeDrops(){
		assertFalse(ChopperSupportPolicy.canRemove(false,true,false,true,true,false));
		assertFalse(ChopperSupportPolicy.canRemove(true,false,false,true,true,false));
		assertFalse(ChopperSupportPolicy.canRemove(true,true,true,false,true,false));
		assertFalse(ChopperSupportPolicy.canRemove(true,true,true,true,false,false));
		assertFalse(ChopperSupportPolicy.canRemove(true,true,true,true,true,true));
		assertTrue(ChopperSupportPolicy.canRemove(true,true,true,true,true,false));
	}
	@Test void treeThenSupportsThenPickupOrdering(){
		assertFalse(ChopperSupportPolicy.canFinishTree(8,3));
		assertFalse(ChopperSupportPolicy.canFinishTree(0,3));
		assertFalse(ChopperSupportPolicy.canFinishTree(0,1));
		assertTrue(ChopperSupportPolicy.canFinishTree(0,0));
	}
	@Test void centeringTheCapturedDiagonalPillarMustNotTriggerAnEndlessBuildAndDismantleLoop(){
		double before=Math.hypot(760991.293-760989.5,797882.293-797880.5);
		double centered=Math.hypot(760991.490-760989.5,797882.490-797880.5);
		assertTrue(ChopperSupportPolicy.shouldLift(before,false));
		assertTrue(ChopperSupportPolicy.shouldLift(centered,true));
		assertFalse(ChopperSupportPolicy.mustRelocate(centered));
		assertTrue(ChopperSupportPolicy.mustRelocate(4.2));
	}
	@Test void centeringWorstCaseIsCoveredByTheExistingPlatformRange(){
		assertTrue(ChopperSupportPolicy.shouldLift(2.8,false));
		assertTrue(ChopperSupportPolicy.shouldLift(2.8+Math.sqrt(.5),true));
		assertFalse(ChopperSupportPolicy.shouldLift(3.7,false));
		assertTrue(ChopperSupportPolicy.shouldLift(3.7,true));
		assertFalse(ChopperSupportPolicy.shouldLift(4.2,true));
	}
}
