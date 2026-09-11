package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class SceneryServerViewTest {
	static class Listener { private int serverChunkRadius = 8; private int serverSimulationDistance = 32; }
	static class WrappedListener extends Listener {}
	@Test void usesServerEightNotClientThirtyTwoOrSimulationDistanceAndTracksNewPackets() {
		var listener = new WrappedListener(); var view = new SceneryServerView();
		assertEquals(new SceneryServerView.Limits(8, 32, 8), view.read(listener, 32));
		((Listener)listener).serverChunkRadius = 4;
		assertEquals(new SceneryServerView.Limits(4, 32, 4), view.read(listener, 32));
		assertEquals(new SceneryServerView.Limits(4, 2, 2), view.read(listener, 2));
	}
	@Test void missingPacketOrUnknownInterfaceNeverFallsBackToAssumingClientThirtyTwo() {
		assertThrows(IllegalStateException.class, () -> SceneryServerView.limits(0, 32));
		assertThrows(IllegalStateException.class, () -> new SceneryServerView().read(new Object(), 32));
		assertThrows(IllegalStateException.class, () -> new SceneryServerView().read(null, 32));
		assertEquals(32, SceneryServerView.limits(64, 128).scan());
	}
	@Test void asymmetricServerEightCoverageWithMissingAndDelayedChunksIsEventuallyFilled() {
		var plan = new SceneryCoverage(-31.75, 127.5, 512);
		var received = new HashSet<SceneryCoverage.Chunk>(); var deferred = new SceneryCoverage.Chunk(-2, 7);
		int radius = SceneryServerView.limits(8, 32).scan(), visits = 0;
		while (plan.next() != null) {
			var target = plan.next();
			for (int dx = -radius; dx <= radius; dx++) for (int dz = -radius; dz <= radius; dz++) {
				var c = new SceneryCoverage.Chunk(target.x() + dx, target.z() + dz);
				// Irregular loaded window and a temporarily withheld chunk: never fill a theoretical square.
				if (dx * dx + dz * dz > radius * radius || visits == 0 && c.equals(deferred)) continue;
				if (plan.needs(c.x(), c.z())) { received.add(c); plan.accepted(c.x(), c.z()); }
			}
			plan.commitBatch();
			if (visits == 0) assertTrue(plan.needs(deferred.x(), deferred.z()));
			assertTrue(++visits < plan.total());
		}
		assertTrue(plan.complete()); assertEquals(new HashSet<>(plan.chunks()), received);
	}
}
