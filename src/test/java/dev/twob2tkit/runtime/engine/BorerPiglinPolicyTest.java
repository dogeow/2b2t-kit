package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerPiglinPolicyTest {
    @Test void noGoldAdultClosingAndFacingPlayerPausesBeforeItsFirstHit() {
        assertTrue(BorerPiglinPolicy.ordinaryThreat(true, false, false, false, false, false,
            false, false, true, true, 6, 0));
        assertTrue(BorerPiglinPolicy.ordinaryThreat(true, false, false, false, false, false,
            false, true, true, false, 8, 0));
    }
    @Test void idleDistantUnseenAndDifferentTargetPiglinsAreNotAttacked() {
        assertFalse(BorerPiglinPolicy.ordinaryThreat(true, false, false, false, false, false,
            false, false, true, false, 2, 0));
        assertFalse(BorerPiglinPolicy.ordinaryThreat(false, false, false, false, false, false,
            false, true, true, true, 2, 0));
        assertFalse(BorerPiglinPolicy.ordinaryThreat(true, false, true, false, false, false,
            false, true, true, true, 2, 0));
        assertFalse(BorerPiglinPolicy.ordinaryThreat(true, false, false, false, false, false,
            false, true, true, true, 15, 0));
    }
    @Test void goldCalmBarteringAndBabyPiglinsRemainNeutral() {
        assertFalse(BorerPiglinPolicy.ordinaryThreat(true, false, false, false, true, false,
            false, false, true, true, 3, 0));
        assertFalse(BorerPiglinPolicy.ordinaryThreat(true, false, false, false, false, false,
            true, true, true, true, 3, 0));
        assertFalse(BorerPiglinPolicy.ordinaryThreat(true, false, false, false, false, true,
            false, true, true, true, 3, 0));
    }
    @Test void actualAttackOrExplicitAggressionOverridesGoldArmor() {
        assertTrue(BorerPiglinPolicy.ordinaryThreat(false, true, true, false, true, false,
            false, false, false, false, 12, 0));
        assertTrue(BorerPiglinPolicy.ordinaryThreat(true, false, false, true, true, false,
            false, false, true, false, 6, 0));
        assertTrue(BorerPiglinPolicy.ordinaryThreat(true, false, false, false, true, false,
            false, true, true, false, 6, 0));
    }
    @Test void neutralZombifiedPiglinWalkingTowardPlayerIsNotAThreat() {
        assertFalse(BorerPiglinPolicy.zombifiedThreat(true, false, false, false, false, true, true, 2, 0));
        assertTrue(BorerPiglinPolicy.zombifiedThreat(true, false, false, false, true, true, true, 2, 0));
        assertTrue(BorerPiglinPolicy.zombifiedThreat(false, true, false, false, false, false, false, 8, 0));
    }
    @Test void onlyWornArmorCanPacifyPiglins() {
        for (String armor : new String[]{"golden_helmet", "golden_chestplate", "golden_leggings", "golden_boots"})
            assertTrue(BorerPiglinPolicy.goldArmorItem(armor));
        for (String held : new String[]{"gold_ingot", "golden_sword", "golden_axe", "golden_pickaxe", "diamond_helmet"})
            assertFalse(BorerPiglinPolicy.goldArmorItem(held));
    }
}
