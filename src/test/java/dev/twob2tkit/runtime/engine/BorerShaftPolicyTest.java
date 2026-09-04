package dev.twob2tkit.runtime.engine;

import net.minecraft.core.Direction;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * 锁住向下挖截面：4×4 从脚下起，多出来的在右/前。
 */
final class BorerShaftPolicyTest {
	@Test
	void evenFourIsOneBehindLeftAndTwoAheadRight() {
		assertEquals(-1, BorerShaftPolicy.startOffset(4));
		assertEquals(2, BorerShaftPolicy.endOffset(4));
		assertEquals("西1东2", BorerShaftPolicy.spanLabel(-1, 2, "西", "东"));
		assertEquals("南1北2", BorerShaftPolicy.spanLabel(-1, 2, "南", "北"));
	}

	@Test
	void oddThreeIsCentered() {
		assertEquals(-1, BorerShaftPolicy.startOffset(3));
		assertEquals(1, BorerShaftPolicy.endOffset(3));
	}

	@Test
	void originHintNamesTheFootBlock() {
		assertEquals("4×4 从脚下这格  西1东2  南1北2",
			BorerShaftPolicy.originHint(4, 4, "西", "东", "南", "北"));
	}

	@Test
	void previewKeepsLockedHeadingWhenLookTurns() {
		assertEquals(Direction.NORTH,
			BorerShaftPolicy.headingForPreview(Direction.NORTH, Direction.EAST));
		assertEquals(Direction.WEST,
			BorerShaftPolicy.headingForPreview(Direction.WEST, Direction.SOUTH));
	}

	@Test
	void firstPressUsesCurrentLook() {
		assertEquals(Direction.EAST,
			BorerShaftPolicy.headingForPreview(null, Direction.EAST));
	}

	@Test
	void previewSliceCoversNextLayerAndHeadNotTheHilltop() {
		assertEquals(-1, BorerShaftPolicy.previewSliceMinDy());
		assertEquals(1, BorerShaftPolicy.previewSliceMaxDy());
		assertEquals(47, BorerShaftPolicy.previewSliceMinY(48));
		assertEquals(50, BorerShaftPolicy.previewSliceMaxYExclusive(48));
	}
}
