package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.phys.AABB;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Comparator;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** 找矿挖掉后走近并拾取对应掉落物。状态从盾构引擎拆出，避免主循环文件继续膨胀。 */
final class BorerLoot {
	private static final Logger LOGGER = LoggerFactory.getLogger("twob2tkit/Borer");
	private static final int SEARCH_RADIUS = 7;
	private static final int STUCK_TICKS = 80;
	private static final int TIMEOUT_TICKS = 200;
	private static final int IGNORE_TICKS = 400;
	private static final int MAX_HEADROOM_PROBE = 5;

	private final DefaultTunnelBorerEngine engine;
	private final Map<Integer, Long> ignored = new HashMap<>();
	private BlockPos origin;
	private OreTarget wanted;
	private int startCount;
	private int lastCount;
	private int ticks;
	private int missingTicks;
	private int stuckTicks;
	private int targetTicks;
	private int entityId = -1;
	private double bestDistance = Double.MAX_VALUE;
	private boolean seen;
	private int sidestepSign = 1;
	private int lastPickupTick;

	BorerLoot(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 想想试验是否进行中。 */
	boolean active() {
		return origin != null;
	}

	/** 拾取起点坐标。 */
	BlockPos origin() {
		return origin;
	}

	/** 本轮要捡的矿种。 */
	OreTarget wanted() {
		return wanted;
	}

	/** 本轮已进行拍数。 */
	int ticks() {
		return ticks;
	}

	/** 是否已看到过目标掉落物。 */
	boolean seen() {
		return seen;
	}

	/** 清空拾取状态。 */
	void clear() {
		origin = null;
		wanted = null;
		startCount = 0;
		lastCount = 0;
		ticks = 0;
		missingTicks = 0;
		stuckTicks = 0;
		targetTicks = 0;
		entityId = -1;
		bestDistance = Double.MAX_VALUE;
		seen = false;
		sidestepSign = 1;
		lastPickupTick = 0;
	}

	/** 清空已忽略掉落记录。 */
	void clearIgnored() {
		ignored.clear();
		clear();
	}

	/** 开始一轮针对该矿种的拾取。 */
	void begin(LocalPlayer player, BlockPos start, OreTarget ore) {
		origin = start.immutable();
		wanted = ore;
		startCount = countMatching(player, wanted);
		lastCount = startCount;
		ticks = 0;
		missingTicks = 0;
		stuckTicks = 0;
		targetTicks = 0;
		entityId = -1;
		bestDistance = Double.MAX_VALUE;
		seen = false;
		sidestepSign = 1;
		lastPickupTick = 0;
		LOGGER.info("[twob2tkit/Borer {}] loot-collection-start ore={} origin={} inventoryCount={} player={}",
			engine.runtimeVersion(), wanted, format(origin), startCount, precise(player));
	}

	/** 地上已经有同类掉落物：先捡，不要立刻改挖旁边的矿。 */
	boolean hasNearby(Minecraft client, LocalPlayer player, BlockPos center, OreTarget ore) {
		return findMatching(client, player, center, ore) != null;
	}

	/** 挖下一块之前，把已经掉在脚边的勾选矿捡起来。 */
	boolean tryBeginFromNearby(Minecraft client, LocalPlayer player, OreTarget ore) {
		if (origin != null || ore == null || client.level == null || player == null) return false;
		ItemEntity found = findMatching(client, player, player.blockPosition(), ore);
		if (found == null) return false;
		begin(player, BlockPos.containing(found.getX(), found.getY(), found.getZ()), ore);
		return true;
	}

	/** true：本拍继续拾取；false：让引擎接着挖遮挡或找下一处矿。 */
	boolean handle(Minecraft client, LocalPlayer player) {
		if (origin == null || wanted == null) return false;
		ticks++;
		pruneIgnored(client);
		int inventoryCount = countMatching(player, wanted);
		ItemEntity loot = findMatching(client, player);
		boolean itemsRemain = loot != null;
		if (inventoryCount > lastCount) {
			lastPickupTick = ticks;
			LOGGER.info("[twob2tkit/Borer {}] loot-collection-progress ore={} origin={} picked={}->{} remaining={} item={} player={}",
				engine.runtimeVersion(), wanted, format(origin), lastCount, inventoryCount, itemsRemain,
				loot == null ? "-" : precise(loot), precise(player));
			if (BorerLootPolicy.inventoryProgressResetsStuck(true, itemsRemain)) {
				stuckTicks = 0;
				targetTicks = 0;
				bestDistance = Double.MAX_VALUE;
			}
			lastCount = inventoryCount;
			if (BorerLootPolicy.finishOnInventoryIncrease(itemsRemain, false)) {
				finish(client, player, "已拾取" + wanted.label + "掉落物", inventoryCount);
				return true;
			}
		}

		if (loot == null) {
			holdStill(client);
			boolean alreadyPicked = inventoryCount > startCount;
			boolean spawnWaitElapsed = BorerLootPolicy.spawnWaitElapsed(alreadyPicked, ticks - lastPickupTick);
			if (seen) missingTicks++;
			if (BorerLootPolicy.finishWhenMissing(seen, missingTicks, spawnWaitElapsed)) {
				String result;
				if (!seen) {
					result = "矿石已挖掉，但附近未生成可追踪的" + wanted.label + "掉落物";
				} else if (alreadyPicked) {
					result = "已拾取" + wanted.label + "掉落物";
				} else {
					result = wanted.label + "掉落物已消失或被拾取";
				}
				finish(client, player, result, inventoryCount);
				return true;
			}
			if (BorerLootPolicy.overlayWaitForMore(seen, false, alreadyPicked)) {
				engine.overlay(client, "等待更多" + wanted.label + "掉落物 " + format(origin), 0xFFFF55);
			} else if (!seen) {
				engine.overlay(client, "等待" + wanted.label + "掉落物出现 " + format(origin), 0xFFFF55);
			}
			return true;
		}

		if (loot.getId() != entityId) {
			entityId = loot.getId();
			targetTicks = 0;
			stuckTicks = 0;
			bestDistance = Double.MAX_VALUE;
		}
		targetTicks++;
		seen = true;
		missingTicks = 0;
		BlockPos lootBlock = BlockPos.containing(loot.getX(), loot.getY(), loot.getZ());
		if (inLava(client, lootBlock)) {
			return abandon(client, player, loot, "掉落物在岩浆里");
		}
		if (!canStore(player, wanted)) {
			if (engine.coalXpMode() && wanted == OreTarget.COAL
				|| engine.quartzXpMode() && wanted == OreTarget.QUARTZ) {
				return abandon(client, player, loot, "经验模式不捡" + wanted.label);
			}
			String label = wanted.label;
			LOGGER.warn("[twob2tkit/Borer {}] loot-collection-home reason=inventory-full ore={} item={} itemPos={} origin={} player={}",
				engine.runtimeVersion(), wanted, loot.getItem().getHoverName().getString(), precise(loot), format(origin), precise(player));
			clear();
			return engine.finishSession(client, player, "背包已满，无法再装" + label, false);
		}

		double dx = loot.getX() - player.getX();
		double dy = loot.getY() - player.getY();
		double dz = loot.getZ() - player.getZ();
		double distance = player.distanceTo(loot);
		double horiz = Math.hypot(dx, dz);
		boolean inPickup = BorerLootPolicy.inVanillaPickupRange(dx, dy, dz);
		if (distance + 0.2 < bestDistance) {
			bestDistance = distance;
			stuckTicks = 0;
		} else if (!inPickup) {
			stuckTicks++;
		} else {
			stuckTicks = 0;
		}
		if (stuckTicks >= STUCK_TICKS || targetTicks >= TIMEOUT_TICKS) {
			return abandon(client, player, loot, stuckTicks >= STUCK_TICKS ? "靠近后仍无法拾取" : "拾取超时");
		}

		BlockPos lootPos = lootBlock.immutable();
		engine.lockHeadingToward(player.blockPosition(), lootPos);
		boolean embedded = embeddedInBlock(client, loot);
		boolean ceilingBlocked = dy > 0.75 && jumpBlocked(client, player, dy);
		BlockPos dropCol = BlockPos.containing(loot.getX(), player.getY(), loot.getZ());
		boolean feetPassable = !hasCollision(client, dropCol);
		BlockPos dropHead = dropCol.above();
		boolean headMineable = engine.canPlanMine(client, dropHead) && BorerAim.inReach(player, dropHead)
			&& engine.canSeeBlock(client, player, dropHead);
		boolean dropSafe = !inLava(client, dropCol) && feetPassable && !hasCollision(client, dropHead)
			&& BorerHazards.canWalkOrFallInto(client, dropCol);
		boolean preferDrop = BorerLootPolicy.preferDropOverMining(dropSafe, inPickup, dy);

		if (BorerLootPolicy.shouldMineHeadToEnterLootDrop(dy, feetPassable, headMineable)) {
			stuckTicks = 0;
			engine.setMiningTarget(client, player, dropHead, "loot-drop-head");
			engine.status = "挖头开 1×2 下去捡 " + format(dropHead);
			return false;
		}

		if (!preferDrop && (!inPickup || embedded || ceilingBlocked)) {
			if (engine.currentTarget != null && engine.shouldMine(client, engine.currentTarget)) {
				stuckTicks = 0;
				engine.status = "清理掉落物前的遮挡 " + format(engine.currentTarget);
				return false;
			}
			if (engine.currentTarget != null) engine.clearMiningTarget();
			BlockPos obstruction = engine.visibleObstructionToward(client, player, lootPos);
			if (obstruction == null && embedded && engine.canPlanMine(client, lootPos)
				&& BorerAim.inReach(player, lootPos) && engine.canSeeBlock(client, player, lootPos)) {
				obstruction = lootPos.immutable();
			}
			if (obstruction == null && ceilingBlocked) {
				BlockPos overhead = firstBlockAbove(client, player);
				if (engine.canPlanMine(client, overhead) && BorerAim.inReach(player, overhead)
					&& engine.canSeeBlock(client, player, overhead)) {
					obstruction = overhead.immutable();
				}
			}
			if (obstruction != null && (!inPickup || embedded || ceilingBlocked)) {
				stuckTicks = 0;
				engine.setMiningTarget(client, player, obstruction, "loot-obstruction");
				engine.status = "清理掉落物前的遮挡 " + format(obstruction);
				return false;
			}
		} else if (engine.currentTarget != null) {
			engine.clearMiningTarget();
		}

		if (inPickup && !embedded && !ceilingBlocked) {
			holdStill(client);
			engine.overlay(client, String.format(Locale.ROOT, "等待拾取%s掉落物 %s",
				wanted.label, precise(loot)), 0x55FF55);
			return true;
		}

		engine.releaseMine(client);
		walkToward(client, player, loot, dropSafe, inPickup, horiz);
		engine.overlay(client, String.format(Locale.ROOT, "正在拾取%s掉落物（距离 %.1f） %s",
			wanted.label, distance, precise(loot)), 0xFFFF55);
		return true;
	}

	/** 拾取 HUD 详情行。 */
	String hudDetail() {
		if (origin == null) return null;
		return "拾取 " + (wanted == null ? "掉落物" : wanted.label) + " " + format(origin);
	}

	/** 当前拾取目标标签。 */
	String goalLabel() {
		return origin == null ? "-" : "loot@" + format(origin);
	}

	/** 放弃当前目标并记日志。 */
	private boolean abandon(Minecraft client, LocalPlayer player, ItemEntity loot, String reason) {
		ignored.put(loot.getId(), client.level.getGameTime() + IGNORE_TICKS);
		LOGGER.warn("[twob2tkit/Borer {}] loot-collection-abandon reason={} ore={} item={} itemPos={} origin={} player={}",
			engine.runtimeVersion(), reason, wanted, loot.getItem().getHoverName().getString(),
			precise(loot), format(origin), precise(player));
		entityId = -1;
		targetTicks = 0;
		stuckTicks = 0;
		bestDistance = Double.MAX_VALUE;
		holdStill(client);
		engine.overlay(client, reason + "：" + wanted.label + "掉落物 " + precise(loot) + "，改捡其他", 0xFFFF55);
		return true;
	}

	/** 停挖并松开全部移动键，原地待命。 */
	private void holdStill(Minecraft client) {
		engine.releaseMine(client);
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		client.options.keyDown.setDown(false);
	}

	/** 转向掉落物并按走/飞策略靠近。 */
	private void walkToward(Minecraft client, LocalPlayer player, ItemEntity loot, boolean dropSafe, boolean inPickup, double horiz) {
		double dx = loot.getX() - player.getX();
		double dz = loot.getZ() - player.getZ();
		double dy = loot.getY() - player.getY();
		float yaw = chooseYaw(client, player, dx, dz, dy, horiz);
		float pitch = dy < -0.7 ? 28.0F : dy > 0.5 ? -18.0F : 6.0F;
		player.setYRot(yaw);
		player.setXRot(pitch);
		player.setYHeadRot(yaw);
		engine.lockHeadingToward(player.blockPosition(), BlockPos.containing(loot.getX(), loot.getY(), loot.getZ()));

		boolean blocked = collisionInYaw(client, player, yaw);
		boolean lavaAhead = lavaInYaw(client, player, yaw);
		boolean yawDrop = !lavaAhead && safeDropInYaw(client, player, yaw);
		boolean canDrop = !lavaAhead && BorerLootPolicy.shouldWalkIntoLootDrop(dy, dropSafe || yawDrop);
		boolean moving = horiz > 0.12 || Math.abs(dy) > 0.35;
		if (moving && (lavaAhead || blocked && !canDrop) && !BorerFlight.isFlying(player)) {
			if (!lavaAhead && dy >= -0.25 && engine.place.shouldBridgeDrops(player)) {
				engine.place.placeWalkingSupport(client, player);
			}
			moving = false;
		}

		if (BorerFlight.isFlying(player)) {
			client.options.keyJump.setDown(dy > 0.2);
			client.options.keyShift.setDown(dy < -0.2);
		} else {
			boolean ceilingAbove = jumpBlocked(client, player, dy);
			boolean hopRim = BorerLootPolicy.shouldHopOffRim(player.onGround(), canDrop, horiz, inPickup);
			client.options.keyShift.setDown(false);
			client.options.keyJump.setDown(hopRim || player.onGround() && !ceilingAbove && (
				dy > 0.45 || stuckTicks > 10 && stuckTicks % 16 < 3
			));
		}
		client.options.keyUp.setDown(moving || canDrop);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		client.options.keyDown.setDown(false);
	}

	/** 选靠近掉落物且尽量安全的偏航。 */
	private float chooseYaw(Minecraft client, LocalPlayer player, double dx, double dz, double dy, double horiz) {
		float toward = (float)Math.toDegrees(Math.atan2(dz, dx)) - 90.0F;
		if (horiz < 0.45 && dy < -0.35) {
			float off = firstSafeExitYaw(client, player, toward);
			if (!Float.isNaN(off)) return off;
		}
		if (!collisionInYaw(client, player, toward) || dy < -0.25 && safeDropInYaw(client, player, toward)) {
			return toward;
		}
		float left = toward - 80.0F;
		float right = toward + 80.0F;
		boolean leftOk = !collisionInYaw(client, player, left) || dy < -0.25 && safeDropInYaw(client, player, left);
		boolean rightOk = !collisionInYaw(client, player, right) || dy < -0.25 && safeDropInYaw(client, player, right);
		if (leftOk && !rightOk) {
			sidestepSign = -1;
			return left;
		}
		if (rightOk && !leftOk) {
			sidestepSign = 1;
			return right;
		}
		if (leftOk || rightOk) {
			if (stuckTicks > 0 && stuckTicks % 16 == 0) sidestepSign = -sidestepSign;
			return sidestepSign < 0 ? left : right;
		}
		return toward;
	}

	/** 在候选偏航里找第一条无碰撞且落差安全的。 */
	private float firstSafeExitYaw(Minecraft client, LocalPlayer player, float fallback) {
		float[] candidates = {fallback, fallback + 90.0F, fallback - 90.0F, fallback + 180.0F};
		for (float yaw : candidates) {
			if (safeDropInYaw(client, player, yaw) || !collisionInYaw(client, player, yaw)) return yaw;
		}
		return Float.NaN;
	}

	/** 该偏航方向是否撞墙。 */
	private boolean collisionInYaw(Minecraft client, LocalPlayer player, float yaw) {
		double rad = Math.toRadians(yaw);
		AABB moved = player.getBoundingBox().move(-Math.sin(rad) * 0.38, 0.0, Math.cos(rad) * 0.38);
		return !client.level.noCollision(player, moved);
	}

	/** 该偏航方向是否有岩浆。 */
	private boolean lavaInYaw(Minecraft client, LocalPlayer player, float yaw) {
		BlockPos dest = ahead(player, yaw);
		return BorerHazards.isLavaFluid(client, dest) || BorerHazards.isLavaFluid(client, dest.above())
			|| BorerHazards.isLavaFluid(client, dest.below()) || BorerHazards.isLavaFluid(client, dest.below(2));
	}

	/** 该偏航方向落差是否安全。 */
	private boolean safeDropInYaw(Minecraft client, LocalPlayer player, float yaw) {
		BlockPos dest = ahead(player, yaw);
		if (BorerHazards.isLavaFluid(client, dest) || BorerHazards.isLavaFluid(client, dest.above())) return false;
		if (hasCollision(client, dest) || hasCollision(client, dest.above())) return false;
		return BorerHazards.canWalkOrFallInto(client, dest);
	}

	/** 该偏航前方一格。 */
	private static BlockPos ahead(LocalPlayer player, float yaw) {
		double rad = Math.toRadians(yaw);
		return BlockPos.containing(
			player.getX() - Math.sin(rad) * 0.85,
			player.getY(),
			player.getZ() + Math.cos(rad) * 0.85
		);
	}

	/** 掉落物是否卡在方块里。 */
	private boolean embeddedInBlock(Minecraft client, ItemEntity loot) {
		return hasCollision(client, BlockPos.containing(loot.getX(), loot.getY() + 0.05, loot.getZ()));
	}

	/** 格是否有碰撞。 */
	private static boolean hasCollision(Minecraft client, BlockPos pos) {
		return !client.level.getBlockState(pos).getCollisionShape(client.level, pos).isEmpty();
	}

	/**
	 * 跳起来够不够得着高 dy 的落点。默认 2 格隧道净空恒为 1，永远返回 true（跳了也白跳）；
	 * 挖 3 格以上的隧道时才会真的允许起跳，所以不能把层数写死。
	 */
	private static boolean jumpBlocked(Minecraft client, LocalPlayer player, double dy) {
		int need = requiredHeadroom(dy);
		return BorerHazards.openHeadroom(client, player.blockPosition(), need) < need;
	}

	/** 净空不够时挡在头顶的第一格，也就是要清掉的那块。 */
	private static BlockPos firstBlockAbove(Minecraft client, LocalPlayer player) {
		int free = BorerHazards.openHeadroom(client, player.blockPosition(), MAX_HEADROOM_PROBE);
		return player.blockPosition().above(free + 1);
	}

	/** 所需头顶净空格数。 */
	private static int requiredHeadroom(double dy) {
		return Math.min(MAX_HEADROOM_PROBE, Math.max(2, (int)Math.ceil(dy) + 1));
	}

	/** 掉落物是否在岩浆里。 */
	private static boolean inLava(Minecraft client, BlockPos lootBlock) {
		return BorerHazards.isLavaFluid(client, lootBlock)
			|| BorerHazards.isLavaFluid(client, lootBlock.below())
			|| BorerHazards.isLavaFluid(client, lootBlock.above());
	}

	/** 找匹配勾选矿的掉落物。 */
	private ItemEntity findMatching(Minecraft client, LocalPlayer player) {
		return findMatching(client, player, origin, wanted);
	}

	/** 找匹配勾选矿的掉落物。 */
	private ItemEntity findMatching(Minecraft client, LocalPlayer player, BlockPos center, OreTarget ore) {
		if (client.level == null || player == null || center == null || ore == null) return null;
		AABB aroundOrigin = new AABB(center).inflate(SEARCH_RADIUS, 10.0, SEARCH_RADIUS);
		AABB aroundPlayer = player.getBoundingBox().inflate(SEARCH_RADIUS, 10.0, SEARCH_RADIUS);
		AABB search = new AABB(
			Math.min(aroundOrigin.minX, aroundPlayer.minX),
			Math.min(aroundOrigin.minY, aroundPlayer.minY),
			Math.min(aroundOrigin.minZ, aroundPlayer.minZ),
			Math.max(aroundOrigin.maxX, aroundPlayer.maxX),
			Math.max(aroundOrigin.maxY, aroundPlayer.maxY),
			Math.max(aroundOrigin.maxZ, aroundPlayer.maxZ)
		);
		long now = client.level.getGameTime();
		return client.level.getEntitiesOfClass(ItemEntity.class, search, entity ->
			entity.isAlive()
				&& !entity.getItem().isEmpty()
				&& ore.matchesDrop(entity.getItem())
				&& ignored.getOrDefault(entity.getId(), 0L) < now
		).stream().min(Comparator.comparingDouble(player::distanceToSqr)).orElse(null);
	}

	/** 清理已忽略掉落记录。 */
	private void pruneIgnored(Minecraft client) {
		long now = client.level.getGameTime();
		ignored.entrySet().removeIf(entry -> entry.getValue() < now);
	}

	/** 背包匹配矿数量。 */
	private static int countMatching(LocalPlayer player, OreTarget wanted) {
		int count = wanted.matchesDrop(player.getOffhandItem()) ? player.getOffhandItem().getCount() : 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (wanted.matchesDrop(stack)) count += stack.getCount();
		}
		return count;
	}

