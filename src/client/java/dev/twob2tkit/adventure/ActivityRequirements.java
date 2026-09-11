package dev.twob2tkit.adventure;

import dev.twob2tkit.KitConfig;

import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.tags.TagKey;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.alchemy.PotionContents;
import net.minecraft.world.item.alchemy.Potions;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Predicate;

/** 活动材料清单：内置资料与自定义需求。 */
public final class ActivityRequirements {
	enum Profile {
		NONE("不启用"),
		MINING("出门挖矿"),
		NETHER("前往下界"),
		ENDERMAN("打末影人");

		final String label;

		Profile(String label) {
			this.label = label;
		}

		static Profile fromConfig(String value) {
			try {
				return value == null ? NONE : valueOf(value.toUpperCase(Locale.ROOT));
			} catch (IllegalArgumentException exception) {
				return NONE;
			}
		}

		boolean builtinList() {
			return this != NONE;
		}
	}

	/** 一条材料需求：物品与数量。 */
	public record Requirement(String match, String label, int target, Predicate<ItemStack> matcher) {
		/** 堆叠是否满足该需求物品。 */
		public boolean matches(ItemStack stack) {
			return !stack.isEmpty() && matcher.test(stack);
		}
	}

	/** 材料清单仓库。 */
	private ActivityRequirements() {
	}

	/** 确保默认清单存在。 */
	public static void ensureLists(KitConfig config) {
		if (config.activityLists == null) config.activityLists = new ArrayList<>();
		for (Profile profile : Profile.values()) {
			if (!profile.builtinList()) continue;
			if (findList(config, profile.name()) == null) {
				config.activityLists.add(copyDefault(profile));
			}
		}
		if (config.miningChecklistVersion < 1) {
			KitConfig.ActivityList mining = findList(config, "MINING");
			config.miningChecklistVersion = migrateMining(mining, config.miningChecklistVersion);
		}
		for (KitConfig.ActivityList list : config.activityLists) {
			if (list.id == null) list.id = "";
			if (list.label == null || list.label.isBlank()) list.label = list.id.isBlank() ? "未命名行动" : list.id;
			if (list.needs == null) list.needs = new ArrayList<>();
			list.needs.removeIf(need -> need == null || need.match == null || need.match.isBlank());
			for (KitConfig.ActivityNeed need : list.needs) {
				if (need.label == null || need.label.isBlank()) need.label = fallbackLabel(need.match);
				if (need.target < 1) need.target = 1;
				if (need.target > 9999) need.target = 9999;
			}
		}
	}
	static int migrateMining(KitConfig.ActivityList mining, int version) {
		if (version >= 1) return version;
		if (mining.needs == null) mining.needs = new ArrayList<>();
		for (KitConfig.ActivityNeed added : miningExtras()) {
			if (mining.needs.stream().noneMatch(n -> n != null && added.match.equals(n.match))) mining.needs.add(added);
		}
		return 1;
	}

	/** 全部清单。 */
	public static List<KitConfig.ActivityList> lists(KitConfig config) {
		ensureLists(config);
		return config.activityLists;
	}

	/** 按名找清单。 */
	public static KitConfig.ActivityList findList(KitConfig config, String id) {
		if (config.activityLists == null || id == null || id.isBlank()) return null;
		for (KitConfig.ActivityList list : config.activityLists) {
			if (id.equals(list.id)) return list;
		}
		return null;
	}

	/** 当前选中清单。 */
	public static KitConfig.ActivityList selectedList(KitConfig config) {
		if (config.activityProfile == null || config.activityProfile.isBlank() || "NONE".equals(config.activityProfile)) {
			return null;
		}
		return findList(config, config.activityProfile);
	}

	/** 清单是否启用。 */
	public static boolean isActive(KitConfig config) {
		return selectedList(config) != null;
	}

	/** 当前清单显示名。 */
	public static String selectedLabel(KitConfig config) {
		KitConfig.ActivityList list = selectedList(config);
		return list == null ? Profile.NONE.label : list.label;
	}

	/** 是否下界资料清单。 */
	public static boolean isNetherProfile(KitConfig config) {
		return "NETHER".equals(config.activityProfile);
	}

	/** 是否内置不可删清单。 */
	public static boolean isBuiltin(KitConfig.ActivityList list) {
		if (list == null) return false;
		return Profile.fromConfig(list.id).builtinList() && Profile.fromConfig(list.id).name().equals(list.id);
	}

	/** 当前/指定清单的需求列表。 */
	public static List<Requirement> requirements(KitConfig config) {
		KitConfig.ActivityList list = selectedList(config);
		if (list == null) return List.of();
		return requirements(list);
	}

