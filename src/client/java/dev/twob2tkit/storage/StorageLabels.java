package dev.twob2tkit.storage;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.DyeColor;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.BarrelBlock;
import net.minecraft.world.level.block.ChestBlock;
import net.minecraft.world.level.block.CopperChestBlock;
import net.minecraft.world.level.block.HopperBlock;
import net.minecraft.world.level.block.ShulkerBoxBlock;
import net.minecraft.world.level.block.WeatheringCopper;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.SignBlockEntity;
import net.minecraft.world.level.block.entity.SignText;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.ChestType;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import dev.twob2tkit.KitConfig;

/** 打开箱子时读告示牌备注、潜影盒/铜箱/旁边染色方块的颜色。 */
public final class StorageLabels {
	private static final String[] COLOR_SUFFIXES = {
		"_glazed_terracotta",
		"_stained_glass_pane",
		"_stained_glass",
		"_concrete_powder",
		"_terracotta",
		"_concrete",
		"_carpet",
		"_candle",
		"_wool",
		"_banner"
	};

	/** 仓库标签与告示牌着色工具。 */
	private StorageLabels() {
	}

    /** Missing containers now become history through StorageLifecycle; never delete a record here. */
    @Deprecated
    public static boolean shouldPruneMissingRecord(Level level,BlockPos pos){return false;}

	/** 是否箱子类存储方块。 */
	public static boolean isStorageBlock(Level level, BlockPos pos) {
		if (level == null || pos == null) return false;
		BlockState state = level.getBlockState(pos);
		var block = state.getBlock();
		if (block instanceof ChestBlock || block instanceof ShulkerBoxBlock
			|| block instanceof HopperBlock || block instanceof BarrelBlock
			|| block instanceof CopperChestBlock) {
			return true;
		}
		String path = BuiltInRegistries.BLOCK.getKey(block).getPath();
		return path.contains("shulker_box") || path.contains("chest")
			|| path.equals("hopper") || path.equals("barrel");
	}

	/** 大箱子两格合成一条记录，用较小的那格当坐标。 */
	public static BlockPos canonicalPos(Level level, BlockPos pos) {
		if (level == null || pos == null) return pos;
		BlockPos best = pos.immutable();
		for (BlockPos part : cluster(level, pos)) {
			if (part.getX() < best.getX()
				|| part.getX() == best.getX() && part.getZ() < best.getZ()
				|| part.getX() == best.getX() && part.getZ() == best.getZ() && part.getY() < best.getY()) {
				best = part.immutable();
			}
		}
		return best;
	}

	/** 给附近存储贴标签/告示牌色。 */
	public static void apply(Level level, BlockPos pos, KitConfig.StorageSnapshot snapshot) {
		if (level == null || pos == null || snapshot == null) return;
		Set<BlockPos> cluster = cluster(level, pos);
		snapshot.blockId = BuiltInRegistries.BLOCK.getKey(level.getBlockState(pos).getBlock()).toString();
		snapshot.colorId = firstNonBlank(containerColor(level, pos), nearbyDye(level, cluster), signDye(level, cluster));
		snapshot.note = signs(level, cluster);
	}

	/** 标签主标题。 */
	public static String headline(KitConfig.StorageSnapshot snapshot) {
		if (snapshot == null) return "箱子";
		String name = blank(snapshot.note) ? (blank(snapshot.title) ? "箱子" : snapshot.title) : snapshot.note;
		String color = colorLabel(snapshot.colorId);
		if (!color.isEmpty() && !name.contains(color)) return color + " · " + name;
		return name;
	}

