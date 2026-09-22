package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.ArrayList;
import static org.junit.jupiter.api.Assertions.*;

class BorerStepCycleTest {
	@Test void inventoryUpdatesAreConsideredBeforeTheSameTickLandingCanTripTheGuard() throws Exception {
		var node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.class")) { new ClassReader(in).accept(node, 0); }
		var tick = node.methods.stream().filter(m -> m.name.equals("tick")).findFirst().orElseThrow();
		var calls = new ArrayList<String>();
		for (var insn : tick.instructions) if (insn instanceof MethodInsnNode call) calls.add(call.owner + "." + call.name);
		int pickup = calls.indexOf("dev/twob2tkit/runtime/engine/BorerLoot.hasInventoryProgress");
		int guard = calls.indexOf("dev/twob2tkit/runtime/engine/BorerStepCycle.observe");
		assertTrue(pickup >= 0 && guard > pickup);
	}
	@Test void actualQuartzPickupBetweenJumpsCannotAccumulateAFalseStepLoop() {
		var cycle = new BorerStepCycle();
		cycle.begin(new BlockPos(95217, 59, 99617), 95218.543, 59, 99617.515);
		assertFalse(cycle.observe(95218.116, 60, 99617.509));
		cycle.madeProgress(); // Inventory 259 -> 260, followed by confirmed mining/pickups.
		assertFalse(cycle.observe(95218.469, 59, 99617.574));
		assertFalse(cycle.observe(95218.519, 60.177, 99617.701));
		cycle.madeProgress(); // Inventory 262 -> 263 just before the reported stop.
		assertFalse(cycle.observe(95218.380, 59, 99617.299));
	}
	@Test void progressClearsOldFailuresButANewFailedAttemptStillStopsAfterTwoReturns() {
		var cycle = new BorerStepCycle(); var block = new BlockPos(0, 0, 1);
		cycle.begin(block, .5, 0, .5); cycle.observe(.5, 1, .5); cycle.observe(.5, 0, .5);
		cycle.madeProgress(); cycle.begin(block, .5, 0, .5);
		cycle.observe(.5, 1, .5); assertFalse(cycle.observe(.5, 0, .5));
		cycle.observe(.5, 1, .5); assertTrue(cycle.observe(.5, 0, .5));
	}
	@Test void revisitingTheSameRouteCellIsNotNewProgress() {
		var progress = new BorerWaypointProgress();
		assertTrue(progress.visit(new BlockPos(1, 64, 1)));
		assertFalse(progress.visit(new BlockPos(1, 64, 1)));
		assertTrue(progress.visit(new BlockPos(1, 65, 1)));
	}
	@Test void observedRepeatedRiseAndRollbackCannotContinueForever() {
		var cycle = new BorerStepCycle(); var block = new BlockPos(95185, 56, 99656);
		cycle.begin(block, 95185.7, 56, 99655.7);
		assertFalse(cycle.observe(95185.7, 57, 99655.798));
		assertFalse(cycle.observe(95185.7, 56, 99655.7));
		cycle.begin(block, 95185.7, 56, 99655.7);
		assertFalse(cycle.observe(95185.7, 57, 99655.798));
		assertTrue(cycle.observe(95185.7, 56, 99655.7));
	}
	@Test void movingOntoTheStepIsProgressAndDoesNotTriggerRollbackProtection() {
		var cycle = new BorerStepCycle(); cycle.begin(new BlockPos(0, 56, 1), .5, 56, .5);
		assertFalse(cycle.observe(.5, 57, 1.4));
		assertFalse(cycle.observe(.5, 56, .5));
		assertFalse(cycle.observe(.5, 57, .5));
		assertFalse(cycle.observe(.5, 56, .5));
	}
	@Test void differentStepOrNewSessionStartsWithFreshHistory() {
		var cycle = new BorerStepCycle(); cycle.begin(new BlockPos(0, 0, 1), 0, 0, 0);
		cycle.observe(0, 1, 0); cycle.observe(0, 0, 0);
		cycle.begin(new BlockPos(1, 0, 0), 0, 0, 0); cycle.observe(0, 1, 0);
		assertFalse(cycle.observe(0, 0, 0)); cycle.reset();
		assertFalse(cycle.observe(0, 0, 0));
	}
}
