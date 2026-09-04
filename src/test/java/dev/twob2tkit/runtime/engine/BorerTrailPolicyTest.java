package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：回家箭头沿巷道走，不要画穿墙斜线去下界门。
 * 来源：2026-08-21 382879 -55 311290，「西北483370格 剩1路点」指着深板岩墙。
 */
final class BorerTrailPolicyTest {
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
