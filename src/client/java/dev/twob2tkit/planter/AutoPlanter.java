package dev.twob2tkit.planter;

import com.mojang.blaze3d.platform.InputConstants;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerAim;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.network.chat.Component;
import net.minecraft.tags.FluidTags;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.HoeItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.BambooSaplingBlock;
import net.minecraft.world.level.block.BambooStalkBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.CactusBlock;
import net.minecraft.world.level.block.CocoaBlock;
import net.minecraft.world.level.block.CropBlock;
import net.minecraft.world.level.block.FarmlandBlock;
import net.minecraft.world.level.block.HorizontalDirectionalBlock;
import net.minecraft.world.level.block.KelpBlock;
import net.minecraft.world.level.block.MangrovePropaguleBlock;
import net.minecraft.world.level.block.NetherWartBlock;
import net.minecraft.world.level.block.PitcherCropBlock;
import net.minecraft.world.level.block.SugarCaneBlock;
import net.minecraft.world.level.block.SweetBerryBushBlock;
import net.minecraft.world.level.block.TorchflowerCropBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.IntegerProperty;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import dev.twob2tkit.ApproachTracker;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitKeys;

/** 自动种田：锄地、收成、播种、捡掉落；准星打到作物才挖。 */
public final class AutoPlanter {
	private static final String VERSION = "1.6.319";
	private static final int ACTION_COOLDOWN = 4;
	private static final int LOG_EVERY_TICKS = 40;
	private static final int SKIP_TICKS = 40;
	private static final int STUCK_TICKS = 40;
	private static final int HARVEST_STALL_TICKS = 40;
	private static final int WATER_CHEBYSHEV = 4;

	private final KitConfig config;
	private final PlanterLoot loot = new PlanterLoot();
	private final Map<BlockPos, Integer> skipUntilTick = new HashMap<>();
	private boolean active;
	private String status = "";
	private Item lockedCrop;
	private Spot target;
	private int cooldown;
	private int plantedCount;
	private int tilledCount;
	private int harvestedCount;
	private BlockPos approachPos;
	private final ApproachTracker approach = new ApproachTracker();
	private BlockPos harvestPos;
	private int harvestTicks;
	private int logTicks;
	private String lastFileLog = "";
	private PlanterPolicy.RowPlan rowPlan;

	/** 按配置构造自动种田。 */
	public AutoPlanter(KitConfig config) {
		this.config = config;
	}

	/** 是否正在种田。 */
	public boolean isActive() {
		return active;
	}

	/** 最近状态文案。 */
	public String status() {
		return status;
	}

	/** 本局已种次数。 */
	public int plantedCount() {
		return plantedCount;
	}

	/** 本局已锄次数。 */
	public int tilledCount() {
		return tilledCount;
	}

	/** 本局已收次数。 */
	public int harvestedCount() {
		return harvestedCount;
	}

	/** 本局已捡次数。 */
	public int pickedLootCount() {
		return loot.picked();
	}

	/** 当前锁定作物名。 */
	public String cropLabel() {
		return lockedCrop == null ? "未选择" : new ItemStack(lockedCrop).getHoverName().getString();
	}

	/** 锁定作物并开始。 */
	public void start(Minecraft client) {
		if (client.player == null || client.level == null) return;
		active = true;
		cooldown = 0;
		plantedCount = 0;
		tilledCount = 0;
		harvestedCount = 0;
		target = null;
		approachPos = null;
		approach.reset();
		harvestPos = null;
		harvestTicks = 0;
		logTicks = 0;
		lastFileLog = "";
		skipUntilTick.clear();
		rowPlan = PlanterPolicy.rowPlanFromYaw(client.player.getYRot());
		loot.resetSession();
		refreshLockedCrop(client, client.player);
		status = lockedCrop == null ? "先拿着农作物，或站在成熟的田里" : "开始种 " + cropLabel();
		fileLog(client, "start player=" + precisePosition(client.player)
			+ " crop=" + cropLabel()
			+ " till=" + config.planterTill
			+ " harvest=" + config.planterHarvest
			+ " pickup=" + config.planterPickup
			+ " walk=" + config.planterWalk
			+ " range=" + config.planterRange);
		message(client, "自动种田已开启。"
			+ (lockedCrop == null
				? "把小麦种子、甘蔗等拿到手上。开了自动收成的话，成熟田也会先收再种。"
				: "当前：" + cropLabel() + "。")
			+ "一片田只种一种，种子用完不会改种别的。"
			+ (config.planterHarvest ? "成熟作物会先收再种。" : "自动收成已关，不抢左键。")
			+ (config.planterPickup ? "地上的种子和作物会顺手捡。" : "")
			+ "再按 "
			+ KitKeys.boundLabel(KitKeys.TOGGLE_PLANTER) + " 或 End 停止");
	}

	/** 停止、松键并说明原因。 */
	public void stop(Minecraft client, String reason) {
		if (!active) return;
		active = false;
		target = null;
		approachPos = null;
		approach.reset();
		harvestPos = null;
		lockedCrop = null;
		rowPlan = null;
		int pickedLoot = loot.picked();
		loot.clear();
		releaseKeys(client);
		status = "已停止：" + reason;
		fileLog(client, "stop reason=" + reason
			+ " planted=" + plantedCount + " tilled=" + tilledCount + " harvested=" + harvestedCount
			+ " loot=" + pickedLoot);
		boolean didWork = plantedCount + tilledCount + harvestedCount + pickedLoot > 0;
		message(client, "自动种田已停止：" + reason
			+ (didWork ? "（种了 " + plantedCount + "，锄了 " + tilledCount + "，收了 " + harvestedCount
				+ (pickedLoot > 0 ? "，捡了 " + pickedLoot : "") + "）" : ""));
	}

