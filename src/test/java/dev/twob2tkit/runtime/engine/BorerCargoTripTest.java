package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoTripTest {
	@Test void fullDepthRoundTripUsesProductionInputsAndNeverMovesSidewaysBelowTop() {
		Pose p = new Pose(0.5, -60, 0.5, 0, 0, 0);
		var trip = new BorerCargoTrip(p, new BlockPos(-4, 65, 0), 64);
		boolean serviced = false; float yaw = 123;
		for (int tick = 0; tick < 1000 && trip.stage() != BorerCargoTrip.Stage.DONE; tick++) {
			Command c = trip.step(b -> Cell.AIR, p);
			assertNotEquals(Action.BLOCKED, c.action());
			if (c.action() == Action.X || c.action() == Action.Z) assertTrue(p.y() >= 68.15, "Transfer above area and chest");
			if (trip.stage() == BorerCargoTrip.Stage.SERVICE) {
				assertEquals(-3.5, p.x(), .085); assertEquals(66.25, p.y(), .10);
				serviced = true; trip.returnToWork();
			}
			var input = BorerAreaMotion.of(c, p, yaw); yaw = input.yaw();
			double a = Math.toRadians(yaw), dx = input.forward() ? -Math.sin(a) * input.speed() * 10 : 0;
			double dz = input.forward() ? Math.cos(a) * input.speed() * 10 : 0;
			double dy = (input.up() ? 1 : input.down() ? -1 : 0) * input.speed() * 5;
			assertTrue(Math.abs(dx) <= .25 && Math.abs(dz) <= .25 && Math.abs(dy) <= 1.2);
			p = new Pose(p.x() + dx, p.y() + dy, p.z() + dz, dx, dy, dz);
		}
		assertTrue(serviced); assertEquals(BorerCargoTrip.Stage.DONE, trip.stage());
		assertEquals(.5, p.x(), .085); assertEquals(.5, p.z(), .085); assertTrue(p.y() > 64);
	}
	@Test void departureCeilingMayBeMinedButLiquidProtectedAndUnloadedNeverAre() {
		Pose p = new Pose(.5, 10, .5, 0, 0, 0);
		BlockPos ceiling = new BlockPos(0, 12, 0);
		for (Cell cell : Cell.values()) {
			var trip = new BorerCargoTrip(p, new BlockPos(-4, 65, 0), 64);
			Command c = trip.step(b -> b.equals(ceiling) ? cell : Cell.AIR, p);
			assertEquals(switch (cell) { case AIR -> Action.UP; case SOLID -> Action.MINE; case UNLOADED -> Action.WAIT; default -> Action.BLOCKED; }, c.action());
		}
	}
	@Test void refusesToMineSidewaysOutsideTheExcavationOrThroughWater() {
		Pose p = new Pose(.5, 68.25, .5, 0, 0, 0);
		var trip = new BorerCargoTrip(p, new BlockPos(-4, 65, 0), 64);
		trip.step(b -> Cell.AIR, p);
		Command c = trip.step(b -> b.getX() == -1 ? Cell.SOLID : Cell.AIR, p);
		assertEquals(Action.BLOCKED, c.action());
	}
}
