package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.HashSet;
import java.util.Set;

/** 区域挖：1×1 竖井逐格往下，到底后飞行换下一格。 */
final class BorerArea {
	private final DefaultTunnelBorerEngine engine;

	final BorerAreaThink think;
	private final Set<Long> completedShafts = new HashSet<>();
	private final Set<Long> skippedShafts = new HashSet<>();
	private BorerAreaShaftPolicy.Phase phase = BorerAreaShaftPolicy.Phase.POSITION_TOP;
	private BlockPos pendingShaftColumn;
	private int snakeStartX;
	private int snakeStartZ;
	private boolean snakeInitialized;
	private boolean initialHighTransfer;
	private int positionStuckTicks;
	private double lastPositionX = Double.NaN;
	private double lastPositionZ = Double.NaN;

	BorerArea(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
		this.think = new BorerAreaThink(engine, this);
	}

	/** 清空区域挖状态。 */
	void reset() {
		engine.areaRunner.reset();
		phase = BorerAreaShaftPolicy.Phase.POSITION_TOP;
		pendingShaftColumn = null;
		completedShafts.clear();
		skippedShafts.clear();
		snakeInitialized = false;
		initialHighTransfer = false;
		positionStuckTicks = 0;
		lastPositionX = Double.NaN;
		lastPositionZ = Double.NaN;
		engine.resetSteer();
		think.reset();
	}

	/** 当前是否允许开想想。 */
	boolean allowThink() {
		return BorerAreaShaftPolicy.allowThink(phase, engine.frontOccluded);
	}

	/** 当前阶段是否允许该想想招。 */
	boolean allowThinkMove(BorerAreaThinkPolicy.Move move) {
		if (!allowThink() || move == null) return false;
		return move == BorerAreaThinkPolicy.Move.MINE_LOOKED
			|| move == BorerAreaThinkPolicy.Move.MINE_FRONT
			|| move == BorerAreaThinkPolicy.Move.RELEASE_FORWARD
			|| move == BorerAreaThinkPolicy.Move.DESCEND;
	}

	/** 附近液体是否由本模块自行处理。 */
	boolean handleNearbyLiquid(BlockPos liquid) {
		return BorerAreaShaftPolicy.handleNearbyLiquid(phase, liquid, engine.areaShaftColumn);
	}

	/** 路线外沾水是否忽略（不逃生）。 */
	boolean ignoreWaterContactOutsideRoute(BlockPos feet) {
		return phase != BorerAreaShaftPolicy.Phase.DIG_DOWN;
	}

	/** 是否当前正在挖的竖井柱。 */
	boolean isCurrentShaftColumn(BlockPos pos) {
		return BorerAreaShaftPolicy.sameColumn(pos, engine.areaShaftColumn);
	}

	/** 诊断用短状态。 */
	String diagnosticState() {
		return phase.name()
			+ ":current=" + columnLabel(engine.areaShaftColumn)
			+ ",next=" + columnLabel(pendingShaftColumn)
			+ ",done=" + completedShafts.size()
			+ ",skipped=" + skippedShafts.size();
	}

	/** 下一挖矿/换井目标。 */
	BlockPos nextTarget(Minecraft client, LocalPlayer player) {
		if (engine.areaMin == null || engine.areaMax == null) return null;
		ensureShaftColumn(client, player);
		int topY = engine.areaMax.getY();
		int bottomY = BorerAreaPolicy.shaftBottomY(engine.areaBoundedDown, engine.areaMin.getY());
		int colX = engine.areaShaftColumn.getX();
		int colZ = engine.areaShaftColumn.getZ();
		BlockPos feet = player.blockPosition();
		if (phase == BorerAreaShaftPolicy.Phase.POSITION_TOP
			|| phase == BorerAreaShaftPolicy.Phase.ASCEND_CURRENT) {
			return ascendObstruction(client, player, colX, colZ, topY, bottomY);
		}
		if (phase == BorerAreaShaftPolicy.Phase.TRANSFER_TOP) {
			return transferObstruction(client, player, colX, colZ, topY, bottomY);
		}
		engine.areaRelocating = false;
		if (!BorerAreaPolicy.sameShaftColumn(feet.getX(), feet.getZ(), colX, colZ)) return null;

		BlockPos jammed = engine.findMovementBlocker(client, player);
		if (jammed != null && inShaft(jammed, colX, colZ) && engine.canPlanMine(client, jammed)) {
			think.cancelMove();
			return jammed;
		}

		BlockPos target = findShaftBlock(client, player, colX, colZ, topY, bottomY);
		if (target != null) {
			think.cancelMove();
			engine.frontOccluded = false;
			return target;
		}
		BlockPos looked = lookedShaftBlock(client, player, colX, colZ, topY, bottomY);
		if (looked != null) {
			think.cancelMove();
			engine.frontOccluded = false;
			return looked;
		}

		boolean hasBlocks = columnHasBlocks(client, colX, colZ, topY, bottomY);
		boolean openBelow = !engine.hasCollision(client, feet.below());
		if (BorerAreaShaftPolicy.shouldDescend(true, feet.getY(), bottomY, openBelow)) {
			engine.frontOccluded = false;
			return null;
		}
		engine.frontOccluded = hasBlocks;
		return null;
	}

