package dev.twob2tkit.storage;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.item.ItemStack;
import dev.twob2tkit.KitConfig;

/** 仓库记录里 StoredItem 转 ItemStack 供界面画图标。 */
public final class StorageItems {
	private StorageItems() {
	}

	/** 配置里的 StoredItem 转成可渲染的 ItemStack。 */
	public static ItemStack stack(KitConfig.StoredItem item) {
		if (item == null || item.id == null || item.id.isBlank()) return ItemStack.EMPTY;
		Identifier id = Identifier.tryParse(item.id);
		if (id == null || !BuiltInRegistries.ITEM.containsKey(id)) return ItemStack.EMPTY;
		return new ItemStack(BuiltInRegistries.ITEM.getValue(id), Math.max(1, item.count));
	}
}
