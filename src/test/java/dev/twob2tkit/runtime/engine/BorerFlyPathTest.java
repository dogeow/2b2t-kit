package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import java.io.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerFlyPathTest {
	@Test void smallHeightDriftAtHorizontalTurnsCanCorrectOnlyWithinClearSpace() {
		for (double feetY : new double[]{44.202, 37.998}) {
			double waypointY = feetY > 40 ? 44.1 : 38.1;
			Vec3 start = new Vec3(.65, feetY, .45);
			Vec3 end = new Vec3(1.5, waypointY, .5);
			var input = BorerHomeFlight.clearanceInput(start, end, 0, d -> d.x == 0 && d.z == 0);
			assertNotNull(input);
			assertTrue(input.delta().y * (waypointY - feetY) > 0);
			assertNull(BorerHomeFlight.clearanceInput(start, end, 0, d -> false));
		}
	}

	@Test void collisionsSeparatedByConfirmedTravelGetIndependentReplans() {
		var blocked = new BorerHomeFlight.Obstructions();
		assertFalse(blocked.repeated(new Vec3(95052.652,44.202,99615.456)));
		var second = new Vec3(95075.346,37.998,99621.456);
		assertFalse(blocked.repeated(second));
		assertTrue(blocked.repeated(second.add(.1,0,0)));
	}

	@Test void bypassCanCrossTheOldRadiusToFindALowerLandingBehindALavaBarrier() {
		Set<BlockPos> air = new HashSet<>();
		for (int x = 0; x <= 32; x++) {
			air.add(new BlockPos(x, 0, 0));
			air.add(new BlockPos(x, -4, 0));
		}
		for (int y = -4; y <= 0; y++) air.add(new BlockPos(32, y, 0));
		for (BlockPos p : List.copyOf(air)) air.add(p.above());
		var landing = new BlockPos(8, -4, 0);
		var route = BorerFlyPath.liquidBypass(air::contains, BlockPos.ZERO, new BlockPos(0,-8,0), landing::equals);
		assertEquals(landing, route.nodes().getLast());
		assertTrue(route.nodes().contains(new BlockPos(32, 0, 0)));
	}

	@Test void widerLiquidDetourCanStartByMovingAwayAndResumeCloserToOre() {
		Set<BlockPos> air = new HashSet<>();
		for (int z = 0; z <= 7; z++) {
			air.add(new BlockPos(0, 0, z));
			air.add(new BlockPos(12, 0, z));
		}
		for (int x = 0; x <= 12; x++) air.add(new BlockPos(x, 0, 7));
		for (BlockPos p : List.copyOf(air)) air.add(p.above());
		BlockPos landing = new BlockPos(12, 0, 0);
		var ore = landing.east(3);
		var route = BorerFlyPath.liquidBypass(air::contains, BlockPos.ZERO, ore, landing::equals);
		assertEquals(landing, route.nodes().getLast());
		assertTrue(route.nodes().contains(new BlockPos(0, 0, 7)));
		air.remove(new BlockPos(5, 1, 7));
		assertTrue(BorerFlyPath.liquidBypass(air::contains, BlockPos.ZERO, ore, landing::equals).nodes().isEmpty());
	}

	@Test void capturedNetherStallHasARealOpenRouteAndNeverCutsThroughSolidBlocks() throws Exception {
		Set<BlockPos> air = new HashSet<>();
		try (var in = new BufferedReader(new InputStreamReader(getClass().getResourceAsStream("/nether-return-air.txt")))) {
			for (String line : in.lines().toList()) {
				String[] xyz = line.split(" ");
				air.add(new BlockPos(Integer.parseInt(xyz[0]), Integer.parseInt(xyz[1]), Integer.parseInt(xyz[2])));
			}
		}
		BlockPos start = BlockPos.ZERO, target = new BlockPos(1, -1, 4);
		var result = BorerFlyPath.find(air::contains, start, target, 12, 2400);
		assertFalse(result.nodes().isEmpty());
		assertTrue(result.expanded() <= 2400);
		assertTrue(result.nodes().getLast().distSqr(target) <= 1.25 * 1.25);
		for (int i = 0; i < result.nodes().size(); i++) {
			BlockPos p = result.nodes().get(i);
			assertTrue(air.contains(p) && air.contains(p.above()));
			if (i > 0) assertEquals(1, p.distManhattan(result.nodes().get(i - 1)));
		}
		// Replay actual offset and Meteor Velocity's speed multipliers, including full player body clearance.
		Vec3 position = new Vec3(.500108, 0, .348913);
		for (BlockPos node : result.nodes()) {
			Vec3 goal = BorerFlyPath.waypoint(node);
			int ticks = 0;
			while (!BorerHomeFlight.reached(position, goal) && ticks++ < 100) {
				var input = BorerFlyPath.input(position, goal, 0);
				assertTrue(input.delta().length() <= .201);
				Vec3 next = position.add(input.delta());
				var body = new net.minecraft.world.phys.AABB(position.x-.3,position.y,position.z-.3,position.x+.3,position.y+1.8,position.z+.3)
					.expandTowards(input.delta()).deflate(.0001);
				for (BlockPos p : BlockPos.betweenClosed(BlockPos.containing(body.minX,body.minY,body.minZ),BlockPos.containing(body.maxX,body.maxY,body.maxZ)))
					assertTrue(air.contains(p), "body touched " + p + " moving " + position + " -> " + next);
				position = next;
			}
			assertTrue(ticks < 100, "failed to reach " + node);
		}
	}
	@Test void bedrockPocketRequiresASideStepBeforeClimbingToSupportedGround() {
		BlockPos start = new BlockPos(0, -62, 0);
		BlockPos landing = new BlockPos(1, -58, 2);
		Set<BlockPos> air = new HashSet<>(List.of(start, start.above(),
			new BlockPos(1, -62, 0), new BlockPos(1, -61, 0), new BlockPos(1, -60, 0),
			new BlockPos(1, -59, 0), new BlockPos(1, -60, 1), new BlockPos(1, -59, 1),
			new BlockPos(1, -58, 1), new BlockPos(1, -58, 2), new BlockPos(1, -57, 2)));
		// The last two cells are accessible only from the higher part of the turning corridor.
		air.add(new BlockPos(1, -57, 1));
		var route = BorerFlyPath.escapePocket(air::contains, start, landing::equals);
		assertFalse(route.nodes().isEmpty());
		assertEquals(start.east(), route.nodes().get(1));
		assertEquals(landing, route.nodes().getLast());
		for (int i = 1; i < route.nodes().size(); i++) {
			BlockPos next = route.nodes().get(i);
			assertTrue(air.contains(next) && air.contains(next.above()));
			assertEquals(1, next.distManhattan(route.nodes().get(i - 1)));
		}
		assertTrue(BorerFlyPath.escapePocket(air::contains, start, p -> false).nodes().isEmpty());
		air.remove(start.east());
		assertTrue(BorerFlyPath.escapePocket(air::contains, start, landing::equals).nodes().isEmpty());
	}

	@Test void flightCanAscendARealShaftButCannotFlyThroughItsCeiling() {
		Set<BlockPos> air = new HashSet<>();
		for (int y = 0; y <= 6; y++) air.add(new BlockPos(0,y,0));
		assertFalse(BorerFlyPath.find(air::contains, BlockPos.ZERO, new BlockPos(0,5,0), 12, 200).nodes().isEmpty());
		air.remove(new BlockPos(0,3,0));
		assertTrue(BorerFlyPath.find(air::contains, BlockPos.ZERO, new BlockPos(0,5,0), 12, 200).nodes().isEmpty());
	}
	@Test void unknownOrDangerousColumnsAreNotAirAndSearchIsBounded() {
		assertTrue(BorerFlyPath.find(p -> false, BlockPos.ZERO, new BlockPos(4,0,0), 12, 10).nodes().isEmpty());
		var limited = BorerFlyPath.find(p -> true, BlockPos.ZERO, new BlockPos(100,0,0), 12, 10);
		assertTrue(limited.nodes().isEmpty()); assertEquals(10, limited.expanded());
	}
	@Test void turnsUseTheImmediateSegmentAndNeverOvershootInOneTick() {
		for (Vec3 delta : List.of(new Vec3(.08,0,0),new Vec3(-2,0,0),new Vec3(0,2,0),new Vec3(0,-.08,0),new Vec3(0,0,-3))) {
			var input = BorerFlyPath.input(Vec3.ZERO, delta, 77);
			Vec3 actual = input.forward() ? new Vec3(-Math.sin(Math.toRadians(input.yaw())) * input.speed()*10,0,
				Math.cos(Math.toRadians(input.yaw())) * input.speed()*10) : new Vec3(0,(input.up()?1:input.down()?-1:0)*input.speed()*5,0);
			assertTrue(actual.distanceTo(input.delta()) < .00001);
			assertTrue(actual.length() < delta.length());
			assertTrue(actual.dot(delta) > 0);
		}
	}
}
