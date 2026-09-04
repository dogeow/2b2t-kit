package dev.twob2tkit.runtime.engine;

import net.minecraft.core.Direction;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：1×2 两边都是石头时不要左右横移；矿在附近更高处不要走进去再跑出来。
 */
final class BorerCenterPolicyTest {
	@Test
	void scrapingLeftWallWhenFacingEastStrafesSouth() {
		double side = BorerCenterPolicy.sideOffset(382799.700, 311146.284, 382799, 311146, 0, 1);
		assertEquals(0.216, side, 0.0001);
		assertTrue(BorerCenterPolicy.overlapsSideWall(side));
		assertTrue(BorerCenterPolicy.shouldPressRight(side));
		assertFalse(BorerCenterPolicy.shouldPressLeft(side));
	}

	@Test
	void screenshotPitEdgeFacingWestNudgesNorthBeforeDescending() {
		double side = BorerCenterPolicy.sideOffset(
			382821.300, 311350.889, 382821, 311350, 0, -1);
		assertEquals(0.389, side, 0.0001);
		assertTrue(BorerCenterPolicy.overlapsSideWall(side));
		assertTrue(BorerCenterPolicy.shouldPressRight(side));
		assertFalse(BorerCenterPolicy.shouldPressLeft(side));
	}

	@Test
	void threeWideEdgeStrafesToBandCenter() {
		double side = BorerCenterPolicy.sideOffsetTo(382782.471, 311345.388, 382782.5, 311346.5, 0, 1);
		assertEquals(1.112, side, 0.001);
		assertTrue(BorerCenterPolicy.shouldStrafeToBandCenter(side));
		assertTrue(BorerCenterPolicy.shouldPressRightToward(side));
		assertFalse(BorerCenterPolicy.shouldPressLeftToward(side));
		assertFalse(BorerCenterPolicy.shouldStrafeToBandCenter(0.05));
		assertFalse(BorerCenterPolicy.shouldPressRightToward(0.05));
	}

	@Test
	void oneByOneShaftOffsetMustCenterBeforeDrop() {
		assertTrue(BorerCenterPolicy.needsShaftCenter(0.20, 0.00));
		assertTrue(BorerCenterPolicy.needsShaftCenter(382825.700 - 382825.5, 311310.502 - 311310.5));
		assertFalse(BorerCenterPolicy.needsShaftCenter(0.04, 0.02));
		assertTrue(BorerCenterPolicy.pressTowardNegative(-0.20));
		assertFalse(BorerCenterPolicy.pressTowardPositive(-0.20));
	}

	@Test
	void slightOffsetInOneByTwoDoesNotStrafe() {
		assertFalse(BorerCenterPolicy.overlapsSideWall(0.05));
		assertFalse(BorerCenterPolicy.overlapsSideWall(0.08));
		assertFalse(BorerCenterPolicy.overlapsSideWall(-0.12));
		assertFalse(BorerCenterPolicy.shouldPressLeft(0.08));
		assertFalse(BorerCenterPolicy.shouldPressRight(-0.08));
	}

	@Test
	void oneWideCorridorIgnoresSideWalls() {
		assertTrue(BorerCenterPolicy.inCorridorColumn(0, 1));
		assertFalse(BorerCenterPolicy.inCorridorColumn(1, 1));
	}

	@Test
	void threeWideCorridorAllowsOneBlockEachSide() {
		assertTrue(BorerCenterPolicy.inCorridorColumn(1, 3));
		assertFalse(BorerCenterPolicy.inCorridorColumn(2, 3));
	}

	@Test
	void walkingPastOreDoesNotCountAsApproaching() {
		assertFalse(BorerCenterPolicy.headingReducesDistance(1, 0, -2, 0));
		assertTrue(BorerCenterPolicy.headingReducesDistance(-1, 0, -2, 0));
		assertFalse(BorerCenterPolicy.headingReducesDistance(1, 0, 0, 0));
	}

	@Test
	void diagonalApproachKeepsCurrentHeading() {
		assertEquals(Direction.WEST, BorerCenterPolicy.stableAxisHeading(-3, -2, Direction.NORTH));
		assertEquals(Direction.WEST, BorerCenterPolicy.stableAxisHeading(-3, -3, Direction.WEST));
		assertEquals(Direction.NORTH, BorerCenterPolicy.stableAxisHeading(-3, -3, Direction.NORTH));
	}

	@Test
	void nearbyVerticalOreStaysAndClimbsInsteadOfExitingTunnel() {
		assertTrue(BorerCenterPolicy.stayAndClimb(2, true));
		assertTrue(BorerCenterPolicy.stayAndClimb(0, true));
		assertFalse(BorerCenterPolicy.stayAndClimb(2, false));
		assertFalse(BorerCenterPolicy.stayAndClimb(8, true));
	}

	@Test
	void selectedFrontBlockIsNotASideWall() {
		assertFalse(BorerCenterPolicy.isOffCorridorWall(1, 0, 1));
		assertFalse(BorerCenterPolicy.isOffCorridorWall(2, 0, 1));
		assertFalse(BorerCenterPolicy.isOffCorridorWall(0, 0, 1));
	}

	@Test
	void currentCellSideWallIsSkipped() {
		assertTrue(BorerCenterPolicy.isOffCorridorWall(0, 1, 1));
		assertTrue(BorerCenterPolicy.isOffCorridorWall(1, 1, 1));
	}

	@Test
	void twistedOreHeadingMustNotDropSelectedFront() {
		// 朝北选出 382809 100 311178：along=1, lateral=0
		assertFalse(BorerCenterPolicy.isOffCorridorWall(1, 0, 1));
		// 同一块被拧成朝西后再算：along=0, lateral=1。引擎必须继续用选出时的朝向。
		assertTrue(BorerCenterPolicy.isOffCorridorWall(0, 1, 1));
	}

	@Test
	void savedBodyColumnAndHeadingKeepTheSelectedBlockInTheCorridor() {
		// 选块时身体在 382833,311127，朝东选中正前方 382834,311127。
		assertFalse(BorerCenterPolicy.isOffCorridorWall(
			382833, 311127, 382834, 311127,
			1, 0, 0, 1, 1));
		// 若错误混用后来朝北的方向和跨格后的列，同一方块会被误判成侧墙。
		assertTrue(BorerCenterPolicy.isOffCorridorWall(
			382833, 311126, 382834, 311127,
			0, -1, 1, 0, 1));
	}
}
