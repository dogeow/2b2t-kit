package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class UnderwaterGravelPolicyTest {
	@Test void exposedGravelWithAirOrBreathingCanStartButDryBuildingsCannot() {
		assertNull(UnderwaterGravelPolicy.startRejection(true,true,false,true,20,250,false,true,500));
		assertNull(UnderwaterGravelPolicy.startRejection(true,true,false,true,20,0,true,true,500));
		assertNotNull(UnderwaterGravelPolicy.startRejection(false,true,false,true,20,250,false,true,500));
		assertNotNull(UnderwaterGravelPolicy.startRejection(true,false,false,true,20,250,false,true,500));
		assertNotNull(UnderwaterGravelPolicy.startRejection(true,true,true,true,20,250,false,true,500));
	}

	@Test void fallingAirHealthOrToolDurabilityStopsTheAttempt() {
		assertNotNull(UnderwaterGravelPolicy.startRejection(true,true,false,true,20,179,false,true,500));
		assertNotNull(UnderwaterGravelPolicy.startRejection(true,true,false,true,20,250,false,true,49));
		assertFalse(UnderwaterGravelPolicy.continueMining(true,20,119,false));
		assertFalse(UnderwaterGravelPolicy.continueMining(true,17,300,false));
		assertFalse(UnderwaterGravelPolicy.continueMining(false,20,300,true));
		assertTrue(UnderwaterGravelPolicy.continueMining(true,20,0,true));
	}
}
