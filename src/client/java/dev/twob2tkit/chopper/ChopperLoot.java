package dev.twob2tkit.chopper;

import dev.twob2tkit.runtime.engine.BorerAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.BlockTags;
import net.minecraft.tags.FluidTags;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** 砍完一棵树后走到树下捡原木、树苗、苹果、木棍。 */
public final class ChopperLoot {
	private static final int SPAWN_WAIT_TICKS = 12;
	private static final int MISSING_TICKS = 8;
	private static final int TIMEOUT_TICKS = 160;
	private static final int IGNORE_TICKS = 200;
	private static final int STUCK_TICKS = 100;
	private static final double SEARCH_RADIUS = 16.0;
	private static final int LEAF_RETRY_TICKS = 40;

	private final Map<Integer, Long> ignored = new HashMap<>();
	/** 整轮里彻底放弃过的掉落物，不设过期。只用来挡住兜底拾取，避免和「附近没有树」来回横跳。 */
	private final Set<Integer> givenUp = new HashSet<>();
	private BlockPos origin;
	private Item saplingItem;
	private int ticks;
	private int targetTicks;
	private int missingTicks;
	private int stuckTicks;
	private double bestDist = Double.MAX_VALUE;
	private int entityId = -1;
	private int entityCount;
	private int picked;
	private Vec3 look;
	private boolean canopyFlight;
	private BlockPos leafObstacle;
	private int leafObstacleTicks;
	private int leafDestroyStage = -1;
	private boolean collectLeaves;

	/** 是否正在捡物流程。 */
	public boolean active() {
		return origin != null;
	}

	/** 本轮拾取原点（树根附近）。 */
	public BlockPos origin() {
		return origin;
	}

	/** 当前瞄准点（掉落物或挡路叶）。 */
	public Vec3 look() {
		return look;
	}

	/** 本局累计捡到的件数。 */
	public int picked() {
		return picked;
	}

	/** 是否连树叶掉落物也捡。 */
	public void setCollectLeaves(boolean collectLeaves) {
		this.collectLeaves = collectLeaves;
	}

	/** 是否正在清挡路树叶（挖树主循环勿松左键）。 */
	public boolean miningObstacle() {
		return leafObstacle != null;
	}

	/** 新开一局：清忽略表与计数。 */
	public void resetSession() {
		ignored.clear();
		givenUp.clear();
		picked = 0;
		clear();
	}

	/** 结束本轮拾取状态（保留会话计数与忽略表）。 */
	public void clear() {
		origin = null;
		saplingItem = null;
		ticks = 0;
		targetTicks = 0;
		missingTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
		entityId = -1;
		entityCount = 0;
		look = null;
		canopyFlight = false;
		leafObstacle = null;
		leafObstacleTicks = 0;
		leafDestroyStage = -1;
	}

	/** 以树根为原点开一轮拾取。 */
	public void begin(BlockPos start, Item sapling) {
		origin = start.immutable();
		saplingItem = sapling;
		ticks = 0;
		targetTicks = 0;
		missingTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
		entityId = -1;
		entityCount = 0;
		look = null;
		canopyFlight = false;
		leafObstacle = null;
		leafObstacleTicks = 0;
		leafDestroyStage = -1;
	}

	/** 附近地上还有没捡的砍树掉落物就重开一轮拾取。找不到新树时兜底用。 */
	public boolean beginNear(Minecraft client, LocalPlayer player) {
		if (origin != null || client.level == null) return false;
		pruneIgnored(client);
		AABB search = player.getBoundingBox().inflate(SEARCH_RADIUS, 8.0, SEARCH_RADIUS);
		for (ItemEntity entity : client.level.getEntitiesOfClass(ItemEntity.class, search)) {
			if (!entity.isAlive() || ignored.containsKey(entity.getId())) continue;
			if (givenUp.contains(entity.getId())) continue;
			if (!isChopLoot(entity.getItem())) continue;
			if (inLava(client, entity)) continue;
			begin(player.blockPosition(), null);
			return true;
		}
		return false;
	}

