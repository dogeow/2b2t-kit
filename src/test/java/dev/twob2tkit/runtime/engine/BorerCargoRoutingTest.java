package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoRoutingTest {
	@Test void chestAlreadyInReachUsesTheCurrentPositionWithoutAnyTravel() {
		Pose p = new Pose(760864.574, 3.217, 797807.518, 0, 0, 0);
		var route = BorerCargoRouting.choose(b -> { throw new AssertionError("No flight needed to use an already reachable chest"); }, p, p, p, 0);
		assertTrue(route.here());
		var trip = new BorerCargoTrip(p, new BlockPos(760866, 3, 797807), route);
		assertEquals(BorerCargoTrip.Stage.SERVICE, trip.stage());
		assertEquals(Action.WAIT, trip.step(b -> Cell.SOLID, p).action());
		trip.returnToWork(); assertEquals(BorerCargoTrip.Stage.DONE, trip.stage());
	}
	@Test void zFirstDetourAndItsReverseAreExecutedWithoutCrossingWalls() {
		World world = b -> b.getX() == 1 && b.getZ() <= 0 ? Cell.SOLID : Cell.AIR;
		Pose start = BorerCargoRouting.pose(.5, 1.05, .5), service = BorerCargoRouting.pose(2.5, 1.05, 2.5);
		var route = BorerCargoRouting.choose(world, start, start, service, 0);
		assertNotNull(route); assertTrue(route.zFirst());
		runRoundTrip(world, start, service, route);
	}
	@Test void chestCanBeApproachedFromTheSideUnderALowCeiling() {
		World world = b -> b.getY() >= 3 || b.equals(new BlockPos(3, 1, 0)) ? Cell.SOLID : Cell.AIR;
		Pose start = BorerCargoRouting.pose(.5, 1.05, .5), service = BorerCargoRouting.pose(2.5, 1.05, .5);
		var route = BorerCargoRouting.choose(world, start, start, service, 0);
		assertNotNull(route); assertEquals(1.05, route.travelY());
		assertFalse(BorerCargoRouting.clear(world, BorerCargoRouting.pose(3.5, 2.25, .5), BorerCargoRouting.pose(3.5, 2.25, .5)));
		runRoundTrip(world, start, service, route);
	}
	@Test void theOldSiteBehindTheWallIsRejectedBeforeThePlayerStartsFlying() {
		World world = b -> b.getZ() == 2 ? Cell.SOLID : Cell.AIR;
		Pose start = BorerCargoRouting.pose(.5, 3.217, .5);
		assertNull(BorerCargoRouting.choose(world, start, start, BorerCargoRouting.pose(.5, 1.25, 4.5), 0));
		assertNotNull(BorerCargoRouting.choose(world, start, start, BorerCargoRouting.pose(1.5, 1.25, .5), 0));
	}
	@Test void waterUnloadedChunksAndProtectedBlocksAreNotPreflightedAsClear() {
		Pose a = BorerCargoRouting.pose(.5, 1.05, .5), b = BorerCargoRouting.pose(2.5, 1.05, .5);
		for (Cell obstruction : new Cell[]{Cell.LIQUID, Cell.UNLOADED, Cell.PROTECTED}) {
			assertNull(BorerCargoRouting.choose(p -> p.getX() == 1 ? obstruction : Cell.AIR, a, a, b, 0));
		}
	}
	@Test void worksiteBoundaryAllowsNearbyPlayerChestsButNotDistantStorage() {
		BlockPos min = new BlockPos(760864, -50, 797792), max = new BlockPos(760879, 0, 797807);
		assertTrue(BorerCargoRouting.worksiteChest(new BlockPos(760866, 3, 797807), min, max));
		assertTrue(BorerCargoRouting.worksiteChest(new BlockPos(760864, 0, 797810), min, max));
		assertFalse(BorerCargoRouting.worksiteChest(new BlockPos(760864, 0, 797850), min, max));
		assertTrue(BorerCargoRouting.worksiteChest(new BlockPos(760864, 60, 797807), min, max), "Same worksite above the current depth slice is still in scope");
		assertFalse(BorerCargoRouting.worksiteChest(new BlockPos(760886, 60, 797807), min, max));
	}
	@Test void chestOnAnExcavationColumnIsReservedAndDoesNotForceADescentIntoIt() {
		Pose p = BorerCargoRouting.pose(.5, 2.25, .5);
		var plan = new BorerAreaPlan(BlockPos.ZERO, new BlockPos(1, 0, 0), p);
		assertTrue(plan.reserveStorageColumn(new BlockPos(0, 1, 0)));
		assertFalse(plan.reserveStorageColumn(new BlockPos(0, 1, 0)));
		plan.resumeAfterStorage(p);
		assertEquals(new BlockPos(1, 0, 0), plan.pending());
		assertEquals(1, plan.skipped()); assertEquals(0, plan.completed());
		assertEquals(2.25, plan.transferY());
	}
	@Test void aChestSixtyBlocksOverTheShaftCanBeServicedFromBelowWithoutFlyingThroughIt() {
		BlockPos chest = new BlockPos(0, 1, 0);
		World w = b -> b.equals(chest) ? Cell.PROTECTED : b.getY() < -59 ? Cell.BEDROCK : Cell.AIR;
		Pose start = BorerCargoRouting.pose(.5, -59, .5);
		Pose service = BorerCargoSites.stances(chest).getFirst();
		var route = BorerCargoRouting.choose(w, start, start, service, -50);
		assertNotNull(route); assertEquals(-1.95, route.travelY(), .001);
		runRoundTrip(w, start, service, route);
	}
	@Test void newBedrockFloorDepotDoesNotRequireReturningAboveTheConfiguredTop() {
		BlockPos chest = new BlockPos(1, -59, 0);
		World afterPlacement = b -> b.equals(chest) ? Cell.PROTECTED : b.getY() < -59 ? Cell.BEDROCK : Cell.AIR;
		Pose start = BorerCargoRouting.pose(.5, -59, .5), service = BorerCargoRouting.pose(1.5, -57.75, .5);
		var route = BorerCargoRouting.choose(afterPlacement, start, start, service, -50);
		assertNotNull(route); assertEquals(-57.75, route.travelY());
		runRoundTrip(afterPlacement, start, service, route);
	}
	@Test void plannedChestMustNotBePlacedAcrossTheOnlyReturnPassage() {
		Pose from = BorerCargoRouting.pose(.5, 1.05, .5), service = BorerCargoRouting.pose(2.5, 1.05, .5);
		World passage = b -> b.getZ() != 0 || b.getY() >= 3 ? Cell.SOLID : Cell.AIR;
		assertNotNull(BorerCargoRouting.choose(passage, from, from, service, 0));
		World afterPlacement = b -> b.equals(new BlockPos(1, 1, 0)) ? Cell.PROTECTED : passage.cell(b);
		assertNull(BorerCargoRouting.choose(afterPlacement, from, from, service, 0));
	}
	private static void runRoundTrip(World world, Pose start, Pose service, BorerCargoRouting.Route route) {
		var trip = new BorerCargoTrip(start, BlockPos.containing(service.x(), service.y(), service.z()), route);
		Pose p = start; float yaw = 0; boolean serviced = false;
		for (int tick = 0; tick < 1000 && trip.stage() != BorerCargoTrip.Stage.DONE; tick++) {
			Command command = trip.step(world, p);
			assertNotEquals(Action.BLOCKED, command.action()); assertNotEquals(Action.MINE, command.action());
			if (trip.stage() == BorerCargoTrip.Stage.SERVICE) { serviced = true; trip.returnToWork(); }
			var input = BorerAreaMotion.of(command, p, yaw); yaw = input.yaw();
			double dx = input.forward() ? -Math.sin(Math.toRadians(yaw)) * input.speed() * 10 : 0;
			double dz = input.forward() ? Math.cos(Math.toRadians(yaw)) * input.speed() * 10 : 0;
			double dy = (input.up() ? 1 : input.down() ? -1 : 0) * input.speed() * 5;
			p = new Pose(p.x() + dx, p.y() + dy, p.z() + dz, dx, dy, dz);
			for (int x = (int)Math.floor(p.x() - .299); x <= (int)Math.floor(p.x() + .299); x++)
				for (int z = (int)Math.floor(p.z() - .299); z <= (int)Math.floor(p.z() + .299); z++)
					for (int y = (int)Math.floor(p.y() + .001); y <= (int)Math.floor(p.y() + 1.799); y++) assertEquals(Cell.AIR, world.cell(new BlockPos(x, y, z)));
		}
		assertTrue(serviced); assertEquals(BorerCargoTrip.Stage.DONE, trip.stage());
		assertEquals(start.x(), p.x(), .09); assertEquals(start.z(), p.z(), .09);
	}
}
