package dev.twob2tkit.chopper;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** 连通原木扫描：超过 80 根当建筑跳过，可选必须连着树叶。 */
public final class ChopperTrees {
	/** 单棵树原木上限；超过当建筑忽略。 */
	public static final int MAX_LOGS = 80;
	/** 「必须连着树叶」时最少树叶数。 */
	public static final int MIN_LEAVES = 4;

	private ChopperTrees() {
	}

	/** 一棵树：原木列表、可补种树桩、最低基座。 */
	public record Tree(List<BlockPos> logs, List<BlockPos> stumps, BlockPos base) {
	}

	/** 玩家附近最近一棵合法树；没有则 null。 */
	public static Tree findNearest(Minecraft client, LocalPlayer player, int range, boolean requireLeaves, Set<BlockPos> ignored) {
		BlockPos origin = player.blockPosition();
		Set<BlockPos> seen = new HashSet<>();
		Tree best = null;
		double bestDist = Double.MAX_VALUE;
		for (int dx = -range; dx <= range; dx++) {
			for (int dz = -range; dz <= range; dz++) {
				if (dx * dx + dz * dz > range * range) continue;
				for (int dy = -1; dy <= 24; dy++) {
					BlockPos pos = origin.offset(dx, dy, dz);
					if (!client.level.hasChunkAt(pos) || seen.contains(pos) || ignored.contains(pos)) continue;
					if (!isWood(client.level.getBlockState(pos))) continue;
					Tree tree = flood(client, pos, seen, requireLeaves, ignored);
					if (tree == null) continue;
					double dist = player.position().distanceToSqr(Vec3.atCenterOf(tree.base));
					if (dist < bestDist) {
						bestDist = dist;
						best = tree;
					}
				}
			}
		}
		return best;
	}

	/** 从起点 BFS 连通原木；太大或叶不够则整片进 ignored。 */
	private static Tree flood(Minecraft client, BlockPos start, Set<BlockPos> globalSeen, boolean requireLeaves, Set<BlockPos> ignored) {
		List<BlockPos> logs = new ArrayList<>();
		ArrayDeque<BlockPos> queue = new ArrayDeque<>();
		Set<BlockPos> local = new HashSet<>();
		queue.add(start);
		local.add(start);
		boolean tooBig = false;
		while (!queue.isEmpty()) {
			BlockPos pos = queue.removeFirst();
			if (!isWood(client.level.getBlockState(pos))) continue;
			logs.add(pos);
			if (logs.size() > MAX_LOGS) {
				tooBig = true;
				break;
			}
			for (int dx = -1; dx <= 1; dx++) {
				for (int dy = -1; dy <= 1; dy++) {
					for (int dz = -1; dz <= 1; dz++) {
						if (dx == 0 && dy == 0 && dz == 0) continue;
						BlockPos next = pos.offset(dx, dy, dz);
						if (!local.add(next) || !client.level.hasChunkAt(next)) continue;
						if (isWood(client.level.getBlockState(next))) queue.add(next);
					}
				}
			}
		}
		globalSeen.addAll(local);
		if (tooBig) {
			ignored.addAll(local);
			return null;
		}
		if (requireLeaves && countLeaves(client, logs) < MIN_LEAVES) {
			ignored.addAll(local);
			return null;
		}
		List<BlockPos> bases = new ArrayList<>();
		BlockPos lowest = logs.getFirst();
		for (BlockPos log : logs) {
			if (log.getY() < lowest.getY()) lowest = log;
			if (!isWood(client.level.getBlockState(log.below()))) bases.add(log.immutable());
		}
		return new Tree(List.copyOf(logs), bases, lowest.immutable());
	}

	/** 原木周围树叶数量（够 {@link #MIN_LEAVES} 可早停）。 */
	public static int countLeaves(Minecraft client, List<BlockPos> logs) {
		int count = 0;
		Set<BlockPos> counted = new HashSet<>();
		for (BlockPos log : logs) {
			for (int dx = -2; dx <= 2; dx++) {
				for (int dy = 0; dy <= 3; dy++) {
					for (int dz = -2; dz <= 2; dz++) {
						BlockPos pos = log.offset(dx, dy, dz);
						if (!counted.add(pos)) continue;
						if (client.level.getBlockState(pos).is(BlockTags.LEAVES) && ++count >= MIN_LEAVES) return count;
					}
				}
			}
		}
		return count;
	}

	/** 原木标签或红树根。 */
	public static boolean isWood(BlockState state) {
		return state.is(BlockTags.LOGS) || state.is(Blocks.MANGROVE_ROOTS) || state.is(Blocks.MUDDY_MANGROVE_ROOTS);
	}

	/** 非空气、可破坏、当前游戏模式允许。 */
	public static boolean canBreak(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		if (state.isAir() || state.getDestroySpeed(client.level, pos) < 0.0F) return false;
		return !client.player.blockActionRestricted(client.level, pos, client.gameMode.getPlayerMode());
	}

	/** 由原木方块推断对应树苗/真菌/红树胚芽。 */
	public static Item saplingFor(Block log) {
		Identifier id = BuiltInRegistries.BLOCK.getKey(log);
		if (id == null) return null;
		String path = id.getPath();
		if (path.startsWith("stripped_")) path = path.substring("stripped_".length());
		if (path.contains("mangrove")) {
			return item(id.getNamespace(), "mangrove_propagule");
		}
		path = path.replace("_log", "").replace("_wood", "").replace("_stem", "").replace("_hyphae", "")
			.replace("_roots", "");
		if (path.equals("crimson") || path.equals("warped")) {
			return item(id.getNamespace(), path + "_fungus");
		}
		return item(id.getNamespace(), path + "_sapling");
	}

	/** 按命名空间路径取物品；不存在则 null。 */
	private static Item item(String namespace, String path) {
		Identifier id = Identifier.fromNamespaceAndPath(namespace, path);
		return BuiltInRegistries.ITEM.containsKey(id) ? BuiltInRegistries.ITEM.getValue(id) : null;
	}
}
