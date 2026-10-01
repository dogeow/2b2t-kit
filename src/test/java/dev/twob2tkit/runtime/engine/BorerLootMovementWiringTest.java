package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

/** The real pickup path must use the guards verified by BorerLootPolicyTest. */
class BorerLootMovementWiringTest {
	private MethodNode method(String name) throws Exception {
		ClassNode node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/BorerLoot.class")) {
			new ClassReader(in).accept(node, 0);
		}
		return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
	}
	private List<String> calls(String name) throws Exception {
		List<String> result = new ArrayList<>();
		for (var instruction : method(name).instructions) {
			if (instruction instanceof MethodInsnNode call) result.add(call.name);
		}
		return result;
	}
	@Test void airborneCollectionWaitsBeforeReplanningAndRetainsTheBlocker() throws Exception {
		var handle = calls("handle");
		assertTrue(handle.indexOf("waitForLanding") >= 0);
		assertTrue(handle.indexOf("waitForLanding") < handle.indexOf("walk"));
		assertTrue(handle.indexOf("waitForLanding") < handle.indexOf("visibleObstructionToward"));
		var landing = calls("waitForLanding");
		assertTrue(landing.containsAll(List.of("isFlying", "onGround", "holdStill")));
		assertFalse(landing.contains("clearMiningTarget"));
		assertFalse(landing.contains("setMiningTarget"));
	}
	@Test void movementChecksTheBodyAndSupportBeforeItsBoundedJumpPulse() throws Exception {
		var moving = calls("walkToward");
		assertTrue(moving.containsAll(List.of("hopBody", "noCollision", "isStandable", "groundHop", "press")));
		assertTrue(moving.indexOf("noCollision") < moving.indexOf("groundHop"));
		assertTrue(moving.indexOf("isStandable") < moving.indexOf("groundHop"));
		assertTrue(moving.indexOf("groundHop") < moving.indexOf("press"));
		assertTrue(moving.indexOf("hopObstruction") < moving.indexOf("press"));
		assertFalse(moving.contains("setDeltaMovement"));
	}
	@Test void clearanceKeepsFloorProtectionAndRequiresARealVisibleMineableBlock() throws Exception {
		assertTrue(calls("hopObstruction").containsAll(List.of("canPlanMine", "isStandingSupport", "isUnsafeFloorMine", "inReach", "canSeeBlock", "getCollisionShape")));
	}
}
