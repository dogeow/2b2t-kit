package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BorerControlPolicyTest {
	@Test void nativeStartRequiresOwnedHealthyGroundedGravelOnlyHandoff() {
		assertNull(BorerControlPolicy.startRejection(true, true, true, true, true, true, true));
		assertNotNull(BorerControlPolicy.startRejection(false, true, true, true, true, true, true));
		assertNotNull(BorerControlPolicy.startRejection(true, false, true, true, true, true, true));
		assertNotNull(BorerControlPolicy.startRejection(true, true, false, true, true, true, true));
		assertNotNull(BorerControlPolicy.startRejection(true, true, true, false, true, true, true));
		assertNotNull(BorerControlPolicy.startRejection(true, true, true, true, false, true, true));
		assertNotNull(BorerControlPolicy.startRejection(true, true, true, true, true, false, true));
		assertNotNull(BorerControlPolicy.startRejection(true, true, true, true, true, true, false));
	}

	@Test void stopCannotTakeOverAnotherPlayersOrManualMiningJob() {
		assertTrue(BorerControlPolicy.ownsStop("native-session-a", "native-session-a", true));
		assertFalse(BorerControlPolicy.ownsStop("native-session-a", "native-session-b", true));
		assertFalse(BorerControlPolicy.ownsStop("native-session-a", "native-session-a", false));
		assertFalse(BorerControlPolicy.ownsStop("", "", true));
	}
}
