package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerMiningModulesHoldTest {
	private static final class Fake implements BorerMiningModules.Module {
		boolean on; Fake(boolean on) { this.on=on; }
		public boolean active() { return on; }
		public void enable() { on=true; }
		public void disable() { on=false; }
	}
	@Test void routeHoldReturnsSpeedMineButKeepsInstantRebreakPausedAndRestoresBoth() {
		var speed=new Fake(true); var rebreak=new Fake(true);
		var modules=new BorerMiningModules(name->name.equals("SpeedMine") ? speed : rebreak);
		modules.acquire();
		assertFalse(speed.on); assertFalse(rebreak.on);
		modules.holdSpeedMine(true);
		assertTrue(speed.on); assertFalse(rebreak.on);
		modules.holdSpeedMine(false);
		assertFalse(speed.on);
		modules.holdSpeedMine(true); modules.release();
		assertTrue(speed.on); assertTrue(rebreak.on);
		modules.holdSpeedMine(false);
		assertTrue(speed.on, "a late release after stopping must not switch the player's module off");
	}
	@Test void aModuleThePlayerHadOffIsNeverEnabled() {
		var speed=new Fake(false);
		var modules=new BorerMiningModules(name->speed);
		modules.acquire(); modules.holdSpeedMine(true);
		assertFalse(speed.on);
	}
}