	/** 主循环：锄/收/种/捡。 */
	public void tick(Minecraft client) {
		if (!active) return;
		if (client.player == null || client.level == null || client.gameMode == null) {
			stop(client, "离开世界");
			return;
		}
		if (client.screen != null) {
			releaseKeys(client);
			status = "先关掉界面再种";
			return;
		}

		LocalPlayer player = client.player;
		int now = player.tickCount;
		prune(skipUntilTick, now);
		logTicks++;
		if (logTicks % LOG_EVERY_TICKS == 0) logPeriodic(client, player);

		refreshLockedCrop(client, player);
		if (lockedCrop == null) {
			releaseKeys(client);
			stop(client, config.planterHarvest
				? "手里没有农作物，附近也没有成熟的可收"
				: "手里或背包没有可种的农作物");
			return;
		}
		boolean hasSeeds = hasItem(player, lockedCrop);
		if (PlanterPolicy.stopBecauseNoSeeds(config.planterHarvest, hasSeeds)) {
			releaseKeys(client);
			stop(client, cropLabel() + " 用完了，不改种别的。拿着要种的种子再继续");
			return;
		}

		Block plant = plantBlock(lockedCrop);
		if (plant == null) {
			releaseKeys(client);
			status = cropLabel() + " 不能种";
			overlay(client, status, 0xFF5555);
			return;
		}

		boolean needsFarm = needsFarmland(lockedCrop, plant);
		boolean hasHoe = selectHoe(client) != null;
		List<Spot> spots = collect(client, player, plant, needsFarm, hasSeeds, hasHoe, now);
		try {
			emitGizmos(spots);
		} catch (IllegalStateException ignored) {
		}

		if (config.planterPickup) {
			if (loot.active()) {
				releaseAttack(client);
				if (loot.tick(client, player, config.planterWalk)) {
					status = loot.status();
					overlay(client, status, 0x55FFFF);
					return;
				}
			} else if (loot.beginNear(client, player, lockedCrop, plant, config.planterRange)) {
				status = loot.status().isEmpty() ? "去捡掉落物" : loot.status();
				overlay(client, status, 0x55FFFF);
				return;
			}
		}

		if (PlanterPolicy.shouldStopNoHoeNoWork(
			hasSeeds, hasPlantOrHarvest(spots), needsFarm, config.planterTill, hasHoe)) {
			if (config.planterPickup && loot.beginNear(client, player, lockedCrop, plant, config.planterRange)) {
				status = loot.status().isEmpty() ? "去捡掉落物" : loot.status();
				overlay(client, status, 0x55FFFF);
				return;
			}
			releaseKeys(client);
			stop(client, idleReason(player, plant, needsFarm, hasSeeds, hasHoe));
			return;
		}

		if (cooldown > 0) {
			cooldown--;
			holdSneak(client, player, false);
			releaseWalk(client);
			releaseAttack(client);
			return;
		}

		Spot next = pick(player, spots);
		target = next;
		if (next == null) {
			if (config.planterPickup && loot.beginNear(client, player, lockedCrop, plant, config.planterRange)) {
				status = loot.status().isEmpty() ? "去捡掉落物" : loot.status();
				overlay(client, status, 0x55FFFF);
				return;
			}
			releaseWalk(client);
			releaseAttack(client);
			holdSneak(client, player, false);
			stop(client, idleReason(player, plant, needsFarm, hasSeeds, hasHoe));
			return;
		}

		if (!inReach(player, next.click)) {
			releaseAttack(client);
			if (!approach(client, player, next, now)) return;
			status = actionLabel(next) + format(next.pos);
			overlay(client, status, 0x55FFFF);
			return;
		}

		releaseWalk(client);
		holdSneak(client, player, false);
		if (next.harvest()) {
			if (harvest(client, player, next, plant, now)) {
				harvestedCount++;
				if (config.planterPickup) loot.begin(next.pos, lockedCrop, plant);
				status = "已收 " + cropLabel()
					+ "  种" + plantedCount + " 锄" + tilledCount + " 收" + harvestedCount;
				overlay(client, status, 0x55FF55);
				cooldown = ACTION_COOLDOWN;
				approachPos = null;
		approach.reset();
				harvestPos = null;
				return;
			}
			status = "收 " + cropLabel() + " " + format(next.pos);
			overlay(client, status, 0x55FFFF);
			return;
		}

		releaseAttack(client);
		if (!hasSeeds) {
			skipUntilTick.put(next.pos.immutable(), now + SKIP_TICKS);
			status = cropLabel() + " 用完了，不改种别的。成熟的还会继续收";
			overlay(client, status, 0xFF5555);
			return;
		}
		if (act(client, player, next, plant, now)) {
			if (next.till()) tilledCount++;
			else plantedCount++;
			status = (next.till() ? "已锄 " : "已种 ") + cropLabel()
				+ "  种" + plantedCount + " 锄" + tilledCount + " 收" + harvestedCount;
			overlay(client, status, 0x55FF55);
			cooldown = ACTION_COOLDOWN;
			approachPos = null;
		approach.reset();
			return;
		}

		skipUntilTick.put(next.pos.immutable(), now + SKIP_TICKS);
		status = "这一格没种上，换一块";
		overlay(client, status, 0xFFFF55);
	}

	/** 保持对准当前格。 */
	public void reapplyLook(Minecraft client) {
		if (!active || target == null || client.player == null || client.screen != null) return;
		if (target.harvest()) {
			lookAt(client.player, harvestLook(client.player, target));
			return;
		}
		lookStable(client.player, clickLocation(target), false);
	}