	/** true：本拍还在捡；false：捡完或没有可捡的，交给补种/下一棵。 */
	public boolean tick(Minecraft client, LocalPlayer player) {
		if (origin == null) return false;
		pruneIgnored(client);
		ticks++;
		if (notePicked(client)) {
			stuckTicks = 0;
			bestDist = Double.MAX_VALUE;
		}
		noteLeafObstacleCleared(client);
		ItemEntity loot = findOrLock(client, player);
		if (loot == null) {
			if (ticks < SPAWN_WAIT_TICKS) {
				ChopperKeys.holdStill(client);
				ChopperKeys.overlay(client, "等木头掉下来", 0xA0A0A0);
				return true;
			}
			missingTicks++;
			if (missingTicks >= MISSING_TICKS) {
				clear();
				return false;
			}
			ChopperKeys.holdStill(client);
			ChopperKeys.overlay(client, "确认掉落物是否已进背包", 0xA0A0A0);
			return true;
		}
		missingTicks = 0;
		// 超时按锁定的单个掉落物算，不因旁边出现更近物品而重置。
		if (inLava(client, loot)) {
			abandon(client, loot, true);
			ChopperKeys.overlay(client, "掉落物在岩浆里，跳过", 0xFF5555);
			return true;
		}
		double distance = player.distanceTo(loot);
		double horiz = Math.hypot(loot.getX() - player.getX(), loot.getZ() - player.getZ());
		double dy = loot.getY() - player.getY();
		if (ChopperLootPolicy.progressResetsStuck(distance, bestDist)) {
			bestDist = distance;
			stuckTicks = 0;
		} else {
			stuckTicks++;
		}
		targetTicks++;
		if (!inventoryCanTake(player, loot.getItem())) {
			ChopperKeys.holdStill(client);
			ChopperKeys.overlay(client, "背包满了，清出空位再捡木头", 0xFF5555);
			return true;
		}
		if (targetTicks >= TIMEOUT_TICKS || stuckTicks >= STUCK_TICKS) {
			abandon(client, loot, bestDist > 3.0);
			ChopperKeys.overlay(client, "这组捡不到，换下一组", 0xFFFF55);
			return true;
		}
		BlockHitResult leafHit = blockingLeafHit(client, player, loot);
		boolean hitLeaves = leafHit != null
			&& client.level.getBlockState(leafHit.getBlockPos()).is(BlockTags.LEAVES)
			&& ChopperTrees.canBreak(client, leafHit.getBlockPos());
		boolean hitInReach = leafHit != null && BorerAim.hitInReach(player, leafHit);
		if (ChopperLootPolicy.shouldClearLeafObstacle(stuckTicks, hitLeaves, hitInReach)) {
			return clearLeafObstacle(client, player, loot, leafHit);
		}
		if (leafObstacle != null && (leafHit == null || !leafObstacle.equals(leafHit.getBlockPos()))) {
			resetLeafObstacle();
		}
		ChopperKeys.releaseMine(client);
		if (ChopperLootPolicy.closeEnoughForPickup(horiz, dy, distance)) {
			ChopperKeys.holdStill(client);
			ChopperKeys.overlay(client, "捡 " + loot.getItem().getHoverName().getString() + " ×" + loot.getItem().getCount(), 0x55FF55);
			return true;
		}
		look = loot.position();
		ChopperKeys.walkToward(client, player, look, horiz, dy, distance);
		ChopperKeys.overlay(client, String.format("去捡 %s  距离 %.1f", loot.getItem().getHoverName().getString(), distance), 0x55FFFF);
		return true;
	}

	/** 当前锁定掉落物是否需要飞行接近。 */
	public boolean wantsFlight(Minecraft client, LocalPlayer player) {
		if (origin == null || client.level == null) return false;
		ItemEntity loot = findOrLock(client, player);
		if (loot == null) return canopyFlight;
		canopyFlight = ChopperLootPolicy.keepFlightForLockedTarget(
			canopyFlight, loot.getY() - player.getY(), true);
		return canopyFlight;
	}

	/** ignored 会过期，好让同一轮里换个角度再试；太远才进 givenUp，避免脚边的木头被永久放弃。 */
	private void abandon(Minecraft client, ItemEntity loot, boolean unreachable) {
		ignored.put(loot.getId(), client.level.getGameTime() + IGNORE_TICKS);
		if (unreachable) givenUp.add(loot.getId());
		log(client, "loot-abandon id=" + loot.getId()
			+ " item=" + loot.getItem().getHoverName().getString()
			+ " pos=" + precise(loot.position())
			+ " targetTicks=" + targetTicks + " stuckTicks=" + stuckTicks
			+ " best=" + String.format(java.util.Locale.ROOT, "%.2f", bestDist));
		ChopperKeys.releaseMine(client);
		resetLockedTarget();
	}

