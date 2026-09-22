package dev.twob2tkit.structure;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GuideSessionTest {
	@Test void netherCoordinatesNeverSurviveThePortalOrReconnectIntoAnotherWorld(){
		GuideSession g=new GuideSession();g.start("simpcraft|nether");
		assertTrue(g.matches("simpcraft|nether"));assertFalse(g.matches("simpcraft|overworld"));
		assertFalse(g.matches("other-server|nether"));assertFalse(g.matches(null));
		g.stop();assertFalse(g.matches("simpcraft|nether"));
	}
	@Test void arrivalNeedsHeightAndStableProximityButNotClosingAScreen(){
		GuideSession g=new GuideSession();g.start("world");
		for(int i=0;i<20;i++)assertFalse(g.arrived(1,10));
		for(int i=0;i<9;i++)assertFalse(g.arrived(2,0));
		assertTrue(g.arrived(2,0));
	}
	@Test void passingByDoesNotAccumulateUnrelatedArrivalSamples(){
		GuideSession g=new GuideSession();g.start("world");
		for(int i=0;i<9;i++)assertFalse(g.arrived(2,0));
		assertFalse(g.arrived(10,0));
		assertFalse(g.arrived(2,0));
		g.start("world");assertFalse(g.arrived(2,0));
	}
	@Test void distantDestinationsStayCompact(){
		assertEquals("42 格",GuideSession.distance(42.2));
		assertEquals("1.5 km",GuideSession.distance(1500));
	}
}