	/** 按完整物品 ID 汇总；搜索命中不同物品时分别显示，数量仅来自开箱缓存。 */
	public static String quantitySummary(KitConfig.StorageSnapshot snapshot, String query) {
		var counts = new LinkedHashMap<String, Long>();
		var names = new LinkedHashMap<String, String>();
		if (snapshot != null && snapshot.items != null) for (var item : snapshot.items) {
			if (item == null || item.count <= 0) continue;
			String id = blank(item.id) ? "" : item.id;
			String name = blank(item.name) ? id : item.name;
			if (name.isEmpty()) continue;
			String key = id.isEmpty() ? "name:" + name : id;
			counts.merge(key, (long)item.count, Long::sum);
			names.putIfAbsent(key, name);
		}
		String normalized = query == null ? "" : query.strip().toLowerCase(Locale.ROOT);
		List<String> hits = new ArrayList<>();
		if (!normalized.isEmpty()) for (var entry : counts.entrySet()) {
			String text = (entry.getKey() + " " + names.get(entry.getKey())).toLowerCase(Locale.ROOT);
			if (java.util.Arrays.stream(normalized.split("\\s+")).allMatch(text::contains))
				hits.add(names.get(entry.getKey()) + "×" + entry.getValue());
		}
		if (!hits.isEmpty()) return "开箱缓存：" + String.join(" · ", hits.subList(0, Math.min(3, hits.size())))
			+ (hits.size() > 3 ? " · 另 " + (hits.size() - 3) + " 类" : "");
		long total = counts.values().stream().mapToLong(Long::longValue).sum();
		return "开箱缓存：" + (total == 0 ? "空箱" : counts.size() + " 类 · 共 " + total + " 件");
	}

    /** Search is answered entirely from recorded contents; timestamps cannot imply live stock. */
    public static String cacheSummary(KitConfig.StorageSnapshot snapshot, String query) {
        return quantitySummary(snapshot, query) + " · 内容 " + contentTime(snapshot)
            + (snapshot != null && snapshot.contentsDirty ? " · 待确认" : "");
    }
    public static String contentTime(KitConfig.StorageSnapshot snapshot) {
        return snapshot == null || snapshot.lastSeenEpochMillis <= 0 ? "时间未知"
            : java.time.format.DateTimeFormatter.ofPattern("MM-dd HH:mm")
                .withZone(java.time.ZoneId.systemDefault())
                .format(java.time.Instant.ofEpochMilli(snapshot.lastSeenEpochMillis));
    }
    public static String evidenceSummary(KitConfig.StorageSnapshot snapshot) {
        String result = "内容观察：" + contentTime(snapshot) + " · " + StorageLifecycle.statusLabel(snapshot);
        if (snapshot != null && snapshot.contentsDirty && snapshot.contentsDirtyReason != null
            && !snapshot.contentsDirtyReason.isBlank()) result += "；" + snapshot.contentsDirtyReason;
        return result + "；实际取料以服务器槽位为准";
    }

	/** 颜色中文名。 */
	public static String colorLabel(String colorId) {
		if (blank(colorId)) return "";
		return switch (colorId) {
			case "white" -> "白";
			case "orange" -> "橙";
			case "magenta" -> "品红";
			case "light_blue" -> "浅蓝";
			case "yellow" -> "黄";
			case "lime" -> "黄绿";
			case "pink" -> "粉";
			case "gray" -> "灰";
			case "light_gray" -> "浅灰";
			case "cyan" -> "青";
			case "purple" -> "紫";
			case "blue" -> "蓝";
			case "brown" -> "棕";
			case "green" -> "绿";
			case "red" -> "红";
			case "black" -> "黑";
			case "copper" -> "铜";
			case "exposed_copper" -> "斑驳铜";
			case "weathered_copper" -> "锈铜";
			case "oxidized_copper" -> "氧化铜";
			default -> colorId;
		};
	}

	/** 颜色 RGB。 */
	public static int colorRgb(String colorId) {
		if (blank(colorId)) return 0;
		DyeColor dye = DyeColor.byName(colorId, null);
		if (dye != null) return dye.getTextureDiffuseColor();
		return switch (colorId) {
			case "copper" -> 0xB87333;
			case "exposed_copper" -> 0xC08A6A;
			case "weathered_copper" -> 0x6D9A78;
			case "oxidized_copper" -> 0x4FA38A;
			default -> 0;
		};
	}

	/** 告示牌行拼成一行。 */
	public static String joinSignLines(String... lines) {
		if (lines == null || lines.length == 0) return "";
		StringBuilder text = new StringBuilder();
		for (String line : lines) {
			if (line == null) continue;
			String trimmed = line.strip();
			if (trimmed.isEmpty()) continue;
			if (text.length() > 0) text.append(' ');
			text.append(trimmed);
		}
		return text.toString();
	}

