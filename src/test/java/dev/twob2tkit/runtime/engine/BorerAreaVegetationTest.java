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
