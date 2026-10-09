package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.FurnaceMenu;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import java.util.List;

/** Server inventory observations are tied to one normal open, not the unsynchronized block entity. */
final class EmptyFurnaceRecovery {
    private static Object connection, level;
    private static BlockPos target;
    private static String task = "";
    private static AbstractContainerMenu menu;
    private static boolean contentSeen;
    private static final int[] counts = new int[3];
    private static long serial;

    static void opening(Minecraft c, String owner, BlockPos pos) {
        connection = level = null; target = null; task = ""; menu = null; contentSeen = false;
        if (owner.isEmpty() || c.player == null || c.player.containerMenu != c.player.inventoryMenu
                || !c.level.getBlockState(pos).is(Blocks.FURNACE)) return;
        connection = c.getConnection(); level = c.level; target = pos.immutable(); task = owner;
    }
    private static boolean current(Minecraft c, Object sender, int id) {
        return target != null && sender == connection && c.getConnection() == connection && c.level == level
            && c.player != null && c.player.containerMenu instanceof FurnaceMenu
            && c.player.containerMenu.containerId == id;
    }
    static void content(Minecraft c, Object sender, int id, List<ItemStack> items) {
        if (!current(c, sender, id) || items.size() < 3) return;
        menu = c.player.containerMenu;
        for (int i = 0; i < 3; i++) counts[i] = items.get(i).getCount();
        contentSeen = true; serial++;
    }
    static void slot(Minecraft c, Object sender, int id, int slot, ItemStack item) {
        if (!current(c, sender, id) || menu != c.player.containerMenu || !contentSeen || slot < 0 || slot >= 3) return;
        counts[slot] = item.getCount(); serial++;
    }
    static JsonObject snapshot(Minecraft c) {
        var out = new JsonObject();
        boolean exact = target != null && c.getConnection() == connection && c.level == level
            && c.player != null && menu == c.player.containerMenu;
        out.addProperty("server_content_seen", exact && contentSeen);
        out.addProperty("content_serial", serial);
        out.addProperty("menu_id", exact ? menu.containerId : -1);
        out.addProperty("server_slots_empty", exact && contentSeen && counts[0] == 0 && counts[1] == 0 && counts[2] == 0);
        if (target != null) {
            var pos = new com.google.gson.JsonArray(); pos.add(target.getX()); pos.add(target.getY()); pos.add(target.getZ());
            out.add("pos", pos);
        }
        return out;
    }
    static void prepare(Minecraft c, JsonObject request, BlockPos pos, boolean owned) {
        var state = c.level.getBlockState(pos);
        var current = c.player.containerMenu;
        int toolSlot = request.get("tool_slot").getAsInt();
        if (toolSlot < 0 || toolSlot >= 9) throw new IllegalArgumentException("Furnace retrieval requires a verified hotbar pickaxe");
        ItemStack tool = c.player.getInventory().getItem(toolSlot);
        boolean pickaxe = tool.is(net.minecraft.tags.ItemTags.PICKAXES) && tool.isDamageableItem()
            && tool.getMaxDamage() - tool.getDamageValue() >= 32;
        boolean exact = target != null && target.equals(pos) && task.equals(request.get("task_session").getAsString())
            && c.getConnection() == connection && c.level == level && current == menu && current instanceof FurnaceMenu
            && current.containerId == request.get("expected_menu_id").getAsInt()
            && serial == request.get("expected_content_serial").getAsLong();
        boolean clientEmpty = current instanceof FurnaceMenu && current.slots.size() >= 3
            && !current.getSlot(0).hasItem() && !current.getSlot(1).hasItem() && !current.getSlot(2).hasItem();
        boolean automated = false;
        for (Direction direction : Direction.values()) {
            BlockPos neighbor = pos.relative(direction);
            if (!c.level.hasChunkAt(neighbor) || c.level.getBlockState(neighbor).is(Blocks.HOPPER)) automated = true;
        }
        boolean otherPlayer = c.level.players().stream().anyMatch(p -> p != c.player && p.isAlive()
            && p.position().distanceToSqr(net.minecraft.world.phys.Vec3.atCenterOf(pos)) <= 36);
        if (!FurnaceRecoveryPolicy.allowed(net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString(),
                true, owned, exact, contentSeen, counts[0] == 0 && counts[1] == 0 && counts[2] == 0,
                clientEmpty, current.getCarried().isEmpty(), state.hasProperty(BlockStateProperties.LIT) && state.getValue(BlockStateProperties.LIT),
                automated, otherPlayer, pickaxe, c.player.getInventory().getFreeSlot() >= 0 ? 1 : 0))
            throw new IllegalStateException("Furnace retrieval requires the current server-confirmed empty owned menu, dry unlit furnace and pickup room");
        // The exception is consumed once. Normal break confirmation still owns every mining send.
        target = null; contentSeen = false;
        c.player.closeContainer(); c.player.getInventory().setSelectedSlot(toolSlot);
    }
    static void validateMining(Minecraft c, JsonObject request, BlockPos pos) {
        ItemStack tool = c.player.getMainHandItem();
        if (c.player.getInventory().getSelectedSlot() != request.get("tool_slot").getAsInt()
                || !tool.is(net.minecraft.tags.ItemTags.PICKAXES) || !tool.isDamageableItem()
                || tool.getMaxDamage() - tool.getDamageValue() < 32 || c.player.getInventory().getFreeSlot() < 0
                || c.player.getHealth() < 19 || c.player.getFoodData().getFoodLevel() < 18)
            throw new IllegalStateException("Furnace retrieval tool, pickup room or survival state changed");
        var state = c.level.getBlockState(pos);
        if (!state.is(Blocks.FURNACE) || state.getValue(BlockStateProperties.LIT))
            throw new IllegalStateException("Empty furnace target changed");
        for (Direction direction : Direction.values()) {
            BlockPos neighbor = pos.relative(direction);
            if (!c.level.hasChunkAt(neighbor) || !c.level.getFluidState(neighbor).isEmpty()
                    || c.level.getBlockState(neighbor).is(Blocks.HOPPER))
                throw new IllegalStateException("Furnace retrieval surroundings changed");
        }
        if (c.level.players().stream().anyMatch(p -> p != c.player && p.isAlive()
                && p.position().distanceToSqr(net.minecraft.world.phys.Vec3.atCenterOf(pos)) <= 36))
            throw new IllegalStateException("Another player is near the furnace being retrieved");
    }
    private EmptyFurnaceRecovery() {}
}
