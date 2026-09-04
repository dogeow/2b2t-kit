package dev.twob2tkit.combat;

import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.alchemy.PotionContents;
import net.minecraft.world.item.alchemy.Potions;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/** 补给物品目录与背包计数（任意食物、治疗药水等）。 */
public final class HealingItems {
	public static final String ANY_FOOD = "twob2tkit:any_food";
	public static final String HEALING_POTION = "twob2tkit:healing_potion";

	/** 一种可选补给：配置 id、界面名、图标。 */
	public record Choice(String id, String label, Item icon) {
	}

	public static final List<Choice> CATALOG = List.of(
		new Choice(ANY_FOOD, "任意食物", Items.APPLE),
		new Choice(itemId(Items.BREAD), "面包", Items.BREAD),
		new Choice(itemId(Items.COOKED_BEEF), "熟牛肉", Items.COOKED_BEEF),
		new Choice(itemId(Items.COOKED_PORKCHOP), "熟猪排", Items.COOKED_PORKCHOP),
		new Choice(itemId(Items.COOKED_CHICKEN), "熟鸡肉", Items.COOKED_CHICKEN),
		new Choice(itemId(Items.COOKED_MUTTON), "熟羊肉", Items.COOKED_MUTTON),
		new Choice(itemId(Items.COOKED_RABBIT), "熟兔肉", Items.COOKED_RABBIT),
		new Choice(itemId(Items.COOKED_COD), "熟鳕鱼", Items.COOKED_COD),
		new Choice(itemId(Items.COOKED_SALMON), "熟鲑鱼", Items.COOKED_SALMON),
		new Choice(itemId(Items.BAKED_POTATO), "烤马铃薯", Items.BAKED_POTATO),
		new Choice(itemId(Items.GOLDEN_CARROT), "金胡萝卜", Items.GOLDEN_CARROT),
		new Choice(itemId(Items.GOLDEN_APPLE), "金苹果", Items.GOLDEN_APPLE),
		new Choice(itemId(Items.ENCHANTED_GOLDEN_APPLE), "附魔金苹果", Items.ENCHANTED_GOLDEN_APPLE),
		new Choice(itemId(Items.MUSHROOM_STEW), "蘑菇煲", Items.MUSHROOM_STEW),
		new Choice(itemId(Items.RABBIT_STEW), "兔肉煲", Items.RABBIT_STEW),
		new Choice(HEALING_POTION, "治疗/再生药水", Items.POTION)
	);

	/** 默认勾选的补给 id 集合。 */
	public static Set<String> defaultIds() {
		return new LinkedHashSet<>(List.of(
			itemId(Items.BREAD),
			itemId(Items.COOKED_BEEF),
			itemId(Items.COOKED_PORKCHOP),
			itemId(Items.COOKED_CHICKEN),
			itemId(Items.GOLDEN_CARROT),
			itemId(Items.GOLDEN_APPLE),
			itemId(Items.ENCHANTED_GOLDEN_APPLE),
			HEALING_POTION
		));
	}

	/** 丢掉未知 id；全空则回默认。 */
	public static Set<String> normalize(Set<String> stored) {
		if (stored == null || stored.isEmpty()) return defaultIds();
		Set<String> remapped = new LinkedHashSet<>();
		for (String id : stored) {
			if (id == null) continue;
			if ("autocruise:any_food".equals(id) || "2b2t-kit:any_food".equals(id)) remapped.add(ANY_FOOD);
			else if ("autocruise:healing_potion".equals(id) || "2b2t-kit:healing_potion".equals(id)) remapped.add(HEALING_POTION);
			else remapped.add(id);
		}
		Set<String> known = new LinkedHashSet<>();
		for (Choice choice : CATALOG) {
			if (remapped.contains(choice.id)) known.add(choice.id);
		}
		return known.isEmpty() ? defaultIds() : known;
	}

	/** 背包与副手中勾选补给的总数量。 */
	public static int count(LocalPlayer player, Set<String> selected) {
		int total = 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) total += value(stack, selected);
		total += value(player.getItemBySlot(EquipmentSlot.OFFHAND), selected);
		return total;
	}

	/** 每种勾选项的「名×数量」列表。 */
	public static List<String> breakdown(LocalPlayer player, Set<String> selected) {
		List<String> lines = new ArrayList<>();
		for (Choice choice : CATALOG) {
			if (!selected.contains(choice.id)) continue;
			int have = countChoice(player, choice);
			lines.add(choice.label + "×" + have);
		}
		return lines;
	}

	/** 勾选补给的中文名串。 */
	public static String summary(Set<String> selected) {
		Set<String> ids = normalize(selected);
		List<String> names = new ArrayList<>();
		for (Choice choice : CATALOG) {
			if (ids.contains(choice.id)) names.add(choice.label);
		}
		return names.isEmpty() ? "未选择" : String.join("、", names);
	}

	/** 某一种补给在背包/副手的数量。 */
	public static int countChoice(LocalPlayer player, Choice choice) {
		int total = 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (matches(stack, choice.id)) total += stack.getCount();
		}
		ItemStack offhand = player.getItemBySlot(EquipmentSlot.OFFHAND);
		if (matches(offhand, choice.id)) total += offhand.getCount();
		return total;
	}

	/** 堆叠若匹配任一勾选则返回数量。 */
	private static int value(ItemStack stack, Set<String> selected) {
		if (stack.isEmpty()) return 0;
		for (String id : selected) {
			if (matches(stack, id)) return stack.getCount();
		}
		return 0;
	}

	/** 堆叠是否匹配配置 id（含任意食物/药水）。 */
	public static boolean matches(ItemStack stack, String id) {
		if (stack.isEmpty()) return false;
		if (ANY_FOOD.equals(id)) return stack.has(DataComponents.FOOD);
		if (HEALING_POTION.equals(id)) return isHealingPotion(stack);
		Identifier identifier = Identifier.tryParse(id);
		if (identifier == null || !BuiltInRegistries.ITEM.containsKey(identifier)) return false;
		return stack.is(BuiltInRegistries.ITEM.getValue(identifier));
	}

	/** 是否治疗或再生药水。 */
	private static boolean isHealingPotion(ItemStack stack) {
		if (!stack.is(Items.POTION) && !stack.is(Items.SPLASH_POTION) && !stack.is(Items.LINGERING_POTION)) return false;
		PotionContents potion = stack.get(DataComponents.POTION_CONTENTS);
		return potion != null && (potion.is(Potions.HEALING)
			|| potion.is(Potions.STRONG_HEALING)
			|| potion.is(Potions.REGENERATION)
			|| potion.is(Potions.LONG_REGENERATION)
			|| potion.is(Potions.STRONG_REGENERATION));
	}

	/** 物品注册表 id 字符串。 */
	private static String itemId(Item item) {
		return BuiltInRegistries.ITEM.getKey(item).toString();
	}

	private HealingItems() {
	}
}
