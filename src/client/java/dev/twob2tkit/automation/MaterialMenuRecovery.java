package dev.twob2tkit.automation;

import java.util.*;
import net.minecraft.world.item.ItemStack;

/** Simulates returning owned crafting inputs without modifying the inventory. */
final class MaterialMenuRecovery {
    enum Decision { MANUAL_HANDOFF, CLOSE_OWNED, SAFE_LOGOUT }
    static Decision decide(boolean scopeCurrent, boolean manualInput, int ownedId, int menuId,
                           boolean canReturnItems) {
        if (!scopeCurrent || manualInput || ownedId < 0 || ownedId != menuId) return Decision.MANUAL_HANDOFF;
        return canReturnItems ? Decision.CLOSE_OWNED : Decision.SAFE_LOGOUT;
    }
    static boolean fits(List<ItemStack> inventory, List<ItemStack> returning) {
        var slots = inventory.stream().map(ItemStack::copy).collect(java.util.stream.Collectors.toCollection(ArrayList::new));
        for (var original : returning) {
            var stack = original.copy();
            for (var slot : slots) {
                if (!slot.isEmpty() && ItemStack.isSameItemSameComponents(slot, stack)) {
                    int n = Math.min(stack.getCount(), Math.max(0, slot.getMaxStackSize() - slot.getCount()));
                    slot.grow(n); stack.shrink(n);
                }
            }
            for (int i=0; i<slots.size() && !stack.isEmpty(); i++) {
                if (!slots.get(i).isEmpty()) continue;
                int n=Math.min(stack.getCount(), stack.getMaxStackSize());
                slots.set(i, stack.copyWithCount(n)); stack.shrink(n);
            }
            if (!stack.isEmpty()) return false;
        }
        return true;
    }
    private MaterialMenuRecovery() {}
}
