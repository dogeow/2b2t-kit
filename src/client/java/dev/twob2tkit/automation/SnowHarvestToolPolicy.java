package dev.twob2tkit.automation;

/** Exact selected-tool gate for natural snow harvesting. */
final class SnowHarvestToolPolicy {
    private SnowHarvestToolPolicy() {}

    static boolean ready(String expectedItem, String heldItem, int expectedSlot,
                         int selectedSlot, boolean silkTouch, boolean requireSilk,
                         int durability) {
        return ("minecraft:diamond_shovel".equals(expectedItem)
                || "minecraft:netherite_shovel".equals(expectedItem))
            && expectedItem.equals(heldItem)
            && expectedSlot >= 0 && expectedSlot < 9 && selectedSlot == expectedSlot
            && silkTouch == requireSilk && durability >= 33;
    }
}
