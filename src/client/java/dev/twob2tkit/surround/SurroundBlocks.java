package dev.twob2tkit.surround;

import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

/** 围箱可用方块：列表从前到后是优先级。 */
public final class SurroundBlocks {
	/** 目录项：注册表 ID + 界面中文名。 */
	public record Choice(String id, String label) {
	}

	/** 界面点选目录（不含用户自定义追加）。 */
	public static final List<Choice> CATALOG = List.of(
		new Choice("minecraft:cobblestone", "圆石"),
		new Choice("minecraft:dirt", "泥土"),
		new Choice("minecraft:stone", "石头"),
		new Choice("minecraft:oak_planks", "木板"),
		new Choice("minecraft:white_wool", "羊毛"),
		new Choice("minecraft:obsidian", "黑曜石"),
		new Choice("minecraft:cobbled_deepslate", "深板岩圆石"),
		new Choice("minecraft:netherrack", "地狱岩")
	);

	/** 「常用一套」预设 ID，顺序即使用优先级。 */
	public static final List<String> DEFAULT_IDS = List.of(
		"minecraft:cobblestone",
		"minecraft:dirt",
		"minecraft:stone",
		"minecraft:oak_planks",
		"minecraft:white_wool",
		"minecraft:obsidian"
	);

	private SurroundBlocks() {
	}

	/** 去重、校验为可放置方块；空列表则回落默认预设。 */
	public static List<String> normalize(List<String> raw) {
		LinkedHashSet<String> unique = new LinkedHashSet<>();
		if (raw != null) {
			for (String value : raw) {
				String id = canonical(value);
				if (id != null && itemOf(id) instanceof BlockItem) unique.add(id);
			}
		}
		if (unique.isEmpty()) unique.addAll(DEFAULT_IDS);
		return new ArrayList<>(unique);
	}

	/** 规范化物品 ID（补 minecraft:、校验注册表）；无效则 null。 */
	public static String canonical(String raw) {
		if (raw == null) return null;
		String text = raw.trim();
		if (text.isEmpty()) return null;
		if (!text.contains(":")) text = "minecraft:" + text;
		Identifier id = Identifier.tryParse(text);
		if (id == null || !BuiltInRegistries.ITEM.containsKey(id)) return null;
		return id.toString();
	}

	/**
	 * 按优先级选出当前该用的围箱物品。
	 * 创造/无限材料用列表第一项；生存则选背包里有的最高优先级。
	 */
	public static Item resolve(Player player, List<String> ids) {
		List<String> order = normalize(ids);
		if (player != null && player.hasInfiniteMaterials()) {
			Item first = itemOf(order.getFirst());
			return first == Items.AIR ? Items.COBBLESTONE : first;
		}
		for (String id : order) {
			Item item = itemOf(id);
			if (item == Items.AIR || !(item instanceof BlockItem)) continue;
			if (player != null && count(player, item) > 0) return item;
		}
		Item fallback = itemOf(order.getFirst());
		return fallback == Items.AIR ? Items.COBBLESTONE : fallback;
	}

	/** 统计背包非装备栏 + 副手中该物品数量。 */
	public static int count(Player player, Item item) {
		int total = 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (stack.is(item)) total += stack.getCount();
		}
		if (player.getOffhandItem().is(item)) total += player.getOffhandItem().getCount();
		return total;
	}

	/** 方块状态对应物品是否在勾选列表中。 */
	public static boolean accepts(BlockState state, List<String> ids) {
		Item item = state.getBlock().asItem();
		if (item == Items.AIR) return false;
		String id = BuiltInRegistries.ITEM.getKey(item).toString();
		return normalize(ids).contains(id);
	}

	/** 界面显示名：目录中文优先，否则用物品悬停名。 */
	public static String label(String id) {
		String canonical = canonical(id);
		if (canonical == null) return id;
		for (Choice choice : CATALOG) {
			if (choice.id.equals(canonical)) return choice.label;
		}
		Item item = itemOf(canonical);
		return new ItemStack(item).getHoverName().getString();
	}

	/** 前几项优先级摘要，供状态栏与提示。 */
	public static String summary(List<String> ids) {
		List<String> order = normalize(ids);
		List<String> labels = new ArrayList<>();
		int shown = Math.min(4, order.size());
		for (int i = 0; i < shown; i++) labels.add((i + 1) + "." + label(order.get(i)));
		if (order.size() > shown) labels.add("等" + order.size() + "种");
		return String.join(" ", labels);
	}

	/** 由 ID 取物品；无效则 AIR。 */
	public static Item itemOf(String id) {
		Identifier identifier = Identifier.tryParse(id);
		if (identifier == null || !BuiltInRegistries.ITEM.containsKey(identifier)) return Items.AIR;
		return BuiltInRegistries.ITEM.getValue(identifier);
	}
}
