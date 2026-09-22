package dev.twob2tkit.runtime.engine;

import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerHomeRouteTest {
	@Test void temporaryLiftHandsBackToWalkingOnlyAboveASafeNearbyFloor() {
		assertTrue(BorerHome.canResumeWalking(true, -.2, 0));
		assertTrue(BorerHome.canResumeWalking(true, -.2, 1));
		assertFalse(BorerHome.canResumeWalking(false, -.2, 0));
		assertFalse(BorerHome.canResumeWalking(true, 2, 0));
		assertFalse(BorerHome.canResumeWalking(true, -.2, -1));
		assertFalse(BorerHome.canResumeWalking(true, -.2, 3));
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
}
