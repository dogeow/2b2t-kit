package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住区域挖：1×1 竖井逐格往下，到底换下一格。
 */
final class BorerAreaPolicyTest {
	@Test
	void fortyByFortyIsInclusiveSpan() {
		assertEquals(40, BorerAreaPolicy.spanInclusive(0, 39));
		assertEquals(40, BorerAreaPolicy.spanInclusive(100, 61));
		assertFalse(BorerAreaPolicy.tooLarge(0, 0, 39, 39));
		assertTrue(BorerAreaPolicy.tooLarge(0, 0, 64, 0));
	}

	@Test
	void sizeFromFeetMatchesShaftOffsets() {
		assertEquals(-19, BorerAreaPolicy.startOffset(40));
		assertEquals(20, BorerAreaPolicy.endOffset(40));
		assertEquals(40, BorerAreaPolicy.endOffset(40) - BorerAreaPolicy.startOffset(40) + 1);
	}

	@Test
	void farPlayerWalksIntoTheRectangle() {
		assertTrue(BorerAreaPolicy.shouldApproach(382800, 311300, 382820, 311320, 382859, 311359));
		assertFalse(BorerAreaPolicy.shouldApproach(382830, 311330, 382820, 311320, 382859, 311359));
		assertEquals(382820, BorerAreaPolicy.clampToRange(382800, 382820, 382859));
		assertTrue(BorerAreaPolicy.keepThinkingDuringHazard(true));
		assertFalse(BorerAreaPolicy.keepThinkingDuringHazard(false));
	}

	@Test
	void shaftColumnsScanXZGrid() {
		BlockPos first = BorerAreaPolicy.firstShaftColumn(10, 20, 10, 20, 12, 21);
		assertEquals(10, first.getX());
		assertEquals(20, first.getZ());
		BlockPos next = BorerAreaPolicy.nextShaftColumn(10, 20, 10, 20, 12, 21);
		assertEquals(11, next.getX());
		assertEquals(20, next.getZ());
		BlockPos wrap = BorerAreaPolicy.nextShaftColumn(12, 20, 10, 20, 12, 21);
		assertEquals(10, wrap.getX());
		assertEquals(21, wrap.getZ());
		assertNull(BorerAreaPolicy.nextShaftColumn(12, 21, 10, 20, 12, 21));
	}

	@Test
	void shaftStartsAtNearestColumnNotMinCorner() {
		BlockPos near = BorerAreaPolicy.nearestShaftColumn(12, 21, 10, 20, 12, 21);
		assertEquals(12, near.getX());
		assertEquals(21, near.getZ());
		BlockPos clamped = BorerAreaPolicy.nearestShaftColumn(0, 0, 10, 20, 12, 21);
		assertEquals(10, clamped.getX());
		assertEquals(20, clamped.getZ());
		assertTrue(BorerAreaPolicy.closerShaft(12, 21, 12, 21, 10, 20));
		assertFalse(BorerAreaPolicy.closerShaft(12, 21, 10, 20, 12, 21));
	}

	@Test
	void shaftMinesTopDownAndFinishesAtBottom() {
		assertTrue(BorerAreaPolicy.shaftMineRank(70) < BorerAreaPolicy.shaftMineRank(50));
		assertEquals(48, BorerAreaPolicy.shaftBottomY(true, 48));
		assertTrue(BorerAreaPolicy.shaftColumnDone(true, 48, 48, false));
		assertFalse(BorerAreaPolicy.shaftColumnDone(true, 48, 48, true));
		assertFalse(BorerAreaPolicy.shaftColumnDone(true, 56, 54, false));
		assertTrue(BorerAreaPolicy.surveyRemainingShaftsWithoutColumnLock());
	}

	@Test
	void digOrderDefaultsToVerticalGrid() {
		assertEquals(BorerAreaPolicy.ORDER_VERTICAL, BorerAreaPolicy.normalizeOrder(null));
		assertEquals(BorerAreaPolicy.ORDER_VERTICAL, BorerAreaPolicy.normalizeOrder(""));
		assertEquals(BorerAreaPolicy.ORDER_NEAREST, BorerAreaPolicy.normalizeOrder("nearest"));
		assertEquals("竖井网格", BorerAreaPolicy.orderLabel("vertical"));
		assertEquals("就近飞", BorerAreaPolicy.orderLabel("nearest"));
		assertFalse(BorerAreaPolicy.useNearestOrder("vertical"));
		assertTrue(BorerAreaPolicy.useNearestOrder("nearest"));
	}

