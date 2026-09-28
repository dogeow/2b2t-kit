package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.*;

class BorerMiningStallAdvisorTest {
	@TempDir Path temp;
	private final BorerMiningStallAdvisor.Incident incident = new BorerMiningStallAdvisor.Incident(
		"mine", "DIG", 12, "pickaxe", "stone", "near_full", "healthy", "none");

	private static JsonObject answer(String choice, double confidence, double pause, double retry) {
		JsonObject probabilities = new JsonObject();
		probabilities.addProperty("pause", pause); probabilities.addProperty("retry_once", retry);
		JsonObject selected = new JsonObject(); selected.addProperty("type", "choice");
		selected.addProperty("choice", choice); selected.addProperty("confidence", confidence);
		selected.add("probabilities", probabilities);
		JsonObject answers = new JsonObject(); answers.add("action", selected);
		JsonObject result = new JsonObject(); result.addProperty("model", "offline-jev");
		result.add("answers", answers);
		JsonObject usage = new JsonObject(); usage.addProperty("input_tokens", 30);
		usage.addProperty("output_tokens", 4); result.add("usage", usage);
		return result;
	}
	private static JsonObject answerAmong(String choice) {
		JsonObject probabilities = new JsonObject();
		for (String candidate : List.of("pause", "wait_once", "retry_once", "rescan"))
			probabilities.addProperty(candidate, candidate.equals(choice) ? .91 : .03);
		JsonObject selected = new JsonObject(); selected.addProperty("type", "choice");
		selected.addProperty("choice", choice); selected.addProperty("confidence", .9);
		selected.add("probabilities", probabilities);
		JsonObject answers = new JsonObject(); answers.add("action", selected);
		JsonObject result = new JsonObject(); result.addProperty("model", "offline-jev");
		result.add("answers", answers); return result;
	}
	@Test void allFourAdviceIdsCanBeRecordedWithoutAnyGameControllerInTheProvider() {
		for (String choice : List.of("pause", "wait_once", "retry_once", "rescan")) {
			var advisor = new BorerMiningStallAdvisor(temp.resolve(choice + ".jsonl"),
				request -> answerAmong(choice), Runnable::run, () -> 900_000L);
			List<BorerMiningStallAdvisor.Decision> decisions = new ArrayList<>();
			advisor.consult("local-" + choice, incident, true, true, true, decisions::add);
			assertEquals(choice, decisions.getFirst().choice());
			assertEquals("jev", decisions.getFirst().source());
		}
	}

	@Test void deidentifiedRequestOffersOnlyNativeActionsAndWritesAnOutcome() throws Exception {
		Path log = temp.resolve("stalls.jsonl");
		AtomicInteger calls = new AtomicInteger();
		var advisor = new BorerMiningStallAdvisor(log, request -> {
			calls.incrementAndGet();
			assertEquals("jev-latest", request.get("model").getAsString());
			assertEquals("DIG", request.getAsJsonObject("state").getAsJsonObject("scene").get("phase").getAsString());
			assertEquals(2, request.getAsJsonObject("questions").getAsJsonObject("action").getAsJsonObject("criteria").size());
			assertFalse(request.toString().contains("server.example"));
			assertFalse(request.toString().contains("world_session"));
			assertFalse(request.toString().contains("position"));
			return answer("retry_once", .92, .09, .91);
		}, Runnable::run, () -> 1_000_000L);
		List<BorerMiningStallAdvisor.Decision> received = new ArrayList<>();
		advisor.consult("private-target-1", incident, false, true, false, received::add);
		assertEquals(1, calls.get());
		assertEquals("retry_once", received.getFirst().choice());
		advisor.receipt(received.getFirst(), "advice_recorded_mining_paused_no_action");
		advisor.outcome(received.getFirst(), "paused_pending_explicit_restart");
		String written = Files.readString(log);
		assertTrue(written.contains("prompt_summary"));
		assertTrue(written.contains("advice_recorded_mining_paused_no_action"));
		assertTrue(written.contains("paused_pending_explicit_restart"));
		assertFalse(written.contains("private-target-1"));
		assertFalse(written.contains("coordinates"));
	}

	@Test void repeatStallUsesCacheAndUncertainOrUnofferedReplyPauses() {
		AtomicInteger calls = new AtomicInteger();
		var advisor = new BorerMiningStallAdvisor(temp.resolve("cache.jsonl"), request -> {
			calls.incrementAndGet(); return answer("retry_once", .9, .1, .9);
		}, Runnable::run, () -> 2_000_000L);
		List<BorerMiningStallAdvisor.Decision> decisions = new ArrayList<>();
		advisor.consult("same-target", incident, false, true, false, decisions::add);
		advisor.consult("same-target", incident, false, true, false, decisions::add);
		assertEquals(1, calls.get());
		assertEquals("cache", decisions.get(1).source());

		var uncertain = new BorerMiningStallAdvisor(temp.resolve("uncertain.jsonl"),
			request -> answer("retry_once", .4, .1, .9), Runnable::run, () -> 2_000_000L);
		uncertain.consult("k", incident, false, true, false, decisions::add);
		assertEquals("pause", decisions.get(2).choice());
		var unoffered = new BorerMiningStallAdvisor(temp.resolve("unoffered.jsonl"),
			request -> answer("invented_command", .99, .01, .99), Runnable::run, () -> 2_000_000L);
		unoffered.consult("k", incident, false, true, false, decisions::add);
		assertEquals("pause", decisions.get(3).choice());
		assertEquals("invalid_response", decisions.get(3).reason());
	}

