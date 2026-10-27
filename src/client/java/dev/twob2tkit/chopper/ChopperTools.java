package dev.twob2tkit.chopper;

import net.minecraft.client.Minecraft;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;

/** One durability rule for tree blocks, pickup obstructions and owned platform cleanup. */
final class ChopperTools {
    private ChopperTools() {}

    static boolean select(Minecraft client, Class<? extends Item> type) {
        return selectToolType(client, type) || selectSafeHand(client);
    }

    static void require(Minecraft client, Class<? extends Item> type) {
        if (!select(client, type))
            throw new IllegalStateException("没有可安全使用的工具或空手槽位，已停止以保留工具耐久");
    }

    private static boolean selectToolType(Minecraft client, Class<? extends Item> type) {
        var inventory = client.player.getInventory();
        int slot = ChopperToolPolicy.chooseSlot(inventory.getSelectedSlot(), 36,
            index -> usableTool(inventory.getItem(index), type));
        if (slot < 0) return false;
        selectSlot(client, slot);
        return usableTool(client.player.getMainHandItem(), type);
    }

    private static boolean usableTool(ItemStack stack, Class<? extends Item> type) {
        return type.isInstance(stack.getItem())
            && !ChopperToolPolicy.tooWorn(stack.getMaxDamage() - stack.getDamageValue(), stack.getMaxDamage());
    }

    /** Prefer an empty slot; a full inventory may use an item that has no durability to consume. */
    private static boolean selectSafeHand(Minecraft client) {
        var inventory = client.player.getInventory();
        int slot = ChopperToolPolicy.chooseSlot(inventory.getSelectedSlot(), 36, index -> inventory.getItem(index).isEmpty());
        if (slot < 0) slot = ChopperToolPolicy.chooseSlot(inventory.getSelectedSlot(), 36,
            index -> !inventory.getItem(index).isDamageableItem());
        if (slot < 0) return false;
        selectSlot(client, slot);
        return !client.player.getMainHandItem().isDamageableItem();
    }

    private static void selectSlot(Minecraft client, int slot) {
        var player = client.player;
        var inventory = player.getInventory();
        if (slot < 9) inventory.setSelectedSlot(slot);
        else client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
    }
}