	@Test
	void verticalGridPicksNextColumnAfterCurrent() {
		// from (10,20): prefer (11,20) over (10,21) and over earlier (10,20) skipped
		assertTrue(BorerAreaPolicy.preferGridCandidate(
			11, 20, 10, 21, 10, 20, 10, 20, 12));
		assertFalse(BorerAreaPolicy.preferGridCandidate(
			10, 21, 11, 20, 10, 20, 10, 20, 12));
		// nothing after: wrap to earlier remaining
		assertTrue(BorerAreaPolicy.preferGridCandidate(
			10, 20, 11, 20, 12, 21, 10, 20, 12));
	}

	@Test
	void nextShaftPrefersNearbyNotFarCorner() {
		// vertical: adjacent to from beats far min-corner
		assertTrue(BorerAreaPolicy.preferNextShaft(
			false, 20, 20, 21, 20, 0, 0, 20, 20));
		assertFalse(BorerAreaPolicy.preferNextShaft(
			false, 20, 20, 0, 0, 21, 20, 20, 20));
		// nearest order: closer to player wins
		assertTrue(BorerAreaPolicy.preferNextShaft(
			true, 20, 20, 21, 20, 0, 50, 20, 20));
		assertFalse(BorerAreaPolicy.mineFlightObstruction(true, true, 8.0));
		assertTrue(BorerAreaPolicy.mineFlightObstruction(true, true, 1.0));
		assertTrue(BorerAreaPolicy.hoverWhileMining(true));
		assertFalse(BorerAreaPolicy.hoverWhileMining(false));
	}

	@Test
	void stripFollowsPlayerHeadingNotLongerWorldSpan() {
		assertEquals(Direction.NORTH, BorerAreaPolicy.stripAxis(0, 0, 49, 10, Direction.NORTH));
		assertEquals(Direction.WEST, BorerAreaPolicy.stripAxis(0, 0, 10, 49, Direction.WEST));
		assertEquals(Direction.WEST, BorerAreaPolicy.stripAxis(0, 0, 40, 40, Direction.WEST));
	}

	@Test
	void mineTargetMustStayInsideMarkedXZ() {
		assertTrue(BorerAreaPolicy.containsXZ(5, 5, 0, 0, 10, 10));
		assertFalse(BorerAreaPolicy.containsXZ(-1, 5, 0, 0, 10, 10));
	}

	@Test
	void threeWideWalksTheBandMidline() {
		assertEquals(311346, BorerAreaPolicy.bandCenterBlock(311345, 311306, 311354, 3));
		assertEquals(311346.5, BorerAreaPolicy.bandCenterZ(Direction.EAST, 382782, 311345, 311306, 311354, 3), 1e-9);
		assertEquals(382782.5, BorerAreaPolicy.bandCenterX(Direction.EAST, 382782, 311345, 311306, 311354, 3), 1e-9);
		assertEquals(1.0, BorerAreaPolicy.bandCenterZ(Direction.EAST, 0, 0, 0, 10, 2), 1e-9);
		assertEquals(4.5, BorerAreaPolicy.bandCenterZ(Direction.EAST, 0, 4, 0, 10, 1), 1e-9);
		assertTrue(BorerAreaPolicy.walkCenteredStrip(3));
		assertTrue(BorerAreaPolicy.walkCenteredStrip(2));
		assertFalse(BorerAreaPolicy.walkCenteredStrip(1));
	}

	@Test
	void twoByTwoMinesTwoRowsThenSkips() {
		assertEquals(0, BorerAreaPolicy.bandStart(0, 0, 2));
		assertEquals(0, BorerAreaPolicy.bandStart(1, 0, 2));
		assertEquals(2, BorerAreaPolicy.bandStart(2, 0, 2));
		assertEquals(1, BorerAreaPolicy.bandEnd(0, 0, 10, 2));
		assertEquals(2, BorerAreaPolicy.nextBand(0, 0, 10, 2));
		assertEquals(2, BorerAreaPolicy.nextBand(1, 0, 10, 2));
		assertEquals(10, BorerAreaPolicy.nextBand(10, 0, 10, 2));
		assertEquals(1, BorerAreaPolicy.nextBand(0, 0, 10, 1));
		assertTrue(BorerAreaPolicy.shouldChangeBand(false, false));
		assertFalse(BorerAreaPolicy.shouldChangeBand(true, false));
		assertFalse(BorerAreaPolicy.shouldChangeBand(false, true));
	}