	/** 同色邻近存储聚成一组。 */
	public static Set<BlockPos> cluster(Level level, BlockPos pos) {
		Set<BlockPos> cluster = new LinkedHashSet<>();
		cluster.add(pos.immutable());
		BlockState state = level.getBlockState(pos);
		if (state.hasProperty(ChestBlock.TYPE) && state.getValue(ChestBlock.TYPE) != ChestType.SINGLE) {
			cluster.add(ChestBlock.getConnectedBlockPos(pos, state).immutable());
		}
		return cluster;
	}

	/** 存储对应标签色。 */
	private static String containerColor(Level level, BlockPos pos) {
		BlockState state = level.getBlockState(pos);
		if (state.getBlock() instanceof ShulkerBoxBlock shulker && shulker.getColor() != null) {
			return shulker.getColor().getSerializedName();
		}
		if (state.getBlock() instanceof CopperChestBlock copper) {
			WeatheringCopper.WeatherState weather = copper.getState();
			if (weather == WeatheringCopper.WeatherState.EXPOSED) return "exposed_copper";
			if (weather == WeatheringCopper.WeatherState.WEATHERED) return "weathered_copper";
			if (weather == WeatheringCopper.WeatherState.OXIDIZED) return "oxidized_copper";
			return "copper";
		}
		return "";
	}

	/** 附近可用染料。 */
	private static String nearbyDye(Level level, Set<BlockPos> cluster) {
		for (BlockPos chest : cluster) {
			for (Direction direction : Direction.values()) {
				String color = dyeFromBlock(level.getBlockState(chest.relative(direction)));
				if (!color.isEmpty()) return color;
			}
		}
		return "";
	}

	/** 方块推断染料色。 */
	private static String dyeFromBlock(BlockState state) {
		String path = BuiltInRegistries.BLOCK.getKey(state.getBlock()).getPath();
		List<DyeColor> dyes = new ArrayList<>(List.of(DyeColor.values()));
		dyes.sort(Comparator.comparingInt((DyeColor dye) -> dye.getSerializedName().length()).reversed());
		for (DyeColor dye : dyes) {
			String name = dye.getSerializedName();
			if (!path.startsWith(name + "_")) continue;
			String rest = path.substring(name.length());
			for (String suffix : COLOR_SUFFIXES) {
				if (rest.equals(suffix)) return name;
			}
		}
		return "";
	}

	/** 告示牌当前染料。 */
	private static String signDye(Level level, Set<BlockPos> cluster) {
		for (BlockPos signPos : signPositions(cluster)) {
			if (!(level.getBlockEntity(signPos) instanceof SignBlockEntity sign)) continue;
			DyeColor front = sign.getFrontText().getColor();
			if (front != DyeColor.BLACK) return front.getSerializedName();
			DyeColor back = sign.getBackText().getColor();
			if (back != DyeColor.BLACK) return back.getSerializedName();
		}
		return "";
	}

	/** 附近告示牌列表。 */
	private static String signs(Level level, Set<BlockPos> cluster) {
		LinkedHashSet<String> notes = new LinkedHashSet<>();
		for (BlockPos signPos : signPositions(cluster)) {
			BlockEntity entity = level.getBlockEntity(signPos);
			if (!(entity instanceof SignBlockEntity sign)) continue;
			String text = firstNonBlank(sideText(sign.getFrontText()), sideText(sign.getBackText()));
			if (!text.isEmpty()) notes.add(text);
		}
		return String.join(" / ", notes);
	}

	/** 告示牌坐标。 */
	private static List<BlockPos> signPositions(Set<BlockPos> cluster) {
		LinkedHashSet<BlockPos> positions = new LinkedHashSet<>();
		for (BlockPos chest : cluster) {
			for (Direction direction : Direction.values()) {
				positions.add(chest.relative(direction));
			}
			positions.add(chest.above(2));
		}
		return List.copyOf(positions);
	}

	/** 侧面文字。 */
	private static String sideText(SignText text) {
		if (text == null) return "";
		String[] lines = new String[4];
		for (int i = 0; i < 4; i++) {
			lines[i] = text.getMessage(i, false).getString();
		}
		return joinSignLines(lines);
	}

	/** 第一条非空行。 */
	private static String firstNonBlank(String... values) {
		for (String value : values) {
			if (!blank(value)) return value;
		}
		return "";
	}

	/** 是否空白告示牌。 */
	private static boolean blank(String value) {
		return value == null || value.isBlank();
	}
}
