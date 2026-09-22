package dev.twob2tkit.adventure;

import dev.twob2tkit.KitConfig;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.component.DataComponents;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.BucketItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** The mining checklist is also the source of truth for what must survive unloading. */
public final class MiningCargoSupplies {
	private MiningCargoSupplies() {}
	public static boolean[] reserved(LocalPlayer player, KitConfig config) {
		ActivityRequirements.ensureLists(config);
		var requirements = new ArrayList<>(ActivityRequirements.requirements(ActivityRequirements.findList(config, "MINING")));
		if (!"MINING".equals(config.activityProfile)) requirements.addAll(ActivityRequirements.requirements(config));
		// Keep emergency sealing and torch-making possible even if a checklist entry was removed.
		for (var need : List.of(ActivityRequirements.need("building_blocks", "应急方块", 64),
			ActivityRequirements.need("item:minecraft:coal", "火把用煤", 16),
			ActivityRequirements.need("item:minecraft:stick", "火把用木棍", 16)))
			requirements.add(ActivityRequirements.requirement(need));
		var inventory = new ArrayList<ItemStack>();
		for (int i = 0; i < 36; i++) inventory.add(player.getInventory().getItem(i));
		var equipment = new ArrayList<ItemStack>();
		for (var slot : List.of(EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET, EquipmentSlot.OFFHAND))
			equipment.add(player.getItemBySlot(slot));
		return reserve(inventory, equipment, requirements);
	}
	/** Whole stacks are retained; no extra inventory splitting or temporary cursor ownership. */
	static boolean[] reserve(List<ItemStack> inventory, List<ItemStack> equipment, List<ActivityRequirements.Requirement> requirements) {
		boolean[] keep = new boolean[inventory.size()];
		for (int i = 0; i < keep.length; i++) keep[i] = alwaysKeep(inventory.get(i));
		for (var requirement : requirements) {
			int remaining = requirement.target();
			for (var stack : equipment) if (requirement.matches(stack)) remaining -= stack.getCount();
			var candidates = new ArrayList<Integer>();
			for (int i = 0; i < keep.length; i++) if (requirement.matches(inventory.get(i))) {
				if (keep[i]) remaining -= inventory.get(i).getCount();
				else candidates.add(i);
			}
			candidates.sort(Comparator.<Integer>comparingInt(i -> requirement.match().equals("building_blocks") ? sealingRank(inventory.get(i)) : 0)
				.thenComparingInt(i -> -inventory.get(i).getCount()).thenComparingInt(i -> i));
			for (int i : candidates) {
				if (remaining <= 0) break;
				keep[i] = true; remaining -= inventory.get(i).getCount();
			}
		}
		return keep;
	}
	private static int sealingRank(ItemStack s) {
		if (s.is(Items.DIRT)) return 0;
		if (s.is(Items.COBBLESTONE) || s.is(Items.COBBLED_DEEPSLATE) || s.is(Items.NETHERRACK)) return 1;
		return 2;
	}
	static boolean alwaysKeep(ItemStack s) {
		if (s.isEmpty()) return false;
		return s.isDamageableItem() || s.isEnchanted() || s.has(DataComponents.CUSTOM_NAME)
			|| s.has(DataComponents.CUSTOM_DATA) || s.has(DataComponents.CUSTOM_MODEL_DATA)
			|| s.has(DataComponents.STORED_ENCHANTMENTS) || !s.getOrDefault(DataComponents.LORE, net.minecraft.world.item.component.ItemLore.EMPTY).lines().isEmpty()
			|| s.has(DataComponents.MAP_ID)
			|| s.has(DataComponents.FOOD) || s.has(DataComponents.TOOL) || s.has(DataComponents.WEAPON)
			|| s.has(DataComponents.EQUIPPABLE) || s.has(DataComponents.POTION_CONTENTS)
			|| s.has(DataComponents.CONTAINER) || s.has(DataComponents.CONTAINER_LOOT) || s.has(DataComponents.BUNDLE_CONTENTS)
			|| s.getItem() instanceof BucketItem || s.is(ItemTags.ARROWS)
			|| s.is(Items.ARROW) || s.is(Items.SPECTRAL_ARROW) || s.is(Items.TIPPED_ARROW)
			|| s.is(Items.TORCH) || s.is(Items.SOUL_TORCH) || s.is(Items.REDSTONE_TORCH)
			|| s.is(Items.CHEST) || s.is(Items.TRAPPED_CHEST) || s.is(Items.ENDER_CHEST)
			|| s.is(Items.TOTEM_OF_UNDYING) || s.is(Items.ENDER_PEARL) || s.is(Items.FIREWORK_ROCKET);
	}
}