	@Test
	void mineThisColumnDownBeforeOtherFloorTiles() {
		int hereDown = BorerAreaPolicy.mineOrder(0, 0, -1);
		int farFloor = BorerAreaPolicy.mineOrder(20, 3, 0);
		assertTrue(hereDown < farFloor);
		int above = BorerAreaPolicy.mineOrder(0, 0, 3);
		int head = BorerAreaPolicy.mineOrder(0, 0, 1);
		int body = BorerAreaPolicy.mineOrder(0, 0, 0);
		assertTrue(above < head);
		assertTrue(head < body);
		assertTrue(body < hereDown);
	}

	@Test
	void leftoverCeilingAscendsInsteadOfDropping() {
		assertTrue(BorerAreaPolicy.shouldAscendToTop(55, 70, true));
		assertFalse(BorerAreaPolicy.shouldAscendToTop(70, 70, true));
		assertFalse(BorerAreaPolicy.shouldAscendToTop(55, 70, false));
		assertTrue(BorerAreaPolicy.holdThisLevel(false, true));
		assertTrue(BorerAreaPolicy.holdThisLevel(true, false));
		assertFalse(BorerAreaPolicy.holdThisLevel(false, false));
		assertFalse(BorerAreaPolicy.fallInStrip(true, true, false, true, false));
	}

	@Test
	void currentStripWalksThenFallsInsteadOfClearingTheWholeLayer() {
		assertTrue(BorerAreaPolicy.walkAlongStrip(true));
		assertFalse(BorerAreaPolicy.fallInStrip(true, true, false, true, false));
		assertTrue(BorerAreaPolicy.fallInStrip(false, true, false, true, false));
		assertFalse(BorerAreaPolicy.fallInStrip(false, false, false, true, false));
	}

	@Test
	void atBottomOrOnGroundMustNotKeepFalling() {
		assertTrue(BorerAreaPolicy.atBottom(true, 55, 55));
		assertFalse(BorerAreaPolicy.fallInStrip(false, true, true, true, false));
		assertFalse(BorerAreaPolicy.fallInStrip(false, true, false, false, false));
		assertFalse(BorerAreaPolicy.fallInStrip(false, true, false, true, true));
		assertTrue(BorerAreaPolicy.walkIntoStripDrop(false, true, false, true, true));
		assertFalse(BorerAreaPolicy.walkIntoStripDrop(true, true, false, true, true));
		assertFalse(BorerAreaPolicy.walkIntoStripDrop(false, true, false, true, false));
		assertTrue(BorerAreaPolicy.abortFallWait(true));
		assertFalse(BorerAreaPolicy.abortFallWait(false));
	}

	@Test
	void lookedBelowInTheAreaIsMinedInsteadOfStaringIntoTheHole() {
		assertTrue(BorerAreaPolicy.mineLookedBelow(false, true, false, 42, 44, -60, true));
		assertFalse(BorerAreaPolicy.mineLookedBelow(true, true, false, 42, 44, -60, true));
		assertFalse(BorerAreaPolicy.mineLookedBelow(false, true, false, 45, 44, -60, true));
		assertFalse(BorerAreaPolicy.mineLookedBelow(false, true, false, -61, 44, -60, true));
		assertFalse(BorerAreaPolicy.mineLookedBelow(false, true, true, 42, 44, -60, true));
		assertFalse(BorerAreaPolicy.mineLookedBelow(false, false, false, 42, 44, -60, true));
	}