	/** 锁定实体消失则计入 picked。 */
	private boolean notePicked(Minecraft client) {
		if (entityId < 0 || client.level == null) return false;
		if (client.level.getEntity(entityId) != null) return false;
		picked += Math.max(1, entityCount);
		log(client, "loot-picked id=" + entityId + " count=" + Math.max(1, entityCount));
		resetLockedTarget();
		return true;
	}

	/** 保持锁定目标，失效则换最近可捡物。 */
	private ItemEntity findOrLock(Minecraft client, LocalPlayer player) {
		if (entityId >= 0) {
			Entity existing = client.level.getEntity(entityId);
			boolean alive = existing instanceof ItemEntity item && item.isAlive() && isChopLoot(item.getItem());
			if (ChopperLootPolicy.keepLockedTarget(alive, ignored.containsKey(entityId))) {
				return (ItemEntity) existing;
			}
			// 消失的实体由 tick 开头 notePicked 结算；wantsFlight 不抢先换目标。
			if (existing == null) return null;
			resetLockedTarget();
		}
		ItemEntity best = findNearest(client, player);
		if (best != null) lockTarget(client, player, best);
		return best;
	}

	/** 原点与玩家附近最近的砍树掉落物。 */
	private ItemEntity findNearest(Minecraft client, LocalPlayer player) {
		AABB aroundOrigin = new AABB(origin).inflate(SEARCH_RADIUS, 16.0, SEARCH_RADIUS);
		AABB aroundPlayer = player.getBoundingBox().inflate(SEARCH_RADIUS, 8.0, SEARCH_RADIUS);
		AABB search = aroundOrigin.minmax(aroundPlayer);
		ItemEntity best = null;
		double bestFound = Double.MAX_VALUE;
		for (ItemEntity entity : client.level.getEntitiesOfClass(ItemEntity.class, search)) {
			if (!entity.isAlive() || ignored.containsKey(entity.getId())) continue;
			if (!isChopLoot(entity.getItem())) continue;
			double dist = player.distanceTo(entity);
			if (dist < bestFound) {
				bestFound = dist;
				best = entity;
			}
		}
		return best;
	}

	/** 锁定一个掉落物并写诊断。 */
	private void lockTarget(Minecraft client, LocalPlayer player, ItemEntity loot) {
		entityId = loot.getId();
		entityCount = loot.getItem().getCount();
		targetTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
		canopyFlight = false;
		resetLeafObstacle();
		log(client, "loot-lock id=" + entityId
			+ " item=" + loot.getItem().getHoverName().getString()
			+ " pos=" + precise(loot.position())
			+ " player=" + precise(player.position()));
	}

	/** 清当前锁定与叶障状态。 */
	private void resetLockedTarget() {
		entityId = -1;
		entityCount = 0;
		targetTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
		canopyFlight = false;
		look = null;
		resetLeafObstacle();
	}

	/** 挡路叶已消失则重置卡住计时。 */
	private void noteLeafObstacleCleared(Minecraft client) {
		if (leafObstacle == null || client.level == null) return;
		if (client.level.getBlockState(leafObstacle).is(BlockTags.LEAVES)) return;
		log(client, "loot-obstacle-cleared leaf=" + format(leafObstacle)
			+ " targetId=" + entityId);
		resetLeafObstacle();
		targetTicks = 0;
		stuckTicks = 0;
		bestDist = Double.MAX_VALUE;
	}

	/** 眼睛到掉落物视线碰到的树叶命中；没有则 null。 */
	private BlockHitResult blockingLeafHit(Minecraft client, LocalPlayer player, ItemEntity loot) {
		BlockHitResult hit = BorerAim.clipOutline(
			client, player, player.getEyePosition(), loot.position());
		if (hit == null) return null;
		BlockPos pos = hit.getBlockPos();
		if (!client.level.getBlockState(pos).is(BlockTags.LEAVES)) return null;
		return hit;
	}

