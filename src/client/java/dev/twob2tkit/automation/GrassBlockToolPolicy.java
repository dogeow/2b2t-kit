package dev.twob2tkit.automation;

/** Native mine_block gate for the opt-in grass-block collection contract. */
final class GrassBlockToolPolicy {
    private GrassBlockToolPolicy() {}

    static boolean ready(String expectedItem, String heldItem, int expectedSlot,
                         int selectedSlot, boolean silkTouch, int durability) {
        return ("minecraft:diamond_shovel".equals(expectedItem)
                || "minecraft:netherite_shovel".equals(expectedItem))
            && expectedItem.equals(heldItem)
            && expectedSlot >= 0 && expectedSlot < 9 && selectedSlot == expectedSlot
            && silkTouch && durability >= 33;
    }
}
