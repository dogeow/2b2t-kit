package dev.twob2tkit.planter;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** 收成或种完一圈后，走到田边捡种子和作物。 */
public final class PlanterLoot {
	private static final int SPAWN_WAIT_TICKS = 8;
	private static final int MISSING_TICKS = 6;
	private static final int TIMEOUT_TICKS = 120;
	private static final int IGNORE_TICKS = 160;
	private static final int STUCK_TICKS = 60;
	private static final double PICKUP_DISTANCE = 0.85;

	private final Map<Integer, Long> ignored = new HashMap<>();
	private BlockPos origin;
	private Item cropItem;
	private Block plantBlock;
	private int ticks;
	private int targetTicks;
	private int missingTicks;
	private int stuckTicks;
	private double bestDist = Double.MAX_VALUE;
	private int entityId = -1;
	private int entityCount;
	private int picked;
	private String status = "";

	/** 是否正在捡掉落物。 */
	public boolean active() {
		return origin != null;
	}

	/** 本局已捡次数估计。 */
	public int picked() {
		return picked;
	}

	/** 最近状态文案。 */
	public String status() {
		return status;
	}

	/** 清忽略表与计数，结束本局捡取。 */
	public void resetSession() {
		ignored.clear();
		picked = 0;
		clear();
	}

	/** 清当前目标与计时。 */
	public void clear() {
		origin = null;
		cropItem = null;
		plantBlock = null;
		ticks = 0;
		targetTicks = 0;
		missingTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
		entityId = -1;
		entityCount = 0;
		status = "";
	}

	/** 从起点开始捡指定作物掉落。 */
	public void begin(BlockPos start, Item crop, Block plant) {
		origin = start.immutable();
		cropItem = crop;
		plantBlock = plant;
		ticks = 0;
		targetTicks = 0;
		missingTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
		entityId = -1;
		entityCount = 0;
		status = "";
	}

	/** 附近已有可捡掉落则开始；否则 false。 */
	public boolean beginNear(Minecraft client, LocalPlayer player, Item crop, Block plant, double range) {
		if (origin != null || client.level == null || crop == null) return false;
		pruneIgnored(client);
		double radius = Math.max(3.0, range);
		AABB search = player.getBoundingBox().inflate(radius, 4.0, radius);
		ItemEntity nearest = null;
		double best = Double.MAX_VALUE;
		for (ItemEntity entity : client.level.getEntitiesOfClass(ItemEntity.class, search)) {
			if (!entity.isAlive() || ignored.containsKey(entity.getId())) continue;
			if (!PlanterPolicy.isFarmLoot(entity.getItem(), crop, plant)) continue;
			if (inLava(client, entity)) continue;
			double dist = player.distanceTo(entity);
			if (dist < best) {
				best = dist;
				nearest = entity;
			}
		}
		if (nearest == null) return false;
		begin(player.blockPosition(), crop, plant);
		return true;
	}

	/** true：本拍还在捡；false：捡完或没有可捡的。 */
	public boolean tick(Minecraft client, LocalPlayer player, boolean canWalk) {
		if (origin == null || cropItem == null) return false;
		pruneIgnored(client);
		ticks++;
		if (notePicked(client)) {
			stuckTicks = 0;
			bestDist = Double.MAX_VALUE;
		}
		ItemEntity loot = findOrLock(client, player);
		if (loot == null) {
			if (ticks < SPAWN_WAIT_TICKS) {
				holdStill(client);
				status = "等掉落物出现";
				return true;
			}
			missingTicks++;
			if (missingTicks >= MISSING_TICKS) {
				clear();
				return false;
			}
			holdStill(client);
			status = "确认掉落物是否已进背包";
			return true;
		}
		missingTicks = 0;
		if (inLava(client, loot)) {
			ignored.put(loot.getId(), client.level.getGameTime() + IGNORE_TICKS);
			resetLockedTarget();
			status = "掉落物在岩浆里，跳过";
			return true;
		}
		double distance = player.distanceTo(loot);
		if (distance + 0.35 < bestDist) {
			bestDist = distance;
			stuckTicks = 0;
		} else {
			stuckTicks++;
		}
		targetTicks++;
		if (!inventoryCanTake(player, loot.getItem())) {
			holdStill(client);
			status = "背包满了，清出空位再捡";
			return true;
		}
		if (targetTicks >= TIMEOUT_TICKS || stuckTicks >= STUCK_TICKS) {
			ignored.put(loot.getId(), client.level.getGameTime() + IGNORE_TICKS);
			resetLockedTarget();
			status = "这组捡不到，换下一组";
			return true;
		}
		if (distance <= PICKUP_DISTANCE) {
			holdStill(client);
			status = "捡 " + loot.getItem().getHoverName().getString() + " ×" + loot.getItem().getCount();
			return true;
		}
		if (!canWalk) {
			holdStill(client);
			status = "太远，打开「走近再种」才能去捡";
			return true;
		}
		Vec3 dest = loot.position();
		lookAt(player, dest);
		double horiz = Math.hypot(dest.x - player.getX(), dest.z - player.getZ());
		client.options.keyUp.setDown(horiz > 0.2);
		client.options.keyDown.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		double dy = dest.y - player.getY();
		boolean stepUp = dy > 0.45 && dy <= 1.25;
		boolean jumpStuck = stuckTicks > 8 && horiz > 0.5 && player.onGround();
		client.options.keyJump.setDown((stepUp && player.onGround()) || jumpStuck);
		status = String.format(Locale.ROOT, "去捡 %s  距离 %.1f",
			loot.getItem().getHoverName().getString(), distance);
		return true;
	}

