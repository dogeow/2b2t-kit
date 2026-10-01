package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.IntInsnNode;
import org.objectweb.asm.tree.LdcInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SnowSeedExpeditionWiringTest {
	@Test void bridgeAdvertisesReadOnlyLocatorAndAuthorizesBeforeStartingCruise() throws Exception {
		MethodNode dispatch = method("AutomationBridge", "dispatch");
		List<MethodInsnNode> calls = calls(dispatch);
		int authorize = index(calls, "SnowSeedExpedition", "authorizeNavigate");
		assertTrue(authorize >= 0);
		assertTrue(calls.subList(authorize+1,calls.size()).stream()
			.anyMatch(call->call.name.equals("deepCopy")),
			"host target must be injected before the active request is copied");
		assertTrue(calls.subList(authorize + 1, calls.size()).stream()
			.anyMatch(call -> call.name.equals("startExact")));
		assertTrue(calls(method("AutomationBridge", "snowSeedCandidates")).stream()
			.anyMatch(call -> call.owner.endsWith("/SnowSeedExpedition")
				&& call.name.equals("candidates")));
		var guardCalls=calls(method("AutomationBridge","guard"));
		assertTrue(guardCalls.stream().anyMatch(call->call.name.equals("pendingSnowReturnScope")));
		assertTrue(guardCalls.stream().anyMatch(call->call.name.equals("activeSnowNavigationScope")));
		assertTrue(calls(method("AutomationBridge","activeSnowNavigationScope")).stream()
			.anyMatch(call->call.owner.endsWith("/SnowSeedExpedition")
				&&call.name.equals("activeNavigation")));
		assertTrue(constants(method("AutomationBridge", "snapshot"))
			.contains("snow_seed_locator_protocol"));
		assertTrue(constants(method("AutomationBridge", "snapshot"))
			.contains("snow_seed_locator_available"));
		assertTrue(method("AutomationBridge", "dispatch").instructions.iterator().hasNext());
		boolean longBound = false;
		for (var instruction : method("AutomationBridge", "dispatch").instructions) {
			if (instruction instanceof LdcInsnNode value
					&& value.cst instanceof Integer number && number == 5400) longBound = true;
			if (instruction instanceof IntInsnNode value && value.operand == 5400) longBound = true;
		}
		assertTrue(longBound, "snow token cruise must not inherit the ordinary 600-second cap");
	}

	@Test void onlyExactNavigateScopesMayUseOrSettleAPermit(){
		var navigate=new com.google.gson.JsonObject();navigate.addProperty("op","navigate");
		for(String wrong:new String[]{"scan","mine_block","interact","unknown"}){
			var request=new com.google.gson.JsonObject();request.addProperty("op",wrong);
			assertFalse(SnowSeedExpedition.navigationOperation(request));
		}
		assertTrue(SnowSeedExpedition.navigationOperation(navigate));
		assertTrue(SnowSeedExpedition.settlementAllowed(false,true,true,true,true,false,false));
		assertFalse(SnowSeedExpedition.settlementAllowed(false,false,true,true,true,false,false));
		assertFalse(SnowSeedExpedition.settlementAllowed(false,true,false,true,true,false,false));
		assertFalse(SnowSeedExpedition.settlementAllowed(false,true,true,false,true,false,false));
		assertFalse(SnowSeedExpedition.settlementAllowed(false,true,true,true,true,true,false));
		assertTrue(SnowSeedExpedition.settlementAllowed(true,true,true,true,true,true,true));
		assertFalse(SnowSeedExpedition.settlementAllowed(true,true,true,true,true,true,false));
	}

	@Test void protectedPermitCapacityCannotEvictTheTwoHundredFiftySeventhRoute(){
		assertTrue(SnowSeedExpedition.capacityPossible(128,128));
		assertFalse(SnowSeedExpedition.capacityPossible(129,128));
		assertFalse(SnowSeedExpedition.capacityPossible(256,1));
		assertFalse(SnowSeedExpedition.capacityPossible(1,256));
		assertFalse(SnowSeedExpedition.cleanupEligible(true,true,false,false),
			"expired outbound in-flight remains owned by its controller deadline");
		assertFalse(SnowSeedExpedition.cleanupEligible(true,true,true,true),
			"expired return in-flight remains owned by its controller deadline");
		assertTrue(SnowSeedExpedition.cleanupEligible(true,true,true,false),
			"expired waiting-return permit can be released");
		assertTrue(SnowSeedExpedition.cleanupEligible(true,false,false,false));
	}

	@Test void everyTerminalPathUsesHostPermitSettlementAndDisconnectClearsAll()throws Exception{
		assertTrue(calls(method("AutomationBridge","finishSnowNavigation")).stream()
			.anyMatch(call->call.owner.endsWith("/SnowSeedExpedition")
				&&call.name.equals("navigationFinished")));
		assertTrue(calls(method("AutomationBridge","finish")).stream()
			.anyMatch(call->call.name.equals("finishSnowNavigation")));
		assertTrue(calls(method("AutomationBridge","cancelWork")).stream()
			.anyMatch(call->call.name.equals("finishSnowNavigation")));
		assertTrue(calls(method("AutomationBridge","afterDisconnectCleanup")).stream()
			.anyMatch(call->call.owner.endsWith("/SnowSeedExpedition")&&call.name.equals("clearAll")));
		long direct=calls(method("AutomationBridge","tick")).stream()
			.filter(call->call.owner.endsWith("/SnowSeedExpedition")
				&&call.name.equals("navigationFinished")).count();
		assertEquals(0,direct,"natural arrival must settle through finish, not a second direct call");
	}

	@Test void candidateReplyCodeHasNoRawSeedFieldAndTokensAreOpaque() throws Exception {
		var constants = constants(method("SnowSeedExpedition", "candidates"));
		assertFalse(constants.contains("seed"));
		assertTrue(constants.containsAll(List.of("x", "z", "biome", "available", "cursor",
			"next_cursor", "processed", "total", "done", "token")));
		String raw = "route-secret-token";
		String fingerprint = SnowSeedExpedition.tokenFingerprint(raw);
		assertNotEquals(raw, fingerprint);
		assertEquals(16, fingerprint.length());
		assertEquals(fingerprint, SnowSeedExpedition.tokenFingerprint(raw));
		var unavailable=SnowSeedExpedition.samplerUnavailableReply();
		assertEquals(1,unavailable.get("protocol").getAsInt());
		assertFalse(unavailable.get("available").getAsBoolean());
		assertEquals("sampler_unavailable",unavailable.get("reason").getAsString());
		assertFalse(unavailable.has("seed"));
	}

	@Test void returnCruiseHeightIsAlwaysInsideTheSafeOverworldBand() {
		assertEquals(160,SnowSeedExpedition.safeCruiseY(-64,200));
		assertEquals(316,SnowSeedExpedition.safeCruiseY(2048,200));
		assertEquals(200,SnowSeedExpedition.safeCruiseY(200,180));
		assertEquals(180,SnowSeedExpedition.safeCruiseY(Double.NaN,180));
		assertTrue(SnowSeedExpedition.safeHorizontal(100,200));
		assertFalse(SnowSeedExpedition.safeHorizontal(Double.NaN,200));
		assertFalse(SnowSeedExpedition.safeHorizontal(30_000_000,200));
		assertFalse(SnowSeedExpedition.safeHorizontal(100,Double.POSITIVE_INFINITY));
		assertTrue(SnowSeedExpedition.eligibleHome(
			new dev.twob2tkit.KitConfig.HomeTarget(10,20,200,"minecraft:overworld"),
			"minecraft:overworld"));
		assertFalse(SnowSeedExpedition.eligibleHome(
			new dev.twob2tkit.KitConfig.HomeTarget(Double.NaN,20,200,"minecraft:overworld"),
			"minecraft:overworld"));
		assertFalse(SnowSeedExpedition.eligibleHome(
			new dev.twob2tkit.KitConfig.HomeTarget(10,20,200,"minecraft:the_nether"),
			"minecraft:overworld"));
	}

	private MethodNode method(String owner, String name) throws Exception {
		var node = new ClassNode();
		try (var input = getClass().getResourceAsStream(
			"/dev/twob2tkit/" + (owner.equals("AutomationBridge") || owner.equals("SnowSeedExpedition")
				? "automation/" : "") + owner + ".class")) {
			assertNotNull(input);
			new ClassReader(input).accept(node, 0);
		}
		return node.methods.stream().filter(method -> method.name.equals(name))
			.findFirst().orElseThrow();
	}

	private List<MethodInsnNode> calls(MethodNode method) {
		var calls = new ArrayList<MethodInsnNode>();
		for (var instruction : method.instructions)
			if (instruction instanceof MethodInsnNode call) calls.add(call);
		return calls;
	}

	private List<String> constants(MethodNode method) {
		var values = new ArrayList<String>();
		for (var instruction : method.instructions)
			if (instruction instanceof LdcInsnNode value && value.cst instanceof String text)
				values.add(text);
		return values;
	}

	private int index(List<MethodInsnNode> calls, String owner, String name) {
		for (int index = 0; index < calls.size(); index++) {
			var call = calls.get(index);
			if (call.owner.endsWith("/" + owner) && call.name.equals(name)) return index;
		}
		return -1;
	}
}