	@Test
	void sliceHeightTwoIsFeetAndHead() {
		assertEquals(2, BorerAreaPolicy.clampSliceHeight(2));
		assertEquals(2, BorerAreaPolicy.clampSliceHeight(0));
		assertEquals(5, BorerAreaPolicy.clampSliceHeight(9));
		assertEquals(65, BorerAreaPolicy.sliceMinY(65, 55, 2, true));
		assertEquals(66, BorerAreaPolicy.sliceMaxY(65, 67, 2, true));
		assertTrue(BorerAreaPolicy.inSlice(65, 65, 2));
		assertTrue(BorerAreaPolicy.inSlice(66, 65, 2));
		assertFalse(BorerAreaPolicy.inSlice(67, 65, 2));
		assertFalse(BorerAreaPolicy.inSlice(64, 65, 2));
	}

	@Test
	void bandClearMinesFloorBeforeFalling() {
		assertTrue(BorerAreaPolicy.shouldMineDropFloor(false, true, true));
		assertFalse(BorerAreaPolicy.shouldMineDropFloor(true, true, true));
		assertFalse(BorerAreaPolicy.shouldMineDropFloor(false, true, false));
	}

	@Test
	void headingTurnsAroundAtStripEnds() {
		assertEquals(Direction.EAST,
			BorerAreaPolicy.headingAlongStrip(Direction.EAST, Direction.WEST, 0, 0, 39));
		assertEquals(Direction.WEST,
			BorerAreaPolicy.headingAlongStrip(Direction.EAST, Direction.EAST, 39, 0, 39));
		assertEquals(Direction.WEST,
			BorerAreaPolicy.headingAlongStrip(Direction.EAST, Direction.WEST, 10, 0, 39));
	}

	@Test
	void sameYKeepsGoingDownDifferentYStopsAtLower() {
		assertFalse(BorerAreaPolicy.boundedDown(67, 67));
		assertTrue(BorerAreaPolicy.boundedDown(67, 50));
		assertTrue(BorerAreaPolicy.finishedBounded(true, 50, 50, true));
		assertFalse(BorerAreaPolicy.finishedBounded(false, 10, 50, true));
	}

	@Test
	void standingOnBottomMustNotMineTheBlockBelow() {
		boolean bounded = BorerAreaPolicy.boundedDown(69, 55);
		int bottom = BorerAreaPolicy.bottomY(69, 55);
		assertTrue(bounded);
		assertEquals(55, bottom);
		assertTrue(BorerAreaPolicy.atBottom(true, 55, 55));
		assertTrue(BorerAreaPolicy.belowBottom(true, 54, 55));
		assertFalse(BorerAreaPolicy.belowBottom(true, 55, 55));
		assertFalse(BorerAreaPolicy.shouldMineDropFloor(false, false, false));
		assertFalse(BorerAreaPolicy.belowBottom(false, 48, 55));
	}

	@Test
	void sizeLabelNamesTheRectangle() {
		assertEquals("40×40  Y 67 往下", BorerAreaPolicy.sizeLabel(0, 67, 0, 39, 67, 39));
		assertEquals("40×40  Y 67→50", BorerAreaPolicy.sizeLabel(0, 67, 0, 39, 50, 39));
	}

	@Test
	void areaMiningUsesFreeAim() {
		assertTrue(BorerAreaPolicy.freeAimMining());
	}

	@Test
	void flyToShaftMinesBlockerInsteadOfStalling() {
		// 两参数重载未知距离 → 当作远处，不得挖路
		assertFalse(BorerAreaPolicy.mineFlightObstruction(true, true));
		assertFalse(BorerAreaPolicy.mineFlightObstruction(false, true));
		assertFalse(BorerAreaPolicy.mineFlightObstruction(true, false));
		assertTrue(BorerAreaPolicy.mineFlightObstruction(true, true, 1.0));
		assertFalse(BorerAreaPolicy.allowAimMissRetarget(false));
		assertTrue(BorerAreaPolicy.allowAimMissRetarget(true));
		assertFalse(BorerAreaPolicy.walkAfterAimMissInArea());
		assertFalse(BorerAreaPolicy.areaShaftUsesBandNudge());
	}