	/** 走近目标格。 */
	private boolean approach(Minecraft client, LocalPlayer player, Spot spot, int now) {
		if (!config.planterWalk) {
			releaseWalk(client);
			holdSneak(client, player, false);
			status = "太远，走近一点或打开「走近再种」";
			overlay(client, status, 0xFFFF55);
			return false;
		}
		if (player.isPassenger()) {
			releaseKeys(client);
			status = "先下来再种";
			overlay(client, status, 0xFFFF55);
			return false;
		}
		Vec3 dest = Vec3.atCenterOf(spot.pos);
		double dist = player.position().distanceTo(dest);
		if (approach.track(spot.pos, dist, STUCK_TICKS)) {
			skipUntilTick.put(spot.pos.immutable(), now + SKIP_TICKS * 3);
			approachPos = null;
			approach.reset();
			releaseWalk(client);
			status = "过不去，先换一块地";
			overlay(client, status, 0xFFFF55);
			return false;
		}
		approachPos = spot.pos.immutable();
		releaseAttack(client);
		holdSneak(client, player, false);
		lookAt(player, dest);
		ApproachTracker.walkToward(client, player, dest, STUCK_TICKS, approach);
		return true;
	}

	/** 收成熟作物。 */
	private boolean harvest(Minecraft client, LocalPlayer player, Spot spot, Block plant, int now) {
		if (!stillHarvestTarget(client, spot, plant)) {
			releaseAttack(client);
			skipUntilTick.put(spot.pos.immutable(), now + 8);
			return true;
		}
		if (harvestPos == null || !harvestPos.equals(spot.pos)) {
			harvestPos = spot.pos.immutable();
			harvestTicks = 0;
		} else {
			harvestTicks++;
			if (harvestTicks >= HARVEST_STALL_TICKS) {
				skipUntilTick.put(spot.pos.immutable(), now + SKIP_TICKS);
				harvestPos = null;
				releaseAttack(client);
				fileLog(client, "harvest-stall crop=" + format(spot.pos)
					+ " player=" + precisePosition(player));
				status = "这一格收不掉，换一块";
				overlay(client, status, 0xFFFF55);
				return false;
			}
		}
		Vec3 look = harvestLook(player, spot);
		lookAt(player, look);
		BlockHitResult hit = BorerAim.verifiedHit(client, player, look, spot.pos);
		if (!PlanterPolicy.harvestIfRayHitsCrop(hit != null)) {
			releaseAttack(client);
			fileLogOnce(client, "clip-miss crop=" + format(spot.pos)
				+ " aimed=" + aimedLabel(client, player, look)
				+ " player=" + precisePosition(player));
			harvestPos = null;
			harvestTicks = 0;
			if (config.planterWalk && player.position().distanceTo(Vec3.atCenterOf(spot.pos)) > 0.85) {
				if (approach(client, player, spot, now)) {
					status = "换角度收，避免打到围墙";
					overlay(client, status, 0xFFFF55);
				}
				return false;
			}
			skipUntilTick.put(spot.pos.immutable(), now + SKIP_TICKS);
			status = "准星打到围墙，换一块";
			overlay(client, status, 0xFFFF55);
			return false;
		}
		client.hitResult = hit;
		client.crosshairPickEntity = null;
		if (harvestTicks == 0 || harvestTicks % 8 == 0) {
			KeyMapping.click(InputConstants.getKey(client.options.keyAttack.saveString()));
		}
		client.options.keyAttack.setDown(true);
		return false;
	}

	/** 对目标格执行锄/种/收动作。 */
	private boolean act(Minecraft client, LocalPlayer player, Spot spot, Block plant, int now) {
		InteractionHand hand = spot.till() ? selectHoe(client) : selectItem(client, lockedCrop);
		if (hand == null) {
			releaseKeys(client);
			if (spot.till()) {
				stop(client, "背包没有锄，附近也没有可种的耕地");
			} else {
				stop(client, "拿不到 " + cropLabel());
			}
			return false;
		}
		lookStable(player, clickLocation(spot), false);
		BlockHitResult hit = new BlockHitResult(clickLocation(spot), spot.face, spot.click, false);
		InteractionResult result = client.gameMode.useItemOn(player, hand, hit);
		player.swing(hand);
		boolean ok = result.consumesAction()
			|| (spot.till() && client.level.getBlockState(spot.click).is(Blocks.FARMLAND))
			|| (!spot.till() && client.level.getBlockState(spot.pos).is(plant));
		if (ok) skipUntilTick.put(spot.pos.immutable(), now + 15);
		return ok;
	}

	/** 按蛇形与距离挑下一工作点。 */
	private Spot pick(LocalPlayer player, List<Spot> spots) {
		if (spots.isEmpty()) return null;
		ensureRowPlan(player);
		if (target != null) {
			for (Spot spot : spots) {
				if (spot.pos.equals(target.pos)) return spot;
			}
		}
		Comparator<BlockPos> order = PlanterPolicy.serpentineOrder(player.blockPosition(), rowPlan);
		Spot best = null;
		for (Spot spot : spots) {
			if (best == null || order.compare(spot.pos, best.pos) < 0) best = spot;
		}
		return best;
	}

	/** 范围内收集可种/可收/可锄的点。 */
	private List<Spot> collect(Minecraft client, LocalPlayer player, Block plant, boolean needsFarm,
		boolean hasSeeds, boolean hasHoe, int now) {
		List<Spot> spots = new ArrayList<>();
		int range = Math.max(3, (int)Math.round(config.planterRange));
		BlockPos origin = player.blockPosition();
		boolean allowTill = needsFarm && config.planterTill && !PlanterPolicy.skipTillWithoutHoe(config.planterTill, hasHoe);
		for (int dx = -range; dx <= range; dx++) {
			for (int dz = -range; dz <= range; dz++) {
				if (dx * dx + dz * dz > range * range) continue;
				for (int dy = -1; dy <= 3; dy++) {
					BlockPos pos = origin.offset(dx, dy, dz);
					if (!client.level.hasChunkAt(pos)) continue;
					Integer skip = skipUntilTick.get(pos);
					if (skip != null && now < skip) continue;
					if (config.planterHarvest) {
						Spot harvest = harvestSpot(client, pos, plant);
						if (harvest != null) {
							spots.add(harvest);
							continue;
						}
					}
					if (!hasSeeds) continue;
					Spot plantSpot = plantSpot(client, player, pos, plant);
					if (plantSpot != null) {
						spots.add(plantSpot);
						continue;
					}
					if (allowTill) {
						Spot till = tillSpot(client, pos, plant);
						if (till != null) spots.add(till);
					}
				}
			}
		}
		return spots;
	}

