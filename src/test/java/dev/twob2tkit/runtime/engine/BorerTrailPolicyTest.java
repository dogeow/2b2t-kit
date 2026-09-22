package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.List;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：回家箭头沿巷道走，不要画穿墙斜线去下界门。
 * 来源：2026-08-21 382879 -55 311290，「西北483370格 剩1路点」指着深板岩墙。
 */
final class BorerTrailPolicyTest {
	@Test
	void returnLeavesTheCurrentWaypointEvenWhenThePreviousPointIsFartherFromHome() {
		var points = List.of(new BlockPos(761071, -41, 797950),
			new BlockPos(761067, -59, 797949), new BlockPos(761069, -59, 797950),
			new BlockPos(761071, -59, 797951));
		assertTrue(points.get(2).distSqr(points.getFirst()) > points.get(3).distSqr(points.getFirst()));
		int index = BorerTrailPolicy.advanceReturnIndex(points, 3,
			new Vec3(761071.7, -59, 797951.4));
		assertEquals(2, index);
		assertEquals(1, BorerTrailPolicy.advanceReturnIndex(points, index,
			Vec3.atBottomCenterOf(points.get(2))));
	}

	@Test
	void reverseRouteCanTraverseAHairpinWithoutOscillatingOrSkippingUnreachedPoints() {
		var points = List.of(new BlockPos(0, 0, 0), new BlockPos(0, 0, 3),
			new BlockPos(3, 0, 3), new BlockPos(3, 0, 0));
		int index = 3;
		for (int i = 3; i >= 0; i--) {
			index = BorerTrailPolicy.advanceReturnIndex(points, index, Vec3.atBottomCenterOf(points.get(i)));
			assertEquals(Math.max(0, i - 1), index);
			assertEquals(index, BorerTrailPolicy.advanceReturnIndex(points, index,
				Vec3.atBottomCenterOf(points.get(i))));
		}
	}

	@Test
	void returnDoesNotSkipAWaypointOnAnotherFloor() {
		var points = List.of(new BlockPos(0, 0, 0), new BlockPos(0, 3, 0));
		assertEquals(1, BorerTrailPolicy.advanceReturnIndex(points, 1, new Vec3(.5, 0, .5)));
	}
	@Test
	void adjacentTunnelStepsAreCorridor() {
		assertTrue(BorerTrailPolicy.isCorridorSegment(1));
		assertTrue(BorerTrailPolicy.isCorridorSegment(3));
		assertTrue(BorerTrailPolicy.isCorridorSegment(8));
		assertTrue(BorerTrailPolicy.isCorridorSegment(12));
	}

	@Test
	void farDiagonalIsNotAWalkableRoute() {
		assertFalse(BorerTrailPolicy.isCorridorSegment(0));
		assertFalse(BorerTrailPolicy.isCorridorSegment(13));
		assertFalse(BorerTrailPolicy.isCorridorSegment(483370));
	}

	@Test
	void portalIsHomeOnlyInTheNether() {
		assertTrue(BorerTrailPolicy.includePortalAsHome(true));
		assertFalse(BorerTrailPolicy.includePortalAsHome(false));
	}

	@Test
	void restartingInTheSameTunnelKeepsTheTrail() {
		assertTrue(BorerTrailPolicy.resumeExistingTrail(0.0));
		assertTrue(BorerTrailPolicy.resumeExistingTrail(16.0));
		assertTrue(BorerTrailPolicy.resumeExistingTrail(32.0));
		assertFalse(BorerTrailPolicy.resumeExistingTrail(32.1));
		assertFalse(BorerTrailPolicy.resumeExistingTrail(400.0));
	}

	@Test
	void resticksWhenMoreThanTwelveBlocksFromStickyPoint() {
		assertFalse(BorerTrailPolicy.shouldRestick(0.0));
		assertFalse(BorerTrailPolicy.shouldRestick(12.0));
		assertTrue(BorerTrailPolicy.shouldRestick(12.1));
		assertTrue(BorerTrailPolicy.shouldRestick(40.0));
	}

	@Test
	void doesNotDrawALowerTunnelThroughThisCorridor() {
		assertTrue(BorerTrailPolicy.drawSegmentNearPlayer(8, 1));
		assertTrue(BorerTrailPolicy.drawSegmentNearPlayer(24, 3));
		assertTrue(BorerTrailPolicy.drawSegmentNearPlayer(40, 8));
		assertFalse(BorerTrailPolicy.drawSegmentNearPlayer(8, 19));
		assertFalse(BorerTrailPolicy.drawSegmentNearPlayer(49, 0));
		assertFalse(BorerTrailPolicy.stopDrawingBeyond(48));
		assertTrue(BorerTrailPolicy.stopDrawingBeyond(49));
	}

	@Test
	void drawingKeepsRecordedDetours() {
		assertFalse(BorerTrailPolicy.skipDetourWhenDrawing());
	}

	@Test
	void arrowsMustGetCloserToHome() {
		assertTrue(BorerTrailPolicy.towardHome(100.0, 400.0));
		assertFalse(BorerTrailPolicy.towardHome(400.0, 100.0));
		assertFalse(BorerTrailPolicy.towardHome(100.0, 100.0));
	}
}
