package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.cruise.CruiseCeilingPolicy;

/**
 * 锁住：升空只挖正头顶。前上方准星打到隔壁列的深板岩不算。
 */
final class CruiseCeilingPolicyTest {
	@Test
	void sideWallIsNotOverhead() {
		assertTrue(CruiseCeilingPolicy.inAscentColumn(17922, 7898, 17922, 17922, 7898, 7898));
		assertFalse(CruiseCeilingPolicy.inAscentColumn(17921, 7898, 17922, 17922, 7898, 7898));
		assertFalse(CruiseCeilingPolicy.inAscentColumn(17920, 7899, 17922, 17922, 7898, 7898));
		assertFalse(CruiseCeilingPolicy.acceptLookHit(false));
		assertTrue(CruiseCeilingPolicy.acceptLookHit(true));
	}

	@Test
	void lowerBlockingBlockIsMinedFirst() {
		int overHead = CruiseCeilingPolicy.ascentOrder(-1, -2, 1.0);
		int fartherUp = CruiseCeilingPolicy.ascentOrder(0, -2, 0.5);
		int side = CruiseCeilingPolicy.ascentOrder(-1, -2, 4.0);
		assertTrue(overHead < fartherUp);
		assertTrue(overHead < side);
	}
}
