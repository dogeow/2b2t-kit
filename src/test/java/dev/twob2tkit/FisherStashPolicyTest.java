package dev.twob2tkit;

import dev.twob2tkit.fisher.FisherStashPolicy;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

final class FisherStashPolicyTest {
    @Test
    void combatGearToolsStorageAndFoodStayInTheBackpack() {
        for (String item : new String[]{"netherite_sword", "bow", "diamond_shovel", "diamond_pickaxe",
                "totem_of_undying", "ender_chest", "blue_shulker_box", "golden_carrot", "cod", "fishing_rod"}) {
            assertFalse(FisherStashPolicy.mayStash("minecraft:" + item, 12, false), item);
        }
    }

    @Test
    void onlyBackpackJunkCanBeDeposited() {
        assertTrue(FisherStashPolicy.mayStash("minecraft:bowl", 9, false));
        assertFalse(FisherStashPolicy.mayStash("minecraft:bowl", 8, false));
        assertFalse(FisherStashPolicy.mayStash("minecraft:bowl", 40, false));
        assertFalse(FisherStashPolicy.mayStash("minecraft:bowl", 9, true));
    }
}
