package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerWalkPathTest {
	@Test void productionWaypointInputsTraverseAnLTurnWithoutClippingTheWall() {
		World w = new World(); w.ground = false;
		List<BlockPos> corridor = List.of(new BlockPos(0, 0, 0), new BlockPos(1, 0, 0), new BlockPos(2, 0, 0), new BlockPos(2, 0, 1), new BlockPos(2, 0, 2));
		for (int x = -1; x <= 3; x++) for (int z = -1; z <= 3; z++) {
			w.blocks.add(new BlockPos(x, -1, z));
			if (!corridor.contains(new BlockPos(x, 0, z))) { w.blocks.add(new BlockPos(x, 0, z)); w.blocks.add(new BlockPos(x, 1, z)); }
		}
		var nodes = BorerWalkPath.find(w, BlockPos.ZERO, corridor.getLast()::equals, 4, 100, 3, false).nodes();
		assertEquals(corridor, nodes);
		double x = .5, z = .62; int index = 0;
		for (int tick = 0; tick < 150 && index < nodes.size(); tick++) {
			BlockPos node = nodes.get(index);
			if (BorerCenterPolicy.reachedWaypoint(node.getX() + .5 - x, 0, node.getZ() + .5 - z)) { index++; continue; }
			var input = BorerCenterPolicy.walkInput(node.getX() + .5 - x, node.getZ() + .5 - z);
			x += input.forward() ? -Math.sin(Math.toRadians(input.yaw())) * .1 : 0;
			z += input.forward() ? Math.cos(Math.toRadians(input.yaw())) * .1 : 0;
			for (int bx = (int)Math.floor(x - .3); bx <= (int)Math.floor(x + .3); bx++)
				for (int bz = (int)Math.floor(z - .3); bz <= (int)Math.floor(z + .3); bz++) {
					assertTrue(w.clear(new BlockPos(bx, 0, bz)), "Body must not clip a corner");
					assertTrue(w.clear(new BlockPos(bx, 1, bz)));
				}
		}
		assertEquals(nodes.size(), index);
	}
	@Test void safeDropLimitIsAppliedAndBlockedFallShaftsAreRejected() {
		World w = new World(); w.ground = false;
		w.blocks.add(new BlockPos(0, 3, 0)); w.blocks.add(new BlockPos(1, 0, 0));
		BlockPos start = new BlockPos(0, 4, 0), goal = new BlockPos(1, 1, 0);
		assertTrue(BorerWalkPath.find(w, start, goal::equals, 3, 100, 2, false).nodes().isEmpty());
		assertEquals(goal, BorerWalkPath.find(w, start, goal::equals, 3, 100, 3, false).nodes().getLast());
		w.forbidden.add(new BlockPos(1, 3, 0));
		assertTrue(BorerWalkPath.find(w, start, goal::equals, 3, 100, 3, false).nodes().isEmpty());
	}
	private static class World implements BorerWalkPath.World {
		Set<BlockPos> blocks = new HashSet<>(), forbidden = new HashSet<>();
		boolean ground = true;
		public boolean clear(BlockPos p) { return p.getY() >= 0 && !blocks.contains(p) && !forbidden.contains(p); }
		public boolean floor(BlockPos p) { return !forbidden.contains(p) && (ground && p.getY() == -1 || blocks.contains(p)); }
	}
	@Test void shortestOpenRouteGoesAroundATwoHighWallInsteadOfWalkingIntoIt() {
		World w = new World();
		for (int z = -1; z <= 1; z++) { w.blocks.add(new BlockPos(1, 0, z)); w.blocks.add(new BlockPos(1, 1, z)); }
		BlockPos goal = new BlockPos(3, 0, 0);
		var route = BorerWalkPath.find(w, BlockPos.ZERO, goal::equals, 8, 640, 3, true);
		assertEquals(8, route.nodes().size());
		assertEquals(goal, route.nodes().getLast());
		for (int i = 1; i < route.nodes().size(); i++) assertEquals(1, route.nodes().get(i - 1).distManhattan(route.nodes().get(i)));
		assertTrue(route.nodes().stream().allMatch(p -> BorerWalkPath.standable(w, p)));
	}
	@Test void diagonalCornerCannotBeCutEvenWhenTargetIsVeryClose() {
		World w = new World();
		for (BlockPos wall : List.of(new BlockPos(1, 0, 0), new BlockPos(0, 0, 1))) { w.blocks.add(wall); w.blocks.add(wall.above()); }
		BlockPos goal = new BlockPos(1, 0, 1);
		var route = BorerWalkPath.find(w, BlockPos.ZERO, goal::equals, 6, 640, 3, false);
		assertTrue(route.nodes().size() > 3);
		for (int i = 1; i < route.nodes().size(); i++) assertEquals(1, route.nodes().get(i - 1).distManhattan(route.nodes().get(i)));
	}
	@Test void unreachableRouteReturnsNoPartialOrBlindMovementWithinBudget() {
		World w = new World();
		var route = BorerWalkPath.find(w, BlockPos.ZERO, p -> false, 32, 24, 3, true);
		assertTrue(route.nodes().isEmpty()); assertTrue(route.expanded() <= 24);
	}
	@Test void floorAndBodyHazardsAreNeverUsedAsWalkableSpace() {
		World w = new World();
		w.forbidden.add(new BlockPos(1, 0, 0)); w.forbidden.add(new BlockPos(1, -1, -1));
		BlockPos goal = new BlockPos(2, 0, 0);
		var route = BorerWalkPath.find(w, BlockPos.ZERO, goal::equals, 5, 640, 3, false);
		assertFalse(route.nodes().isEmpty());
		assertFalse(route.nodes().contains(new BlockPos(1, 0, 0)));
		assertFalse(route.nodes().contains(new BlockPos(1, 0, -1)));
	}
	@Test void lowCeilingPreventsSteppingUp() {
		World w = new World(); w.ground = false;
		w.blocks.add(new BlockPos(0, -1, 0)); w.blocks.add(new BlockPos(1, 0, 0));
		BlockPos goal = new BlockPos(1, 1, 0);
		assertFalse(BorerWalkPath.find(w, BlockPos.ZERO, goal::equals, 2, 100, 3, true).nodes().isEmpty());
		w.blocks.add(new BlockPos(0, 2, 0));
		assertTrue(BorerWalkPath.find(w, BlockPos.ZERO, goal::equals, 2, 100, 3, true).nodes().isEmpty());
	}
	@Test void stepRequiresTheExistingStepCapabilityInsteadOfBlindJumping() {
		World w = new World(); w.ground = false;
		w.blocks.add(new BlockPos(0, -1, 0)); w.blocks.add(new BlockPos(1, 0, 0));
		BlockPos goal = new BlockPos(1, 1, 0);
		assertTrue(BorerWalkPath.find(w, BlockPos.ZERO, goal::equals, 2, 100, 3, false).nodes().isEmpty());
	}
	@Test void pitEdgeUsesBodyColumnNotTheNeighbouringSupportingBlock() {
		BlockPos body = new BlockPos(382674, 115, 311120), support = new BlockPos(382674, 115, 311119);
		assertEquals(body, BorerCenterPolicy.navigationColumn(body, support, true));
		assertEquals(support, BorerCenterPolicy.navigationColumn(body, support, false));
		assertTrue(BorerCenterPolicy.centerBeforeForward(.24));
		assertFalse(BorerCenterPolicy.centerBeforeForward(.1));
	}
}