	@Test void ackUncertaintyCanOnlyWaitOrPauseAndSinglePauseSkipsProvider() {
		AtomicInteger calls = new AtomicInteger();
		var advisor = new BorerMiningStallAdvisor(temp.resolve("ack.jsonl"), request -> {
			calls.incrementAndGet(); throw new AssertionError("No network should be scheduled");
		}, Runnable::run, () -> 3_000_000L);
		var ack = new BorerMiningStallAdvisor.Incident("server_ack", "DIG", 5, "pickaxe", "stone", "roomy", "healthy", "timeout");
		List<BorerMiningStallAdvisor.Decision> decisions = new ArrayList<>();
		advisor.consult("ack", ack, false, false, false, decisions::add);
		assertEquals(0, calls.get());
		assertEquals("pause", decisions.getFirst().choice());
		assertEquals(List.of("pause", "wait_once"), List.copyOf(BorerMiningStallAdvisor.choices(true, false, false).keySet()));
	}
	@Test void optInIsRequiredEvenWhenAProviderAndRecoveryChoiceAreAvailable() throws Exception {
		Path marker = temp.resolve("jev-mining-opt-in.txt");
		assertFalse(BorerMiningStallAdvisor.optInEnabled(marker));
		Files.writeString(marker, "yes\n");
		assertFalse(BorerMiningStallAdvisor.optInEnabled(marker));
		Files.writeString(marker, "area_stall_v1\n");
		assertTrue(BorerMiningStallAdvisor.optInEnabled(marker));
		AtomicInteger calls = new AtomicInteger();
		Path log = temp.resolve("disabled.jsonl");
		var advisor = new BorerMiningStallAdvisor(log, request -> {
			calls.incrementAndGet(); return answer("retry_once", .9, .1, .9);
		}, Runnable::run, () -> 3_500_000L, () -> false);
		List<BorerMiningStallAdvisor.Decision> decisions = new ArrayList<>();
		advisor.consult("k", incident, false, true, false, decisions::add);
		assertEquals(0, calls.get());
		assertEquals("pause", decisions.getFirst().choice());
		assertEquals("opt_in_required", decisions.getFirst().reason());
		assertFalse(Files.exists(temp.resolve("jev-mining-budget.json")));
	}
	@Test void removingOptInBeforeQueuedRequestPreventsNetworkCall() {
		AtomicBoolean enabled = new AtomicBoolean(true);
		AtomicInteger calls = new AtomicInteger();
		List<Runnable> queued = new ArrayList<>();
		var advisor = new BorerMiningStallAdvisor(temp.resolve("revoked.jsonl"), request -> {
			calls.incrementAndGet(); return answer("retry_once", .9, .1, .9);
		}, queued::add, () -> 3_600_000L, enabled::get);
		List<BorerMiningStallAdvisor.Decision> decisions = new ArrayList<>();
		advisor.consult("k", incident, false, true, false, decisions::add);
		assertEquals(1, queued.size());
		enabled.set(false);
		queued.getFirst().run();
		assertEquals(0, calls.get());
		assertEquals("opt_in_required", decisions.getFirst().reason());
	}

	@Test void freshStallsStillConsultAfterManyCallsAndNetworkFailuresStaySanitized() throws Exception {
		Path log = temp.resolve("unlimited.jsonl");
		AtomicInteger calls = new AtomicInteger();
		var advisor = new BorerMiningStallAdvisor(log, request -> {
			if (calls.incrementAndGet() <= 125)
				throw new java.io.IOException("secret server.example coordinate 10,20,30");
			return answer("retry_once", .9, .1, .9);
		}, Runnable::run, () -> 4_000_000L);
		for (int i = 0; i < 125; i++) {
			advisor.consult("distinct-" + i, incident, false, true, false,
				decision -> {
					assertEquals("pause", decision.choice());
					assertEquals("provider_unavailable", decision.reason());
				});
		}
		List<BorerMiningStallAdvisor.Decision> decisions = new ArrayList<>();
		advisor.consult("fresh-after-125", incident, false, true, false, decisions::add);
		assertEquals(126, calls.get());
		assertEquals("jev", decisions.getFirst().source());
		assertEquals("retry_once", decisions.getFirst().choice());
		var reloaded = new BorerMiningStallAdvisor(log, request -> {
			calls.incrementAndGet(); return answer("retry_once", .9, .1, .9);
		}, Runnable::run, () -> 4_000_000L);
		reloaded.consult("fresh-after-reload", incident, false, true, false, decisions::add);
		assertEquals(127, calls.get());
		assertEquals("jev", decisions.get(1).source());
		assertFalse(Files.exists(temp.resolve("jev-mining-budget.json")));
		assertFalse(Files.readString(log).contains("server.example"));
		assertFalse(Files.readString(log).contains("10,20,30"));
	}
}
