package dev.twob2tkit.combat;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CombatDamageLabelTest {
    @Test void beeAndWitherEffectTicksAreNamedInsteadOfUnknown() {
        assertEquals("中毒", CombatDamageLabel.fallback("magic", true, false));
        assertEquals("中毒", CombatDamageLabel.fallback(null, true, false));
        assertEquals("凋零", CombatDamageLabel.fallback("wither", false, true));
        assertEquals("凋零", CombatDamageLabel.fallback(null, true, true));
        assertEquals("魔法", CombatDamageLabel.fallback("indirectMagic", false, false));
        assertEquals("饥饿", CombatDamageLabel.fallback("starve", false, false));
    }

    @Test void unexplainedLossStaysUnknownAndPoisonDoesNotRenameOtherDamage() {
        assertEquals(CombatDamageLabel.UNKNOWN, CombatDamageLabel.fallback(null, false, false));
        assertEquals(CombatDamageLabel.UNKNOWN, CombatDamageLabel.fallback("generic", false, false));
        assertEquals(CombatDamageLabel.UNKNOWN, CombatDamageLabel.fallback("mob", true, false));
    }

    @Test void repeatedEffectTicksAreAnnouncedOncePerWindowButHitsAlwaysAre() {
        assertFalse(CombatDamageLabel.quietChat("中毒", "", 1_000, 0));
        assertTrue(CombatDamageLabel.quietChat("中毒", "中毒", 2_000, 1_000));
        assertFalse(CombatDamageLabel.quietChat("中毒", "中毒", 11_000, 1_000));
        assertFalse(CombatDamageLabel.quietChat("凋零", "中毒", 2_000, 1_000));
        assertFalse(CombatDamageLabel.quietChat("僵尸", "僵尸", 2_000, 1_000));
        assertFalse(CombatDamageLabel.quietChat(CombatDamageLabel.UNKNOWN, CombatDamageLabel.UNKNOWN, 2_000, 1_000));
    }
}