	/** 锁定实体消失则记一次捡到。 */
	private boolean notePicked(Minecraft client) {
		if (entityId < 0 || client.level == null) return false;
		if (client.level.getEntity(entityId) != null) return false;
		picked += Math.max(1, entityCount);
		resetLockedTarget();
		return true;
	}

	/** 沿用锁定实体或重找最近。 */
	private ItemEntity findOrLock(Minecraft client, LocalPlayer player) {
		if (entityId >= 0) {
			Entity existing = client.level.getEntity(entityId);
			boolean alive = existing instanceof ItemEntity item
				&& item.isAlive()
				&& PlanterPolicy.isFarmLoot(item.getItem(), cropItem, plantBlock);
			if (alive && !ignored.containsKey(entityId)) return (ItemEntity) existing;
			if (existing == null) return null;
			resetLockedTarget();
		}
		ItemEntity best = findNearest(client, player);
		if (best != null) lockTarget(best);
		return best;
	}

	/** 原点与玩家附近找最近田产物。 */
	private ItemEntity findNearest(Minecraft client, LocalPlayer player) {
		AABB aroundOrigin = new AABB(origin).inflate(12.0, 4.0, 12.0);
		AABB aroundPlayer = player.getBoundingBox().inflate(12.0, 4.0, 12.0);
		AABB search = aroundOrigin.minmax(aroundPlayer);
		ItemEntity best = null;
		double bestFound = Double.MAX_VALUE;
		for (ItemEntity entity : client.level.getEntitiesOfClass(ItemEntity.class, search)) {
			if (!entity.isAlive() || ignored.containsKey(entity.getId())) continue;
			if (!PlanterPolicy.isFarmLoot(entity.getItem(), cropItem, plantBlock)) continue;
			double dist = player.distanceTo(entity);
			if (dist < bestFound) {
				bestFound = dist;
				best = entity;
			}
		}
		return best;
	}

	/** 锁定掉落物实体与数量。 */
	private void lockTarget(ItemEntity loot) {
		entityId = loot.getId();
		entityCount = loot.getItem().getCount();
		targetTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
	}

	/** 清锁定目标计时。 */
	private void resetLockedTarget() {
		entityId = -1;
		entityCount = 0;
		targetTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
	}

	/** 有空位或可堆叠同物。 */
	private static boolean inventoryCanTake(LocalPlayer player, ItemStack stack) {
		Inventory inventory = player.getInventory();
		if (inventory.getFreeSlot() >= 0) return true;
		return inventory.getSlotWithRemainingSpace(stack) >= 0;
	}

	/** 掉落物是否在岩浆里。 */
	private static boolean inLava(Minecraft client, ItemEntity loot) {
		BlockPos pos = loot.blockPosition();
		return client.level.getFluidState(pos).is(FluidTags.LAVA)
			|| client.level.getFluidState(pos.below()).is(FluidTags.LAVA);
	}

	/** 清掉过期忽略 id。 */
	private void pruneIgnored(Minecraft client) {
		if (client.level == null || ignored.isEmpty()) return;
		long now = client.level.getGameTime();
		ignored.entrySet().removeIf(entry -> entry.getValue() <= now);
	}

	/** 松开移动与跳跃。 */
	private static void holdStill(Minecraft client) {
		client.options.keyUp.setDown(false);
		client.options.keyDown.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		client.options.keyJump.setDown(false);
	}

	/** 瞬间对准目标点。 */
	private static void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}
}
