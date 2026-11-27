package dev.twob2tkit.combat;

import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CombatActivityTest {
    @Test void legacyModuleLabelStillWins() {
        assertEquals("盾构", CombatActivity.describe("盾构", List.of("材料任务"), "navigate"));
    }

    @Test void materialJobsAndOtherFeaturesAreNoLongerIdle() {
        assertEquals("材料任务", CombatActivity.describe(CombatActivity.IDLE, List.of("材料任务"), ""));
        assertEquals("农场管家+自动围箱", CombatActivity.describe(CombatActivity.IDLE, List.of("农场管家", "自动围箱"), "settle"));
    }

    @Test void externalControlIsNamedWhenNoFeatureRuns() {
        assertEquals("外部控制:navigate", CombatActivity.describe(CombatActivity.IDLE, List.of(), "navigate"));
        assertEquals(CombatActivity.IDLE, CombatActivity.describe(CombatActivity.IDLE, List.of(), ""));
        assertEquals(CombatActivity.IDLE, CombatActivity.describe(CombatActivity.IDLE, List.of(), null));
    }
}
