package dev.twob2tkit.compat;

import net.minecraft.util.thread.BlockableEventLoop;
import org.junit.jupiter.api.Test;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class ClientLogoutQueueTest {
	private static final class Queue extends BlockableEventLoop<Runnable> {
		Queue() { super("logout-test", false); }
		@Override protected boolean shouldRun(Runnable r) { return true; }
		@Override protected Thread getRunningThread() { return Thread.currentThread(); }
		@Override public Runnable wrapRunnable(Runnable r) { return r; }
		@Override protected void doRunTask(Runnable r) { r.run(); }
		void drain() { runAllTasks(); }
	}
	@Test void logoutIsQueuedEvenWhenRequestedOnTheClientThread() {
		Queue queue = new Queue(); AtomicInteger disconnected = new AtomicInteger();
		queue.schedule(disconnected::incrementAndGet);
		assertEquals(0, disconnected.get(), "Must not clear the player in the calling listener");
		assertEquals(1, queue.getPendingTasksCount());
		queue.drain(); assertEquals(1, disconnected.get());
	}
	@Test void reconnectBeforeTheQueuedTaskRunsDoesNotDisconnectTheNewSession() {
		Queue queue = new Queue(); Object oldWorld = new Object(), oldConnection = new Object();
		Object[] session = {oldWorld, oldConnection}; AtomicInteger disconnected = new AtomicInteger();
		queue.schedule(() -> { if (ClientWorldGuard.sameSession(oldWorld, session[0], oldConnection, session[1])) disconnected.incrementAndGet(); });
		session[0] = new Object(); session[1] = new Object();
		queue.drain(); assertEquals(0, disconnected.get());
	}
}
