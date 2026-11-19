package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class OreTunnelSearchTest {
	@Test void singleTapFallsBackOnlyForAnObservedUnchangedSolidAfterTheGracePeriod() {
		assertFalse(BorerOreTunnel.resumeSingleFace(7,true,false,true));
		assertFalse(BorerOreTunnel.resumeSingleFace(20,false,false,true));
		assertFalse(BorerOreTunnel.resumeSingleFace(20,true,true,true));
		assertFalse(BorerOreTunnel.resumeSingleFace(20,true,false,false));
		assertTrue(BorerOreTunnel.resumeSingleFace(8,true,false,true));
	}

	@Test void digsReachableWallBeforeWalkingAndKeepsMovementCursorAtTheTurn() {
		var start=BlockPos.ZERO;
		var path=List.of(start,start.east(),start.east(2),start.east(3),start.east(3).south());
		assertEquals(3,BorerOreTunnel.clearanceIndex(path,0,5,p->p.equals(start.east(3))?1:0));
		assertEquals(1,BorerOreTunnel.clearanceIndex(path,1,5,p->p.equals(start.east(2))?-1:0));
		assertEquals(1,BorerOreTunnel.clearanceIndex(path,1,5,p->p.equals(path.getLast())?1:0));
	}
	@Test void walkingNeedsContinuousFloorAndOnlyATinyLandingDrop() {
		var body=new net.minecraft.world.phys.AABB(.2,30.1,.2,.8,31.9,.8);
		var dest=new net.minecraft.world.phys.Vec3(2.5,30,.5);
		assertTrue(BorerOreTunnel.groundLane(body,dest,b->b.getY()==29));
		assertFalse(BorerOreTunnel.groundLane(body,dest,b->b.getX()!=1));
		assertFalse(BorerOreTunnel.groundLane(body,dest.add(0,1,0),b->true));
		assertFalse(BorerOreTunnel.groundLane(body.move(0,.5,0),dest,b->true));
	}

	@Test void planningProgressStaysAtTheFrontWhenTheHudClipsCoordinates() {
		var ore = new BlockPos(95042,21,99606);
		assertTrue(BorerOreTunnel.planningStatus(758,40,ore).startsWith("已查 758 个站位 · 规划剩余 13 秒"));
		assertTrue(BorerOreTunnel.planningStatus(12961,280,ore).startsWith("已查 12961 个站位 · 规划剩余 1 秒"));
	}

	private final Map<BlockPos,Integer> cells = new HashMap<>();
	private final Set<BlockPos> floors = new HashSet<>();
	private final OreTunnelSearch.World world = new OreTunnelSearch.World() {
		public int cell(BlockPos p) { return cells.getOrDefault(p,-1); }
		public boolean floor(BlockPos p) { return floors.contains(p); }
	};

	private void tunnel(BlockPos feet) {
		cells.put(feet, 0);
		cells.put(feet.above(), 0);
	}

	private OreTunnelSearch finished(BlockPos goal) {
		var search = new OreTunnelSearch(BlockPos.ZERO, goal);
		search.advance(world, 1, Long.MAX_VALUE);
		// A sealed destination can be rejected on the very first tick.
		assertTrue(search.path.isEmpty());
		for (int i=0; i<10000 && !search.done; i++) search.advance(world, 8, Long.MAX_VALUE);
		assertTrue(search.done);
		return search;
	}

	@Test void provesTheEntireExcavationAndDetourBeyond48BeforeReturningAnyStep() {
		var ore = new BlockPos(0,0,5);
		for (int x=0; x<=61; x++) {
			tunnel(new BlockPos(x,0,0));
			tunnel(new BlockPos(x,0,4));
		}
		for (int z=1; z<4; z++) tunnel(new BlockPos(61,0,z));
		cells.put(new BlockPos(61,1,2),1);
		floors.add(new BlockPos(0,-1,4));
		var route=finished(ore).path;
		assertEquals(new BlockPos(0,0,4),route.getLast());
		assertTrue(route.contains(new BlockPos(61,0,2)));
		// Lava or unloaded headroom blocks the far turn. No partial route may be executed.
		cells.put(new BlockPos(61,1,2),-1);
		assertTrue(finished(ore).path.isEmpty());
	}

	@Test void sealedMineFaceDoesNotFloodTheSurroundingCave() {
		var ore = new BlockPos(12,-3,0);
		var search = new OreTunnelSearch(BlockPos.ZERO,ore);
		search.advance(new OreTunnelSearch.World() {
			public int cell(BlockPos p) { return p.distManhattan(ore)<=3 ? -1 : 0; }
			public boolean floor(BlockPos p) { return true; }
		},1,Long.MAX_VALUE);
		assertTrue(search.done);
		assertTrue(search.path.isEmpty());
		assertEquals(0,search.expanded());
	}

	@Test void descendingStairNeedsClearHeadroomAndASafeLanding() {
		var ore=new BlockPos(2,-1,0);
		tunnel(BlockPos.ZERO);
		var next=new BlockPos(1,-1,0);
		for (int i=0;i<3;i++) cells.put(next.above(i),1);
		floors.add(next.below());
		assertEquals(next,finished(ore).path.getLast());
		floors.clear();
		assertTrue(finished(ore).path.isEmpty());
	}
}
