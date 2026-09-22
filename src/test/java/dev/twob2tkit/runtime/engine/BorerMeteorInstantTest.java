package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerMeteorInstantTest {
	public static final class Setting { boolean value = true; public Boolean get() { return value; } }
	public static final class Repeat {
		public final BlockPos.MutableBlockPos blockPos = new BlockPos.MutableBlockPos(9,9,9);
		private Direction direction = Direction.NORTH;
		private final Setting pick = new Setting();
		boolean active, fail;
		final List<String> sent = new ArrayList<>();
		public boolean isActive() { return active; }
		public void sendPacket() { sent.add(blockPos.immutable()+":"+direction); if(fail)throw new IllegalStateException("unavailable"); }
	}
	@Test void chineseInstantRebreakIsUsableEvenWhenSpeedMineThresholdFailsInFlight() {
		var module = new Repeat(); var bridge = new BorerMeteorInstant(name -> name.equals("InstantRebreak")?module:null);
		assertFalse(bridge.allows(null,.15f));
		assertTrue(bridge.repeatAllows(true));
		bridge.finishRepeat(new BlockPos(1,0,0),Direction.WEST);
		bridge.finishRepeat(new BlockPos(2,0,0),Direction.UP);
		assertEquals(2,module.sent.size()); assertNotEquals(module.sent.get(0),module.sent.get(1));
		assertEquals(new BlockPos(9,9,9),module.blockPos); assertEquals(Direction.NORTH,module.direction);
		assertFalse(module.active);
	}
	@Test void onlyPickaxeSettingAndUnavailableModuleFallBackWithoutBlindPackets() {
		var module = new Repeat();var bridge = new BorerMeteorInstant(name -> module);
		assertFalse(bridge.repeatAllows(false));module.pick.value=false;assertTrue(bridge.repeatAllows(false));
		assertFalse(new BorerMeteorInstant(name -> null).repeatAllows(true));
		assertTrue(module.sent.isEmpty());
	}
	@Test void sendFailureStillRestoresTargetAndFace() {
		var module = new Repeat();module.fail=true;var bridge = new BorerMeteorInstant(name -> module);
		assertTrue(bridge.repeatAllows(true));
		assertThrows(IllegalStateException.class,()->bridge.finishRepeat(BlockPos.ZERO,Direction.DOWN));
		assertEquals(new BlockPos(9,9,9),module.blockPos);assertEquals(Direction.NORTH,module.direction);
	}
	@Test void independentlyReenabledBackgroundLoopIsNotAllowedToRaceTheQueue() {
		var module = new Repeat();module.active=true;var bridge = new BorerMeteorInstant(name -> module);
		assertTrue(bridge.repeatAllows(true));
		assertThrows(IllegalStateException.class,()->bridge.finishRepeat(BlockPos.ZERO,Direction.UP));
		assertTrue(module.sent.isEmpty());assertTrue(module.active);
	}
	@Test void conflictingLoopCannotKeepMiningTheJustStartedOwnedTargetAfterTheError() {
		var module=new Repeat();module.active=true;module.blockPos.set(BlockPos.ZERO);
		var bridge=new BorerMeteorInstant(name->module);assertTrue(bridge.repeatAllows(true));
		assertThrows(IllegalStateException.class,()->bridge.finishRepeat(BlockPos.ZERO,Direction.UP));
		assertEquals(Integer.MIN_VALUE,module.blockPos.getY());assertTrue(module.active);assertTrue(module.sent.isEmpty());
	}
}
