package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.block.state.BlockState;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.List;

/** 找矿扫描、顺路矿和暂时跳过矿脉。 */
final class BorerOreScan {
	static final int SIDE_RADIUS = 5;
	static final int LAYERS_PER_TICK = 4;

	private final DefaultTunnelBorerEngine engine;

	BorerOreScan(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 分批扫描已加载区块，锁定最近的勾选矿石。 */
	void updateTarget(Minecraft client, LocalPlayer player) {
		if (engine.mode != DefaultTunnelBorerEngine.Mode.ORE) {
			engine.oreTargetPos = null;
			engine.sideOreTargetPos = null;
			resetState();
			return;
		}
		pruneBlocked(client);
		if (engine.oreTargetPos != null && !isBlocked(engine.oreTargetPos)
			&& engine.wantedBlock(client.level.getBlockState(engine.oreTargetPos))) {
			if (!reachableAtCurrentHeight(client, player, engine.oreTargetPos)) {
				skipActive(client, "矿石 " + BorerText.block(engine.oreTargetPos) + " 低于当前站立高度，脚下已是基岩，不再往下绕");
				return;
			}
			if (engine.currentTarget == null) {
				engine.lockHeadingToward(player.blockPosition(), engine.oreTargetPos);
			}
			return;
		}
		engine.oreTargetPos = null;
		if (engine.oreScanCooldown > 0) {
			engine.oreScanCooldown--;
			return;
		}
		BlockPos feet = player.blockPosition();
		int radius = Math.max(8, Math.min(32, engine.host.borerOreRadius()));
		List<Entity> hostiles = engine.host.borerPauseOnMob()
			? engine.mobs.nearby(client, player, radius + 8.0)
			: List.of();
		prepare(feet);
		int minY = client.level.getMinY();
		int maxY = client.level.getMaxY() - 1;
		int centerY = Mth.clamp(engine.oreScanCenter.getY(), minY, maxY);
		int maxOffset = Math.max(centerY - minY, maxY - centerY);
		int totalSlots = maxOffset * 2 + 1;
		int scannedLayers = 0;
		double best = Double.MAX_VALUE;
		while (scannedLayers < LAYERS_PER_TICK && engine.oreScanLayerCursor < totalSlots) {
			int slot = engine.oreScanLayerCursor++;
			int step = (slot + 1) / 2;
			int dy = slot == 0 ? 0 : (slot % 2 == 1 ? -step : step);
			int y = centerY + dy;
			if (y < minY || y > maxY) continue;
			scannedLayers++;
			for (int dx = -radius; dx <= radius; dx++) {
				for (int dz = -radius; dz <= radius; dz++) {
					if (dx * dx + dz * dz > radius * radius) continue;
					BlockPos pos = new BlockPos(engine.oreScanCenter.getX() + dx, y, engine.oreScanCenter.getZ() + dz);
					if (!client.level.hasChunkAt(pos)) continue;
					engine.oreScanCheckedBlocks++;
					if (isBlocked(pos) || !engine.wantedBlock(client.level.getBlockState(pos))) continue;
					if (BorerHazards.wouldOpenLava(client, pos) || BorerHazards.wouldOpenWater(client, pos)) continue;
					if (!reachableAtCurrentHeight(client, player, pos)) continue;
					if (!hostiles.isEmpty() && engine.mobs.nearCached(hostiles, pos, 5.0)) continue;
					double score = approachScore(feet, pos);
					if (score < best) {
						best = score;
						engine.oreTargetPos = pos.immutable();
					}
				}
			}
		}
		if (engine.oreTargetPos != null) {
			engine.fileLog(client, "ore-scan-found ore=" + engine.wantedLabel()
				+ " radius=" + radius + " yRange=" + minY + ".." + maxY
				+ " checked=" + engine.oreScanCheckedBlocks + " target=" + BorerText.block(engine.oreTargetPos)
				+ " player=" + BorerText.precise(player));
			if (engine.currentTarget == null) {
				engine.lockHeadingToward(feet, engine.oreTargetPos);
			}
			resetState();
			return;
		}
		if (engine.oreScanLayerCursor >= totalSlots) {
			engine.fileLog(client, "ore-scan-complete ore=" + engine.wantedLabel()
				+ " radius=" + radius + " yRange=" + minY + ".." + maxY
				+ " checked=" + engine.oreScanCheckedBlocks + " found=none center=" + BorerText.block(engine.oreScanCenter));
			engine.oreScanCenter = feet.immutable();
			engine.oreScanWantedKey = engine.oreConfig();
			engine.oreScanLayerCursor = 0;
			engine.oreScanCheckedBlocks = 0;
			engine.oreScanCooldown = 20;
		}
	}

	/** 按脚底准备扫描缓存。 */
	private void prepare(BlockPos feet) {
		boolean moved = engine.oreScanCenter != null
			&& (Math.abs(engine.oreScanCenter.getX() - feet.getX()) > 2
				|| Math.abs(engine.oreScanCenter.getY() - feet.getY()) > 2
				|| Math.abs(engine.oreScanCenter.getZ() - feet.getZ()) > 2);
		if (engine.oreScanCenter == null || !engine.oreConfig().equals(engine.oreScanWantedKey) || moved) {
			engine.oreScanCenter = feet.immutable();
			engine.oreScanWantedKey = engine.oreConfig();
			engine.oreScanLayerCursor = 0;
			engine.oreScanCheckedBlocks = 0;
		}
	}

	/** 清空扫描状态。 */
	void resetState() {
		engine.oreScanCooldown = 0;
		engine.oreScanCenter = null;
		engine.oreScanWantedKey = null;
		engine.oreScanLayerCursor = 0;
		engine.oreScanCheckedBlocks = 0;
	}

	/** 状态文案。 */
	String status(Minecraft client) {
		int radius = Math.max(8, Math.min(32, engine.host.borerOreRadius()));
		int minY = client.level.getMinY();
		int maxY = client.level.getMaxY() - 1;
		if (engine.oreScanCooldown > 0) {
			return "完整扫描未发现" + engine.wantedLabel() + "，即将重新扫描已加载区块";
		}
		int centerY = engine.oreScanCenter == null
			? Mth.clamp(client.player.blockPosition().getY(), minY, maxY)
			: engine.oreScanCenter.getY();
		int totalSlots = Math.max(centerY - minY, maxY - centerY) * 2 + 1;
		int progress = totalSlots <= 0 ? 0 : Math.min(99, engine.oreScanLayerCursor * 100 / totalSlots);
		return "正在扫描" + engine.wantedLabel() + "：水平半径 " + radius + "，Y " + minY + "～" + maxY + "（" + progress + "%）";
	}

	/** 更新身旁矿目标。 */
	void updateSideTarget(Minecraft client, LocalPlayer player) {
		if (engine.mode != DefaultTunnelBorerEngine.Mode.ORE) {
			engine.sideOreTargetPos = null;
			return;
		}
		BlockPos feet = player.blockPosition();
		BlockPos closest = null;
		double best = Double.MAX_VALUE;
		for (int dy = -SIDE_RADIUS; dy <= SIDE_RADIUS; dy++) {
			for (int dx = -SIDE_RADIUS; dx <= SIDE_RADIUS; dx++) {
				for (int dz = -SIDE_RADIUS; dz <= SIDE_RADIUS; dz++) {
					if (dx * dx + dy * dy + dz * dz > SIDE_RADIUS * SIDE_RADIUS) continue;
					BlockPos pos = feet.offset(dx, dy, dz);
					if (!client.level.hasChunkAt(pos) || isBlocked(pos) || !engine.wantedBlock(client.level.getBlockState(pos))) continue;
					if (BorerHazards.wouldOpenLava(client, pos) || BorerHazards.wouldOpenWater(client, pos)) continue;
					if (!reachableAtCurrentHeight(client, player, pos)) continue;
					double distance = approachScore(feet, pos);
					if (distance < best) {
						best = distance;
						closest = pos.immutable();
					}
				}
			}
		}
		engine.sideOreTargetPos = closest;
	}

	/** 暂时跳过当前矿脉并改找其它勾选矿石。拾取中不跳过，避免残骸掉落被清掉。 */
	boolean skipActive(Minecraft client, String reason) {
		if (engine.loot.active()) return false;
		BlockPos blocked = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		if (blocked == null || client.level == null) return false;
		if (client.player != null) engine.logDiagnostic(client, client.player, "skip-ore");
		engine.fileLog(client, "skip goal=" + BorerText.block(blocked) + " reason=" + reason);
		int blockedCount = blockCluster(client, blocked, client.level.getGameTime() + 200L);
		if (blocked.equals(engine.sideOreTargetPos)) engine.sideOreTargetPos = null;
		if (blocked.equals(engine.oreTargetPos)) engine.oreTargetPos = null;
		engine.clearMiningTarget(client, "skip-active-ore");
		engine.resetAimMissProgress();
		engine.frontOccluded = false;
		engine.occludedTicks = 0;
		engine.attemptedForward = false;
		engine.noMovementTicks = 0;
		resetState();
		engine.loot.clear();
		engine.resetJumpControl();
		engine.forcedTallObstacleLower = null;
		engine.liquidDetourPos = null;
		engine.lavaBypassTicks = 0;
		engine.releaseMine(client);
		engine.status = reason + "，已暂时跳过 " + BorerText.block(blocked)
			+ (blockedCount > 1 ? " 所在的 " + blockedCount + " 块矿脉" : "")
			+ " 并寻找其它矿石";
		engine.overlay(client, engine.status, 0xFFFF55);
		DefaultTunnelBorerEngine.message(client, engine.status);
		return true;
	}

	/** 统计同种矿簇大小。 */
	private int blockCluster(Minecraft client, BlockPos origin, long until) {
		ArrayDeque<BlockPos> pending = new ArrayDeque<>();
		HashSet<BlockPos> visited = new HashSet<>();
		OreTarget concreteOre = OreTarget.firstMatching(engine.oreConfig(), client.level.getBlockState(origin));
		int blockedCount = 0;
		pending.add(origin.immutable());
		while (!pending.isEmpty() && blockedCount < 128) {
			BlockPos pos = pending.removeFirst();
			if (!visited.add(pos)) continue;
			if (concreteOre == null || !concreteOre.matches(client.level.getBlockState(pos))) continue;
			engine.blockedOreTargets.put(pos.immutable(), until);
			blockedCount++;
			for (int dx = -1; dx <= 1; dx++) {
				for (int dy = -1; dy <= 1; dy++) {
					for (int dz = -1; dz <= 1; dz++) {
						if (dx == 0 && dy == 0 && dz == 0) continue;
						BlockPos neighbor = pos.offset(dx, dy, dz);
						if (!visited.contains(neighbor)) pending.addLast(neighbor.immutable());
					}
				}
			}
		}
		if (!engine.blockedOreTargets.containsKey(origin)) engine.blockedOreTargets.put(origin.immutable(), until);
		return Math.max(1, blockedCount);
	}

	/** 清掉暂时不可达的矿标记。 */
	void pruneBlocked(Minecraft client) {
		if (client.level == null) return;
		long now = client.level.getGameTime();
		engine.blockedOreTargets.entrySet().removeIf(entry -> entry.getValue() <= now);
	}

	/** 该矿是否被标为暂时不可达。 */
	boolean isBlocked(BlockPos pos) {
		return engine.blockedOreTargets.containsKey(pos);
	}

	/** 已经站在基岩上时，不要为更低的矿贴着基岩绕；通路被基岩挡住则立刻换目标。 */
	boolean skipIfHeightOrBedrock(Minecraft client, LocalPlayer player) {
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		if (goal == null) return false;
		if (!reachableAtCurrentHeight(client, player, goal)) {
			return skipActive(client, "矿石 " + BorerText.block(goal) + " 低于当前高度，脚下已是基岩，不再往下绕");
		}
		BlockPos wall = unbreakableBlockingToward(client, player, goal);
		if (wall == null) return false;
		return skipActive(client, "基岩挡住通路 " + BorerText.block(wall) + "，不贴着基岩绕路");
	}

	/** 1×2 通道高度：同层和头顶可挖；更低的矿只有能安全落下时才去。 */
	boolean reachableAtCurrentHeight(Minecraft client, LocalPlayer player, BlockPos ore) {
		BlockPos feet = player.blockPosition();
		int dy = ore.getY() - feet.getY();
		if (dy >= -1) return true;
		if (!BorerHazards.isUnbreakable(client, feet.below())) return true;
		for (Direction direction : Direction.Plane.HORIZONTAL) {
			if (BorerHazards.safeFallDepth(client, feet.relative(direction)) > 0) return true;
		}
		return false;
	}

	/** 朝目标路上不可破坏挡块。 */
	private BlockPos unbreakableBlockingToward(Minecraft client, LocalPlayer player, BlockPos goal) {
		BlockPos feet = player.blockPosition();
		int gx = goal.getX() - feet.getX();
		int gz = goal.getZ() - feet.getZ();
		int steps = Math.max(Math.abs(gx), Math.abs(gz));
		if (steps <= 0) {
			if (goal.getY() >= feet.getY()) return null;
			for (int y = feet.getY() - 1; y >= goal.getY(); y--) {
				BlockPos pos = new BlockPos(feet.getX(), y, feet.getZ());
				if (y == feet.getY() - 1) continue;
				if (BorerHazards.isUnbreakable(client, pos)) return pos;
			}
			return null;
		}
		int limit = Math.min(steps, 2);
		for (int i = 1; i <= limit; i++) {
			int x = feet.getX() + gx * i / steps;
			int z = feet.getZ() + gz * i / steps;
			for (int dy = 0; dy <= 1; dy++) {
				BlockPos pos = new BlockPos(x, feet.getY() + dy, z);
				if (BorerHazards.isUnbreakable(client, pos)) return pos;
			}
		}
		return null;
	}

	/** 选矿接近代价分（越小越优先）。 */
	static double approachScore(BlockPos feet, BlockPos ore) {
		return BorerOrePolicy.approachScore(
			ore.getX() - feet.getX(),
			ore.getZ() - feet.getZ(),
			ore.getY() - feet.getY());
	}
}
