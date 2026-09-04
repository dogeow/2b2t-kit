package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class BorerAreaThinkPolicyTest {
	@Test
	void thinksOnlyAfterStandingStillWithoutMining() {
		assertFalse(BorerAreaThinkPolicy.stuck(5, false));
		assertFalse(BorerAreaThinkPolicy.stuck(20, true));
		assertTrue(BorerAreaThinkPolicy.stuck(20, false));
		assertEquals(20, BorerAreaThinkPolicy.stuckTicksAfterHazard(5));
		assertEquals(40, BorerAreaThinkPolicy.stuckTicksAfterHazard(40));
		assertFalse(BorerAreaThinkPolicy.moved(0.01));
		assertTrue(BorerAreaThinkPolicy.moved(0.05));
	}

	@Test
	void sceneKeyIsCoarseNotExactCoordinates() {
		assertEquals(
			"go|fly|same|wall|out|near",
			BorerAreaThinkPolicy.sceneKey(true, true, "same", true, "out", true));
		assertEquals("below", BorerAreaThinkPolicy.destRel(-13));
		assertEquals("same", BorerAreaThinkPolicy.destRel(-0.8));
		assertFalse(BorerAreaThinkPolicy.allowFlyUp(false, "above"));
		assertFalse(BorerAreaThinkPolicy.allowFlyUp(true, "below"));
		assertTrue(BorerAreaThinkPolicy.allowFlyUp(true, "above"));
		assertEquals("out", BorerAreaThinkPolicy.lookKind(true, false));
	}

	@Test
	void successfulMovesComeBeforeUntestedThenFailed() {
		int[] wins = new int[BorerAreaThinkPolicy.Move.values().length];
		int[] losses = new int[wins.length];
		wins[BorerAreaThinkPolicy.Move.SKIP_SHAFT.ordinal()] = 3;
		losses[BorerAreaThinkPolicy.Move.MINE_LOOKED.ordinal()] = 2;
		List<BorerAreaThinkPolicy.Move> order = BorerAreaThinkPolicy.order(wins, losses);
		assertEquals(BorerAreaThinkPolicy.Move.SKIP_SHAFT, order.get(0));
		assertEquals(BorerAreaThinkPolicy.Move.MINE_LOOKED, order.get(order.size() - 1));
		assertTrue(order.indexOf(BorerAreaThinkPolicy.Move.MINE_FRONT)
			< order.indexOf(BorerAreaThinkPolicy.Move.MINE_LOOKED));
	}

	@Test
	void skipShaftHasCooldown() {
		assertTrue(BorerAreaThinkPolicy.allowSkipShaft(0));
		assertFalse(BorerAreaThinkPolicy.allowSkipShaft(10));
		assertTrue(BorerAreaThinkPolicy.keepTrying(10));
		assertFalse(BorerAreaThinkPolicy.keepTrying(24));
	}

	@Test
	void asksAiOnlyOnCooldownAndOpportunity() {
		assertFalse(BorerAreaThinkPolicy.shouldAskAi(false, false, 3000, true, 0));
		assertFalse(BorerAreaThinkPolicy.shouldAskAi(true, true, 3000, true, 0));
		assertFalse(BorerAreaThinkPolicy.shouldAskAi(true, false, 100, true, 9));
		// 全失败：短冷却 200 ticks 可 ask
		assertFalse(BorerAreaThinkPolicy.shouldAskAi(true, false, 199, true, 0));
		assertTrue(BorerAreaThinkPolicy.shouldAskAi(true, false, 200, true, 0));
		assertTrue(BorerAreaThinkPolicy.shouldAskAi(true, false, 2400, true, 0));
		// 例行请教（挖过几口井）仍要 2400
		assertFalse(BorerAreaThinkPolicy.shouldAskAi(true, false, 200, false, 5));
		assertTrue(BorerAreaThinkPolicy.shouldAskAi(true, false, 2400, false, 5));
		// 同场景反复卡住 >=3：短冷却可 ask
		assertFalse(BorerAreaThinkPolicy.shouldAskAi(true, false, 199, false, 0, 3));
		assertTrue(BorerAreaThinkPolicy.shouldAskAi(true, false, 200, false, 0, 3));
		assertEquals("busy", BorerAreaThinkPolicy.askSkipReason(true, true, false, 3000, true, 0, 0));
		assertEquals("no-grok-or-key", BorerAreaThinkPolicy.askSkipReason(false, false, false, 3000, true, 0, 0));
		assertEquals("cooldown-100/200", BorerAreaThinkPolicy.askSkipReason(false, true, false, 100, true, 0, 0));
		assertEquals("wait-fail-or-shafts", BorerAreaThinkPolicy.askSkipReason(false, true, false, 3000, false, 0, 0));
		assertFalse(BorerAreaThinkPolicy.askTimedOut(20));
		assertTrue(BorerAreaThinkPolicy.askTimedOut(1400));
		assertFalse(BorerAreaThinkPolicy.askTimedOut(1400, true));
		assertTrue(BorerAreaThinkPolicy.askTimedOut(12000, true));
		assertFalse(BorerAreaThinkPolicy.shouldPatchCode(true, true, false));
		assertFalse(BorerAreaThinkPolicy.shouldPatchCode(true, false, true));
		assertTrue(BorerAreaThinkPolicy.shouldPatchCode(true, true, true));
	}

	@Test
	void acceptThinkWinNeedsHalfBlockOrMining() {
		assertFalse(BorerAreaThinkPolicy.acceptThinkWin(false, 0.2));
		assertTrue(BorerAreaThinkPolicy.acceptThinkWin(false, 0.25));
		assertFalse(BorerAreaThinkPolicy.acceptDescendWin(63.2, 63.0));
		assertTrue(BorerAreaThinkPolicy.acceptDescendWin(63.2, 62.2));
		assertTrue(BorerAreaThinkPolicy.acceptThinkWin(true, 0.0));
		assertFalse(BorerAreaThinkPolicy.acceptThinkWin(false, 0.04));
	}

	@Test
	void liveMiningCreditsAMoveAndParsesAiNames() {
		assertEquals(BorerAreaThinkPolicy.Move.MINE_FRONT,
			BorerAreaThinkPolicy.liveMove(true, true, true, false));
		assertEquals(BorerAreaThinkPolicy.Move.FLY_LEVEL,
			BorerAreaThinkPolicy.liveMove(true, false, true, false));
		assertEquals(BorerAreaThinkPolicy.Move.DESCEND,
			BorerAreaThinkPolicy.liveMove(true, false, false, true));
		assertEquals(BorerAreaThinkPolicy.Move.MINE_LOOKED,
			BorerAreaThinkPolicy.parseMove("mine_looked"));
		assertEquals(
			"{\"prefer\":[\"MINE_LOOKED\"]}",
			BorerAreaThinkPolicy.stripJsonFence("```json\n{\"prefer\":[\"MINE_LOOKED\"]}\n```"));
		BorerAreaThinkAsk.Advice advice = BorerAreaThinkAsk.parse(
			"{\"choices\":[{\"message\":{\"content\":\"{\\\"prefer\\\":[\\\"MINE_LOOKED\\\"],\\\"avoid\\\":[\\\"FLY_UP\\\"],\\\"lesson\\\":\\\"先挖准星\\\"}\"}}]}");
		assertEquals(BorerAreaThinkPolicy.Move.MINE_LOOKED, advice.prefer.get(0));
		assertEquals(BorerAreaThinkPolicy.Move.FLY_UP, advice.avoid.get(0));
		assertEquals("先挖准星", advice.lesson);
		BorerAreaThinkAsk.Advice grok = BorerAreaThinkAsk.parse(
			"{\"text\":\"{\\\"prefer\\\":[\\\"DESCEND\\\"],\\\"avoid\\\":[\\\"FLY_UP\\\"],\\\"lesson\\\":\\\"往下\\\"}\"}");
		assertEquals(BorerAreaThinkPolicy.Move.DESCEND, grok.prefer.get(0));
		assertEquals("往下", grok.lesson);
		BorerAreaThinkAsk.Advice raw = BorerAreaThinkAsk.parse(
			"{\"prefer\":[\"MINE_FRONT\"],\"avoid\":[\"SKIP_SHAFT\"],\"lesson\":\"贴脸挖\"}");
		assertEquals(BorerAreaThinkPolicy.Move.MINE_FRONT, raw.prefer.get(0));
		assertTrue(BorerAreaThinkAsk.hasAdvice(raw));
		assertFalse(BorerAreaThinkAsk.hasAdvice(BorerAreaThinkAsk.parse("{\"type\":\"error\",\"message\":\"nope\"}")));
		BorerAreaThinkAsk.Advice patched = BorerAreaThinkAsk.parse(
			"{\"prefer\":[],\"avoid\":[],\"lesson\":\"先挖挡路\",\"patched\":true,\"deployed\":false,\"version\":\"1.6.276\"}");
		assertTrue(patched.patched);
		assertFalse(patched.deployed);
		assertEquals("1.6.276", patched.version);
		assertTrue(BorerAreaThinkAsk.hasAdvice(patched));
	}

	@Test
	void grokChildStdinIsReadableNotDiscardWrite() {
		assertEquals(ProcessBuilder.Redirect.Type.WRITE, ProcessBuilder.Redirect.DISCARD.type());
		ProcessBuilder builder = new ProcessBuilder("true");
		BorerAreaThinkPolicy.discardStdin(builder);
		assertEquals(ProcessBuilder.Redirect.Type.READ, builder.redirectInput().type());
	}

	@Test
	void grokHomeEnvWinsOverHmclUserHome() {
		assertEquals("/Users/sam", BorerAreaThinkPolicy.realHome(
			Path.of("/Users/sam/.grok"), "/Users/sam", "/Applications"));
		assertEquals("/Users/sam", BorerAreaThinkPolicy.realHome(
			Path.of("/Users/sam/.grok"), null, "/Applications"));
		assertEquals("/Applications", BorerAreaThinkPolicy.realHome(null, null, "/Applications"));
	}

	@Test
	void discoversGrokFromHomeEnvWhenUserHomeDiffers(@TempDir Path tmp) throws Exception {
		Path terminalHome = tmp.resolve("sam");
		Path fakeUserHome = tmp.resolve("minecraft-user");
		Files.createDirectories(terminalHome.resolve(".grok/bin"));
		Files.writeString(terminalHome.resolve(".grok/auth.json"), "{}");
		Files.writeString(terminalHome.resolve(".grok/bin/grok"), "x");
		Path found = BorerAreaThinkPolicy.discoverGrokHome(null, terminalHome.toString(), fakeUserHome.toString());
		assertEquals(terminalHome.resolve(".grok").toAbsolutePath(), found);
		assertTrue(BorerAreaThinkPolicy.isGrokBin(found.resolve("bin/grok")));
		assertEquals(found.resolve("bin/grok").toAbsolutePath(),
			BorerAreaThinkPolicy.discoverGrokBin(found, null));
	}

	@Test
	void localGrokLoginCountsAsAskableWithoutApiKey(@TempDir Path grokHome) throws Exception {
		Files.createDirectories(grokHome.resolve("bin"));
		Path bin = grokHome.resolve("bin/grok");
		Files.writeString(bin, "#!/bin/sh\n");
		bin.toFile().setExecutable(true);
		assertFalse(BorerAreaThinkAsk.grokAvailable(grokHome, null));
		Files.writeString(grokHome.resolve("auth.json"), "{}");
		assertTrue(BorerAreaThinkAsk.grokAvailable(grokHome, null));
		assertEquals(bin.toAbsolutePath(), BorerAreaThinkAsk.grokBin(grokHome, null));
		assertTrue(BorerAreaThinkAsk.promptText("go|fly|same|wall|out|near", "MINE_LOOKED w=1 l=0", "stuck")
			.contains("scene=go|fly|same|wall|out|near"));
		assertEquals("1.6.276", BorerAreaThinkDeploy.nextPatchVersion("1.6.275"));
		Path repo = grokHome.resolve("repo");
		Files.createDirectories(repo.resolve("src/client/java/dev/twob2tkit/runtime/engine"));
		Files.writeString(repo.resolve("gradlew"), "#!/bin/sh\n");
		assertTrue(BorerAreaThinkPolicy.looksLikeRepo(repo));
		assertEquals(repo.toAbsolutePath(),
			BorerAreaThinkPolicy.sourceRoot(repo.toString(), null, grokHome.resolve("missing")));
		assertTrue(BorerAreaThinkAsk.patchPromptText(
			"go|fly|same|wall|out|near", "MINE_LOOKED w=1 l=0", "stuck", "1.6.275",
			repo, grokHome.resolve("reply.json")).contains("Never edit host"));
	}
}
