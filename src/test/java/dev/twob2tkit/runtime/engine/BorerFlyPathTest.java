package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import java.io.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerFlyPathTest {
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
