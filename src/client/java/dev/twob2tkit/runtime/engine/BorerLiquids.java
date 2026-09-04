package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** 岩浆/水封堵、接触逃生、岩浆块离开、找矿绕行。放置走 BorerPlace。 */
final class BorerLiquids {
	private final DefaultTunnelBorerEngine engine;

	BorerLiquids(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 收集通道附近可封堵的水或岩浆。 */
	BlockPos findHazard(Minecraft client, LocalPlayer player) {
		BlockPos feet = player.blockPosition();
		List<BlockPos> candidates = new ArrayList<>();
		if (engine.mode == DefaultTunnelBorerEngine.Mode.DOWN || engine.mode == DefaultTunnelBorerEngine.Mode.AREA) {
			for (int dy = -6; dy <= 3; dy++) {
				for (int dx = -2; dx <= 2; dx++) {
					for (int dz = -2; dz <= 2; dz++) addCandidate(client, player, candidates, feet.offset(dx, dy, dz));
				}
			}
		} else {
			int half = engine.effectiveWidth() / 2;
			int height = engine.effectiveHeight();
			int ahead = engine.mode == DefaultTunnelBorerEngine.Mode.ORE
				? 3 : Math.max(2, Math.min(5, engine.host.borerLookAhead() + 1));
			for (int dist = 0; dist <= ahead; dist++) {
				for (int dy = -2; dy <= height + 3; dy++) {
					for (int dx = -half - 1; dx <= half + 1; dx++) {
						addCandidate(client, player, candidates, engine.offset(feet, dist, dx, dy));
					}
				}
			}
		}
		candidates.sort(Comparator
			.comparingInt((BlockPos pos) -> client.level.getFluidState(pos).isSource() ? 0 : 1)
			.thenComparingDouble(pos -> player.getEyePosition().distanceToSqr(Vec3.atCenterOf(pos))));
		return candidates.isEmpty() ? null : candidates.getFirst();
	}

	/** 把液体格加入候选。 */
	private void addCandidate(Minecraft client, LocalPlayer player, List<BlockPos> candidates, BlockPos pos) {
		if (client.level.getBlockState(pos).is(Blocks.MAGMA_BLOCK)) return;
		if (client.level.getFluidState(pos).isEmpty()) return;
		boolean touching = player.getBoundingBox().inflate(0.05).intersects(new AABB(pos));
		if (!touching && (!engine.inMiningReach(player, pos) || !BorerHazards.canSeeLiquid(client, player, pos))) return;
		boolean area = engine.mode == DefaultTunnelBorerEngine.Mode.AREA;
		if (area && !engine.area.handleNearbyLiquid(pos)) return;
		if (area && BorerLiquidPolicy.ignoreLakeCandidate(true, waterNeighbors(client, pos))
			&& !engine.area.isCurrentShaftColumn(pos)) return;
		if (!candidates.contains(pos)) candidates.add(pos.immutable());
	}

	/** 用背包方块封堵看见的水或岩浆。 */
	void handle(Minecraft client, LocalPlayer player, BlockPos liquid) {
		engine.releaseMine(client);
		engine.sealTarget = liquid;
		String kind = BorerHazards.isLavaFluid(client, liquid) ? "岩浆" : "水";
		boolean area = engine.mode == DefaultTunnelBorerEngine.Mode.AREA;
		int waterN = waterNeighbors(client, liquid);
		int solidN = solidNeighbors(client, liquid);
		boolean leak = BorerLiquidPolicy.isSmallLeak(waterN, solidN);
		if (engine.liquidSealFailPos == null || !engine.liquidSealFailPos.equals(liquid)) {
			engine.liquidSealFailPos = liquid.immutable();
			engine.liquidSealFails = 0;
		}
		if (BorerLiquidPolicy.skipShaftForLake(area, waterN)) {
			abandon(client, player, liquid, kind, "lake waterN=" + waterN);
			return;
		}
		if (engine.liquidSettleTicks > 0) {
			engine.status = "等待" + kind + "封堵生效 " + BorerText.block(liquid);
			engine.overlay(client, engine.status, 0xFFFF55);
			return;
		}
		DefaultTunnelBorerEngine.SealChoice choice = engine.place.selectSealBlock(client, player);
		if (choice == null) {
			if (bypassUnsealableLava(client, player, liquid, kind)) return;
			engine.status = "发现" + kind + " " + BorerText.block(liquid) + "，但背包没有可用封堵方块";
			engine.overlay(client, engine.status, 0xFF5555);
			engine.fileLog(client, "liquid-no-seal liquid=" + BorerText.block(liquid) + " kind=" + kind
				+ " cobble=" + BorerItems.countItem(player, Items.COBBLESTONE)
				+ " dirt=" + BorerItems.countItem(player, Items.DIRT)
				+ " player=" + BorerText.precise(player));
			if (BorerAreaPolicy.keepThinkingDuringHazard(area)) {
				engine.area.handleHazard(client, player, true);
			}
			return;
		}
		double distSqr = player.getEyePosition().distanceToSqr(Vec3.atCenterOf(liquid));
		if (BorerLiquidPolicy.shouldWalkToLeak(leak, engine.inMiningReach(player, liquid), distSqr)) {
			approachLeak(client, player, liquid, kind);
			return;
		}
		if (!client.level.getBlockState(liquid).getFluidState().isEmpty()) {
			client.options.keyShift.setDown(true);
		} else {
			client.options.keyShift.setDown(false);
		}
		boolean placed = engine.place.placeAndProtect(client, player, liquid, choice);
		engine.fileLog(client, "liquid-seal result=" + placed + " liquid=" + BorerText.block(liquid)
			+ " kind=" + kind + " waterN=" + waterN + " solidN=" + solidN + " leak=" + leak
			+ " block=" + BuiltInRegistries.BLOCK.getKey(choice.block())
			+ " player=" + BorerText.precise(player));
		if (placed) {
			engine.lavaBypassTicks = 0;
			engine.liquidSealFails = 0;
		} else if (bypassUnsealableLava(client, player, liquid, kind)) {
			return;
		} else {
			engine.liquidSealFails++;
			if (BorerLiquidPolicy.giveUpAfterFails(engine.liquidSealFails) && area) {
				abandon(client, player, liquid, kind, "fails=" + engine.liquidSealFails);
				return;
			}
		}
		engine.liquidSettleTicks = BorerLiquidPolicy.settleTicks(placed, area);
		engine.status = placed
			? "已用" + engine.place.itemLabel(choice.item()) + "堵住" + kind + " " + BorerText.block(liquid)
			: leak
				? "去堵住漏水 " + BorerText.block(liquid)
				: "尝试封堵" + kind + "失败 " + BorerText.block(liquid) + "，稍后重试";
		engine.overlay(client, engine.status, placed ? 0x55FFFF : 0xFFFF55);
	}

	/** 走近漏水点。 */
	private void approachLeak(Minecraft client, LocalPlayer player, BlockPos liquid, String kind) {
		engine.enableMeteorFlight(player);
		engine.lookAt(player, Vec3.atCenterOf(liquid));
		client.options.keyAttack.setDown(false);
		client.options.keyUp.setDown(true);
		double dy = (liquid.getY() + 0.5) - player.getY();
		client.options.keyJump.setDown(dy > 0.35);
		client.options.keyShift.setDown(dy < -0.35);
		engine.attemptedForward = true;
		engine.status = "去堵住漏水 " + BorerText.block(liquid);
		engine.overlay(client, engine.status, 0xFFFF55);
		engine.fileLog(client, "liquid-approach liquid=" + BorerText.block(liquid) + " kind=" + kind
			+ " player=" + BorerText.precise(player));
	}

	/** 放弃当前目标并记日志。 */
	private void abandon(Minecraft client, LocalPlayer player, BlockPos liquid, String kind, String reason) {
		engine.liquidSettleTicks = 0;
		engine.liquidSealFails = 0;
		engine.liquidSealFailPos = null;
		engine.sealTarget = null;
		engine.fileLog(client, "liquid-abandon liquid=" + BorerText.block(liquid) + " kind=" + kind
			+ " " + reason + " player=" + BorerText.precise(player));
		if (engine.mode == DefaultTunnelBorerEngine.Mode.AREA && engine.areaMin != null && engine.areaMax != null) {
			engine.area.ensureShaftColumn(client, player);
		}
		if (engine.mode == DefaultTunnelBorerEngine.Mode.AREA && engine.areaShaftColumn != null) {
			if (engine.area.skipCurrentShaft(client, liquid, "liquid-" + kind)) {
				engine.status = "水面太大，先沿原井返顶再换下一口";
				engine.overlay(client, engine.status, 0xFFFF55);
			} else if (engine.active) {
				engine.status = "液体不在当前下挖列，保持当前竖井，不会误跳下一口";
				engine.overlay(client, engine.status, 0xFFFF55);
			}
			return;
		}
		if (BorerAreaPolicy.keepThinkingDuringHazard(engine.mode == DefaultTunnelBorerEngine.Mode.AREA)) {
			engine.area.handleHazard(client, player, true);
		}
	}

	/** 邻接水面数。 */
	private int waterNeighbors(Minecraft client, BlockPos pos) {
		int count = 0;
		for (Direction direction : Direction.values()) {
			if (!client.level.getFluidState(pos.relative(direction)).isEmpty()) count++;
		}
		return count;
	}

	/** 邻接固体数。 */
	private int solidNeighbors(Minecraft client, BlockPos pos) {
		int count = 0;
		for (Direction direction : Direction.values()) {
			var state = client.level.getBlockState(pos.relative(direction));
			if (state.isAir() || state.canBeReplaced() || !state.getFluidState().isEmpty()) continue;
			count++;
		}
		return count;
	}

	/** 岩浆封不住时不要停机：找矿改绕开其它矿，直挖则停步等。 */
	private boolean bypassUnsealableLava(Minecraft client, LocalPlayer player, BlockPos liquid, String kind) {
		if (!"岩浆".equals(kind) || BorerHazards.playerTouchedLava(client, player)) return false;
		engine.lavaBypassTicks++;
		if (engine.mode == DefaultTunnelBorerEngine.Mode.ORE && engine.lavaBypassTicks >= 8) {
			engine.lavaBypassTicks = 0;
			engine.ores.skipActive(client, "岩浆 " + BorerText.block(liquid) + " 封不住，不挖岩浆下的方块，改绕开等待");
			return true;
		}
		engine.releaseMine(client);
		client.options.keyUp.setDown(false);
		engine.status = engine.mode == DefaultTunnelBorerEngine.Mode.ORE
			? "岩浆 " + BorerText.block(liquid) + " 封不住，准备绕开"
			: "岩浆 " + BorerText.block(liquid) + " 封不住，已停步，不挖岩浆下的方块";
		engine.overlay(client, engine.status, 0xFFFF55);
		return engine.mode != DefaultTunnelBorerEngine.Mode.ORE || engine.lavaBypassTicks < 8;
	}

	/** 在贴身和通道范围内找岩浆，供停机保护。 */
	BlockPos findLava(Minecraft client, LocalPlayer player) {
		BlockPos feet = player.blockPosition();
		for (int dy = -1; dy <= 3; dy++) {
			for (int dx = -1; dx <= 1; dx++) {
				for (int dz = -1; dz <= 1; dz++) {
					BlockPos pos = feet.offset(dx, dy, dz);
					if (BorerHazards.isLavaFluid(client, pos)) return pos.immutable();
				}
			}
		}
		if (engine.mode == DefaultTunnelBorerEngine.Mode.DOWN || engine.mode == DefaultTunnelBorerEngine.Mode.AREA) {
			for (int dy = 1; dy <= 10; dy++) {
				for (int dx = -2; dx <= 2; dx++) {
					for (int dz = -2; dz <= 2; dz++) {
						BlockPos pos = feet.offset(dx, -dy, dz);
						if (BorerHazards.isLavaFluid(client, pos) && visible(client, player, pos)) return pos;
					}
				}
			}
			return null;
		}
		int width = engine.effectiveWidth();
		int height = engine.effectiveHeight();
		int half = width / 2;
		for (int dist = 0; dist <= 4; dist++) {
			for (int dy = -2; dy <= height + 3; dy++) {
				for (int dx = -half - 1; dx <= half + 1; dx++) {
					BlockPos pos = engine.offset(feet, dist, dx, dy);
					if (BorerHazards.isLavaFluid(client, pos) && (dist <= 1 || visible(client, player, pos))) return pos;
				}
			}
		}
		return null;
	}

	/**
	 * 已经泡在水里就停挖：封水或上浮，不要在水里继续挖方块。
	 */
	boolean handleWaterContact(Minecraft client, LocalPlayer player) {
		if (player == null || !player.isInWater()) return false;
		if (engine.mode == DefaultTunnelBorerEngine.Mode.AREA
			&& engine.area.ignoreWaterContactOutsideRoute(player.blockPosition())) return false;
		engine.releaseMine(client);
		engine.clearMiningTarget(client, "water-contact");
		client.options.keyUp.setDown(false);
		if (player.isUnderWater()) client.options.keyJump.setDown(true);
		BlockPos liquid = engine.host.borerSealLiquids() ? findHazard(client, player) : null;
		if (liquid != null) {
			handle(client, player, liquid);
			return true;
		}
		if (player.isUnderWater() && engine.enableMeteorFlight(player)) {
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
			engine.status = "已进水，飞行上浮，不挖方块";
			engine.overlay(client, engine.status, 0xFFFF55);
			return true;
		}
		engine.status = "已进水，先游上去，不挖方块";
		engine.overlay(client, engine.status, 0xFFFF55);
		return true;
	}

	/**
	 * 真的泡进岩浆流体才处理。旁边岩浆湖不算接触。
	 * 绕道模式不因此停机：飞离、走到安全格、拐弯或铺路。
	 */
	boolean handleLavaContact(Minecraft client, LocalPlayer player) {
		if (!BorerHazards.playerTouchedLava(client, player)) {
			engine.lavaContactTicks = 0;
			return false;
		}
		engine.lavaContactTicks++;
		if (!engine.turnAroundLava() && engine.host.borerStopOnLava()) {
			engine.stop(client, "已接触岩浆 " + BorerText.block(player.blockPosition()) + "，直线隧道已停");
			return true;
		}
		if (engine.lavaContactTicks >= DefaultTunnelBorerEngine.LAVA_CONTACT_ESCAPE_TICKS && engine.host.borerStopOnLava()) {
			engine.stop(client, "踩在岩浆里绕不开，已停 " + BorerText.block(player.blockPosition()));
			return true;
		}
		engine.releaseMine(client);
		client.options.keyUp.setDown(false);
		if (engine.enableMeteorFlight(player)) {
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
			engine.tryTurnAroundLava(client, player, true);
			engine.status = "踩到岩浆，飞离并绕道";
			engine.overlay(client, engine.status, 0xFF5555);
			return true;
		}
		if (BorerFlight.isFlying(player)) {
			engine.enableMeteorFlight(player);
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
			engine.tryTurnAroundLava(client, player, true);
			engine.status = "踩到岩浆，飞离并绕道";
			engine.overlay(client, engine.status, 0xFF5555);
			return true;
		}
		client.options.keyJump.setDown(true);
		if (tryStepOffMagma(client, player)) {
			engine.status = "踩到岩浆，走到安全格";
			engine.overlay(client, engine.status, 0xFFFF55);
			return true;
		}
		engine.tryTurnAroundLava(client, player, true);
		if (engine.place.shouldBridgeDrops(player)) engine.place.placeWalkingSupport(client, player);
		engine.status = "踩到岩浆，正在绕开，不挖岩浆下的方块";
		engine.overlay(client, engine.status, 0xFF5555);
		return true;
	}

	/**
	 * 踩到岩浆块会烫：先潜行停伤，再走到旁边安全地板。
	 * 走不开则继续本 tick 去挖开岩浆块，不再当成「被打了」傻站着。
	 */
	boolean handleMagmaBurn(Minecraft client, LocalPlayer player) {
		if (!BorerHazards.playerOnMagma(client, player)) return false;
		client.options.keyShift.setDown(true);
		if (tryStepOffMagma(client, player)) return true;
		BlockPos feet = player.blockPosition();
		Direction[] exitDirections = {
			engine.forward,
			engine.forward,
			engine.forward.getClockWise(),
			engine.forward.getCounterClockWise()
		};
		BlockPos[] exits = {
			feet.relative(engine.forward),
			feet.relative(engine.forward).above(),
			feet.relative(engine.forward.getClockWise()),
			feet.relative(engine.forward.getCounterClockWise())
		};
		for (int i = 0; i < exits.length; i++) {
			BlockPos pos = exits[i];
			if (!BorerHazards.isMagma(client, pos) || !engine.canPlanMine(client, pos) || !engine.inMiningReach(player, pos)) continue;
			engine.forward = exitDirections[i];
			engine.setMiningTarget(client, player, pos, "magma-exit");
			client.options.keyUp.setDown(false);
			engine.status = "脚下岩浆块，潜行并挖开离开 " + BorerText.block(pos);
			engine.overlay(client, engine.status, 0xFFFF55);
			return false;
		}
		if (engine.enableMeteorFlight(player)) {
			client.options.keyJump.setDown(true);
			client.options.keyUp.setDown(false);
			engine.status = "脚下岩浆块，飞行离开";
			engine.overlay(client, engine.status, 0xFFFF55);
			return true;
		}
		engine.status = "脚下岩浆块，已潜行停烫，正在找路离开";
		engine.overlay(client, engine.status, 0xFFFF55);
		return false;
	}

	/** 尝试从岩浆块上下来。 */
	private boolean tryStepOffMagma(Minecraft client, LocalPlayer player) {
		BlockPos feet = player.blockPosition();
		Direction[] dirs = {engine.forward, engine.forward.getClockWise(), engine.forward.getCounterClockWise(), engine.forward.getOpposite()};
		for (Direction dir : dirs) {
			BlockPos next = feet.relative(dir);
			BlockPos floor = next.below();
			if (engine.isLava(client, next) || engine.isLava(client, floor) || BorerHazards.isMagma(client, floor)) continue;
			if (!BorerFlight.isFlying(player) && !engine.isStandable(client, floor)) continue;
			if (engine.hasCollision(client, next) && !engine.isReplaceable(client, next)) continue;
			if (dir != engine.forward) {
				engine.clearMiningTarget(client, "step-off-magma-turn");
				boolean clockwise = dir == engine.forward.getClockWise();
				engine.forward = dir;
				engine.lastTurnClockwise = clockwise;
				engine.turnCooldown = DefaultTunnelBorerEngine.LAVA_TURN_COOLDOWN_TICKS;
				engine.turnedThisTick = true;
			}
			engine.releaseMine(client);
			client.options.keyShift.setDown(true);
			client.options.keyUp.setDown(true);
			engine.attemptedForward = true;
			engine.status = "脚下岩浆块，潜行走开 " + BorerText.direction(dir);
			engine.overlay(client, engine.status, 0x55FFFF);
			return true;
		}
		return false;
	}

	/** 当前 1×2 通道或锁定矿石贴着岩浆：继续挖会把岩浆留下来，应绕开。墙后岩浆不算。 */
	private BlockPos blockingCurrentRoute(Minecraft client, LocalPlayer player) {
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		if (goal != null) {
			BlockPos opened = BorerHazards.lavaOpenedByMining(client, goal);
			if (opened != null) return opened;
			opened = BorerHazards.waterOpenedByMining(client, goal);
			if (opened != null) return opened;
		}
		BlockPos feet = engine.standingColumn(client, player);
		int height = engine.effectiveHeight();
		for (int dist = 0; dist <= 1; dist++) {
			for (int dy = 0; dy < height; dy++) {
				BlockPos pos = engine.offset(feet, dist, 0, dy);
				BlockPos opened = atOrOpenedBy(client, pos);
				if (opened != null) return opened;
			}
		}
		return null;
	}

	/**
	 * 沿通往矿脉的 1×2 通道提前扫已加载区块里的岩浆/水。
	 * 能侧向绕开就改朝向；绕不开才跳过这颗矿。封口仍由 findHazard 兜底。
	 */
	boolean skipOrDetour(Minecraft client, LocalPlayer player) {
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		if (goal == null) return false;
		BlockPos from = engine.standingColumn(client, player);
		BlockPos immediate = blockingCurrentRoute(client, player);
		BlockPos onPath = onTunnelLine(client, from, goal, DefaultTunnelBorerEngine.LAVA_LOOK_BLOCKS);
		BlockPos liquid = immediate != null ? immediate : onPath;
		if (engine.liquidDetourPos != null) {
			boolean arrived = from.distManhattan(engine.liquidDetourPos) <= 1;
			boolean pathClear = onPath == null;
			if (arrived || pathClear) {
				engine.liquidDetourPos = null;
			} else {
				engine.status = "前方液体，绕行 " + BorerText.block(engine.liquidDetourPos);
				engine.overlay(client, engine.status, 0xFFFF55);
				return false;
			}
		}
		if (liquid == null) return false;
		BlockPos via = pickDryDetour(client, from, goal);
		if (via != null) {
			engine.liquidDetourPos = via;
			engine.lockHeadingToward(from, via);
			engine.status = "前方液体 " + BorerText.block(liquid) + "，改绕 " + BorerText.block(via);
			engine.overlay(client, engine.status, 0xFFFF55);
			engine.fileLog(client, "liquid-detour liquid=" + BorerText.block(liquid) + " via=" + BorerText.block(via)
				+ " goal=" + BorerText.block(goal) + " player=" + BorerText.precise(player));
			engine.releaseMine(client);
			engine.clearMiningTarget(client, "liquid-detour");
			return false;
		}
		String kind = BorerHazards.isLavaFluid(client, liquid) || BorerHazards.lavaOpenedByMining(client, liquid) != null
			? "岩浆" : "水";
		return engine.ores.skipActive(client, kind + " " + BorerText.block(liquid) + " 挡住通往矿脉的通路，提前改挖别处");
	}

	/** 选一条干绕路点。 */
	private BlockPos pickDryDetour(Minecraft client, BlockPos from, BlockPos goal) {
		int dx = goal.getX() - from.getX();
		int dz = goal.getZ() - from.getZ();
		Direction along;
		if (Math.abs(dx) > Math.abs(dz)) along = dx >= 0 ? Direction.EAST : Direction.WEST;
		else if (dz != 0) along = dz >= 0 ? Direction.SOUTH : Direction.NORTH;
		else return null;
		Direction right = along.getClockWise();
		int[] sides = {1, -1, 2, -2, 3, -3, 4, -4};
		int[] aheads = {6, 8, 10};
		for (int side : sides) {
			for (int ahead : aheads) {
				BlockPos via = from.relative(right, side).relative(along, ahead);
				if (!client.level.hasChunkAt(via)) continue;
				if (inStandColumn(client, via) != null) continue;
				if (onTunnelLine(client, from, via, ahead + Math.abs(side)) != null) continue;
				return via.immutable();
			}
		}
		return null;
	}

	/** 沿巷道线推进若干步。 */
	private BlockPos onTunnelLine(Minecraft client, BlockPos from, BlockPos to, int maxSteps) {
		int gx = to.getX() - from.getX();
		int gz = to.getZ() - from.getZ();
		int steps = Math.max(Math.abs(gx), Math.abs(gz));
		if (steps <= 0) return inStandColumn(client, from);
		steps = Math.min(steps, Math.max(1, maxSteps));
		for (int i = 1; i <= steps; i++) {
			int x = from.getX() + gx * i / steps;
			int z = from.getZ() + gz * i / steps;
			BlockPos col = new BlockPos(x, from.getY(), z);
			if (!client.level.hasChunkAt(col)) continue;
			BlockPos hit = inStandColumn(client, col);
			if (hit != null) return hit;
		}
		return null;
	}

	/** 在立足柱内找液体或挖开会露出的液体。 */
	private BlockPos inStandColumn(Minecraft client, BlockPos feet) {
		for (BlockPos pos : new BlockPos[]{feet.below(), feet, feet.above()}) {
			BlockPos found = atOrOpenedBy(client, pos);
			if (found != null) return found;
		}
		return null;
	}

	/** 该格是液体，或挖开后会露出的液体；可替换格返回 null。 */
	private BlockPos atOrOpenedBy(Minecraft client, BlockPos pos) {
		if (BorerHazards.isLavaFluid(client, pos) || BorerHazards.isWater(client, pos)) return pos.immutable();
		if (engine.isReplaceable(client, pos)) return null;
		BlockPos opened = BorerHazards.lavaOpenedByMining(client, pos);
		if (opened != null) return opened;
		return BorerHazards.waterOpenedByMining(client, pos);
	}

	/** 液体格是否够得着且视线通。 */
	private boolean visible(Minecraft client, LocalPlayer player, BlockPos pos) {
		return engine.inMiningReach(player, pos) && BorerHazards.canSeeLiquid(client, player, pos);
	}
}
