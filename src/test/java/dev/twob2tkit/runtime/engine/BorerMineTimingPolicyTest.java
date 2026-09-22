package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** 锁住：人手点一下能碎的石头按破坏进度只按一两拍，裂纹满了立刻换块。 */
final class BorerMineTimingPolicyTest {
	@Test
	void keysSeparateToolEnchantHasteAndBlock() {
		String stone = BorerMineTimingPolicy.key("minecraft:netherite_pickaxe", "efficiency:5", 0, 0, false, "minecraft:stone");
		String deep = BorerMineTimingPolicy.key("minecraft:netherite_pickaxe", "efficiency:5", 0, 0, false, "minecraft:deepslate");
		String iron = BorerMineTimingPolicy.key("minecraft:iron_pickaxe", "efficiency:5", 0, 0, false, "minecraft:stone");
		String noEff = BorerMineTimingPolicy.key("minecraft:netherite_pickaxe", "", 0, 0, false, "minecraft:stone");
		String haste = BorerMineTimingPolicy.key("minecraft:netherite_pickaxe", "efficiency:5", 2, 0, false, "minecraft:stone");
		String wet = BorerMineTimingPolicy.key("minecraft:netherite_pickaxe", "efficiency:5", 0, 0, true, "minecraft:stone");
		assertNotEquals(stone, deep);
		assertNotEquals(stone, iron);
		assertNotEquals(stone, noEff);
		assertNotEquals(stone, haste);
		assertNotEquals(stone, wet);
	}

	@Test
	void graniteLikeProgressIsATwoTickTap() {
		float granite = 0.577f;
		assertEquals(2, BorerMineTimingPolicy.ticksToBreak(granite));
		assertTrue(BorerMineTimingPolicy.tapSized(granite));
		assertTrue(BorerMineTimingPolicy.shouldClick(null, granite, true, false, 0));
		assertTrue(BorerMineTimingPolicy.shouldHold(null, granite, 0, false));
		assertTrue(BorerMineTimingPolicy.shouldHold(null, granite, 1, false));
		assertTrue(BorerMineTimingPolicy.shouldHold(null, granite, 2, false));
		assertTrue(BorerMineTimingPolicy.shouldHold(null, granite, 1, true));
	}

	@Test
	void instaProgressClicksOnceNeverHolds() {
		assertEquals(1, BorerMineTimingPolicy.ticksToBreak(1.0f));
		assertTrue(BorerMineTimingPolicy.shouldClick(null, 1.0f, true, false, 0));
		assertFalse(BorerMineTimingPolicy.shouldHold(null, 1.0f, 0, false));
	}

	@Test
	void fullCracksDoNotReleaseAnExistingNonInstantBlock() {
		assertTrue(BorerMineTimingPolicy.crackComplete(9));
		assertTrue(BorerMineTimingPolicy.crackComplete(10));
		assertFalse(BorerMineTimingPolicy.crackComplete(8));
		assertTrue(BorerMineTimingPolicy.shouldHold(null, 0.577f, 2, true));
		assertTrue(BorerMineTimingPolicy.shouldHold(null, 0.577f, 30, false));
	}

	@Test
	void netherGoldKeepsHoldingAfterCrackUntilAir() {
		float netherGold = 0.289f;
		assertEquals(4, BorerMineTimingPolicy.ticksToBreak(netherGold));
		assertFalse(BorerMineTimingPolicy.tapSized(netherGold));
		assertTrue(BorerMineTimingPolicy.shouldHold(null, netherGold, 4, true));
		assertTrue(BorerMineTimingPolicy.shouldHold(null, netherGold, 20, true));
	}

	@Test
	void rememberCapsHoldToVanillaNeed() {
		assertEquals(new BorerMineTimingPolicy.Memory(true, 0), BorerMineTimingPolicy.remember(true, 12, 1.0f));
		assertEquals(new BorerMineTimingPolicy.Memory(false, 2), BorerMineTimingPolicy.remember(true, 12, 0.577f));
		assertNull(BorerMineTimingPolicy.remember(true, 0, 0.2f));
	}

	@Test
	void combineKeepsFasterBreak() {
		BorerMineTimingPolicy.Memory slow = new BorerMineTimingPolicy.Memory(false, 12);
		BorerMineTimingPolicy.Memory fast = new BorerMineTimingPolicy.Memory(false, 2);
		assertEquals(fast, BorerMineTimingPolicy.combine(slow, fast));
		assertEquals(new BorerMineTimingPolicy.Memory(true, 0),
			BorerMineTimingPolicy.combine(slow, new BorerMineTimingPolicy.Memory(true, 0)));
	}

	@Test void staleInstantAndOneTickMemoriesCannotCancelAnUnfinishedNetherrackBlock() {
		for (var memory : new BorerMineTimingPolicy.Memory[]{
			new BorerMineTimingPolicy.Memory(true, 0), new BorerMineTimingPolicy.Memory(false, 1)}) {
			for (int tick : new int[]{0, 1, 2, 20, 1120}) assertTrue(BorerMineTimingPolicy.shouldHold(memory, .6667f, tick, false));
		}
	}

	@Test void delayedBreakingStillCompletesWithContinuousInputInsteadOfRepeatedCancellation() {
		var memory = new BorerMineTimingPolicy.Memory(true, 0);
		double damage = 0;
		for (int tick = 0; tick < 6 && damage < 1; tick++) {
			boolean held = BorerMineTimingPolicy.shouldHold(memory, .6667f, tick, tick > 2);
			// Model delayed server progress: slower than the client's predicted two ticks.
			damage = held ? damage + .2 : 0;
		}
		assertTrue(damage >= 1);
		assertFalse(BorerMineTimingPolicy.shouldHold(memory, 0, 6, false));
	}
}
