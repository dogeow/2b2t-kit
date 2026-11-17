package dev.twob2tkit.runtime.engine;

import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerHomeRouteTest {
	@Test void temporaryLiftHandsBackToWalkingOnlyAboveAHighEnoughSafeFloor() {
		assertTrue(BorerHome.landingCanContinueOnFoot(0, 0));
		assertTrue(BorerHome.landingCanContinueOnFoot(1, 1));
		assertFalse(BorerHome.landingCanContinueOnFoot(0, -1));
		assertFalse(BorerHome.landingCanContinueOnFoot(-1, 0));
		assertFalse(BorerHome.landingCanContinueOnFoot(3, 0));
	}
	@Test void homeArrivalMatchesTheTrailIncludingAnAirbornePointAboveTheActualFloor() {
		BlockPos goal = new BlockPos(761061, -59, 797939);
		var home = BorerWalkRoute.routeGoal(Vec3.atBottomCenterOf(goal), false, true);
		assertTrue(home.test(goal));
		assertTrue(home.test(goal.east()));
		assertTrue(home.test(goal.below()));
		assertFalse(home.test(goal.below(2)));
		assertTrue(BorerTrailPolicy.reachedReturnWaypoint(Vec3.atBottomCenterOf(goal.below()), goal));
		assertTrue(BorerWalkRoute.routeGoal(Vec3.atBottomCenterOf(goal), false, false).test(goal.east()));
	}

	@Test void liveCornerIsFollowedThroughOpenColumnsInsteadOfMiningTheDiagonalWall() {
		var open = List.of(new BlockPos(761063, -59, 797941), new BlockPos(761063, -59, 797940),
			new BlockPos(761063, -59, 797939), new BlockPos(761062, -59, 797939), new BlockPos(761061, -59, 797939));
		Set<BlockPos> air = new HashSet<>();
		for (BlockPos p : open) { air.add(p); air.add(p.above()); }
		var world = new BorerWalkPath.World() {
			public boolean clear(BlockPos p) { return air.contains(p); }
			public boolean floor(BlockPos p) { return open.contains(p.above()); }
		};
		var route = BorerWalkPath.find(world, open.getFirst(),
			BorerWalkRoute.routeGoal(Vec3.atBottomCenterOf(open.getLast()), false, true), 12, 640, 3, true);
		assertEquals(open.subList(0, 4), route.nodes());
		assertFalse(route.nodes().contains(new BlockPos(761062, -59, 797940)));
	}

	@Test void airborneReturnClimbsBeforeEnteringTheHigherCorner() {
		BlockPos start = new BlockPos(760957, -55, 797882);
		BlockPos raised = start.above();
		BlockPos target = new BlockPos(760959, -54, 797883);
		Set<BlockPos> air = new HashSet<>();
		for (BlockPos feet : List.of(start, raised, raised.east(), raised.east(2), target)) {
			air.add(feet);
			air.add(feet.above());
		}
		assertFalse(air.contains(start.east()));
		var route = BorerFlyPath.find(air::contains, start, target, 12, 2400);
		assertEquals(List.of(start, raised, raised.east(), raised.east(2)), route.nodes());
		var rise = BorerFlyPath.input(BorerFlyPath.waypoint(start), BorerFlyPath.waypoint(raised), 0);
		assertTrue(rise.up());
		assertFalse(rise.forward());
	}

	private MethodNode method(String name, String method) throws Exception {
		ClassNode node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/" + name + ".class")) {
			assertNotNull(in); new ClassReader(in).accept(node, 0);
		}
		return node.methods.stream().filter(m -> m.name.equals(method)).findFirst().orElseThrow();
	}
	private List<String> calls(MethodNode method) {
		List<String> calls = new ArrayList<>();
		for (var node : method.instructions) if (node instanceof MethodInsnNode call) calls.add(call.owner + "." + call.name);
		return calls;
	}

	@Test void actualLateLookHookKeepsTheCurrentMovementDirectionAndNeverTargetsTheTrailTail() throws Exception {
		var calls = calls(method("DefaultTunnelBorerEngine", "reapplyLook"));
		assertTrue(calls.stream().anyMatch(c -> c.endsWith("BorerHome.reapplyLook")));
		assertFalse(calls.stream().anyMatch(c -> c.endsWith("BorerTrail.last")));
	}

	@Test void actualReturnUsesOpenRouteBeforeSelectingAStraightLineMiningObstruction() throws Exception {
		var calls = calls(method("BorerHome", "handle"));
		int walk = -1, obstruction = -1;
		for (int i = 0; i < calls.size(); i++) {
			if (calls.get(i).endsWith("BorerWalkRoute.walkHome")) walk = i;
			if (calls.get(i).endsWith("DefaultTunnelBorerEngine.visibleObstructionToward")) obstruction = i;
		}
		assertTrue(walk >= 0 && obstruction > walk);
	}

	@Test void actualFlyingReturnBranchesIntoSafeNavigationBeforeGroundFallback() throws Exception {
		var calls = calls(method("BorerHome", "handle"));
		int flying = calls.indexOf("dev/twob2tkit/runtime/engine/BorerFlight.isFlying");
		int walk = calls.indexOf("dev/twob2tkit/runtime/engine/BorerWalkRoute.walkHome");
		assertTrue(flying >= 0 && walk > flying);
		assertEquals("dev/twob2tkit/runtime/engine/BorerHome.flyTowardWaypoint", calls.get(flying + 1));
	}
	@Test void theObservedLiftWouldDropBackToTheLowerFloor() {
		int goalY = -52;
		int airborneFeetY = BlockPos.containing(760958.531, -51.830, 797886.435).getY();
		assertFalse(BorerHome.landingCanContinueOnFoot(1, airborneFeetY - 1 - goalY));
		assertTrue(BorerHome.landingCanContinueOnFoot(0, airborneFeetY - goalY));
	}

	@Test void activeFlightRouteIsCheckedBeforeAnyGroundHandoff() throws Exception {
		var calls = calls(method("BorerHome", "handle"));
		int canLand = calls.indexOf("dev/twob2tkit/runtime/engine/BorerHome.landingCanContinueOnFoot");
		int release = calls.indexOf("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.releaseMeteorFlightIfHeld");
		int activeFlight = calls.lastIndexOf("dev/twob2tkit/runtime/engine/BorerHomeFlight.isFollowing");
		assertTrue(activeFlight >= 0 && activeFlight < canLand && canLand < release);
	}
}