	/** 处理危险；已接管返回 true。 */
	boolean handleHazard(Minecraft client, LocalPlayer player, boolean blocked) {
		if (player == null) return false;
		if (engine.areaMin != null && engine.areaMax != null) {
			ensureShaftColumn(client, player);
		}
		if (!allowThink()) return false;
		if (blocked) think.nudgeStuck();
		think.note(client, player);
		return think.handle(client, player);
	}

	/** 推进区域挖移动/挖掘。 */
	void handleMove(Minecraft client, LocalPlayer player) {
		if (engine.areaMin == null || engine.areaMax == null) return;
		ensureShaftColumn(client, player);
		int topY = engine.areaMax.getY();
		int bottomY = BorerAreaPolicy.shaftBottomY(engine.areaBoundedDown, engine.areaMin.getY());
		int colX = engine.areaShaftColumn.getX();
		int colZ = engine.areaShaftColumn.getZ();
		BlockPos feet = player.blockPosition();
		if (phase == BorerAreaShaftPolicy.Phase.POSITION_TOP) {
			handlePosition(client, player, colX, colZ, topY);
			return;
		}
		if (phase == BorerAreaShaftPolicy.Phase.ASCEND_CURRENT) {
			handleAscend(client, player, colX, colZ, topY);
			return;
		}
		if (phase == BorerAreaShaftPolicy.Phase.TRANSFER_TOP) {
			handleTransfer(client, player, colX, colZ, topY);
			return;
		}
		engine.areaRelocating = false;
		if (!BorerAreaPolicy.sameShaftColumn(feet.getX(), feet.getZ(), colX, colZ)) {
			releaseMoveKeys(client);
			engine.enableMeteorFlight(player);
			engine.centerOnShaftColumn(client, player, true);
			engine.status = "回到当前 1×1 格心再继续往下挖";
			engine.overlay(client, engine.status, 0xFFFF55);
			return;
		}
		if (simpleShaftDown(client, player)) {
			if (tryDescendShaft(client, player, colX, colZ, bottomY, feet)) return;
			BlockPos below = feet.below();
			if (below.getY() >= bottomY && engine.canPlanMine(client, below) && engine.hasCollision(client, below)) {
				engine.setMiningTarget(client, player, below, "area-shaft-below");
				releaseMoveKeys(client);
				engine.status = "竖井往下挖 " + BorerText.block(below);
				engine.overlay(client, engine.status, 0x55FFFF);
				return;
			}
		} else if (allowThink()) {
			think.note(client, player);
			if (think.handle(client, player)) return;
		}

		if (tryDescendShaft(client, player, colX, colZ, bottomY, feet)) return;
		BlockPos unmineable = unmineableSupport(client, feet, colX, colZ, bottomY);
		if (unmineable != null) {
			if (skipCurrentShaft(client, unmineable, "unmineable-support")) {
				engine.status = "当前 1×1 遇到不可挖方块，已记录并沿原井返顶";
				engine.overlay(client, engine.status, 0xFFFF55);
			}
			return;
		}

		if (engine.frontOccluded) {
			engine.occludedTicks++;
			releaseMoveKeys(client);
			engine.status = "这口 1×1 还有方块，但当前没有可挖视线，已原地等待";
			if (engine.occludedTicks >= DefaultTunnelBorerEngine.ROUTE_TIMEOUT_TICKS) {
				engine.stop(client, "区域竖井被遮挡，已释放手动挖掘");
			}
			return;
		}
		engine.occludedTicks = 0;

		boolean hasBlocks = columnHasBlocks(client, colX, colZ, topY, bottomY);
		if (BorerAreaShaftPolicy.shaftComplete(engine.areaBoundedDown, feet.getY(), bottomY, hasBlocks)) {
			advanceShaft(client, colX, colZ, topY);
			return;
		}
		engine.areaStallTicks = 0;

		if (hasBlocks) engine.frontOccluded = true;
	}

	boolean tryDescendShaft(
		Minecraft client, LocalPlayer player, int colX, int colZ, int bottomY, BlockPos feet
	) {
		boolean openBelow = !engine.hasCollision(client, feet.below());
		if (!BorerAreaShaftPolicy.shouldDescend(
			BorerAreaPolicy.sameShaftColumn(feet.getX(), feet.getZ(), colX, colZ),
			feet.getY(), bottomY, openBelow)) {
			return false;
		}
		engine.frontOccluded = false;
		think.cancelMove();
		if (engine.centerOnShaftColumn(client, player, true)) {
			client.options.keyShift.setDown(false);
			engine.status = "先对准 1×1 格心，再垂直下潜";
			engine.overlay(client, engine.status, 0xFFFF55);
			return true;
		}
		engine.fallDown(client, player, "竖井下层还有方块，下去挖");
		return true;
	}

	/** 简单竖井下挖一步。 */
	boolean simpleShaftDown(Minecraft client, LocalPlayer player) {
		if (phase != BorerAreaShaftPolicy.Phase.DIG_DOWN
			|| player == null || engine.areaShaftColumn == null || engine.areaMax == null) return false;
		BlockPos feet = player.blockPosition();
		int colX = engine.areaShaftColumn.getX();
		int colZ = engine.areaShaftColumn.getZ();
		int topY = engine.areaMax.getY();
		int bottomY = BorerAreaPolicy.shaftBottomY(engine.areaBoundedDown, engine.areaMin.getY());
		boolean same = BorerAreaPolicy.sameShaftColumn(feet.getX(), feet.getZ(), colX, colZ);
		boolean remaining = columnHasBlocks(client, colX, colZ, feet.getY() - 1, bottomY);
		boolean openBelow = !engine.hasCollision(client, feet.below());
		boolean mine = findShaftBlock(client, player, colX, colZ, topY, bottomY) != null;
		return BorerAreaPolicy.skipThinkForSimpleDown(
			same, BorerAreaPolicy.aboveMarkedTop(feet.getY(), topY), remaining, openBelow, mine);
	}