	/** 背包是否还能收该矿。 */
	private static boolean canStore(LocalPlayer player, OreTarget wanted) {
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (wanted.matchesDrop(stack) && stack.getCount() < stack.getMaxStackSize()) return true;
		}
		return player.getInventory().getFreeSlot() >= 0;
	}

	/** 结束本轮拾取。 */
	private void finish(Minecraft client, LocalPlayer player, String result, int inventoryCount) {
		LOGGER.info("[twob2tkit/Borer {}] loot-collection-finish result={} ore={} origin={} ticks={} inventoryBefore={} inventoryAfter={} player={}",
			engine.runtimeVersion(), result, wanted, format(origin), ticks, startCount, inventoryCount, precise(player));
		clear();
		engine.releaseMine(client);
		client.options.keyShift.setDown(false);
		if (engine.currentTarget != null && !engine.shouldMine(client, engine.currentTarget)) {
			engine.clearMiningTarget();
		}
		engine.overlay(client, result + "，继续找矿", 0x55FFFF);
	}

	/** 坐标/对象短文本。 */
	private static String format(BlockPos pos) {
		return pos == null ? "-" : pos.getX() + " " + pos.getY() + " " + pos.getZ();
	}

	/** 精确坐标短文本。 */
	private static String precise(Entity entity) {
		return String.format(Locale.ROOT, "%.3f,%.3f,%.3f", entity.getX(), entity.getY(), entity.getZ());
	}
}