	@Test
	void flyToShaftJumpsOverWhenCeilingIsClear() {
		assertTrue(BorerAreaPolicy.flyJump(true, true, false));
		assertFalse(BorerAreaPolicy.flyJump(true, true, true));
		assertTrue(BorerAreaPolicy.flyJump(false, true, false));
		assertFalse(BorerAreaPolicy.flyJump(false, false, false));
		assertFalse(BorerAreaPolicy.flyJump(true, false, true));
		assertTrue(BorerAreaPolicy.flyOverInsteadOfMine(true, true, false));
		assertFalse(BorerAreaPolicy.flyOverInsteadOfMine(true, true, true));
		assertFalse(BorerAreaPolicy.flyOverInsteadOfMine(false, true, false));
	}

	@Test
	void flyToShaftLocksLookAtDestNotCrosshair() {
		assertTrue(BorerAreaPolicy.lockLookWhileFlyingToShaft(true));
		assertFalse(BorerAreaPolicy.lockLookWhileFlyingToShaft(false));
	}

	@Test
	void surfaceAboveMarkedTopMinesDownInsteadOfSneak() {
		assertTrue(BorerAreaPolicy.aboveMarkedTop(80, 67));
		assertFalse(BorerAreaPolicy.aboveMarkedTop(67, 67));
		assertFalse(BorerAreaPolicy.aboveMarkedTop(68, 67));
		assertTrue(BorerAreaPolicy.atShaftTop(67, 67));
		assertTrue(BorerAreaPolicy.atShaftTop(68, 67));
		assertFalse(BorerAreaPolicy.atShaftTop(80, 67));
		assertTrue(BorerAreaPolicy.mineDownToShaftTop(true, 80, 67));
		assertFalse(BorerAreaPolicy.mineDownToShaftTop(false, 80, 67));
		assertTrue(BorerAreaPolicy.destBelow(67 - 80));
		assertFalse(BorerAreaPolicy.destBelow(67 - 67));
		assertFalse(BorerAreaPolicy.destBelow(67 - 67.87));
		assertTrue(BorerAreaPolicy.mineAdjacentShaftInsteadOfFly(0.8));
		assertFalse(BorerAreaPolicy.mineAdjacentShaftInsteadOfFly(8.0));
		assertFalse(BorerAreaPolicy.holdForwardWhileFlying(0.8, true));
		assertTrue(BorerAreaPolicy.holdForwardWhileFlying(0.8, false));
		assertTrue(BorerAreaPolicy.holdForwardWhileFlying(50.0, true));
		assertFalse(BorerAreaPolicy.sneakDiveToShaft(true, true));
		assertTrue(BorerAreaPolicy.sneakDiveToShaft(true, false));
		assertFalse(BorerAreaPolicy.flyJump(false, true, false, true));
		assertFalse(BorerAreaPolicy.flyOverInsteadOfMine(true, true, false, true));
	}

	@Test
	void shaftWithBlocksBelowDescendsInsteadOfWaiting() {
		assertTrue(BorerAreaPolicy.descendShaftInsteadOfWait(true, true, true));
		assertTrue(BorerAreaPolicy.skipThinkForSimpleDown(true, false, true, true, false));
		assertTrue(BorerAreaPolicy.skipThinkForSimpleDown(true, false, false, false, true));
		assertFalse(BorerAreaPolicy.skipThinkForSimpleDown(false, false, true, true, true));
		assertFalse(BorerAreaPolicy.skipThinkForSimpleDown(true, true, true, true, true));
		assertFalse(BorerAreaPolicy.descendShaftInsteadOfWait(true, true, false));
		assertFalse(BorerAreaPolicy.descendShaftInsteadOfWait(true, false, true));
		assertFalse(BorerAreaPolicy.descendShaftInsteadOfWait(false, true, true));
		assertTrue(BorerAreaPolicy.mineLookedShaftBlock(true, true));
		assertFalse(BorerAreaPolicy.mineLookedShaftBlock(false, true));
		assertFalse(BorerAreaPolicy.mineLookedShaftBlock(true, false));
		assertTrue(BorerAreaPolicy.acceptShaftMineTarget(true));
		assertFalse(BorerAreaPolicy.acceptShaftMineTarget(false));
		assertEquals(0.0, BorerAreaPolicy.thinkDestDy(false, 67, 53, null), 0.01);
		assertEquals(-4.0, BorerAreaPolicy.thinkDestDy(false, 67, 53, 49), 0.01);
		assertEquals(14.0, BorerAreaPolicy.thinkDestDy(true, 67, 53, 49), 0.01);
	}
}
