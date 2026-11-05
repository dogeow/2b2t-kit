package dev.twob2tkit.fisher;

import java.util.Set;

/** Deposit only ordinary fishing junk from the backpack. */
public final class FisherStashPolicy {
    private static final Set<String> JUNK = Set.of(
        "minecraft:bowl", "minecraft:string", "minecraft:stick", "minecraft:leather",
        "minecraft:ink_sac", "minecraft:tripwire_hook", "minecraft:lily_pad"
    );

    private FisherStashPolicy() {}

    public static boolean mayStash(String item, int slot, boolean food) {
        return slot >= 9 && slot < 36 && !food && JUNK.contains(item);
    }
}
