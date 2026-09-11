package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class SceneryCoverageTest {
	@Test void everyBlockInsideCircleIncludingNegativeCoordinatesAndEdgesBelongsToAPlannedChunk() {
		for (double x : new double[]{-32.1, -16, -.25, 0, 15.9, 1234.5}) for (double z : new double[]{-15.9, .1, 16}) {
			var plan = new SceneryCoverage(x, z, 65);
			Set<SceneryCoverage.Chunk> chunks = new HashSet<>(plan.chunks());
			assertEquals(plan.total(), chunks.size());
			for (int bx = (int)Math.floor(x - 65); bx <= Math.ceil(x + 65); bx++)
				for (int bz = (int)Math.floor(z - 65); bz <= Math.ceil(z + 65); bz++)
					if (Math.hypot(bx - x, bz - z) <= 65) assertTrue(chunks.contains(new SceneryCoverage.Chunk(Math.floorDiv(bx, 16), Math.floorDiv(bz, 16))));
		}
	}
	@Test void spiralsOutwardWithoutOmittingAnyIntersectingEdgeChunk() {
		var plan = new SceneryCoverage(-7.5, 3.25, 256);
		int ring = -1;
		for (var chunk : plan.chunks()) {
			int nextRing = Math.max(Math.abs(chunk.x() + 1), Math.abs(chunk.z()));
			assertTrue(nextRing >= ring); ring = nextRing;
		}
		assertEquals(new SceneryCoverage.Chunk(-1, 0), plan.next());
		for (int x = -18; x <= 17; x++) for (int z = -17; z <= 18; z++) {
			double nx = Math.max(x * 16., Math.min(-7.5, x * 16. + 16));
			double nz = Math.max(z * 16., Math.min(3.25, z * 16. + 16));
			assertEquals(Math.hypot(nx + 7.5, nz - 3.25) <= 256, plan.chunks().contains(new SceneryCoverage.Chunk(x, z)));
		}
	}
	@Test void coordinatesAloneCannotMarkCoverageAndUnfinishedBatchesDoNotSurviveRestart() {
		var plan = new SceneryCoverage(0, 0, 64); var target = plan.next();
		assertEquals(0, plan.confirmed()); assertFalse(plan.complete());
		plan.accepted(target.x(), target.z()); assertFalse(plan.needs(target.x(), target.z()));
		assertEquals(0, plan.checkpoint().length);
		var resumed = new SceneryCoverage(0, 0, 64); resumed.restore(plan.checkpoint());
		assertEquals(target, resumed.next());
		plan.commitBatch(); resumed.restore(plan.checkpoint());
		assertEquals(1, resumed.confirmed()); assertNotEquals(target, resumed.next());
	}
	@Test void largeLoadedWindowsReduceWaypointsButNeverPretendMissingChunksWereLoaded() {
		var plan = new SceneryCoverage(123.25, -37.4, 512);
		var missing = new SceneryCoverage.Chunk(10, 4);
		int visits = 0;
		while (true) {
			var target = plan.next(); if (target == null || target.equals(missing)) break;
			for (int x = target.x() - 4; x <= target.x() + 4; x++) for (int z = target.z() - 4; z <= target.z() + 4; z++)
				if (!missing.equals(new SceneryCoverage.Chunk(x, z))) plan.accepted(x, z);
			plan.commitBatch(); assertTrue(++visits < plan.total());
		}
		assertEquals(missing, plan.next()); assertFalse(plan.complete());
		plan.accepted(missing.x(), missing.z()); plan.commitBatch();
		while (plan.next() != null) { var target = plan.next(); plan.accepted(target.x(), target.z()); plan.commitBatch(); }
		assertTrue(plan.complete()); assertEquals(plan.total(), plan.confirmed());
	}
	@Test void invalidRadiusWorldLimitAndOutOfBoundsCheckpointAreRejected() {
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(0, 0, 0));
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(0, 0, 4097));
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(Double.NaN, 0, 256));
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(29_999_899, 0, 16));
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(0, 0, 16).restore(new long[]{-1L}));
		assertTrue(new SceneryCoverage(0, 0, 4096).total() < 270_000);
	}
}
