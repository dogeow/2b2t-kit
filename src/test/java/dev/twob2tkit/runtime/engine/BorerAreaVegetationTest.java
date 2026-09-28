package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaVegetationTest {
	private static final BlockPos MIN = new BlockPos(760976,49,797914);
	private static final BlockPos MAX = new BlockPos(760977,66,797915);
	private static final BlockPos GRASS_LOWER = new BlockPos(760977,67,797914);
	private static final BlockPos GRASS_UPPER = GRASS_LOWER.above();
	private static final Pose ARRIVAL = new Pose(760977.0009031498,68.95889868565064,
		797914.9464534238,0,0,0);

	private World observedWorld(boolean vegetationPassable) {
		return pos -> {
			if (pos.equals(GRASS_LOWER) || pos.equals(GRASS_UPPER)) {
				return vegetationPassable ? BorerAreaVegetation.classify(Cell.SOLID,"minecraft:tall_grass",true,true) : Cell.SOLID;
			}
			return pos.getX()>=MIN.getX() && pos.getX()<=MAX.getX()
				&& pos.getZ()>=MIN.getZ() && pos.getZ()<=MAX.getZ()
				&& pos.getY()>=MIN.getY() && pos.getY()<=MAX.getY() ? Cell.SOLID : Cell.AIR;
		};
	}

	@Test void actualFractionalArrivalPreviouslyHitTheUpperTallGrassBeforeMining() {
		var plan = new BorerAreaPlan(MIN,MAX,ARRIVAL);
		Command command = null;
		for (int tick=0; tick<8; tick++) {
			command=plan.step(observedWorld(false),ARRIVAL);
			if (command.action()==Action.BLOCKED) break;
		}
		assertNotNull(command);
		assertEquals(Action.BLOCKED,command.action());
		assertEquals(GRASS_UPPER,command.block());
		assertEquals(0,plan.completed());
	}

	@Test void actualEntryWithPassableGrassCentersThenMinesTheSelectedTopLayer() {
		var plan = new BorerAreaPlan(MIN,MAX,ARRIVAL);
		Pose pose = ARRIVAL;
		boolean centeredX=false, centeredZ=false, descended=false;
		for (int tick=0; tick<20; tick++) {
			Command command=plan.step(observedWorld(true),pose);
			assertNotEquals(Action.BLOCKED,command.action());
			assertNotEquals(Action.DONE,command.action());
			assertEquals(0,plan.completed(),"Passing grass must not count an unmined column as complete");
			switch (command.action()) {
				case X, Z, UP, DOWN -> {
					centeredX |= command.action()==Action.X;
					centeredZ |= command.action()==Action.Z;
					descended |= command.action()==Action.DOWN;
					pose=new Pose(command.x(),command.y(),command.z(),0,0,0);
				}
				case MINE, MINE_DOWN -> {
					assertTrue(centeredX && centeredZ && descended);
					assertEquals(new BlockPos(760977,66,797914),command.block());
					assertEquals(760977.5,pose.x(),0.00001);
					assertEquals(797914.5,pose.z(),0.00001);
					return;
				}
				default -> { }
			}
		}
		fail("No first mining command reached for the observed tall-grass entry");
	}

	@Test void onlyKnownVegetationWithBothEmptyCollisionAndFluidBecomesAir() {
		for (String id : new String[]{"minecraft:short_grass","minecraft:tall_grass","minecraft:fern","minecraft:poppy"}) {
			assertEquals(Cell.AIR,BorerAreaVegetation.classify(Cell.SOLID,id,true,true));
			assertEquals(Cell.SOLID,BorerAreaVegetation.classify(Cell.SOLID,id,false,true));
			assertEquals(Cell.SOLID,BorerAreaVegetation.classify(Cell.SOLID,id,true,false));
		}
	}

	@Test void onlyTheObservedShortGrassDirectlyAboveTheSelectedBlockCanBeCleared() {
		BlockPos target = new BlockPos(760973,66,797910);
		BlockPos min = new BlockPos(760959,64,797902), max = new BlockPos(761021,78,797926);
		BlockPos tuft = target.above();
		assertTrue(BorerAreaVegetation.clearableRayOccluder(target,tuft,min,max,"minecraft:short_grass",true,true));
		assertFalse(BorerAreaVegetation.clearableRayOccluder(target,tuft.east(),min,max,"minecraft:short_grass",true,true));
		assertFalse(BorerAreaVegetation.clearableRayOccluder(target,tuft.above(),min,max,"minecraft:short_grass",true,true));
		assertFalse(BorerAreaVegetation.clearableRayOccluder(target,tuft,min,new BlockPos(max.getX(),66,max.getZ()),"minecraft:short_grass",true,true));
		assertFalse(BorerAreaVegetation.clearableRayOccluder(target,tuft,min,max,"minecraft:grass_block",true,true));
		assertFalse(BorerAreaVegetation.clearableRayOccluder(target,tuft,min,max,"minecraft:short_grass",false,true));
		assertFalse(BorerAreaVegetation.clearableRayOccluder(target,tuft,min,max,"minecraft:short_grass",true,false));
	}

	@Test void twoBlockGrassRequiresBothPartsInTheSameSelectedShaftBounds() {
		BlockPos target = new BlockPos(760988,67,797910);
		BlockPos min = new BlockPos(760959,64,797902), max = new BlockPos(761021,78,797926);
		assertTrue(BorerAreaVegetation.clearableTallGrassPair(target,target.above(2),min,max));
		assertFalse(BorerAreaVegetation.clearableTallGrassPair(target,target.above(),min,max));
		assertFalse(BorerAreaVegetation.clearableTallGrassPair(target,target.above(2).east(),min,max));
		assertFalse(BorerAreaVegetation.clearableTallGrassPair(target,target.above(2),min,new BlockPos(max.getX(),68,max.getZ())));
		assertFalse(BorerAreaVegetation.clearableTallGrassPair(target,target.above(2),new BlockPos(min.getX(),69,min.getZ()),max));
	}

	@Test void eitherVerticalDigActionMayClearVerifiedGrassButTravelAndHorizontalMayNot() {
		assertTrue(BorerAreaVegetation.clearableAction(Phase.DIG,Action.MINE));
		assertTrue(BorerAreaVegetation.clearableAction(Phase.DIG,Action.MINE_DOWN));
		assertFalse(BorerAreaVegetation.clearableAction(Phase.DIG,Action.DOWN));
		assertFalse(BorerAreaVegetation.clearableAction(Phase.LOWER_TO_TOP,Action.MINE_DOWN));
		assertFalse(BorerAreaVegetation.clearableAction(Phase.HORIZONTAL,Action.MINE));
	}

	@Test void liveAreaRunnerVerifiesTheRealRayAndWaitsForServerEvidenceBeforeContinuing() throws Exception {
		var node=new ClassNode();
		try (var input=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/BorerAreaRunner.class")) {
			assertNotNull(input);new ClassReader(input).accept(node,0);
		}
		var mine=node.methods.stream().filter(m->m.name.equals("mine")).findFirst().orElseThrow();
		var tick=node.methods.stream().filter(m->m.name.equals("tick")).findFirst().orElseThrow();
		var clear=node.methods.stream().filter(m->m.name.equals("tryClearGrass")).findFirst().orElseThrow();
		var await=node.methods.stream().filter(m->m.name.equals("tickClearingGrass")).findFirst().orElseThrow();
		assertTrue(calls(mine,"tryClearGrass") >= 0 && calls(mine,"tryClearGrass") < calls(mine,"startObservedBreak"),
			"Failed target aim must be checked for a verified grass occluder before mining the target");
		assertTrue(calls(clear,"clearableAction") >= 0 && calls(clear,"clearableAction") < calls(clear,"startObservedBreak"));
		assertTrue(calls(clear,"clearableRayOccluder") >= 0 && calls(clear,"clearableRayOccluder") < calls(clear,"clipView"));
		assertTrue(calls(clear,"clearableTallGrassPair") >= 0 && calls(clear,"clearableTallGrassPair") < calls(clear,"clipView"));
		assertTrue(callCount(clear,"getValue") >= 2,"Both tall-grass halves must be type-checked before one click");
		assertTrue(callCount(clear,"safeGrassPart") >= 2,"Both halves must pass protection and liquid checks");
		assertTrue(calls(clear,"clipView") >= 0 && calls(clear,"clipView") < calls(clear,"startObservedBreak"));
		assertTrue(calls(clear,"manualMovementHeld") >= 0 && calls(clear,"manualMovementHeld") < calls(clear,"startObservedBreak"));
		assertTrue(calls(tick,"manualMovementHeld") >= 0 && calls(tick,"manualMovementHeld") < calls(tick,"tickClearingGrass"),
			"Physical manual movement must stop a pending clear before it can claim confirmation");
		assertTrue(calls(tick,"clearGrassState") >= 0 && calls(tick,"clearGrassState") < calls(tick,"tickClearingGrass"));
		assertTrue(calls(await,"pending") >= 0 && calls(await,"pending") < calls(await,"isAir"));
		assertTrue(callCount(await,"pending") >= 2 && callCount(await,"getBlockState") >= 2,
			"Upper and lower grass must both be server-confirmed air before shaft mining resumes");
		assertEquals(-1,calls(await,"startObservedBreak"),"A pending clear must never issue another blind click");
	}

	private static int calls(org.objectweb.asm.tree.MethodNode method,String name) {
		int index=0;
		for (var instruction:method.instructions) {
			if (instruction instanceof MethodInsnNode call && call.name.equals(name)) return index;
			index++;
		}
		return -1;
	}
	private static long callCount(org.objectweb.asm.tree.MethodNode method,String name) {
		long count=0;
		for (var instruction:method.instructions)
			if (instruction instanceof MethodInsnNode call && call.name.equals(name)) count++;
		return count;
	}

	@Test void fluidsProtectionUnknownsAndDangerousOrUnrecognizedBlocksStayBlocked() {
		for (Cell cell : new Cell[]{Cell.BEDROCK,Cell.LIQUID,Cell.PROTECTED,Cell.UNLOADED})
			assertEquals(cell,BorerAreaVegetation.classify(cell,"minecraft:tall_grass",true,true));
		for (String id : new String[]{"minecraft:fire","minecraft:soul_fire","minecraft:cobweb",
			"minecraft:wither_rose","minecraft:sweet_berry_bush","minecraft:powder_snow",
			"minecraft:nether_portal","minecraft:end_portal","minecraft:chest","minecraft:white_concrete"})
			assertEquals(Cell.SOLID,BorerAreaVegetation.classify(Cell.SOLID,id,true,true),id);
	}

	@Test void compiledLiveRunnerUsesTheClassifierAfterExistingProtectionChecks() throws Exception {
		var node=new ClassNode();
		try (var input=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/BorerAreaRunner.class")) {
			assertNotNull(input);new ClassReader(input).accept(node,0);
		}
		var method=node.methods.stream().filter(m->m.name.equals("cell")).findFirst().orElseThrow();
		int position=0, fluid=-1, entity=-1, seal=-1, restricted=-1, classify=-1;
		for (var instruction:method.instructions) {
			if (instruction instanceof MethodInsnNode call) {
				if (call.name.equals("getFluidState") && fluid<0) fluid=position;
				if (call.name.equals("getBlockEntity")) entity=position;
				if (call.name.equals("isProtectedSealBlock")) seal=position;
				if (call.name.equals("blockActionRestricted")) restricted=position;
				if (call.owner.endsWith("/BorerAreaVegetation") && call.name.equals("classify")) classify=position;
			}
			position++;
		}
		assertTrue(fluid>=0 && entity>=0 && seal>=0 && restricted>=0 && classify>Math.max(Math.max(fluid,entity),Math.max(seal,restricted)));
	}
}
