package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BorerRecoveryEvidenceTest {
    @Test void reselectingWithoutAnotherConfirmedClearNeverCountsAgain() {
        var history = new BorerReappearance();
        BlockPos pos = BlockPos.ZERO;
        history.confirmedClear(pos, 1);
        assertEquals(0, history.observe(pos, 2, false, false));
        assertEquals(0, history.observe(pos, 2, true, true));
        assertEquals(1, history.observe(pos, 3, true, false));
        assertEquals(0, history.observe(pos, 4, true, false));
        history.confirmedClear(pos, 5);
        assertEquals(2, history.observe(pos, 6, true, false));
        history.confirmedClear(pos, 7);
        assertTrue(BorerMiningPolicy.suppressReappearedBlock(history.observe(pos, 8, true, false)));
        history.confirmedClear(pos, 250);
        assertEquals(1, history.observe(pos, 251, true, false));
    }

    @Test void sustainedFlyingAscentAndInterruptedStallAreDistinguished() {
        var progress = new BorerAscentProgress();
        BlockPos goal = BlockPos.ZERO.above(10);
        for (int tick = 0; tick <= 80; tick++) {
            assertFalse(progress.stalled(goal, tick, tick * .1, true));
        }
        assertFalse(progress.stalled(goal, 81, 8.5, true));
        for (int tick = 83; tick < 131; tick += 2) {
            assertFalse(progress.stalled(goal, tick, 8.5, true));
        }
        assertTrue(progress.stalled(goal, 131, 8.5, true));
        assertFalse(progress.stalled(goal.above(), 132, 8.5, true));
    }
}
