package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Mining melee is scoped to piglins and reachable ground foes; flying/bow threats keep bow defense. */
class BorerMiningCombatPolicyTest {
    @Test void hostilePiglinsAndBrutesKeepMeleeEvenWhenClosingFromOutsideSwordRange() {
        assertTrue(BorerMiningCombatPolicy.meleeTarget(true, false, false, 24, 0));
        assertTrue(BorerMiningCombatPolicy.meleeTarget(true, false, true, 12, 3));
        assertTrue(BorerMiningCombatPolicy.meleeTarget(false, true, false, 24, 0));
    }

    @Test void ordinaryGroundFoesNeedBothCloseDistanceAndReachableHeight() {
        assertTrue(BorerMiningCombatPolicy.meleeTarget(false, false, false, 2, 0));
        assertTrue(BorerMiningCombatPolicy.meleeTarget(false, false, false, 6, 2));
        assertTrue(BorerMiningCombatPolicy.meleeTarget(false, false, false, 6, -2));
        assertFalse(BorerMiningCombatPolicy.meleeTarget(false, false, false, 6.01, 0));
        assertFalse(BorerMiningCombatPolicy.meleeTarget(false, false, false, 2, 2.01));
        assertFalse(BorerMiningCombatPolicy.meleeTarget(false, false, false, 2, -2.01));
    }

    @Test void GhastBlazeAndBowFoesRemainOnTheBowPathEvenWhenClose() {
        assertFalse(BorerMiningCombatPolicy.meleeTarget(false, false, true, 2, 0));
        assertFalse(BorerMiningCombatPolicy.meleeTarget(false, false, true, 24, 0));
        assertFalse(BorerMiningCombatPolicy.meleeTarget(false, false, true, 24, 12));
    }
}