	/** 确保当前竖井柱已选定。 */
	void ensureShaftColumn(Minecraft client, LocalPlayer player) {
		if (engine.areaShaftColumn != null) return;
		BlockPos feet = player.blockPosition();
		int px = BorerAreaPolicy.clampToRange(feet.getX(), engine.areaMin.getX(), engine.areaMax.getX());
		int pz = BorerAreaPolicy.clampToRange(feet.getZ(), engine.areaMin.getZ(), engine.areaMax.getZ());
		boolean nearestOrder = BorerAreaPolicy.useNearestOrder(engine.host.borerAreaOrder());
		BlockPos firstShaft = nearestOrder
			? new BlockPos(px, 0, pz)
			: BorerAreaShaftPolicy.nearestCorner(
				feet.getX(), feet.getZ(), engine.areaMin.getX(), engine.areaMin.getZ(),
				engine.areaMax.getX(), engine.areaMax.getZ());
		snakeStartX = firstShaft.getX();
		snakeStartZ = firstShaft.getZ();
		snakeInitialized = !nearestOrder;
		// 先从人物当前列垂直升到区域顶；地下时不能为了远处角点在原地盲跳撞天花板。
		BlockPos entry = new BlockPos(feet.getX(), 0, feet.getZ());
		engine.areaShaftColumn = entry;
		phase = BorerAreaShaftPolicy.Phase.POSITION_TOP;
		pendingShaftColumn = firstShaft;
		initialHighTransfer = false;
		engine.areaRelocating = true;
		engine.resetSteer();
		engine.fileLog(client, "area-shaft-start entry=" + entry.getX() + "," + entry.getZ()
			+ " first=" + firstShaft.getX() + "," + firstShaft.getZ()
			+ " phase=" + phase
			+ " order=" + BorerAreaPolicy.normalizeOrder(engine.host.borerAreaOrder()));
	}

	/** 推进当前竖井流程。 */
	boolean advanceShaft(Minecraft client, int colX, int colZ, int topY) {
		int bottomY = BorerAreaPolicy.shaftBottomY(engine.areaBoundedDown, engine.areaMin.getY());
		BlockPos feet = client.player == null ? new BlockPos(colX, 0, colZ) : client.player.blockPosition();
		boolean hasBlocks = columnHasBlocks(client, colX, colZ, topY, bottomY);
		if (!BorerAreaShaftPolicy.shaftComplete(engine.areaBoundedDown, feet.getY(), bottomY, hasBlocks)) {
			engine.fileLog(client, "area-shaft-advance-reject col=" + colX + "," + colZ
				+ " feetY=" + feet.getY() + " bottomY=" + bottomY + " blocks=" + hasBlocks
				+ " phase=" + phase);
			return false;
		}
		return beginNextShaft(client, colX, colZ, topY, "complete");
	}

	/** 跳过当前井并记原因。 */
	boolean skipCurrentShaft(Minecraft client, BlockPos obstacle, String reason) {
		if (engine.areaShaftColumn == null || engine.areaMax == null
			|| !BorerAreaShaftPolicy.allowSkip(phase, obstacle, engine.areaShaftColumn)) {
			engine.fileLog(client, "area-column-skip-reject reason=" + reason
				+ " obstacle=" + columnLabel(obstacle)
				+ " state=" + diagnosticState());
			return false;
		}
		skippedShafts.add(columnKey(engine.areaShaftColumn.getX(), engine.areaShaftColumn.getZ()));
		return beginNextShaft(client, engine.areaShaftColumn.getX(), engine.areaShaftColumn.getZ(),
			engine.areaMax.getY(), "skip-" + (reason == null ? "hazard" : reason));
	}

	/** 开始下一口竖井。 */
	private boolean beginNextShaft(Minecraft client, int colX, int colZ, int topY, String reason) {
		BlockPos feet = client.player == null ? new BlockPos(colX, 0, colZ) : client.player.blockPosition();
		completedShafts.add(columnKey(colX, colZ));
		BlockPos next = nextRemainingShaft(feet.getX(), feet.getZ(), colX, colZ);
		if (next == null) {
			engine.fileLog(client, "area-shaft-advance none remaining after=" + colX + "," + colZ
				+ " bounds=" + engine.areaMin.getX() + "," + engine.areaMin.getZ()
				+ ".." + engine.areaMax.getX() + "," + engine.areaMax.getZ());
			engine.stop(client, skippedShafts.isEmpty()
				? "区域 1×1 竖井已全部挖完"
				: "区域逐列已结束；" + skippedShafts.size() + " 口因液体或不可挖方块跳过");
			return false;
		}
		pendingShaftColumn = next;
		phase = BorerAreaShaftPolicy.Phase.ASCEND_CURRENT;
		initialHighTransfer = false;
		engine.areaRelocating = true;
		engine.resetSteer();
		think.cancelMove();
		engine.releaseMine(client);
		engine.clearMiningTarget(client, "area-column-" + reason);
		releaseMoveKeys(client);
		double horiz = Math.hypot(next.getX() + 0.5 - feet.getX(), next.getZ() + 0.5 - feet.getZ());
		engine.status = "这口 1×1 已到底，先沿原井飞回顶部";
		engine.overlay(client, engine.status, 0x55FFFF);
		engine.fileLog(client, "area-column-done reason=" + reason + " from=" + colX + "," + colZ
			+ " to=" + next.getX() + "," + next.getZ()
			+ " dist=" + String.format(java.util.Locale.ROOT, "%.1f", horiz)
			+ " phase=" + phase + " completed=" + completedShafts.size()
			+ " order=" + BorerAreaPolicy.normalizeOrder(engine.host.borerAreaOrder()));
		think.onShaftDone(client, client.player);
		return true;
	}

