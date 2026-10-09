package dev.twob2tkit.automation;

/** A narrow exception for an explicitly selected, server-observed empty ordinary furnace. */
final class FurnaceRecoveryPolicy {
    static boolean allowed(String block, boolean explicit, boolean owned, boolean exactMenu,
                           boolean serverContentSeen, boolean serverSlotsEmpty, boolean clientSlotsEmpty,
                           boolean cursorEmpty, boolean lit, boolean automatedInput, boolean otherPlayer,
                           boolean usablePickaxe, int freeSlots) {
        return "minecraft:furnace".equals(block) && explicit && owned && exactMenu
            && serverContentSeen && serverSlotsEmpty && clientSlotsEmpty && cursorEmpty
            && !lit && !automatedInput && !otherPlayer && usablePickaxe && freeSlots > 0;
    }
    private FurnaceRecoveryPolicy() {}
}
