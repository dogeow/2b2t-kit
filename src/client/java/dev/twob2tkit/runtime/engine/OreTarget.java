package dev.twob2tkit.runtime.engine;

import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** 盾构机可勾选的矿种，以及配置字符串的解析与匹配。 */
public enum OreTarget {
	DIAMOND("钻石"),
	COAL("煤矿"),
	IRON("铁矿"),
	GOLD("金矿"),
	REDSTONE("红石"),
	LAPIS("青金石"),
	COPPER("铜矿"),
	EMERALD("绿宝石"),
	QUARTZ("下界石英"),
	ANCIENT_DEBRIS("远古残骸"),
	ANY("任意矿石");

	public final String label;

	OreTarget(String label) {
		this.label = label;
	}

	/** 取配置里的第一种矿；空配置当作钻石。 */
	static OreTarget fromConfig(String value) {
		return parseList(value).getFirst();
	}

	/** 把逗号分隔的配置解析成矿种列表；含「全选」时只保留全选。 */
	static List<OreTarget> parseList(String value) {
		ArrayList<OreTarget> selected = new ArrayList<>();
		if (value != null) {
			for (String part : value.split("[,;|\\s]+")) {
				if (part.isBlank()) continue;
				try {
					OreTarget target = valueOf(part.trim().toUpperCase(Locale.ROOT));
					if (!selected.contains(target)) selected.add(target);
				} catch (IllegalArgumentException ignored) {
				}
			}
		}
		if (selected.contains(ANY)) return List.of(ANY);
		if (selected.isEmpty()) return List.of(DIAMOND);
		return selected;
	}

	/** 方块是否属于当前勾选的矿种。 */
	static boolean selectedMatches(String value, BlockState state) {
		for (OreTarget target : parseList(value)) {
			if (target.matches(state)) return true;
		}
		return false;
	}

	/** 掉落物是否属于当前勾选的矿种。 */
	static boolean selectedMatchesDrop(String value, ItemStack stack) {
		for (OreTarget target : parseList(value)) {
			if (target.matchesDrop(stack)) return true;
		}
		return false;
	}

	/** 不构造 ItemStack 的纯物品匹配，供扫描规则和轻量回归测试复用。 */
	static boolean selectedMatchesDropItem(String value, Item item) {
		for (OreTarget target : parseList(value)) {
			if (target.matchesDropItem(item)) return true;
		}
		return false;
	}

	/** 勾选矿种的中文名，多个用顿号连接。 */
	static String selectedLabel(String value) {
		List<OreTarget> selected = parseList(value);
		if (selected.contains(ANY)) return ANY.label;
		StringBuilder text = new StringBuilder();
		for (OreTarget target : selected) {
			if (!text.isEmpty()) text.append('、');
			text.append(target.label);
		}
		return text.toString();
	}

	/** 在勾选矿种里找出匹配该方块的第一种。 */
	static OreTarget firstMatching(String value, BlockState state) {
		for (OreTarget target : parseList(value)) {
			if (target == ANY) {
				for (OreTarget concrete : values()) {
					if (concrete != ANY && concrete.matches(state)) return concrete;
				}
				continue;
			}
			if (target.matches(state)) return target;
		}
		return null;
	}