	/** 列表里是否还有可种或可收。 */
	private static boolean hasPlantOrHarvest(List<Spot> spots) {
		for (Spot spot : spots) {
			if (!spot.till()) return true;
		}
		return false;
	}

	/** 暂时没事做时的原因文案。 */
	private String idleReason(LocalPlayer player, Block plant, boolean needsFarm, boolean hasSeeds, boolean hasHoe) {
		return emptyStatus(player, plant, needsFarm, hasSeeds, hasHoe);
	}

	/** 构造播种 Spot。 */
	private Spot plantSpot(Minecraft client, LocalPlayer player, BlockPos pos, Block plant) {
		BlockState state = client.level.getBlockState(pos);
		if (!isPlantableSpace(state)) return null;
		if (state.is(plant)) return null;
		if (!config.planterStack && client.level.getBlockState(pos.below()).is(plant) && isStackable(plant)) {
			return null;
		}
		if (hasCollision(client, pos) && player.getBoundingBox().intersects(new AABB(pos))) return null;

		if (plant instanceof CocoaBlock) {
			Direction attach = cocoaAttach(client, pos);
			if (attach == null) return null;
			BlockPos log = pos.relative(attach);
			return new Spot(pos.immutable(), log.immutable(), attach.getOpposite(), Action.PLANT, false);
		}

		if (!plant.defaultBlockState().canSurvive(client.level, pos)) return null;
		if (!patchAllows(client, pos, plant)) return null;
		if (needsWaterHydration(plant) && !farmlandHydrated(client, pos.below())) return null;
		return new Spot(pos.immutable(), pos.below().immutable(), Direction.UP, Action.PLANT, false);
	}

	/** 构造锄地 Spot。 */
	private Spot tillSpot(Minecraft client, BlockPos soil, Block plant) {
		BlockState state = client.level.getBlockState(soil);
		if (!isTillable(state)) return null;
		BlockState above = client.level.getBlockState(soil.above());
		if (!isPlantableSpace(above)) return null;
		if (isEnclosureWallSoil(client, soil)) return null;
		if (!patchAllows(client, soil.above(), plant)) return null;
		if (needsWaterHydration(plant) && !farmlandHydrated(client, soil)) return null;
		return new Spot(soil.immutable(), soil.immutable(), Direction.UP, Action.TILL, false);
	}

	/** 9×9 田边那圈土：一边耕地、两边连着土、一边空，锄了就像把围墙打掉。 */
	private static boolean isEnclosureWallSoil(Minecraft client, BlockPos soil) {
		int farmland = 0;
		int dirt = 0;
		int open = 0;
		for (Direction dir : Direction.Plane.HORIZONTAL) {
			BlockPos neighbor = soil.relative(dir);
			BlockState neighborState = client.level.getBlockState(neighbor);
			if (neighborState.is(Blocks.FARMLAND)) {
				farmland++;
			} else if (isTillable(neighborState) && isPlantableSpace(client.level.getBlockState(neighbor.above()))) {
				dirt++;
			} else if (isPlantableSpace(neighborState)) {
				open++;
			}
		}
		return PlanterPolicy.isEnclosureWallSoil(farmland, dirt, open);
	}

	/** 构造收成 Spot。 */
	private Spot harvestSpot(Minecraft client, BlockPos pos, Block plant) {
		BlockState state = client.level.getBlockState(pos);
		if ((plant instanceof SugarCaneBlock || plant instanceof CactusBlock)
			&& state.is(plant)
			&& client.level.getBlockState(pos.below()).is(plant)) {
			return new Spot(pos.immutable(), pos.immutable(), Direction.UP, Action.HARVEST, true);
		}
		if (!isHarvestTarget(state, plant)) return null;
		if (isFarmlandCrop(plant) && !patchAllows(client, pos, plant)) return null;
		return new Spot(pos.immutable(), pos.immutable(), Direction.UP, Action.HARVEST, false);
	}

	/** 该收成点是否仍是成熟目标。 */
	private static boolean stillHarvestTarget(Minecraft client, Spot spot, Block plant) {
		BlockState state = client.level.getBlockState(spot.pos);
		if (spot.stackHarvest) {
			return state.is(plant) && client.level.getBlockState(spot.pos.below()).is(plant);
		}
		return isHarvestTarget(state, plant);
	}

	/** 方块状态是否可收目标植株。 */
	private static boolean isHarvestTarget(BlockState state, Block plant) {
		if (!matchesLockedPlant(state, plant)) return false;
		if (isStackable(plant)) return false;
		return isMatureCrop(state);
	}

	/** 是否与锁定作物一致。 */
	private static boolean matchesLockedPlant(BlockState state, Block plant) {
		if (state.is(plant)) return true;
		return plant instanceof TorchflowerCropBlock && state.is(Blocks.TORCHFLOWER);
	}

	/** 作物是否已成熟。 */
	private static boolean isMatureCrop(BlockState state) {
		Block block = state.getBlock();
		if (block instanceof CropBlock crop) return crop.isMaxAge(state);
		if (block instanceof NetherWartBlock) return ageAtLeast(state, 3);
		if (block instanceof PitcherCropBlock) return ageAtLeast(state, 4);
		return block == Blocks.TORCHFLOWER;
	}

