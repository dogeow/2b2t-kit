package dev.twob2tkit.runtime.engine;

import java.util.*;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerGhostBlockTest {
	@Test void vanillaPredictionBindingsResolveAndMissingAcknowledgementsHaveABoundedWait() {
		var confirmation = new BorerMiningConfirmation();
		for (int tick = 1; tick < 100; tick++) { assertEquals(tick, confirmation.update(1)); assertFalse(confirmation.expired()); }
		confirmation.update(1); assertTrue(confirmation.expired());
		assertEquals(0, confirmation.update(0)); assertFalse(confirmation.expired());
		confirmation.update(3); confirmation.reset(); assertEquals(1, confirmation.update(1));
	}

	@Test void replanningTheSameTwoWaypointsCannotResetLootTimeoutForever() {
		var route = new BorerWaypointProgress(); var loot = new BorerLootPolicy.Progress();
		long previous = 0; boolean timedOut = false;
		for (int tick = 0; tick < 250; tick++) {
			if (tick % 20 == 0) route.visit(new BlockPos(95142 + tick / 20 % 2, 67, 99654));
			timedOut |= loot.tick(2 + (tick % 2) * .4, false, false, route.count() != previous);
			previous = route.count();
		}
		assertEquals(2, route.count()); assertTrue(timedOut);
	}

	@Test void newDetourWaypointsRemainRealProgressAndANewGoalCanReuseCells() {
		var route = new BorerWaypointProgress(); var loot = new BorerLootPolicy.Progress(); long previous = 0;
		for (int tick = 0; tick < 600; tick++) {
			if (tick % 20 == 0) route.visit(new BlockPos(tick / 20, 64, 0));
			assertFalse(loot.tick(10 + tick * .01, false, false, route.count() != previous)); previous = route.count();
		}
		long old = route.count(); route.resetTarget(); route.visit(new BlockPos(0, 64, 0)); assertEquals(old + 1, route.count());
	}

	private static class Module implements BorerMiningModules.Module {
		boolean enabled; int enables, disables;
		Module(boolean enabled) { this.enabled = enabled; }
		public boolean active() { return enabled; }
		public void enable() { enabled = true; enables++; }
		public void disable() { enabled = false; disables++; }
	}
	@Test void conflictingMiningModulesArePausedAndRestoredWithoutChangingOriginallyDisabledOnes() {
		Module speed = new Module(true), repeat = new Module(false); var names = new ArrayList<String>();
		var lease = new BorerMiningModules(name -> { names.add(name); return name.equals("SpeedMine") ? speed : repeat; });
		assertEquals(1, lease.acquire()); assertFalse(speed.enabled); assertFalse(repeat.enabled);
		assertEquals(1, lease.acquire()); assertEquals(1, speed.disables);
		lease.release(); assertTrue(speed.enabled); assertFalse(repeat.enabled);
		assertEquals(List.of("SpeedMine", "InstantRebreak"), names);
	}
	@Test void partialAcquireFailureRestoresTheAlreadyPausedModule() {
		Module speed = new Module(true);
		var lease = new BorerMiningModules(name -> { if (name.equals("SpeedMine")) return speed; throw new ReflectiveOperationException("missing"); });
		assertThrows(IllegalStateException.class, lease::acquire); assertTrue(speed.enabled);
	}
	@Test void areaCooperatesWithSpeedMineButDisablesRepeatingTheSameBlock() {
		Module speed = new Module(true), repeat = new Module(true);
		var lease = new BorerMiningModules(name -> name.equals("SpeedMine") ? speed : repeat);
		assertEquals(1,lease.acquire(true));assertTrue(speed.enabled);assertFalse(repeat.enabled);
		assertTrue(lease.instantRebreakRequested());
		lease.release();assertTrue(speed.enabled);assertTrue(repeat.enabled);assertEquals(0,speed.disables);
		assertFalse(lease.instantRebreakRequested());
	}
	@Test void switchingFromAreaToReturnModeRestoresThenAcquiresExclusiveMining() {
		Module speed = new Module(true), repeat = new Module(false);
		var lease = new BorerMiningModules(name -> name.equals("SpeedMine") ? speed : repeat);
		assertEquals(0,lease.acquire(true));assertTrue(speed.enabled);
		assertEquals(1,lease.acquire());assertFalse(speed.enabled);
		lease.release();assertTrue(speed.enabled);assertFalse(repeat.enabled);
	}
	@Test void manualReenableIsNotToggledAgainDuringCleanup() {
		Module speed = new Module(true); var lease = new BorerMiningModules(name -> name.equals("SpeedMine") ? speed : null);
		lease.acquire(); speed.enable(); lease.release(); assertEquals(1, speed.enables); assertTrue(speed.enabled);
	}
	@Test void actualTickWaitsForVanillaPredictionsAndNeverTreatsEstimatedMiningTimeAsCompletion() throws Exception {
		var node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.class")) { new ClassReader(in).accept(node, 0); }
		var tick = node.methods.stream().filter(m -> m.name.equals("tick")).findFirst().orElseThrow();
		List<String> calls = new ArrayList<>();
		for (var insn : tick.instructions) if (insn instanceof MethodInsnNode call) calls.add(call.owner + "." + call.name);
		assertFalse(calls.stream().anyMatch(c -> c.endsWith(".tapFinished")));
		assertTrue(calls.contains("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.waitForMiningConfirmation"));
		var home = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/BorerHome.class")) { new ClassReader(in).accept(home, 0); }
		var handle = home.methods.stream().filter(m -> m.name.equals("handle")).findFirst().orElseThrow();
		var methodCalls = new ArrayList<String>();
		for (var insn : handle.instructions) if (insn instanceof MethodInsnNode call) methodCalls.add(call.name);
		assertEquals("waitForMiningConfirmation", methodCalls.getFirst(), "Tool-wear return also waits before any movement");
	}

	@Test void miningTimeoutRunsBeforeAimRetryBranchesCanReturnEarly() throws Exception {
		var node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.class")) { new ClassReader(in).accept(node, 0); }
		var tick = node.methods.stream().filter(m -> m.name.equals("tick")).findFirst().orElseThrow();
		List<String> calls = new ArrayList<>();
		for (var insn : tick.instructions) if (insn instanceof MethodInsnNode call) calls.add(call.name);
		assertTrue(calls.indexOf("handleMiningTimeout") >= 0);
		assertTrue(calls.indexOf("handleMiningTimeout") < calls.indexOf("keepMiningInReach"),
			"The aligned-but-not-attacking branch previously bypassed timeout for over 1100 ticks");
	}
}
