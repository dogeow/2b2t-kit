package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class SceneryCoverageTest {
	@Test void borderClipsOnlyTheOutsideAndKeepsConfirmedBitsWhenTheBorderExpands() {
		for (int radius : new int[]{64,20000}) {
			var plan=new SceneryCoverage(0,0,radius);
			var outside=new SceneryCoverage.Chunk(1,0);
			var inside=new SceneryCoverage.Chunk(0,0);
			plan.reuse(outside);
			int original=plan.total();
			plan.clipTo(SceneryCoverage.ChunkBounds.inside(0,16,0,16));
			assertEquals(1,plan.total());
			assertEquals(original-1,plan.skippedOutside());
			assertEquals(0,plan.confirmed());
			assertEquals(inside,plan.nextNearest(outside,24,8));
			assertEquals(java.util.List.of(inside),plan.missingInRegion(0,0));
			plan.reuse(inside);
			assertTrue(plan.complete());
			var restored=new SceneryCoverage(0,0,radius);
			restored.restore(plan.checkpoint());
			restored.clipTo(SceneryCoverage.ChunkBounds.inside(0,32,0,16));
			assertEquals(2,restored.confirmed());
			assertTrue(restored.complete());
		}
	}

	@Test void returnUsesAnInsideCoordinateWhenTheChosenCenterIsOutside() {
		assertEquals(97,SceneryExplorer.returnCoordinate(110,-100,100));
		assertEquals(20,SceneryExplorer.returnCoordinate(20,-100,100));
	}
	@Test void compactIndexMatchesLegacyCircleAtNegativeAndFractionalCentres() {
		for (double x : new double[]{-17,-16,3.25}) for (double z : new double[]{-3.25,0,16}) {
			var legacy=new SceneryCoverage(x,z,64);
			var rows=new SceneryChunkRows(x,z,64);
			assertEquals(new HashSet<>(legacy.chunks()),new HashSet<>(rows));
			for (int i=0;i<rows.size();i++) assertEquals(i,rows.indexOf(rows.get(i).x(),rows.get(i).z()));
		}
	}

	@Test void tensOfThousandsOfBlocksKeepNearestBatchAndConfirmedCoverage(@org.junit.jupiter.api.io.TempDir java.nio.file.Path dir) throws Exception {
		var plan=new SceneryCoverage(-3.25,19.5,20000);
		assertTrue(plan.total()>4_900_000);
		var corner=plan.nextNearest(null,19985,19.5);
		plan.reuse(corner);
		var nearby=plan.nextNearest(null,19985,19.5);
		assertNotEquals(corner,nearby);
		assertTrue(nearby.x()>=corner.x()-1);
		var region=plan.missingInRegion(Math.floorDiv(nearby.x(),32),Math.floorDiv(nearby.z(),32));
		assertTrue(region.size()<=1024);
		assertTrue(region.contains(nearby));
		var file=dir.resolve("progress.json");
		SceneryProgress.write(file,"world","cache",plan);
		var resumed=SceneryProgress.read(file,"world","cache");
		assertEquals(1,resumed.confirmed());
		assertEquals(nearby,resumed.nextNearest(null,19985,19.5));
		assertFalse(resumed.expanded(30000).needs(corner.x(),corner.z()));
	}

	@Test void expandingKeepsSameCentreAndOnlyVerifiedCoverage() {
		var original=new SceneryCoverage(-7.5,3.25,64);
		var confirmed=original.next();
		original.reuse(confirmed);
		original.reuse(confirmed);
		var pending=original.next();
		original.accepted(pending.x(),pending.z());
		var expanded=original.expanded(128);
		assertEquals(original.centreX,expanded.centreX);
		assertEquals(original.centreZ,expanded.centreZ);
		assertTrue(expanded.total()>original.total());
		assertEquals(1,expanded.confirmed());
		assertFalse(expanded.needs(confirmed.x(),confirmed.z()));
		assertTrue(expanded.needs(pending.x(),pending.z()));
		assertThrows(IllegalArgumentException.class,()->original.expanded(64));
	}

	@Test void bobbyHeaderCountsOnlyIndexedChunksAndHandlesMissingData(@org.junit.jupiter.api.io.TempDir java.nio.file.Path tmp) throws Exception {
		var header=java.nio.ByteBuffer.allocate(4096);
		header.putInt(0,2<<8|1);
		header.putInt(4,4<<8);
		header.putInt(8,1<<8|2);
		var file=tmp.resolve("r.-1.0.mca");
		java.nio.file.Files.write(file,header.array());
		var indexed=SceneryBobby.readHeader(file);
		assertEquals(1,indexed.cardinality());
		assertTrue(indexed.get(0));
		assertTrue(SceneryBobby.readHeader(tmp.resolve("missing")).isEmpty());
	}
	@Test void maxRadiusKeepsTheCircleAndEdgeChunkInsideTheBorder() {
		assertEquals(983, SceneryCoverage.maxRadiusInside(0, 0, -1000, 1000, -5000, 5000));
		assertEquals(32768, SceneryCoverage.maxRadiusInside(0, 0, -3e7, 3e7, -3e7, 3e7));
		assertEquals(0, SceneryCoverage.maxRadiusInside(995, 0, -1000, 1000, -1000, 1000));
	}
	@Test void resumeChoosesTheNearbyGapAndKeepsItUntilAccepted() {
		var plan = new SceneryCoverage(0, 0, 256);
		var near = new SceneryCoverage.Chunk(12, 0);
		assertEquals(near, plan.nextNearest(null, 200, 8));
		assertEquals(near, plan.nextNearest(near, 8, 8));
		plan.accepted(12, 0);
		assertNotEquals(near, plan.nextNearest(near, 200, 8));
		plan.commitBatch();
		assertEquals(new SceneryCoverage.Chunk(0, 0), plan.next());
	}
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
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(0, 0, 32769));
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(Double.NaN, 0, 256));
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(30_000_000, 0, 16));
		assertThrows(IllegalArgumentException.class, () -> new SceneryCoverage(0, 0, 16).restore(new long[]{-1L}));
		assertTrue(new SceneryCoverage(0, 0, 4096).total() < 270_000);
	}
}