	/** 年龄属性是否达到下限。 */
	private static boolean ageAtLeast(BlockState state, int min) {
		for (Property<?> property : state.getProperties()) {
			if (!"age".equals(property.getName()) || !(property instanceof IntegerProperty age)) continue;
			return state.getValue(age) >= min;
		}
		return false;
	}

	/** 原版耕地浇水：先看耕地湿润度，再扫附近水方块（同层或高 1 格）。 */
	private static boolean farmlandHydrated(Minecraft client, BlockPos farmland) {
		if (client.level == null) return false;
		BlockState soil = client.level.getBlockState(farmland);
		if (soil.is(Blocks.FARMLAND) && soil.getValue(FarmlandBlock.MOISTURE) > 0) {
			return true;
		}
		for (int dx = -WATER_CHEBYSHEV; dx <= WATER_CHEBYSHEV; dx++) {
			for (int dz = -WATER_CHEBYSHEV; dz <= WATER_CHEBYSHEV; dz++) {
				for (int dy = 0; dy <= 1; dy++) {
					if (client.level.getFluidState(farmland.offset(dx, dy, dz)).is(FluidTags.WATER)) {
						return true;
					}
				}
			}
		}
		return false;
	}

	/** 该作物是否要附近有水。 */
	private static boolean needsWaterHydration(Block plant) {
		return plant instanceof CropBlock
			|| plant instanceof PitcherCropBlock
			|| plant instanceof TorchflowerCropBlock;
	}

	/** 连着的耕地算一片。这片已经有胡萝卜，就不要再插小麦。 */
	private static boolean patchAllows(Minecraft client, BlockPos plantPos, Block want) {
		if (!isFarmlandCrop(want)) return true;
		Block existing = patchCrop(client, plantPos);
		if (existing == null || existing == want) return true;
		return want instanceof TorchflowerCropBlock && existing == Blocks.TORCHFLOWER;
	}

	/** 根据田里植株推断作物方块。 */
	private static Block patchCrop(Minecraft client, BlockPos plantPos) {
		if (client.level == null) return null;
		BlockPos soil = plantPos.below();
		BlockState ground = client.level.getBlockState(soil);
		boolean farmland = ground.is(Blocks.FARMLAND);
		boolean soul = ground.is(Blocks.SOUL_SAND);
		if (!farmland && !soul) return null;
		ArrayDeque<BlockPos> queue = new ArrayDeque<>();
		Set<BlockPos> seen = new HashSet<>();
		queue.add(soil.immutable());
		seen.add(soil.immutable());
		Map<Block, Integer> counts = new HashMap<>();
		int scanned = 0;
		while (!queue.isEmpty() && scanned < 128) {
			BlockPos current = queue.removeFirst();
			scanned++;
			Block crop = client.level.getBlockState(current.above()).getBlock();
			if (crop instanceof TorchflowerCropBlock || crop == Blocks.TORCHFLOWER) {
				counts.merge(Blocks.TORCHFLOWER, 1, Integer::sum);
			} else if (isFarmlandCrop(crop)) {
				counts.merge(crop, 1, Integer::sum);
			}
			for (Direction direction : Direction.Plane.HORIZONTAL) {
				BlockPos next = current.relative(direction);
				if (!seen.add(next.immutable())) continue;
				BlockState nextGround = client.level.getBlockState(next);
				if (farmland && nextGround.is(Blocks.FARMLAND) || soul && nextGround.is(Blocks.SOUL_SAND)) {
					queue.add(next.immutable());
				}
			}
		}
		Block best = null;
		int bestCount = 0;
		for (Map.Entry<Block, Integer> entry : counts.entrySet()) {
			if (entry.getValue() > bestCount) {
				bestCount = entry.getValue();
				best = entry.getKey();
			}
		}
		return best;
	}

	/** 是否需要耕地的作物。 */
	private static boolean isFarmlandCrop(Block block) {
		return block instanceof CropBlock
			|| block instanceof PitcherCropBlock
			|| block instanceof TorchflowerCropBlock
			|| block instanceof NetherWartBlock;
	}

	/** 可可豆可贴的原木朝向。 */
	private Direction cocoaAttach(Minecraft client, BlockPos pos) {
		for (Direction direction : Direction.Plane.HORIZONTAL) {
			BlockState trial = Blocks.COCOA.defaultBlockState().setValue(HorizontalDirectionalBlock.FACING, direction);
			if (trial.canSurvive(client.level, pos)) return direction;
		}
		return null;
	}

	/** 无可做时的说明。 */
	private String emptyStatus(LocalPlayer player, Block plant, boolean needsFarm, boolean hasSeeds, boolean hasHoe) {
		if (needsFarm && !hasSeeds) {
			return config.planterHarvest
				? "种子用完了。附近也没有成熟的 " + cropLabel()
				: "种子用完了";
		}
		if (needsFarm && config.planterTill && !hasHoe && !hasFarmlandNearby(player)) {
			return "附近没有耕地，背包也没有锄";
		}
		if (needsFarm && config.planterTill && !hasHoe) {
			return "背包没有锄，附近也没有可种的空耕地";
		}
		if (needsFarm) {
			return "这片田不是 " + cropLabel() + "，没有空位，或土没浇到水（水要在 4 格内）"
				+ (config.planterHarvest ? "。成熟的会先收" : "")
				+ "（已种 " + plantedCount + (config.planterHarvest ? " 已收 " + harvestedCount : "") + "）";
		}
		if (plant instanceof SugarCaneBlock) return "附近没有能种甘蔗的位置（要靠水的泥土/沙子）";
		if (plant instanceof CactusBlock) return "附近没有能种仙人掌的沙子";
		if (plant instanceof NetherWartBlock) return "附近没有灵魂沙";
		if (plant instanceof CocoaBlock) return "附近没有可挂可可的丛林原木";
		return "附近没有可种 " + cropLabel() + " 的位置（已种 " + plantedCount + "）";
	}

