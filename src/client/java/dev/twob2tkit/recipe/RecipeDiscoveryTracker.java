package dev.twob2tkit.recipe;

import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ItemStack;
import dev.twob2tkit.KitConfig;

/** 跟踪背包发现的物品，驱动配方书解锁外观。 */
public final class RecipeDiscoveryTracker {
	private final KitConfig config;

	/** 按配置构造发现追踪器。 */
	public RecipeDiscoveryTracker(KitConfig config) {
		this.config = config;
	}

	/** 每拍扫背包/装备/鼠标携带，记住新物品并可选刷新配方书。 */
	public void tick(Minecraft minecraft) {
		if (minecraft.player == null || minecraft.level == null) return;

		boolean changed = initializeExistingHistory();
		for (ItemStack stack : minecraft.player.getInventory().getNonEquipmentItems()) {
			changed |= remember(stack);
		}
		for (EquipmentSlot slot : EquipmentSlot.values()) {
			changed |= remember(minecraft.player.getItemBySlot(slot));
		}
		changed |= remember(minecraft.player.containerMenu.getCarried());

		if (!changed) return;
		config.save();
		if (config.recipeBookEnhancementEnabled) LocalRecipeBookInjector.onDiscoveredItemsChanged(minecraft);
	}

	/** 首次把仓库快照与旧提示种子写进发现集合。 */
	private boolean initializeExistingHistory() {
		if (config.recipeDiscoveryInitialized) return false;

		for (KitConfig.StorageSnapshot snapshot : config.storageSnapshots) {
			for (KitConfig.StoredItem item : snapshot.items) {
				if (item.id != null && !item.id.isBlank()) config.discoveredRecipeItems.add(item.id);
			}
		}
		for (String hint : config.seenRecipeHints) {
			switch (hint) {
				case "logs" -> config.discoveredRecipeItems.add("minecraft:oak_log");
				case "cobblestone" -> config.discoveredRecipeItems.add("minecraft:cobblestone");
				case "furnace" -> config.discoveredRecipeItems.add("minecraft:furnace");
				case "coal" -> config.discoveredRecipeItems.add("minecraft:coal");
				case "iron" -> config.discoveredRecipeItems.add("minecraft:iron_ingot");
				default -> {
				}
			}
		}
		config.recipeDiscoveryInitialized = true;
		return true;
	}

	/** 把物品 id 记入已发现集合；新增则返回 true。 */
	private boolean remember(ItemStack stack) {
		if (stack == null || stack.isEmpty()) return false;
		return config.discoveredRecipeItems.add(BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());
	}
}