	/** 只清真实挡在锁定掉落物前的树叶，不碰原木、建筑或其它方块。 */
	private boolean clearLeafObstacle(
		Minecraft client,
		LocalPlayer player,
		ItemEntity loot,
		BlockHitResult hit
	) {
		BlockPos pos = hit.getBlockPos().immutable();
		boolean fresh = !pos.equals(leafObstacle);
		if (fresh) {
			leafObstacle = pos;
			leafObstacleTicks = 0;
			leafDestroyStage = -1;
			log(client, "loot-obstacle id=" + loot.getId()
				+ " item=" + loot.getItem().getHoverName().getString()
				+ " itemPos=" + precise(loot.position())
				+ " leaf=" + format(pos)
				+ " player=" + precise(player.position()));
		}
		int stage = client.gameMode.getDestroyStage();
		if (stage > leafDestroyStage) {
			leafDestroyStage = stage;
			leafObstacleTicks = 0;
		} else {
			leafObstacleTicks++;
		}
		look = BorerAim.lookPoint(hit);
		ChopperKeys.releaseWalk(client);
		ChopperKeys.lookAt(player, look);
		BlockHitResult freshHit = BorerAim.clipView(client, player);
		boolean exactLeaf = freshHit != null
			&& freshHit.getBlockPos().equals(pos)
			&& BorerAim.hitInReach(player, freshHit)
			&& client.level.getBlockState(pos).is(BlockTags.LEAVES)
			&& ChopperTrees.canBreak(client, pos);
		if (!exactLeaf) {
			if (fresh || leafObstacleTicks % LEAF_RETRY_TICKS == 0) {
				log(client, "loot-obstacle-aim-miss leaf=" + format(pos)
					+ " actual=" + (freshHit == null ? "-" : format(freshHit.getBlockPos()))
					+ " stage=" + stage + " targetId=" + entityId);
			}
			ChopperKeys.holdStill(client);
			return true;
		}
		client.hitResult = freshHit;
		client.crosshairPickEntity = null;
		if (fresh || leafObstacleTicks > 0 && leafObstacleTicks % LEAF_RETRY_TICKS == 0) {
			ChopperKeys.clickAttack(client);
		}
		client.options.keyAttack.setDown(true);
		ChopperKeys.overlay(client, "树叶挡住 " + loot.getItem().getHoverName().getString()
			+ "，先清叶 " + format(pos), 0xFFFF55);
		return true;
	}

	/** 清叶障挖掘状态。 */
	private void resetLeafObstacle() {
		leafObstacle = null;
		leafObstacleTicks = 0;
		leafDestroyStage = -1;
	}

	/** 周期性诊断字符串（挂到 chopper periodic）。 */
	public String diagnostic(Minecraft client, LocalPlayer player) {
		Entity entity = client.level == null || entityId < 0 ? null : client.level.getEntity(entityId);
		String item = entity instanceof ItemEntity loot ? loot.getItem().getHoverName().getString() : "-";
		String itemPos = entity instanceof ItemEntity loot ? precise(loot.position()) : "-";
		return "lootId=" + entityId + " item=" + item + " itemPos=" + itemPos
			+ " targetTicks=" + targetTicks + " stuckTicks=" + stuckTicks
			+ " best=" + String.format(java.util.Locale.ROOT, "%.2f", bestDist)
			+ " canopyFlight=" + canopyFlight
			+ " leafObstacle=" + (leafObstacle == null ? "-" : format(leafObstacle))
			+ " leafTicks=" + leafObstacleTicks
			+ " player=" + precise(player.position());
	}

	/** 是否算砍树相关掉落（原木/树苗/苹果等）。 */
	private boolean isChopLoot(ItemStack stack) {
		if (stack.isEmpty()) return false;
		Item item = stack.getItem();
		if (stack.is(ItemTags.LOGS) || stack.is(ItemTags.SAPLINGS)) return true;
		if (collectLeaves && stack.is(ItemTags.LEAVES)) return true;
		if (item == Items.APPLE || item == Items.STICK) return true;
		if (item == Items.CRIMSON_FUNGUS || item == Items.WARPED_FUNGUS) return true;
		return saplingItem != null && stack.is(saplingItem);
	}

	/** 背包有空位或可合并该堆。 */
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

	/** 去掉过期的临时忽略。 */
	private void pruneIgnored(Minecraft client) {
		if (client.level == null || ignored.isEmpty()) return;
		long now = client.level.getGameTime();
		ignored.entrySet().removeIf(entry -> entry.getValue() <= now);
	}

	/** 方块坐标短串。 */
	private static String format(BlockPos pos) {
		return pos.getX() + "," + pos.getY() + "," + pos.getZ();
	}

	/** 三维坐标精确串。 */
	private static String precise(Vec3 pos) {
		return String.format(java.util.Locale.ROOT, "%.3f,%.3f,%.3f", pos.x, pos.y, pos.z);
	}

	/** 写入 chopper.log。 */
	private static void log(Minecraft client, String line) {
		ChopperFileLog.append(client, AutoChopper.VERSION, line);
	}
}
