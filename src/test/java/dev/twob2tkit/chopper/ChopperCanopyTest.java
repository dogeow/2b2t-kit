package dev.twob2tkit.chopper;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import java.util.*;
import java.io.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChopperCanopyTest {
	static Map<BlockPos,Character> fixture() throws Exception {
		Map<BlockPos,Character> map=new HashMap<>();
		try(var reader=new BufferedReader(new InputStreamReader(ChopperCanopyTest.class.getResourceAsStream("/chopper-crown.txt")))){
			for(String row:reader.lines().toList()){String[] p=row.split(" ");map.put(new BlockPos(Integer.parseInt(p[0]),Integer.parseInt(p[1]),Integer.parseInt(p[2])),p[3].charAt(0));}
		}return map;
	}
	static ChopperCanopy.World world(Map<BlockPos,Character> m){return new ChopperCanopy.World(){
		public boolean wood(BlockPos p){return m.getOrDefault(p,' ' )=='L';}
		public boolean leaf(BlockPos p){return m.getOrDefault(p,' ' )=='F';}
	};}
	static Set<BlockPos> component(Map<BlockPos,Character> m,BlockPos seed){
		Set<BlockPos> found=new HashSet<>();List<BlockPos> queue=new ArrayList<>();found.add(seed);queue.add(seed);
		for(int i=0;i<queue.size();i++){BlockPos p=queue.get(i);for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++){
			BlockPos n=p.offset(x,y,z);if(m.getOrDefault(n,' ' )=='L'&&found.add(n))queue.add(n);
		}}return found;
	}
	@Test void actualSeparatedThreeAndTenLogBranchesBecomeOneThirteenLogCrownFromEitherSide() throws Exception {
		var map=fixture();var a=component(map,new BlockPos(-1,9,-1));var b=component(map,new BlockPos(3,8,0));
		assertEquals(3,a.size());assertEquals(10,b.size());
		var crown=ChopperCanopy.collect(world(map),a,80);var other=ChopperCanopy.collect(world(map),b,80);
		assertTrue(crown.complete());assertEquals(13,crown.logs().size());assertEquals(crown.logs(),other.logs());
		assertFalse(crown.logs().contains(new BlockPos(9,2,-2)),"nearby separate tree stays outside this crown");
	}
	@Test void removingTheLockedBranchOrDecayingLeavesDoesNotHideAResidualLog() throws Exception {
		var map=fixture();var crown=ChopperCanopy.collect(world(map),component(map,new BlockPos(3,8,0)),80);
		BlockPos last=new BlockPos(-1,10,-1);
		for(BlockPos p:crown.witness())if(!p.equals(last))map.remove(p);
		assertEquals(Set.of(last),ChopperCanopy.remaining(world(map),crown.witness()));
		map.remove(last);assertTrue(ChopperCanopy.remaining(world(map),crown.witness()).isEmpty());
	}
	@Test void nonNaturalLeafDecorationDoesNotJoinSeparateLogs(){
		Map<BlockPos,Character> map=new HashMap<>();map.put(BlockPos.ZERO,'L');map.put(new BlockPos(3,0,0),'L');
		map.put(new BlockPos(1,0,0),'P');map.put(new BlockPos(2,0,0),'P');
		assertEquals(Set.of(BlockPos.ZERO),ChopperCanopy.collect(world(map),Set.of(BlockPos.ZERO),80).logs());
	}
	@Test void capturedCrownCanBeCoveredUsingSingleFloatingWorkBlocksWithoutPillars() throws Exception {
		var map=fixture();var crown=ChopperCanopy.collect(world(map),component(map,new BlockPos(3,8,0)),80);
		Set<BlockPos> remaining=new HashSet<>(crown.logs());Vec3 position=new Vec3(5.23,17.2,5.75);int placements=0;
		var w=new ChopperPlatformPlan.World(){
			public boolean clear(BlockPos p){return p.getX()>=-15&&p.getX()<=15&&p.getY()>=-1&&p.getY()<=22&&p.getZ()>=-10&&p.getZ()<=21&&!map.containsKey(p);}
			public boolean replaceable(BlockPos p){return clear(p);}
			public boolean floor(BlockPos p){return map.getOrDefault(p,' ' )=='#';}
		};
		while(!remaining.isEmpty()&&placements<10){
			var plan=ChopperPlatformPlan.choose(w,position,remaining,3.9);assertNotNull(plan,"no work position for "+remaining);
			assertEquals(plan.feet(),plan.route().getLast());
			for(BlockPos n:plan.route())assertTrue(w.clear(n)&&w.clear(n.above()));
			BlockPos platform=plan.feet().below();
			if(plan.platform()){assertTrue(w.clear(platform));map.put(platform,'D');}
			Vec3 eye=Vec3.atBottomCenterOf(plan.feet()).add(0,1.62,0);
			var removed=remaining.stream().filter(b->ChopperPlatformPlan.distanceSquared(eye,b)<3.65*3.65).toList();
			assertFalse(removed.isEmpty());for(BlockPos b:removed){remaining.remove(b);map.remove(b);}
			// Dismantle the one block while flying before changing work positions.
			if(plan.platform())map.remove(platform);
			assertFalse(map.containsValue('D'));position=Vec3.atBottomCenterOf(plan.feet()).add(0,.12,0);placements++;
		}
		assertTrue(remaining.isEmpty());assertTrue(placements<=6);
	}
}
