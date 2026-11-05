package dev.twob2tkit.fisher;

import java.util.Set;

/** Deposit a safe subset of vanilla fishing loot from the backpack. */
public final class FisherStashPolicy {
    private static final Set<String> LOOT = Set.of(
        "minecraft:bowl", "minecraft:string", "minecraft:stick", "minecraft:leather",
        "minecraft:ink_sac", "minecraft:tripwire_hook", "minecraft:lily_pad",
        "minecraft:bone", "minecraft:bamboo", "minecraft:leather_boots", "minecraft:bow",
        "minecraft:cod", "minecraft:salmon", "minecraft:tropical_fish", "minecraft:pufferfish"
    );

    private FisherStashPolicy() {}

    public static boolean mayStash(String item, int slot, boolean protectedItem) {
        return slot >= 9 && slot < 36 && !protectedItem && LOOT.contains(item);
    }
}