	/** 按顺序选下一未挖完柱。 */
	private BlockPos nextRemainingShaft(int px, int pz, int currentX, int currentZ) {
		int minX = engine.areaMin.getX();
		int minZ = engine.areaMin.getZ();
		int maxX = engine.areaMax.getX();
		int maxZ = engine.areaMax.getZ();
		boolean nearestOrder = BorerAreaPolicy.useNearestOrder(engine.host.borerAreaOrder());
		if (!nearestOrder) {
			if (!snakeInitialized) return null;
			int total = Math.max(1, (maxX - minX + 1) * (maxZ - minZ + 1));
			BlockPos cursor = new BlockPos(currentX, 0, currentZ);
			for (int i = 0; i < total; i++) {
				BlockPos next = BorerAreaShaftPolicy.nextSnakeColumn(
					cursor.getX(), cursor.getZ(), minX, minZ, maxX, maxZ,
					snakeStartX, snakeStartZ);
				if (next == null) return null;
				cursor = next;
				if (!completedShafts.contains(columnKey(cursor.getX(), cursor.getZ()))) return cursor;
			}
			return null;
		}
		BlockPos best = null;
		for (int x = minX; x <= maxX; x++) {
			for (int z = minZ; z <= maxZ; z++) {
				if (completedShafts.contains(columnKey(x, z))) continue;
				if (best == null) {
					best = new BlockPos(x, 0, z);
					continue;
				}
				if (BorerAreaPolicy.closerShaft(px, pz, x, z, best.getX(), best.getZ())) {
					best = new BlockPos(x, 0, z);
				}
			}
		}
		return best;
	}

