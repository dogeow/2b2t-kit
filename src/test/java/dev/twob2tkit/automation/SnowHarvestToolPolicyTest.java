package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SnowHarvestToolPolicyTest {
    @Test void exactSelectedShovelMustMatchRequestedSilkMode() {
        assertTrue(SnowHarvestToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel",
            5, 5, true, true, 33));
        assertTrue(SnowHarvestToolPolicy.ready("minecraft:netherite_shovel", "minecraft:netherite_shovel",
            0, 0, false, false, 200));
        assertFalse(SnowHarvestToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel",
            5, 5, true, false, 300));
        assertFalse(SnowHarvestToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel",
            5, 5, false, true, 300));
    }

    @Test void changedSlotToolOrDurabilityStopsMining() {
        assertFalse(SnowHarvestToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel",
            5, 2, true, true, 300));
        assertFalse(SnowHarvestToolPolicy.ready("minecraft:diamond_shovel", "minecraft:netherite_shovel",
            5, 5, true, true, 300));
        assertFalse(SnowHarvestToolPolicy.ready("minecraft:iron_shovel", "minecraft:iron_shovel",
            5, 5, false, false, 300));
        assertFalse(SnowHarvestToolPolicy.ready("minecraft:diamond_shovel", "minecraft:diamond_shovel",
            5, 5, true, true, 32));
    }
}