	/** 附近是否已有耕地。 */
	private boolean hasFarmlandNearby(LocalPlayer player) {
		if (player.level() == null) return false;
		BlockPos origin = player.blockPosition();
		int range = Math.max(3, (int)Math.round(config.planterRange));
		for (int dx = -range; dx <= range; dx++) {
			for (int dz = -range; dz <= range; dz++) {
				for (int dy = -1; dy <= 1; dy++) {
					if (player.level().getBlockState(origin.offset(dx, dy, dz)).is(Blocks.FARMLAND)) return true;
				}
			}
		}
		return false;
	}

	/** 从手或田刷新锁定作物。 */
	private void refreshLockedCrop(Minecraft client, LocalPlayer player) {
		Item held = cropInHand(player);
		if (held != null) lockedCrop = held;
		if (lockedCrop == null) lockedCrop = resolveCrop(player);
		if (!config.planterHarvest) {
			if (lockedCrop == null) lockedCrop = resolveCropFromField(client, player);
			return;
		}
		Item fieldCrop = resolveCropFromField(client, player);
		if (fieldCrop == null) return;
		if (lockedCrop == null) {
			lockedCrop = fieldCrop;
			return;
		}
		Block handPlant = plantBlock(lockedCrop);
		boolean handHasMature = handPlant != null && hasMatureNearby(client, player, handPlant);
		if (PlanterPolicy.preferFieldCropForHarvest(lockedCrop == fieldCrop, handHasMature)) {
			lockedCrop = fieldCrop;
		}
	}

	/** 附近是否有该种成熟作物。 */
	private boolean hasMatureNearby(Minecraft client, LocalPlayer player, Block plant) {
		int range = Math.max(3, (int)Math.round(config.planterRange));
		BlockPos origin = player.blockPosition();
		for (int dx = -range; dx <= range; dx++) {
			for (int dz = -range; dz <= range; dz++) {
				if (dx * dx + dz * dz > range * range) continue;
				for (int dy = -1; dy <= 3; dy++) {
					BlockPos pos = origin.offset(dx, dy, dz);
					if (!client.level.hasChunkAt(pos)) continue;
					if (isHarvestTarget(client.level.getBlockState(pos), plant)) return true;
				}
			}
		}
		return false;
	}