	/** 该矿种是否对应此方块（含深层变种）。 */
	boolean matches(BlockState state) {
		return switch (this) {
			case DIAMOND -> state.is(Blocks.DIAMOND_ORE) || state.is(Blocks.DEEPSLATE_DIAMOND_ORE);
			case COAL -> state.is(Blocks.COAL_ORE) || state.is(Blocks.DEEPSLATE_COAL_ORE);
			case IRON -> state.is(Blocks.IRON_ORE) || state.is(Blocks.DEEPSLATE_IRON_ORE);
			case GOLD -> state.is(Blocks.GOLD_ORE) || state.is(Blocks.DEEPSLATE_GOLD_ORE) || state.is(Blocks.NETHER_GOLD_ORE);
			case REDSTONE -> state.is(Blocks.REDSTONE_ORE) || state.is(Blocks.DEEPSLATE_REDSTONE_ORE);
			case LAPIS -> state.is(Blocks.LAPIS_ORE) || state.is(Blocks.DEEPSLATE_LAPIS_ORE);
			case COPPER -> state.is(Blocks.COPPER_ORE) || state.is(Blocks.DEEPSLATE_COPPER_ORE);
			case EMERALD -> state.is(Blocks.EMERALD_ORE) || state.is(Blocks.DEEPSLATE_EMERALD_ORE);
			case QUARTZ -> state.is(Blocks.NETHER_QUARTZ_ORE);
			case ANCIENT_DEBRIS -> state.is(Blocks.ANCIENT_DEBRIS);
			case ANY -> isAnyOre(state);
		};
	}

	/** 该矿种是否对应此掉落物（原矿、粗矿或成品）。 */
	boolean matchesDrop(ItemStack stack) {
		return !stack.isEmpty() && matchesDropItem(stack.getItem());
	}

	/** 掉落物是否匹配勾选矿种。 */
	private boolean matchesDropItem(Item item) {
		return switch (this) {
			case DIAMOND -> item == Items.DIAMOND || item == Items.DIAMOND_ORE || item == Items.DEEPSLATE_DIAMOND_ORE;
			case COAL -> item == Items.COAL || item == Items.COAL_ORE || item == Items.DEEPSLATE_COAL_ORE;
			case IRON -> item == Items.RAW_IRON || item == Items.IRON_ORE || item == Items.DEEPSLATE_IRON_ORE;
			case GOLD -> item == Items.RAW_GOLD || item == Items.GOLD_NUGGET
				|| item == Items.GOLD_ORE || item == Items.DEEPSLATE_GOLD_ORE || item == Items.NETHER_GOLD_ORE;
			case REDSTONE -> item == Items.REDSTONE || item == Items.REDSTONE_ORE || item == Items.DEEPSLATE_REDSTONE_ORE;
			case LAPIS -> item == Items.LAPIS_LAZULI || item == Items.LAPIS_ORE || item == Items.DEEPSLATE_LAPIS_ORE;
			case COPPER -> item == Items.RAW_COPPER || item == Items.COPPER_ORE || item == Items.DEEPSLATE_COPPER_ORE;
			case EMERALD -> item == Items.EMERALD || item == Items.EMERALD_ORE || item == Items.DEEPSLATE_EMERALD_ORE;
			case QUARTZ -> item == Items.QUARTZ || item == Items.NETHER_QUARTZ_ORE;
			case ANCIENT_DEBRIS -> item == Items.ANCIENT_DEBRIS || item == Items.NETHERITE_SCRAP;
			case ANY -> isAnyOreDropItem(item);
		};
	}

	/** 是否为任意已登记矿石方块。 */
	private static boolean isAnyOre(BlockState state) {
		for (OreTarget target : values()) {
			if (target != ANY && target.matches(state)) return true;
		}
		return false;
	}

	/** 是否为任意已登记矿石掉落物。 */
	private static boolean isAnyOreDrop(ItemStack stack) {
		for (OreTarget target : values()) {
			if (target != ANY && target.matchesDrop(stack)) return true;
		}
		return false;
	}

	/** 是否为任一常见矿石掉落物。 */
	private static boolean isAnyOreDropItem(Item item) {
		for (OreTarget target : values()) {
			if (target != ANY && target.matchesDropItem(item)) return true;
		}
		return false;
	}

	/** 时运能增加掉落的矿石。远古残骸不受时运影响。 */
	static boolean fortuneApplies(BlockState state) {
		if (state.is(Blocks.ANCIENT_DEBRIS)) return false;
		return isAnyOre(state);
	}
}
