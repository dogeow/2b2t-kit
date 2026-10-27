package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mojang.serialization.JsonOps;
import net.minecraft.client.Minecraft;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.RegistryOps;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.alchemy.PotionContents;

/** Read-only potion components, including one level of currently received box contents. */
final class LoadedPotionDetails {
    static final int MAX_MENU_SLOTS=90,MAX_BOX_ITEMS=27;
    static boolean supportedMenuSize(int size){return size>=0&&size<=MAX_MENU_SLOTS;}
    static boolean retain(JsonObject frame){return frame.has("potions")&&!frame.getAsJsonArray("potions").isEmpty();}
    static JsonObject observe(Minecraft c,long now){
        var menu=c.player.containerMenu;var result=new JsonObject();var potions=new JsonArray();
        result.addProperty("observed_at",now);result.addProperty("menu_id",menu.containerId);
        result.addProperty("menu_type",menu.getClass().getSimpleName());
        result.addProperty("scope","client_received_components_not_server_inventory_probe");
        result.addProperty("complete",supportedMenuSize(menu.slots.size()));result.add("potions",potions);
        if(!supportedMenuSize(menu.slots.size()))return result;
        for(int slot=0;slot<menu.slots.size();slot++){
            var stack=menu.getSlot(slot).getItem();append(c,potions,stack,slot,-1);
            var contents=stack.get(DataComponents.CONTAINER);
            if(contents!=null){var children=contents.nonEmptyItemCopyStream().limit(MAX_BOX_ITEMS).toList();
                for(int child=0;child<children.size();child++)append(c,potions,children.get(child),slot,child);
            }
        }
        return result;
    }
    private static void append(Minecraft c,JsonArray rows,ItemStack stack,int slot,int child){
        var contents=stack.get(DataComponents.POTION_CONTENTS);if(stack.isEmpty()||contents==null)return;
        var row=new JsonObject();row.addProperty("slot",slot);row.addProperty("nonempty_child_index",child);
        row.addProperty("item",BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());row.addProperty("count",stack.getCount());
        row.addProperty("display_name",stack.getHoverName().getString());
        row.add("potion_contents",PotionContents.CODEC.encodeStart(RegistryOps.create(JsonOps.INSTANCE,c.player.registryAccess()),contents).getOrThrow());rows.add(row);
    }
}