	/** 解析当前应种的作物物品。 */
	private Item resolveCrop(LocalPlayer player) {
		Item held = cropInHand(player);
		if (held != null) return held;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (isCrop(stack)) return stack.getItem();
		}
		return null;
	}

	/** 背包没种子时，按附近成熟作物认是哪种，打掉就会掉种子。 */
	private Item resolveCropFromField(Minecraft client, LocalPlayer player) {
		if (client.level == null || player == null) return null;
		int range = Math.max(3, (int)Math.round(config.planterRange));
		BlockPos origin = player.blockPosition();
		Map<Item, Integer> counts = new HashMap<>();
		for (int dx = -range; dx <= range; dx++) {
			for (int dz = -range; dz <= range; dz++) {
				if (dx * dx + dz * dz > range * range) continue;
				for (int dy = -1; dy <= 3; dy++) {
					BlockPos pos = origin.offset(dx, dy, dz);
					if (!client.level.hasChunkAt(pos)) continue;
					BlockState state = client.level.getBlockState(pos);
					if (!isMatureCrop(state)) continue;
					Item seed = seedItemOf(state);
					if (seed == null || !isCrop(new ItemStack(seed))) continue;
					counts.merge(seed, 1, Integer::sum);
				}
			}
		}
		Item best = null;
		int bestCount = 0;
		for (Map.Entry<Item, Integer> entry : counts.entrySet()) {
			if (entry.getValue() > bestCount) {
				bestCount = entry.getValue();
				best = entry.getKey();
			}
		}
		return best;
	}

	/** 植株状态对应的种子物品。 */
	private static Item seedItemOf(BlockState state) {
		Block block = state.getBlock();
		if (block == Blocks.WHEAT) return Items.WHEAT_SEEDS;
		if (block == Blocks.CARROTS) return Items.CARROT;
		if (block == Blocks.POTATOES) return Items.POTATO;
		if (block == Blocks.BEETROOTS) return Items.BEETROOT_SEEDS;
		if (block == Blocks.NETHER_WART) return Items.NETHER_WART;
		if (block == Blocks.TORCHFLOWER_CROP || block == Blocks.TORCHFLOWER) return Items.TORCHFLOWER_SEEDS;
		if (block == Blocks.PITCHER_CROP) return Items.PITCHER_POD;
		if (block == Blocks.COCOA) return Items.COCOA_BEANS;
		if (block == Blocks.SWEET_BERRY_BUSH) return Items.SWEET_BERRIES;
		if (block == Blocks.SUGAR_CANE) return Items.SUGAR_CANE;
		if (block == Blocks.CACTUS) return Items.CACTUS;
		if (block == Blocks.BAMBOO || block == Blocks.BAMBOO_SAPLING) return Items.BAMBOO;
		if (block == Blocks.KELP || block == Blocks.KELP_PLANT) return Items.KELP;
		Item item = block.asItem();
		return item != Items.AIR && isCrop(new ItemStack(item)) ? item : null;
	}

	/** 手里拿的作物/种子。 */
	private static Item cropInHand(LocalPlayer player) {
		if (isCrop(player.getMainHandItem())) return player.getMainHandItem().getItem();
		if (isCrop(player.getOffhandItem())) return player.getOffhandItem().getItem();
		return null;
	}

	/** 堆叠是否可种作物。 */
	public static boolean isCrop(ItemStack stack) {
		if (stack.isEmpty()) return false;
		if (stack.is(ItemTags.VILLAGER_PLANTABLE_SEEDS)) return true;
		if (!(stack.getItem() instanceof BlockItem blockItem)) return false;
		Block block = blockItem.getBlock();
		return block instanceof CropBlock
			|| block instanceof PitcherCropBlock
			|| block instanceof TorchflowerCropBlock
			|| block instanceof SugarCaneBlock
			|| block instanceof CactusBlock
			|| block instanceof NetherWartBlock
			|| block instanceof CocoaBlock
			|| block instanceof BambooStalkBlock
			|| block instanceof BambooSaplingBlock
			|| block instanceof KelpBlock
			|| block instanceof SweetBerryBushBlock
			|| block instanceof MangrovePropaguleBlock;
	}

	/** 当前植株方块。 */
	private static Block plantBlock(Item item) {
		return item instanceof BlockItem blockItem ? blockItem.getBlock() : null;
	}

	/** 该作物是否需要耕地。 */
	private static boolean needsFarmland(Item item, Block plant) {
		if (plant instanceof CropBlock || plant instanceof PitcherCropBlock || plant instanceof TorchflowerCropBlock) {
			return true;
		}
		return new ItemStack(item).is(ItemTags.VILLAGER_PLANTABLE_SEEDS)
			&& !(plant instanceof SugarCaneBlock)
			&& !(plant instanceof NetherWartBlock);
	}

	/** 是否可往上叠种（甘蔗等）。 */
	private static boolean isStackable(Block plant) {
		return plant instanceof SugarCaneBlock
			|| plant instanceof CactusBlock
			|| plant instanceof KelpBlock
			|| plant instanceof BambooStalkBlock
			|| plant instanceof BambooSaplingBlock;
	}

	/** 是否可锄成耕地。 */
	private static boolean isTillable(BlockState state) {
		return state.is(Blocks.DIRT) || state.is(Blocks.GRASS_BLOCK) || state.is(Blocks.DIRT_PATH);
	}

	/** 顶上是否可种的空间。 */
	private static boolean isPlantableSpace(BlockState state) {
		return state.isAir() || state.canBeReplaced();
	}

	/** 该格是否有碰撞。 */
	private static boolean hasCollision(Minecraft client, BlockPos pos) {
		return !client.level.getBlockState(pos).getCollisionShape(client.level, pos).isEmpty();
	}

	/** 主手或背包换成指定物品。 */
	private InteractionHand selectItem(Minecraft client, Item item) {
		LocalPlayer player = client.player;
		if (player.getMainHandItem().is(item)) return InteractionHand.MAIN_HAND;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			inventory.setSelectedSlot(slot);
			return InteractionHand.MAIN_HAND;
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			if (player.getMainHandItem().is(item) || inventory.getItem(inventory.getSelectedSlot()).is(item)) {
				return InteractionHand.MAIN_HAND;
			}
		}
		if (player.getOffhandItem().is(item)) return InteractionHand.OFF_HAND;
		return null;
	}

	/** 手上换成锄。 */
	private InteractionHand selectHoe(Minecraft client) {
		LocalPlayer player = client.player;
		if (player.getMainHandItem().getItem() instanceof HoeItem) return InteractionHand.MAIN_HAND;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (!(inventory.getItem(slot).getItem() instanceof HoeItem)) continue;
			inventory.setSelectedSlot(slot);
			return InteractionHand.MAIN_HAND;
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!(inventory.getItem(slot).getItem() instanceof HoeItem)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			if (player.getMainHandItem().getItem() instanceof HoeItem) return InteractionHand.MAIN_HAND;
		}
		if (player.getOffhandItem().getItem() instanceof HoeItem) return InteractionHand.OFF_HAND;
		return null;
	}

	/** 背包是否有该物品。 */
	private static boolean hasItem(LocalPlayer player, Item item) {
		if (player.getMainHandItem().is(item) || player.getOffhandItem().is(item)) return true;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (stack.is(item)) return true;
		}
		return false;
	}

	/** 画出田块目标。 */
	private void emitGizmos(List<Spot> spots) {
		for (Spot spot : spots) {
			boolean current = target != null && spot.pos.equals(target.pos);
			int stroke;
			int fill;
			if (current) {
				stroke = 0xFF00FFFF;
				fill = 0x3300FFFF;
			} else if (spot.harvest()) {
				stroke = 0xFFFFFF55;
				fill = 0x33FFFF00;
			} else if (spot.till()) {
				stroke = 0xFFFFAA00;
				fill = 0x33FFAA00;
			} else {
				stroke = 0xFF55FF55;
				fill = 0x2200FF55;
			}
			Gizmos.cuboid(spot.pos, GizmoStyle.strokeAndFill(stroke, current ? 2.4F : 1.2F, fill));
		}
	}

	/** 是否够得着。 */
	private static boolean inReach(LocalPlayer player, BlockPos pos) {
		return player.isWithinBlockInteractionRange(pos, 0.0);
	}

	/** Spot 的点击坐标。 */
	private static Vec3 clickLocation(Spot spot) {
		return Vec3.atCenterOf(spot.click).add(spot.face.getStepX() * 0.51, spot.face.getStepY() * 0.51, spot.face.getStepZ() * 0.51);
	}

	/** 按朝向确保蛇形行计划。 */
	private void ensureRowPlan(LocalPlayer player) {
		if (rowPlan == null) rowPlan = PlanterPolicy.rowPlanFromYaw(player.getYRot());
	}

	/** 行走时稳住视角，减少甩头。 */
	private void lookStable(LocalPlayer player, Vec3 aim, boolean walking) {
		ensureRowPlan(player);
		Vec3 eye = player.getEyePosition();
		Vec3 delta = aim.subtract(eye);
		double horiz = Math.hypot(delta.x, delta.z);
		float pitch = (float)Math.toDegrees(-Math.atan2(delta.y, Math.max(0.001, horiz)));
		if (walking) pitch = Math.max(pitch, 35.0F);
		player.setYRot(rowPlan.lockedYaw);
		player.setXRot(pitch);
		player.setYHeadRot(rowPlan.lockedYaw);
	}

	/** 走向目标。 */
	private void walkToward(Minecraft client, LocalPlayer player, BlockPos dest) {
		ensureRowPlan(player);
		Vec3 delta = Vec3.atCenterOf(dest).subtract(player.position());
		float yawRad = (float)Math.toRadians(rowPlan.lockedYaw);
		float forwardX = -((float)Math.sin(yawRad));
		float forwardZ = (float)Math.cos(yawRad);
		float forward = (float)(delta.x * forwardX + delta.z * forwardZ);
		float right = (float)(delta.x * forwardZ - delta.z * forwardX);
		client.options.keyUp.setDown(forward > 0.12);
		client.options.keyDown.setDown(forward < -0.12);
		client.options.keyLeft.setDown(right < -0.12);
		client.options.keyRight.setDown(right > 0.12);
	}

	/** 瞬间对准。 */
	private static void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}

	/** 按需按住潜行（护耕地）。 */
	private static void holdSneak(Minecraft client, LocalPlayer player, boolean sneak) {
		boolean flying = player.getAbilities().flying || player.isFallFlying();
		client.options.keyShift.setDown(sneak && !flying);
	}

	/** 松开移动键。 */
	private static void releaseWalk(Minecraft client) {
		client.options.keyUp.setDown(false);
		client.options.keyDown.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		client.options.keyJump.setDown(false);
	}

	/** 松开攻击键。 */
	private static void releaseAttack(Minecraft client) {
		if (client.options != null) client.options.keyAttack.setDown(false);
		if (client.gameMode != null) client.gameMode.stopDestroyBlock();
	}

	/** 松键。 */
	private static void releaseKeys(Minecraft client) {
		releaseWalk(client);
		releaseAttack(client);
		client.options.keyShift.setDown(false);
	}

	/** Spot 动作中文名。 */
	private static String actionLabel(Spot spot) {
		if (spot.harvest()) return "去收 ";
		if (spot.till()) return "去锄地 ";
		return "去种 ";
	}

	/** 清过期格冷却。 */
	private static void prune(Map<BlockPos, Integer> map, int now) {
		Iterator<Map.Entry<BlockPos, Integer>> iterator = map.entrySet().iterator();
		while (iterator.hasNext()) {
			if (iterator.next().getValue() < now) iterator.remove();
		}
	}

	/** 坐标短字符串。 */
	private static String format(BlockPos pos) {
		return pos.getX() + "," + pos.getY() + "," + pos.getZ();
	}

	/** 玩家精确坐标文案。 */
	private static String precisePosition(LocalPlayer player) {
		return String.format(Locale.ROOT, "%.3f,%.3f,%.3f", player.getX(), player.getY(), player.getZ());
	}

	/** 瞄准作物靠近眼睛的那一面，避免射线擦过旁边土墙。 */
	private static Vec3 harvestLook(LocalPlayer player, Spot spot) {
		Vec3 center = Vec3.atCenterOf(spot.pos);
		Vec3 towardEye = player.getEyePosition().subtract(center);
		double len = towardEye.length();
		if (len < 1.0E-6) return center;
		return center.add(towardEye.scale(0.42 / len));
	}

	/** 准星当前打到的标签。 */
	private static String aimedLabel(Minecraft client, LocalPlayer player, Vec3 look) {
		BlockHitResult hit = BorerAim.clipToward(client, player, look);
		return hit == null ? "-" : format(hit.getBlockPos());
	}

	/** 写种田诊断一行。 */
	private void fileLog(Minecraft client, String line) {
		PlanterFileLog.append(client, VERSION, line);
	}

	/** 同一文案只写一次。 */
	private void fileLogOnce(Minecraft client, String line) {
		if (line.equals(lastFileLog)) return;
		lastFileLog = line;
		fileLog(client, line);
	}

	/** 周期性进度日志。 */
	private void logPeriodic(Minecraft client, LocalPlayer player) {
		String cross = "-";
		if (client.hitResult instanceof BlockHitResult hit && hit.getType() == HitResult.Type.BLOCK) {
			cross = format(hit.getBlockPos()) + "/" + hit.getDirection().getSerializedName();
		}
		fileLog(client, "periodic crop=" + cropLabel()
			+ " player=" + precisePosition(player)
			+ " target=" + (target == null ? "-" : target.action() + " " + format(target.pos))
			+ " planted=" + plantedCount
			+ " tilled=" + tilledCount
			+ " harvested=" + harvestedCount
			+ " loot=" + loot.picked()
			+ (loot.active() ? " lootActive=true" : "")
			+ " attack=" + client.options.keyAttack.isDown()
			+ " up=" + client.options.keyUp.isDown()
			+ " crosshair=" + cross
			+ " status=" + status);
	}

	/** 叠字幕。 */
	private static void overlay(Minecraft client, String text, int color) {
		client.gui.setOverlayMessage(Component.literal("[种田] " + text).withColor(color), false);
	}

	/** 发系统消息。 */
	private static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[种田] " + text));
	}

	private enum Action {
		PLANT, TILL, HARVEST
	}

	/** 一个工作点：位置、点击面与动作。 */
	private record Spot(BlockPos pos, BlockPos click, Direction face, Action action, boolean stackHarvest) {
		boolean till() {
			return action == Action.TILL;
		}

		boolean harvest() {
			return action == Action.HARVEST;
		}
	}
}
