package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoModulesTest {
	public static class Module {
		boolean active;
		int toggles;
		Module(boolean active) { this.active = active; }
		public boolean isActive() { return active; }
		public void toggle() { active = !active; toggles++; }
	}
	@Test void restoresOnlyOriginallyActiveModulesAndCleanupIsIdempotent() throws Exception {
		var lease = new BorerCargoModules(); var active = new Module(true); var idle = new Module(false);
		lease.pause(active); lease.pause(idle);
		assertFalse(active.active); assertFalse(idle.active);
		lease.close(); lease.close();
		assertTrue(active.active); assertEquals(2, active.toggles); assertEquals(0, idle.toggles);
	}
	@Test void doesNotTurnOffAModuleManuallyReenabledDuringTrip() throws Exception {
		var lease = new BorerCargoModules(); var module = new Module(true);
		lease.pause(module); module.toggle(); lease.close();
		assertTrue(module.active); assertEquals(2, module.toggles);
	}
}
