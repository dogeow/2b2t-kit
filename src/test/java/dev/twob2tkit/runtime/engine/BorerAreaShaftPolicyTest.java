package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class BorerAreaShaftPolicyTest {
	@Test
	void emptyShaftStillDescendsToTargetYBeforeCompleting() {
		assertTrue(BorerAreaShaftPolicy.shouldDescend(true, 52, 50, true));
		assertFalse(BorerAreaShaftPolicy.shaftComplete(true, 52, 50, false));
		assertTrue(BorerAreaShaftPolicy.shaftComplete(true, 50, 50, false));
		assertFalse(BorerAreaShaftPolicy.shaftComplete(true, 50, 50, true));
		assertTrue(BorerAreaShaftPolicy.shaftComplete(false, -63, -64, false));
	}

	@Test
	void snakeGridIsAdjacentUniqueAndComplete() {
		List<BlockPos> actual = new ArrayList<>();
		BlockPos pos = new BlockPos(10, 0, 20);
		while (pos != null) {
			actual.add(pos);
			pos = BorerAreaShaftPolicy.nextSnakeColumn(
				pos.getX(), pos.getZ(), 10, 20, 12, 21);
		}
		assertEquals(List.of(
			new BlockPos(10, 0, 20), new BlockPos(11, 0, 20), new BlockPos(12, 0, 20),
			new BlockPos(12, 0, 21), new BlockPos(11, 0, 21), new BlockPos(10, 0, 21)
		), actual);
		Set<BlockPos> unique = new HashSet<>(actual);
		assertEquals(6, unique.size());
		for (int i = 1; i < actual.size(); i++) {
			assertEquals(1, actual.get(i - 1).distManhattan(actual.get(i)));
		}
	}

	@Test
	void snakeHandlesSingleRowsColumnsAndNegativeCoordinates() {
		assertNull(BorerAreaShaftPolicy.nextSnakeColumn(2, 3, 2, 3, 2, 3));
		assertEquals(new BlockPos(-1, 0, -3),
			BorerAreaShaftPolicy.nextSnakeColumn(-2, -3, -2, -3, 0, -3));
		assertEquals(new BlockPos(-2, 0, -2),
			BorerAreaShaftPolicy.nextSnakeColumn(-2, -3, -2, -3, -2, 0));
	}

	@Test
	void snakeCanStartAtNearestCornerAndStillStayAdjacent() {
		assertEquals(new BlockPos(12, 0, 20),
			BorerAreaShaftPolicy.nearestCorner(13, 19, 10, 20, 12, 21));
		List<BlockPos> actual = new ArrayList<>();
		BlockPos pos = new BlockPos(12, 0, 20);
		while (pos != null) {
			actual.add(pos);
			pos = BorerAreaShaftPolicy.nextSnakeColumn(
				pos.getX(), pos.getZ(), 10, 20, 12, 21, 12, 20);
		}
		assertEquals(List.of(
			new BlockPos(12, 0, 20), new BlockPos(11, 0, 20), new BlockPos(10, 0, 20),
			new BlockPos(10, 0, 21), new BlockPos(11, 0, 21), new BlockPos(12, 0, 21)
		), actual);
		for (int i = 1; i < actual.size(); i++) {
			assertEquals(1, actual.get(i - 1).distManhattan(actual.get(i)));
		}
	}

	@Test
	void returnAndTransferMiningAreSeparated() {
		BlockPos current = new BlockPos(10, 0, 20);
		BlockPos next = new BlockPos(11, 0, 20);
		assertFalse(BorerAreaShaftPolicy.allowsMine(
			BorerAreaShaftPolicy.Phase.ASCEND_CURRENT,
			new BlockPos(11, 50, 20), current, next, 67, 50));
		assertTrue(BorerAreaShaftPolicy.allowsMine(
			BorerAreaShaftPolicy.Phase.ASCEND_CURRENT,
			new BlockPos(10, 69, 20), current, next, 67, 50));
		assertTrue(BorerAreaShaftPolicy.allowsMine(
			BorerAreaShaftPolicy.Phase.TRANSFER_TOP,
			new BlockPos(11, 69, 20), current, next, 67, 50));
		assertFalse(BorerAreaShaftPolicy.allowsMine(
			BorerAreaShaftPolicy.Phase.TRANSFER_TOP,
			new BlockPos(11, 68, 20), current, next, 67, 50));
		assertFalse(BorerAreaShaftPolicy.allowsMine(
			BorerAreaShaftPolicy.Phase.TRANSFER_TOP,
			new BlockPos(11, 50, 20), current, next, 67, 50));
	}

	@Test
	void transferHeightAndThinkAreDeterministic() {
		assertTrue(BorerAreaShaftPolicy.centered(10.44, 20.44, 10, 20));
		assertFalse(BorerAreaShaftPolicy.centered(10.41, 20.49, 10, 20));
		assertEquals(69, BorerAreaShaftPolicy.transferFeetY(67));
		assertTrue(BorerAreaShaftPolicy.belowTransferHeight(68.4, 67));
		assertTrue(BorerAreaShaftPolicy.atTransferHeight(69.0, 67));
		assertTrue(BorerAreaShaftPolicy.atTransferHeight(69.5, 67));
		assertTrue(BorerAreaShaftPolicy.aboveTransferHeight(69.6, 67));
		assertFalse(BorerAreaShaftPolicy.allowThink(
			BorerAreaShaftPolicy.Phase.ASCEND_CURRENT, true));
		assertFalse(BorerAreaShaftPolicy.allowThink(
			BorerAreaShaftPolicy.Phase.TRANSFER_TOP, true));
		assertTrue(BorerAreaShaftPolicy.allowThink(
			BorerAreaShaftPolicy.Phase.DIG_DOWN, true));
		BlockPos current = new BlockPos(10, 0, 20);
		assertTrue(BorerAreaShaftPolicy.allowSkip(
			BorerAreaShaftPolicy.Phase.DIG_DOWN, new BlockPos(10, 45, 20), current));
		assertFalse(BorerAreaShaftPolicy.allowSkip(
			BorerAreaShaftPolicy.Phase.DIG_DOWN, new BlockPos(11, 45, 20), current));
		assertFalse(BorerAreaShaftPolicy.allowSkip(
			BorerAreaShaftPolicy.Phase.ASCEND_CURRENT, new BlockPos(10, 45, 20), current));
		assertTrue(BorerAreaShaftPolicy.handleNearbyLiquid(
			BorerAreaShaftPolicy.Phase.DIG_DOWN, new BlockPos(11, 45, 20), current));
		assertFalse(BorerAreaShaftPolicy.handleNearbyLiquid(
			BorerAreaShaftPolicy.Phase.POSITION_TOP, new BlockPos(11, 45, 20), current));
		assertFalse(BorerAreaShaftPolicy.handleNearbyLiquid(
			BorerAreaShaftPolicy.Phase.ASCEND_CURRENT, new BlockPos(10, 45, 20), current));
	}
}
