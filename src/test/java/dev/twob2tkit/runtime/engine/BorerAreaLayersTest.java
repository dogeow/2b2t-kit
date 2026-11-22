package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaLayersTest {
	@Test void onlyTallAreasAtOrAboveTheWaterLineAreDugStanding() {
		assertTrue(BorerAreaLayers.standing(62, 77, 63));   // beach: bottom is the sea surface block
		assertFalse(BorerAreaLayers.standing(61, 77, 63));  // reaches under the sea surface: keep shafts
		assertFalse(BorerAreaLayers.standing(62, 67, 63));  // six high already uses one shallow pass
		assertTrue(BorerAreaLayers.standing(70, 120, 63));
	}
	@Test void slabsAreFourHighFromTheTopAndTheLastOneStopsAtTheBottom() {
		assertEquals(4, BorerAreaLayers.count(62, 77));
		assertEquals(77, BorerAreaLayers.top(77, 0)); assertEquals(74, BorerAreaLayers.bottom(62, 77, 0));
		assertEquals(65, BorerAreaLayers.top(77, 3)); assertEquals(62, BorerAreaLayers.bottom(62, 77, 3));
		assertEquals(5, BorerAreaLayers.count(62, 78));
		assertEquals(78 - 16, BorerAreaLayers.top(78, 4)); assertEquals(62, BorerAreaLayers.bottom(62, 78, 4));
	}
	@Test void emptyAirSlabsAboveTheBeachAreSkipped() {
		var work = Set.of(2, 3);
		assertEquals(2, BorerAreaLayers.firstWithWork(0, 62, 77, work::contains));
		assertEquals(3, BorerAreaLayers.firstWithWork(3, 62, 77, work::contains));
		assertEquals(-1, BorerAreaLayers.firstWithWork(4, 62, 77, work::contains));
		assertEquals(-1, BorerAreaLayers.firstWithWork(0, 62, 77, i -> false));
	}
}