	/** 就位阶段：飞到井口对准。 */
	private void handlePosition(Minecraft client, LocalPlayer player, int colX, int colZ, int topY) {
		think.cancelMove();
		engine.enableMeteorFlight(player);
		engine.releaseMine(client);
		releaseMoveKeys(client);
		if (!BorerAreaShaftPolicy.centered(player.getX(), player.getZ(), colX, colZ)) {
			double curDx = player.getX() - lastPositionX;
			double curDz = player.getZ() - lastPositionZ;
			if (!Double.isNaN(lastPositionX) && Math.abs(curDx) < 0.01 && Math.abs(curDz) < 0.01) {
				positionStuckTicks++;
			} else {
				positionStuckTicks = 0;
			}
			lastPositionX = player.getX();
			lastPositionZ = player.getZ();
			if (positionStuckTicks > 40) {
				engine.fileLog(client, "area-position-stuck y=" + String.format(java.util.Locale.ROOT, "%.3f", player.getY()));
				if (BorerAreaShaftPolicy.belowTransferHeight(player.getY(), topY)) {
					tuneVerticalFlight(client, player, topY);
					client.options.keyJump.setDown(true);
					engine.status = "卡住了，垂直上升脱困 Y" + BorerAreaShaftPolicy.transferFeetY(topY);
					engine.overlay(client, engine.status, 0xFFFF55);
					return;
				}
				double dx = (colX + 0.5) - player.getX();
				double dz = (colZ + 0.5) - player.getZ();
				BlockPos feet = player.blockPosition();
				int mineX = feet.getX();
				int mineZ = feet.getZ();
				if (Math.abs(dx) > Math.abs(dz)) {
					mineX += dx > 0 ? 1 : -1;
				} else {
					mineZ += dz > 0 ? 1 : -1;
				}
				BlockPos target = new BlockPos(mineX, feet.getY(), mineZ);
				engine.setMiningTarget(client, player, target, "area-position-stuck");
				engine.status = "卡住了，挖开挡路方块 " + target.getX() + " " + target.getY() + " " + target.getZ();
				engine.overlay(client, engine.status, 0xFFFF55);
				return;
			}
			engine.centerOnShaftColumn(client, player, true);
			engine.status = "进区域前先对准当前格心";
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		positionStuckTicks = 0;
		lastPositionX = Double.NaN;
		lastPositionZ = Double.NaN;
		if (BorerAreaShaftPolicy.belowTransferHeight(player.getY(), topY)) {
			tuneVerticalFlight(client, player, topY);
			client.options.keyJump.setDown(true);
			engine.status = "从当前列垂直升到区域顶部 Y" + BorerAreaShaftPolicy.transferFeetY(topY);
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		if (pendingShaftColumn == null) {
			engine.stop(client, "区域首列状态丢失，已安全停止");
			return;
		}
		initialHighTransfer = BorerAreaShaftPolicy.aboveTransferHeight(player.getY(), topY);
		BlockPos entry = engine.areaShaftColumn;
		engine.areaShaftColumn = pendingShaftColumn;
		phase = BorerAreaShaftPolicy.Phase.TRANSFER_TOP;
		engine.resetSteer();
		engine.fileLog(client, "area-entry-top entry=" + columnLabel(entry)
			+ " first=" + columnLabel(pendingShaftColumn)
			+ " high=" + initialHighTransfer
			+ " y=" + String.format(java.util.Locale.ROOT, "%.3f", player.getY()));
	}

	/** 上升阶段：飞到换井高度。 */
	private void handleAscend(Minecraft client, LocalPlayer player, int colX, int colZ, int topY) {
		think.cancelMove();
		engine.enableMeteorFlight(player);
		engine.releaseMine(client);
		releaseMoveKeys(client);
		if (!BorerAreaShaftPolicy.centered(player.getX(), player.getZ(), colX, colZ)) {
			engine.centerOnShaftColumn(client, player, true);
			engine.status = "原井返顶：先对准格心";
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		if (BorerAreaShaftPolicy.belowTransferHeight(player.getY(), topY)) {
			tuneVerticalFlight(client, player, topY);
			client.options.keyJump.setDown(true);
			engine.status = "沿原 1×1 竖井垂直飞回 Y" + BorerAreaShaftPolicy.transferFeetY(topY);
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		if (BorerAreaShaftPolicy.aboveTransferHeight(player.getY(), topY)) {
			tuneVerticalFlight(client, player, topY);
			client.options.keyShift.setDown(true);
			engine.status = "原井返顶：校准顶部高度 Y" + BorerAreaShaftPolicy.transferFeetY(topY);
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		if (pendingShaftColumn == null) {
			engine.stop(client, "区域换井状态丢失，已安全停止");
			return;
		}
		BlockPos from = engine.areaShaftColumn;
		engine.areaShaftColumn = pendingShaftColumn;
		phase = BorerAreaShaftPolicy.Phase.TRANSFER_TOP;
		initialHighTransfer = false;
		engine.resetSteer();
		engine.fileLog(client, "area-return-top from=" + columnLabel(from)
			+ " next=" + columnLabel(pendingShaftColumn)
			+ " y=" + String.format(java.util.Locale.ROOT, "%.3f", player.getY())
			+ " phase=" + phase);
		engine.status = "已回到顶部，开始平移到旁边 1×1";
		engine.overlay(client, engine.status, 0x55FFFF);
	}

	/** 平移阶段：飞向下一井。 */
	private void handleTransfer(Minecraft client, LocalPlayer player, int colX, int colZ, int topY) {
		think.cancelMove();
		engine.enableMeteorFlight(player);
		engine.releaseMine(client);
		releaseMoveKeys(client);
		double dx = colX + 0.5 - player.getX();
		double dz = colZ + 0.5 - player.getZ();
		double horiz = Math.hypot(dx, dz);
		if (BorerAreaShaftPolicy.belowTransferHeight(player.getY(), topY)) {
			tuneVerticalFlight(client, player, topY);
			client.options.keyJump.setDown(true);
			engine.status = "先垂直升到换井高度 Y" + BorerAreaShaftPolicy.transferFeetY(topY);
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		// 第一次进区域时若人在高处，先保持高度飞到目标列，不能在区域外原地往下钻。
		if (BorerAreaShaftPolicy.aboveTransferHeight(player.getY(), topY)
			&& (!initialHighTransfer || horiz <= 0.45)) {
			tuneVerticalFlight(client, player, topY);
			client.options.keyShift.setDown(true);
			engine.status = "校准换井高度 Y" + BorerAreaShaftPolicy.transferFeetY(topY);
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		BlockPos dest = new BlockPos(colX, BorerAreaShaftPolicy.transferFeetY(topY), colZ);
		if (horiz > 0.45) {
			if (horiz <= 1.75) BorerFlight.slowForPrecision(client);
			else BorerFlight.restoreSpeed(client);
			engine.lockHeadingToward(player.blockPosition(), dest);
			RotationAim.apply(player, RotationAim.lookAt(player,
				new Vec3(colX + 0.5, player.getEyeY(), colZ + 0.5)));
			client.options.keyUp.setDown(true);
			engine.attemptedForward = true;
			engine.status = "在顶部水平飞到旁边 1×1 " + BorerText.block(dest);
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		if (engine.centerOnShaftColumn(client, player, true)) {
			engine.status = "对准下一口 1×1 格心";
			engine.overlay(client, engine.status, 0x55FFFF);
			return;
		}
		phase = BorerAreaShaftPolicy.Phase.DIG_DOWN;
		pendingShaftColumn = null;
		initialHighTransfer = false;
		engine.areaRelocating = false;
		engine.resetSteer();
		releaseMoveKeys(client);
		engine.fileLog(client, "area-next-column col=" + colX + "," + colZ
			+ " y=" + String.format(java.util.Locale.ROOT, "%.3f", player.getY())
			+ " phase=" + phase + " completed=" + completedShafts.size());
		engine.status = "已对准，开始垂直挖这口 1×1";
		engine.overlay(client, engine.status, 0x55FFFF);
	}

	/** 上升阶段柱内挡路可挖块。 */
	private BlockPos ascendObstruction(
		Minecraft client, LocalPlayer player, int colX, int colZ, int topY, int bottomY
	) {
		int fromY = Math.max(bottomY, player.blockPosition().getY());
		int toY = Math.min(BorerAreaShaftPolicy.transferFeetY(topY) + 1, fromY + 3);
		for (int y = fromY; y <= toY; y++) {
			BlockPos pos = new BlockPos(colX, y, colZ);
			if (phaseMineable(client, player, pos, topY, bottomY)) return pos;
		}
		return null;
	}

	/** 换井阶段脚/头层挡路可挖块。 */
	private BlockPos transferObstruction(
		Minecraft client, LocalPlayer player, int colX, int colZ, int topY, int bottomY
	) {
		double horiz = Math.hypot(colX + 0.5 - player.getX(), colZ + 0.5 - player.getZ());
		if (horiz > 1.75) return null;
		int transferY = BorerAreaShaftPolicy.transferFeetY(topY);
		BlockPos feet = new BlockPos(colX, transferY, colZ);
		if (phaseMineable(client, player, feet, topY, bottomY)) return feet;
		BlockPos head = feet.above();
		if (phaseMineable(client, player, head, topY, bottomY)) return head;
		return null;
	}

	/** 当前阶段下该格是否够得着且可挖挡路。 */
	private boolean phaseMineable(
		Minecraft client, LocalPlayer player, BlockPos pos, int topY, int bottomY
	) {
		return allowsMiningTarget(pos)
			&& engine.inMiningReach(player, pos)
			&& engine.canMineFlightObstruction(client, pos)
			&& engine.hasCollision(client, pos);
	}

	/** 脚下不可挖的支撑块（卡井底用）。 */
	private BlockPos unmineableSupport(
		Minecraft client, BlockPos feet, int colX, int colZ, int bottomY
	) {
		if (feet.getY() <= bottomY) return null;
		BlockPos below = feet.below();
		if (!inShaft(below, colX, colZ) || !engine.hasCollision(client, below)) return null;
		return engine.canSurveyAreaMine(client, below) ? null : below;
	}

	/** 微调垂直飞行键。 */
	private static void tuneVerticalFlight(Minecraft client, LocalPlayer player, int topY) {
		double error = Math.abs(BorerAreaShaftPolicy.transferFeetY(topY) - player.getY());
		if (error <= 2.0) BorerFlight.slowForPrecision(client);
		else BorerFlight.restoreSpeed(client);
	}

	/** 该格是否允许作为挖矿目标。 */
	boolean allowsMiningTarget(BlockPos pos) {
		if (engine.areaShaftColumn == null || engine.areaMax == null || engine.areaMin == null) return false;
		int bottomY = BorerAreaPolicy.shaftBottomY(engine.areaBoundedDown, engine.areaMin.getY());
		return BorerAreaShaftPolicy.allowsMine(
			phase, pos, engine.areaShaftColumn, pendingShaftColumn, engine.areaMax.getY(), bottomY);
	}

	/** XZ 打包成长整型键。 */
	private static long columnKey(int x, int z) {
		return ((long) x << 32) ^ (z & 0xffffffffL);
	}

	/** 柱坐标短标签。 */
	private static String columnLabel(BlockPos pos) {
		return pos == null ? "-" : pos.getX() + "," + pos.getZ();
	}

	/** 松开移动相关键。 */
	private static void releaseMoveKeys(Minecraft client) {
		if (client.options == null) return;
		client.options.keyUp.setDown(false);
		client.options.keyDown.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
	}

	/** 飞向指定竖井顶。 */
	boolean flyToShaft(Minecraft client, LocalPlayer player, int colX, int colZ, int topY) {
		engine.enableMeteorFlight(player);
		BlockPos dest = BorerAreaPolicy.shaftStandPos(colX, colZ, topY);
		BlockPos feet = player.blockPosition();
		double dx = (colX + 0.5) - player.getX();
		double dz = (colZ + 0.5) - player.getZ();
		double horiz = Math.sqrt(dx * dx + dz * dz);
		double dy = topY - player.getY();
		Direction dir = engine.headingToward(feet, dest);
		if (dir == null) dir = engine.forward;
		boolean destBelow = BorerAreaPolicy.destBelow(topY - feet.getY());
		boolean ceilingSolid = engine.hasCollision(client, feet.above(2));
		boolean frontBlocked = dir != null && (engine.hasCollision(client, feet.relative(dir))
			|| engine.hasCollision(client, feet.relative(dir).above()));
		BlockPos destFeet = new BlockPos(colX, feet.getY(), colZ);
		boolean destSolid = engine.hasCollision(client, destFeet)
			|| engine.hasCollision(client, destFeet.above());
		boolean nearby = BorerAreaPolicy.mineAdjacentShaftInsteadOfFly(horiz);
		boolean pathBlocked = frontBlocked || (destSolid && nearby);
		boolean jump = BorerAreaPolicy.flyJump(dy > 0.35, frontBlocked && nearby, ceilingSolid, destBelow);

		client.options.keyAttack.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		engine.lockHeadingToward(feet, dest);
		aimAtShaft(player, dest);

		if (horiz > 0.45) {
			boolean go = BorerAreaPolicy.holdForwardWhileFlying(horiz, pathBlocked && nearby);
			boolean climb = BorerAreaPolicy.flyJump(dy > 0.35 || (frontBlocked && !nearby), false, ceilingSolid, destBelow);
			client.options.keyUp.setDown(go);
			client.options.keyJump.setDown(climb);
			client.options.keyShift.setDown(false);
			engine.attemptedForward = go;
			engine.status = go
				? "开飞行到附近竖井 " + BorerText.block(dest)
				: climb
					? "升高飞过挡路，去竖井 " + BorerText.block(dest)
					: "飞行到竖井 " + BorerText.block(dest);
			engine.overlay(client, engine.status, 0x55FFFF);
			return true;
		}
		client.options.keyUp.setDown(false);
		if (dy > 0.35) {
			client.options.keyJump.setDown(jump);
			client.options.keyShift.setDown(false);
			engine.status = "开飞行升到区域顶 Y" + topY + " " + BorerText.block(dest);
			engine.overlay(client, engine.status, 0x55FFFF);
			return true;
		}
		if (BorerAreaPolicy.sneakDiveToShaft(destBelow, false)) {
			client.options.keyJump.setDown(false);
			client.options.keyShift.setDown(true);
			engine.status = "下潜到竖井顶 Y" + topY;
			engine.overlay(client, engine.status, 0x55FFFF);
			return true;
		}
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
		engine.areaRelocating = false;
		return false;
	}

	/** 换井飞行时再写回朝向。 */
	void reapplyFlyLook(LocalPlayer player) {
		if (player == null || engine.currentTarget != null) return;
		if (!BorerAreaPolicy.lockLookWhileFlyingToShaft(engine.areaRelocating)) return;
		if (engine.areaShaftColumn == null || engine.areaMax == null) return;
		aimAtShaft(player, new BlockPos(
			engine.areaShaftColumn.getX(),
			BorerAreaShaftPolicy.transferFeetY(engine.areaMax.getY()),
			engine.areaShaftColumn.getZ()));
	}

	/** 瞄准竖井站立点。 */
	private static void aimAtShaft(LocalPlayer player, BlockPos dest) {
		double dy = dest.getY() + 0.5 - player.getY();
		double dx = dest.getX() + 0.5 - player.getX();
		double dz = dest.getZ() + 0.5 - player.getZ();
		double horiz = Math.sqrt(dx * dx + dz * dz);
		if (BorerAreaPolicy.destBelow(dy) && horiz > 0.45) {
			RotationAim.apply(player, RotationAim.lookAt(player,
				new Vec3(dest.getX() + 0.5, player.getEyeY(), dest.getZ() + 0.5)));
			return;
		}
		BorerAim.lookAtBlockCenter(player, dest);
	}

	/** 落到井顶时要挖/处理的挡路格。 */
	BlockPos descendToShaftTop(Minecraft client, LocalPlayer player, int colX, int colZ, int topY) {
		BlockPos feet = player.blockPosition();
		if (!BorerAreaPolicy.mineDownToShaftTop(
			BorerAreaPolicy.sameShaftColumn(feet.getX(), feet.getZ(), colX, colZ),
			feet.getY(), topY)) {
			return null;
		}
		BlockPos below = feet.below();
		if (isOverburden(client, player, below, topY)) return below;
		if (isOverburden(client, player, feet, topY)) return feet;
		for (int y = feet.getY(); y > topY; y--) {
			BlockPos pos = new BlockPos(colX, y, colZ);
			if (isOverburden(client, player, pos, topY)) return pos;
		}
		return null;
	}

	/** 是否为井顶以上覆盖层。 */
	private boolean isOverburden(Minecraft client, LocalPlayer player, BlockPos pos, int topY) {
		if (pos == null || pos.getY() <= topY) return false;
		if (!engine.inMiningReach(player, pos)) return false;
		return engine.canMineFlightObstruction(client, pos) && engine.hasCollision(client, pos);
	}

	/** 准星打到的可挖挡路格。 */
	BlockPos lookedMineable(Minecraft client, LocalPlayer player) {
		if (!(client.hitResult instanceof BlockHitResult hit) || hit.getType() != HitResult.Type.BLOCK) {
			return null;
		}
		BlockPos pos = hit.getBlockPos();
		if (!allowsMiningTarget(pos)) return null;
		if (engine.areaShaftColumn != null
			&& !inShaft(pos, engine.areaShaftColumn.getX(), engine.areaShaftColumn.getZ())) {
			return null;
		}
		if (engine.areaShaftColumn != null) {
			double horiz = Math.hypot(
				engine.areaShaftColumn.getX() + 0.5 - player.getX(),
				engine.areaShaftColumn.getZ() + 0.5 - player.getZ());
			if (engine.areaRelocating && !BorerAreaPolicy.mineFlightObstruction(true, true, horiz)) {
				return null;
			}
		}
		if (!engine.inMiningReach(player, pos) && !BorerAim.hitInReach(player, hit)) return null;
		if (!engine.canMineFlightObstruction(client, pos)) return null;
		if (!engine.hasCollision(client, pos)) return null;
		return pos;
	}

	/** 飞向井口路上的挡飞方块。 */
	BlockPos flyObstruction(Minecraft client, LocalPlayer player, int colX, int colZ, int topY) {
		BlockPos dest = BorerAreaPolicy.shaftStandPos(colX, colZ, topY);
		BlockPos feet = player.blockPosition();
		double horiz = Math.hypot((colX + 0.5) - player.getX(), (colZ + 0.5) - player.getZ());
		Direction dir = engine.headingToward(feet, dest);
		if (dir == null) dir = engine.forward;
		BlockPos destFeet = new BlockPos(colX, feet.getY(), colZ);
		BlockPos destHead = destFeet.above();
		BlockPos head = feet.above();
		BlockPos front = dir == null ? feet : feet.relative(dir);
		BlockPos frontHead = front.above();
		BlockPos ceiling = feet.above(2);
		boolean destBelow = BorerAreaPolicy.destBelow(topY - feet.getY());
		boolean ceilingSolid = engine.hasCollision(client, ceiling);
		boolean frontBlocked = dir != null && (engine.hasCollision(client, front) || engine.hasCollision(client, frontHead));

		// 远处：只飞过去，不挖准星/前方开路；卡进方块里才挖自己。
		if (!BorerAreaPolicy.mineFlightObstruction(engine.areaRelocating, true, horiz)) {
			if (isFlightBlocker(client, player, feet, horiz)) return feet;
			if (isFlightBlocker(client, player, head, horiz)) return head;
			if (BorerAreaPolicy.flyOverInsteadOfMine(
				BorerFlight.isFlying(player), frontBlocked, ceilingSolid, destBelow)) {
				return null;
			}
			return null;
		}

		if (client.hitResult instanceof BlockHitResult look
			&& look.getType() == HitResult.Type.BLOCK
			&& isFlightBlocker(client, player, look.getBlockPos(), horiz)) {
			return look.getBlockPos();
		}
		if (isFlightBlocker(client, player, destFeet, horiz)) return destFeet;
		if (isFlightBlocker(client, player, destHead, horiz)) return destHead;
		if (isFlightBlocker(client, player, feet, horiz)) return feet;
		if (isFlightBlocker(client, player, head, horiz)) return head;
		if (isFlightBlocker(client, player, front, horiz)) return front;
		if (isFlightBlocker(client, player, frontHead, horiz)) return frontHead;
		if (!destBelow) {
			if (isFlightBlocker(client, player, ceiling, horiz)) return ceiling;
			if (BorerAreaPolicy.flyOverInsteadOfMine(
				BorerFlight.isFlying(player), frontBlocked, ceilingSolid, destBelow)) {
				return null;
			}
		}
		return null;
	}

	/** 是否挡住换井飞行。 */
	private boolean isFlightBlocker(Minecraft client, LocalPlayer player, BlockPos pos, double horiz) {
		if (pos == null) return false;
		if (!allowsMiningTarget(pos)) return false;
		if (!BorerAreaPolicy.mineFlightObstruction(
			engine.areaRelocating, engine.inMiningReach(player, pos), horiz)) {
			return false;
		}
		return engine.canMineFlightObstruction(client, pos) && engine.hasCollision(client, pos);
	}

	/** 竖井柱内选最优可挖目标。 */
	private BlockPos findShaftBlock(
		Minecraft client, LocalPlayer player, int x, int z, int topY, int bottomY
	) {
		BlockPos feet = player.blockPosition();
		int scanTop = Math.min(topY, feet.getY() + 2);
		BlockPos best = null;
		int bestRank = Integer.MAX_VALUE;
		for (int y = scanTop; y >= bottomY; y--) {
			BlockPos pos = new BlockPos(x, y, z);
			if (!engine.canPlanMine(client, pos)) continue;
			if (!BorerAreaPolicy.acceptShaftMineTarget(engine.inMiningReach(player, pos))) continue;
			boolean stuck = pos.equals(feet) && engine.hasCollision(client, pos);
			if (!stuck && pos.equals(feet)) continue;
			if (!(engine.canSeeBlock(client, player, pos)
				|| engine.playerTouchesBlock(player, pos))) {
				continue;
			}
			int rank = BorerAreaPolicy.shaftMineRank(y);
			if (rank < bestRank) {
				bestRank = rank;
				best = pos;
			}
		}
		return best;
	}

	/** 准星打中的竖井柱内可挖块。 */
	private BlockPos lookedShaftBlock(
		Minecraft client, LocalPlayer player, int x, int z, int topY, int bottomY
	) {
		if (!(client.hitResult instanceof BlockHitResult hit) || hit.getType() != HitResult.Type.BLOCK) {
			return null;
		}
		BlockPos pos = hit.getBlockPos();
		if (!BorerAreaPolicy.mineLookedShaftBlock(inShaft(pos, x, z), engine.canPlanMine(client, pos))) {
			return null;
		}
		if (!BorerAreaPolicy.acceptShaftMineTarget(engine.inMiningReach(player, pos))) return null;
		if (pos.getY() > topY || pos.getY() < bottomY) return null;
		if (pos.equals(player.blockPosition()) && !engine.hasCollision(client, pos)) return null;
		return pos;
	}

	/** 柱在高度范围内是否还有可挖块。 */
	private boolean columnHasBlocks(Minecraft client, int x, int z, int topY, int bottomY) {
		for (int y = topY; y >= bottomY; y--) {
			BlockPos pos = new BlockPos(x, y, z);
			// 必须用 survey：canPlanMine 锁当前井列，扫下一格会全空 → 误停「全部挖完」。
			if (engine.canSurveyAreaMine(client, pos)) return true;
		}
		return false;
	}

	/** 方块是否属于该柱。 */
	private static boolean inShaft(BlockPos pos, int x, int z) {
		return pos.getX() == x && pos.getZ() == z;
	}
}
