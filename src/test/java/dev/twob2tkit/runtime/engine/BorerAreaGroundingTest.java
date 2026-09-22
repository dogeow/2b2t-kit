package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaGroundingTest {
	@Test void actualShallowMiningHeightCanLandNaturallyOnVerifiedFloor() {
		assertTrue(BorerAreaGrounding.allowed(true,63.0,63,0,0,0,true));
		assertTrue(BorerAreaGrounding.allowed(true,63.08,63,0,-.0784,0,true));
	}
	@Test void emptyUnloadedOrUnconfirmedSupportNeverDisablesFlight() {
		assertFalse(BorerAreaGrounding.allowed(true,63,63,0,0,0,false));
		assertFalse(BorerAreaGrounding.allowed(false,63,63,0,0,0,true));
		assertFalse(BorerAreaGrounding.allowed(true,70,63,0,0,0,true));
	}
	@Test void motionAndFallingMustSettleBeforeGroundedMining() {
		assertFalse(BorerAreaGrounding.allowed(true,63.08,63,.1,0,0,true));
		assertFalse(BorerAreaGrounding.allowed(true,63.08,63,0,-.3,0,true));
		assertFalse(BorerAreaGrounding.allowed(true,62.8,63,0,0,0,true));
	}
}
