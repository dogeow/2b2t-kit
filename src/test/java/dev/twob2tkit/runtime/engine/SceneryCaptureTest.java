package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class SceneryCaptureTest {
	@Test void unlitReloadedOrOnlyJustLoadedChunksAreNotReady() {
		assertFalse(SceneryCapturePolicy.ready(false, true, true, 20));
		assertFalse(SceneryCapturePolicy.ready(true, false, true, 20));
		assertFalse(SceneryCapturePolicy.ready(true, true, false, 20));
		assertFalse(SceneryCapturePolicy.ready(true, true, true, 9));
		assertTrue(SceneryCapturePolicy.ready(true, true, true, 10));
	}
	@Test void pendingBatchAndBackpressurePauseFlightButACompletedReturnMayContinue() {
		assertTrue(SceneryCapturePolicy.drain(32, 0, false, false));
		assertTrue(SceneryCapturePolicy.drain(1, 257, false, false));
		assertTrue(SceneryCapturePolicy.drain(1, 0, true, false));
		assertFalse(SceneryCapturePolicy.drain(0, 0, true, true));
	}
	@Test void onlyTwentyConsecutiveIdleObservationsCommitABatch() {
		var quiet = new SceneryCapturePolicy.Quiet();
		for (int i = 0; i < 19; i++) assertFalse(quiet.observe(true, true));
		assertFalse(quiet.observe(true, false));
		for (int i = 0; i < 19; i++) assertFalse(quiet.observe(true, true));
		assertTrue(quiet.observe(true, true)); assertFalse(quiet.observe(false, true));
	}
	public static class Executor { private final AtomicInteger currentRunning = new AtomicInteger(); }
	public static class Service {
		private final Executor executor = new Executor(); int queued; boolean live = true;
		public boolean isLive() { return live; } public int numJobs() { return queued; }
	}
	public static class Owner { private final Service service = new Service(); }
	@Test void emptyQueueIsNotIdleWhileAnIngestOrSaveIsStillExecuting() {
		var owner = new Owner(); assertTrue(SceneryVoxy.idleService(owner));
		owner.service.executor.currentRunning.set(1); assertFalse(SceneryVoxy.idleService(owner));
		owner.service.executor.currentRunning.set(0); owner.service.queued = 1; assertFalse(SceneryVoxy.idleService(owner));
		owner.service.live = false; assertThrows(IllegalStateException.class, () -> SceneryVoxy.idleService(owner));
	}
}