	/** 当前/指定清单的需求列表。 */
	public static List<Requirement> requirements(KitConfig.ActivityList list) {
		List<Requirement> result = new ArrayList<>();
		if (list == null || list.needs == null) return result;
		for (KitConfig.ActivityNeed need : list.needs) {
			Requirement requirement = requirement(need);
			if (requirement != null) result.add(requirement);
		}
		return result;
	}

	/** 配置条目转 Requirement。 */
	public static Requirement requirement(KitConfig.ActivityNeed need) {
		if (need == null || need.match == null || need.match.isBlank()) return null;
		return new Requirement(need.match, need.label == null || need.label.isBlank() ? fallbackLabel(need.match) : need.label,
			Math.max(1, need.target), matcher(need.match));
	}

	/** 玩家已有该需求物品数量。 */
	public static int count(LocalPlayer player, Requirement requirement) {
		int count = 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (requirement.matches(stack)) count += stack.getCount();
		}
		for (EquipmentSlot slot : List.of(EquipmentSlot.HEAD, EquipmentSlot.CHEST, EquipmentSlot.LEGS, EquipmentSlot.FEET, EquipmentSlot.OFFHAND)) {
			ItemStack stack = player.getItemBySlot(slot);
			if (requirement.matches(stack)) count += stack.getCount();
		}
		return count;
	}

	/** 缺料摘要文案。 */
	public static String missingSummary(LocalPlayer player, KitConfig config) {
		return missingSummary(player, requirements(config));
	}
	public static String miningMissingSummary(LocalPlayer player, KitConfig config) {
		ensureLists(config);
		return missingSummary(player, requirements(findList(config, "MINING")));
	}
	private static String missingSummary(LocalPlayer player, List<Requirement> requirements) {
		StringBuilder result = new StringBuilder();
		for (Requirement requirement : requirements) {
			int current = count(player, requirement);
			if (current >= requirement.target()) continue;
			if (!result.isEmpty()) result.append("、");
			result.append(requirement.label()).append(' ').append(current).append('/').append(requirement.target());
		}
		return result.toString();
	}

	/** 复制某资料的默认清单。 */
	public static KitConfig.ActivityList copyDefault(Profile profile) {
		KitConfig.ActivityList list = new KitConfig.ActivityList();
		list.id = profile.name();
		list.label = profile.label;
		list.needs = new ArrayList<>(defaultNeeds(profile));
		return list;
	}

	/** 内置资料的默认需求条目。 */
	public static List<KitConfig.ActivityNeed> defaultNeedsForId(String id) { return defaultNeeds(Profile.fromConfig(id)); }

	public static List<KitConfig.ActivityNeed> defaultNeeds(Profile profile) {
		return switch (profile) {
			case MINING -> miningDefaults();
			case NETHER -> List.of(
				need("gold_armor", "金质护甲（进入下界前穿上）", 1),
				need("item:minecraft:obsidian", "黑曜石", 10),
				need("item:minecraft:flint_and_steel", "打火石", 1),
				need("fire_resistance", "抗火药水", 1),
				need("food", "熟食", 16)
			);
			case ENDERMAN -> List.of(
				need("tag:minecraft:swords", "剑", 1),
				need("item:minecraft:shield", "盾牌", 1),
				need("item:minecraft:water_bucket", "水桶", 1),
				need("item:minecraft:carved_pumpkin", "雕刻南瓜", 1),
				need("tag:minecraft:boats", "船（困住末影人）", 1),
				need("food", "熟食", 16)
			);
			case NONE -> List.of();
		};
	}
	private static List<KitConfig.ActivityNeed> miningDefaults() {
		List<KitConfig.ActivityNeed> needs = new ArrayList<>(List.of(
				need("tag:minecraft:pickaxes", "镐（含备用）", 2),
				need("item:minecraft:torch", "火把", 64),
				need("food", "食物", 32),
				need("tag:minecraft:logs", "原木", 16),
				need("item:minecraft:crafting_table", "工作台", 1)
		));
		needs.addAll(miningExtras());
		return needs;
	}
	private static List<KitConfig.ActivityNeed> miningExtras() {
		return List.of(
			need("item:minecraft:water_bucket", "水桶（主世界灭火/应急）", 1),
			need("fire_resistance", "抗火药水（熔岩应急，建议放快捷栏）", 2),
			need("building_blocks", "普通实心方块（封水/搭路）", 128),
			need("ranged_weapon", "弓或弩", 1),
			need("tag:minecraft:arrows", "箭", 64),
			need("tag:minecraft:swords", "剑", 1),
			need("item:minecraft:shield", "盾牌", 1),
			need("tag:minecraft:shovels", "铲子（泥土/沙砾）", 1),
			need("tag:minecraft:head_armor", "头盔", 1),
			need("tag:minecraft:chest_armor", "胸甲", 1),
			need("tag:minecraft:leg_armor", "护腿", 1),
			need("tag:minecraft:foot_armor", "靴子", 1),
			need("item:minecraft:totem_of_undying", "不死图腾（应急）", 1));
	}

	/** 从手上物品生成需求。 */
	public static KitConfig.ActivityNeed fromHeld(ItemStack stack, int target) {
		if (stack == null || stack.isEmpty()) return null;
		String id = BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();
		KitConfig.ActivityNeed need = new KitConfig.ActivityNeed();
		need.match = "item:" + id;
		need.label = stack.getHoverName().getString();
		need.target = Math.max(1, Math.min(9999, target));
		return need;
	}

	/** 构造一条 ActivityNeed。 */
	public static KitConfig.ActivityNeed need(String match, String label, int target) {
		KitConfig.ActivityNeed need = new KitConfig.ActivityNeed();
		need.match = match;
		need.label = label;
		need.target = target;
		return need;
	}

	/** 生成新清单唯一 id。 */
	public static String newListId() {
		return "CUSTOM_" + Long.toString(System.currentTimeMillis(), 36).toUpperCase(Locale.ROOT);
	}

	/** 清单无标题时的回退名。 */
	private static String fallbackLabel(String match) {
		if (match.startsWith("item:")) return match.substring(5);
		if (match.startsWith("tag:")) return match.substring(4);
		if ("food".equals(match)) return "熟食";
		if ("gold_armor".equals(match)) return "金质护甲";
		if ("fire_resistance".equals(match)) return "抗火药水";
		return match;
	}

	/** 物品是否匹配需求谓词。 */
	private static Predicate<ItemStack> matcher(String match) {
		return switch (match) {
			case "ranged_weapon" -> stack -> stack.is(Items.BOW) || stack.is(Items.CROSSBOW);
			case "building_blocks" -> stack -> stack.is(Items.COBBLESTONE) || stack.is(Items.COBBLED_DEEPSLATE)
				|| stack.is(Items.STONE) || stack.is(Items.DIRT) || stack.is(Items.NETHERRACK);
			case "food" -> ActivityRequirements::isTravelFood;
			case "gold_armor" -> ActivityRequirements::isGoldArmor;
			case "fire_resistance" -> ActivityRequirements::isFireResistancePotion;
			default -> {
				if (match.startsWith("item:")) {
					Identifier id = Identifier.tryParse(match.substring(5));
					yield id == null ? stack -> false : stack -> id.equals(BuiltInRegistries.ITEM.getKey(stack.getItem()));
				}
				if (match.startsWith("tag:")) {
					Identifier id = Identifier.tryParse(match.substring(4));
					if (id == null) yield stack -> false;
					TagKey<Item> tag = TagKey.create(Registries.ITEM, id);
					yield stack -> stack.typeHolder().is(tag);
				}
				yield stack -> false;
			}
		};
	}

	/** 是否金质盔甲。 */
	private static boolean isGoldArmor(ItemStack stack) {
		return stack.is(Items.GOLDEN_HELMET)
			|| stack.is(Items.GOLDEN_CHESTPLATE)
			|| stack.is(Items.GOLDEN_LEGGINGS)
			|| stack.is(Items.GOLDEN_BOOTS);
	}

	/** 是否适合赶路的食物。 */
	private static boolean isTravelFood(ItemStack stack) {
		return stack.is(Items.BREAD)
			|| stack.is(Items.COOKED_BEEF)
			|| stack.is(Items.COOKED_PORKCHOP)
			|| stack.is(Items.COOKED_CHICKEN)
			|| stack.is(Items.COOKED_MUTTON)
			|| stack.is(Items.COOKED_RABBIT)
			|| stack.is(Items.COOKED_COD)
			|| stack.is(Items.COOKED_SALMON)
			|| stack.is(Items.BAKED_POTATO)
			|| stack.is(Items.GOLDEN_CARROT)
			|| stack.has(DataComponents.FOOD) && stack.is(Items.GOLDEN_APPLE);
	}

	/** 是否抗火药水。 */
	private static boolean isFireResistancePotion(ItemStack stack) {
		if (!stack.is(Items.POTION) && !stack.is(Items.SPLASH_POTION) && !stack.is(Items.LINGERING_POTION)) return false;
		PotionContents potion = stack.get(DataComponents.POTION_CONTENTS);
		return potion != null && (potion.is(Potions.FIRE_RESISTANCE) || potion.is(Potions.LONG_FIRE_RESISTANCE));
	}
}
