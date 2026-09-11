package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaWaterPlanTest {
	static class World implements BorerAreaPlan.World {
		final Map<BlockPos, Cell> cells = new HashMap<>();
		BlockPos barrier, water;
		boolean canSeal = true;
		public Cell cell(BlockPos p) { return cells.getOrDefault(p, Cell.AIR); }
		public boolean opensLiquid(BlockPos p) { return p.equals(barrier) && cell(water) == Cell.LIQUID; }
		public BlockPos sealableSideWater(BlockPos p) { return canSeal && opensLiquid(p) ? water : null; }
	}
	@Test void transferSealsSideWaterThenMinesTheOriginalDryBarrierAndContinues() {
		World w = new World();
		w.barrier = new BlockPos(1, 2, 0); w.water = new BlockPos(2, 2, 0);
		w.cells.put(new BlockPos(1, 0, 0), Cell.SOLID); w.cells.put(w.barrier, Cell.SOLID); w.cells.put(w.water, Cell.LIQUID);
		Pose p = new Pose(.5, 1.25, .5, 0, 0, 0);
		BorerAreaPlan plan = new BorerAreaPlan(BlockPos.ZERO, new BlockPos(1, 0, 0), p);
		Command command = null;
		for (int tick = 0; tick < 10; tick++) { command = plan.step(w, p); if (command.action() == Action.SEAL_WATER) break; }
		assertEquals(Action.SEAL_WATER, command.action()); assertEquals(w.barrier, command.block());
		assertEquals(Phase.TRANSFER, plan.phase()); assertEquals(Cell.SOLID, w.cell(w.barrier));
		w.cells.put(w.water, Cell.SOLID); plan.rememberWaterSeal(w.water);
		assertEquals(Action.MINE, plan.step(w, p).action());
		w.cells.put(w.barrier, Cell.AIR);
		assertEquals(Action.X, plan.step(w, p).action());
		assertTrue(plan.isWaterSeal(w.water)); assertEquals(0, plan.skipped());
	}
	@Test void verticalDigDoesNotSkipTheCurrentShaftWhenItsSideWaterCanBeSealed() {
		World w = new World(); w.barrier = BlockPos.ZERO; w.water = new BlockPos(1, 0, 0);
		w.cells.put(w.barrier, Cell.SOLID); w.cells.put(w.water, Cell.LIQUID);
		Pose p = new Pose(.5, 1.25, .5, 0, 0, 0); var plan = new BorerAreaPlan(BlockPos.ZERO, BlockPos.ZERO, p);
		Command c = null;
		for (int i = 0; i < 12; i++) { c = plan.step(w, p); if (c.action() == Action.SEAL_WATER) break; }
		assertEquals(Action.SEAL_WATER, c.action()); assertEquals(Phase.DIG, plan.phase());
		w.cells.put(w.water, Cell.SOLID); plan.rememberWaterSeal(w.water);
		assertEquals(Action.MINE, plan.step(w, p).action());
		assertEquals(0, plan.completed()); assertEquals(0, plan.skipped());
	}
	@Test void lavaOrUnsealableWaterRetainsTheOriginalSafetyFallback() {
		World w = new World(); w.barrier = BlockPos.ZERO; w.water = new BlockPos(1, 0, 0); w.canSeal = false;
		w.cells.put(w.barrier, Cell.SOLID); w.cells.put(w.water, Cell.LIQUID);
		Pose p = new Pose(.5, 1.25, .5, 0, 0, 0); var plan = new BorerAreaPlan(BlockPos.ZERO, BlockPos.ZERO, p);
		for (int i = 0; i < 12 && plan.phase() != Phase.RETURN; i++) assertNotEquals(Action.SEAL_WATER, plan.step(w, p).action());
		assertEquals(Phase.RETURN, plan.phase()); assertEquals(1, plan.skipped()); assertEquals(Cell.SOLID, w.cell(w.barrier));
	}
	@Test void waterWallReservationSurvivesRestartAndDoesNotCountAsExcavated(@TempDir Path temp) throws Exception {
		BlockPos min = BlockPos.ZERO, max = new BlockPos(2, 0, 0), seal = new BlockPos(2, 2, 0);
		Pose p = new Pose(.5, 1.25, .5, 0, 0, 0); var plan = new BorerAreaPlan(min, max, p);
		plan.rememberWaterSeal(seal); plan.rememberWaterSeal(seal);
		assertEquals(1, plan.skipped()); assertEquals(0, plan.completed());
		Path file = temp.resolve("area.json"); BorerAreaProgress.write(file, "server|dimension", plan.snapshot());
		var restored = BorerAreaPlan.restore(min, max, p, BorerAreaProgress.read(file, "server|dimension"));
		assertNotNull(restored); assertTrue(restored.isWaterSeal(seal)); assertEquals(1, restored.skipped());
		assertNull(BorerAreaProgress.read(file, "another-server|dimension"));
	}
}
