package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class GrassBlockToolPolicyTest {
    @Test void exactSelectedSilkShovelWithMarginIsAccepted() {
        assertTrue(GrassBlockToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel", 5, 5, true, 33));
        assertTrue(GrassBlockToolPolicy.ready("minecraft:netherite_shovel", "minecraft:netherite_shovel", 0, 0, true, 200));
    }

    @Test void changedToolSlotEnchantmentOrDurabilityStopsMining() {
        assertFalse(GrassBlockToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel", 5, 2, true, 300));
        assertFalse(GrassBlockToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel", 9, 9, true, 300));
        assertFalse(GrassBlockToolPolicy.ready("minecraft:diamond_shovel", "minecraft:netherite_shovel", 5, 5, true, 300));
        assertFalse(GrassBlockToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel", 5, 5, false, 300));
        assertFalse(GrassBlockToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel", 5, 5, true, 32));
        assertFalse(GrassBlockToolPolicy.ready("minecraft:diamond_pickaxe", "minecraft:diamond_pickaxe", 5, 5, true, 300));
        assertFalse(GrassBlockToolPolicy.ready("minecraft:iron_shovel", "minecraft:iron_shovel", 5, 5, true, 300));
    }
}
