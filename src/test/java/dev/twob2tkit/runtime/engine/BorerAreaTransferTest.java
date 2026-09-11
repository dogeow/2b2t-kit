package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.util.HashMap;
import java.util.Map;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Cell;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaTransferTest {
	@Test void aSingleBottomBlockIsTheTrueTopAndUnknownIsNotAir() {
		Map<BlockPos, Cell> cells = new HashMap<>(); cells.put(BlockPos.ZERO, Cell.SOLID);
		BorerAreaPlan.World w = p -> cells.getOrDefault(p, Cell.AIR);
		assertEquals(new BorerAreaTransfer.Surface(true, 0), BorerAreaTransfer.top(w, BlockPos.ZERO, 0, 64));
		cells.put(new BlockPos(0, 30, 0), Cell.UNLOADED);
		assertFalse(BorerAreaTransfer.top(w, BlockPos.ZERO, 0, 64).loaded());
	}
	@Test void routeChecksTheTurnAndBothLegsNotOnlyDestinationOrWrongDiagonal() {
		Map<BlockPos, Cell> cells = new HashMap<>();
		cells.put(new BlockPos(2, 5, 2), Cell.SOLID);
		cells.put(new BlockPos(2, 12, 0), Cell.BEDROCK); // X then Z turn.
		cells.put(new BlockPos(2, 20, 1), Cell.LIQUID); // Second leg.
		cells.put(new BlockPos(1, 40, 1), Cell.PROTECTED); // Not on the route.
		var surface = BorerAreaTransfer.routeTop(p -> cells.getOrDefault(p, Cell.AIR), BlockPos.ZERO, new BlockPos(2, 0, 2), 0, 64);
		assertTrue(surface.loaded()); assertEquals(20, surface.y());
	}
	@Test void unknownIntermediateColumnPreventsLowTransfer() {
		var surface = BorerAreaTransfer.routeTop(p -> p.getX() == -1 ? Cell.UNLOADED : Cell.AIR,
			new BlockPos(-2, 0, -2), new BlockPos(0, 0, 0), -64, 64);
		assertFalse(surface.loaded());
	}
}
