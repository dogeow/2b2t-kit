package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class BorerMeleeProgressTest {
    private final UUID piglin = UUID.fromString("00000000-0000-0000-0000-000000000001");
    @Test void enabledMeteorWithoutHealthDamageGetsNormalMeleeFallbackAfterOneSecond() {
        var progress = new BorerMeleeProgress();
        assertFalse(progress.stalled(piglin, 100, 20));
        assertFalse(progress.stalled(piglin, 119, 20));
        assertTrue(progress.stalled(piglin, 120, 20));
        assertTrue(progress.stalled(piglin, 200, 20));
    }
    @Test void actualDamageRenewsNativeGraceButHealingOrMovementDoesNot() {
        var progress = new BorerMeleeProgress();
        progress.stalled(piglin, 0, 20);
        assertFalse(progress.stalled(piglin, 19, 12));
        assertFalse(progress.stalled(piglin, 38, 15));
        assertTrue(progress.stalled(piglin, 39, 15));
    }
    @Test void targetSwitchAndManualStopDoNotReuseAnotherTargetGrace() {
        var progress = new BorerMeleeProgress();
        progress.stalled(piglin, 0, 20);
        assertTrue(progress.stalled(piglin, 30, 20));
        assertFalse(progress.stalled(new UUID(0, 2), 31, 20));
        progress.clear();
        assertFalse(progress.stalled(piglin, 100, 20));
    }
    @Test void checkboxActivationAndAttackAttemptsCannotReleaseTheMiningGoal() {
        var session = new BorerCombatSession<String>();
        for (int tick = 0; tick <= 700; tick++) {
            session.beginTick(tick);
            session.observe(piglin, "piglin", true, false, true, 20);
            assertTrue(session.pending());
        }
        assertTrue(session.timedOut());
        session.beginTick(701);
        session.observe(piglin, "piglin", false, false, false, 20);
        assertTrue(session.pending(), "unload or lost line of sight is not a kill");
        session.beginTick(702);
        session.observe(piglin, "piglin", false, true, false, 0);
        assertFalse(session.pending());
    }
}
