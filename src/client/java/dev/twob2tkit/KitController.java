package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.DisconnectedScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.gui.screens.multiplayer.JoinMultiplayerScreen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.world.phys.AABB;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerFlight;
import dev.twob2tkit.runtime.engine.BorerItems;

import java.util.Locale;
import dev.twob2tkit.combat.HealingItems;
import dev.twob2tkit.cruise.CruiseCeilingMiner;
import dev.twob2tkit.cruise.CruiseScreenHud;
import dev.twob2tkit.nether.NetherRoofAssist;

/**
 * 高空巡航：升空、转向前进、绕障、到达/离线。
 * 模拟跳跃/潜行/前进键；飞行靠玩家已开的第三方飞行。
 */
public final class KitController {
	/** 巡航阶段。 */
	private enum Phase {
		IDLE("空闲"),
		ALTITUDE("调整高度"),
		CRUISE("巡航"),
		AVOIDING("绕开障碍");

		private final String label;

		Phase(String label) {
			this.label = label;
		}
	}

	private final KitConfig config;
	private Phase phase = Phase.IDLE;
	private int ticks;
	private int stationarySeconds;
	private double sampleX = Double.NaN;
	private double sampleZ = Double.NaN;
	private double recentSpeed;
	/** 本趟已走水平路程（格），窗口速度与卡住检测仍会用到。 */
	private double traveledDistance;
	/** 开始时起点到目标的直线距离（格），全程固定不跳动。 */
	private double plannedDistance;
	private double trackX = Double.NaN;
	private double trackZ = Double.NaN;
	private boolean hasTrackSample;
	/** 近段每秒位移环，用来估当前巡航速度（避免全程均速被前期拉高）。 */
	private static final int SPEED_WINDOW_SECONDS = 30;
	private final double[] recentMoved = new double[SPEED_WINDOW_SECONDS];
	private int recentMovedCount;
	private int recentMovedIndex;
	private double windowMovedSum;
	/** 平滑倒计时秒数；&lt;0 表示尚未就绪。 */
	private long etaDisplaySeconds = -1;
	private boolean avoidanceActive;
	private boolean blockedByObstacle;
	private double avoidanceX;
	private double avoidanceZ;
	private int lastObstacleMessageTick = -1000;
	private String pendingDisconnectReason;
	private boolean disconnectOnThisArrival;
	private final CruiseCeilingMiner ceilingMiner;
	private double sampleY = Double.NaN;
	private int altitudeStuckSeconds;
	private int lastCeilingMessageTick = -1000;
	private int lastHealthWarnTick = -1000;
	private double altitudeOffset;
	private double dodgeFromX = Double.NaN;
	private double dodgeFromZ = Double.NaN;
	private int lastAltitudeDodgeTick = -200;
	private boolean hasNavLook;
	private float navYaw;
	private float navPitch;
	private int bypassSide;
	private double lastBypassOffset = 12.0;
	private int unstickTicksRemaining;
	private int unstickPhase;
	private int unstickRound;

	public KitController(KitConfig config) {
		this.config = config;
		this.ceilingMiner = new CruiseCeilingMiner(config);
	}

	/** 是否正在巡航（非空闲）。 */
	public boolean isActive() {
		return phase != Phase.IDLE;
	}

	/** 当前阶段中文标签。 */
	public String phaseLabel() {
		return phase.label;
	}

	/** HUD/指令用的状态一行。 */
	public String statusLine(Minecraft client) {
		if (!config.hasTarget) return "当前状态：" + phase.label + "  |  尚未设置目标";
		String target = String.format(Locale.ROOT, "目标 %.1f, %.1f @ Y %.1f", config.targetX, config.targetZ, config.cruiseY);
		if (!isActive() || client.player == null) return "当前状态：" + phase.label + "  |  " + target;
		double remaining = Math.hypot(config.targetX - client.player.getX(), config.targetZ - client.player.getZ());
		return "当前状态：" + phase.label + "  |  " + compactProgress(remaining);
	}

	/** 写入目标并起飞；到达是否离线跟配置。 */
	private boolean exactArrival;

	/** Scripted interaction targets require the requested height as well as X/Z. */
	public void startExact(Minecraft client, double targetX, double targetZ, double cruiseY) {
		start(client, targetX, targetZ, cruiseY);
		exactArrival = true;
	}

	public void start(Minecraft client, double targetX, double targetZ, double cruiseY) {
		config.targetX = targetX;
		config.targetZ = targetZ;
		config.cruiseY = cruiseY;
		config.hasTarget = true;
		config.save();
		disconnectOnThisArrival = config.disconnectOnArrival;
		activate(client);
	}

	/** 死亡返航：到达上方不离线。 */
	public void startDeathRecovery(Minecraft client, double targetX, double targetZ, double cruiseY) {
		config.targetX = targetX;
		config.targetZ = targetZ;
		config.cruiseY = cruiseY;
		config.hasTarget = true;
		config.save();
		disconnectOnThisArrival = false;
		activate(client);
		message(client, "死亡点返航：到达上方后不会自动离线，请手动下降捡取物品");
	}

	/** 按已存目标继续；无目标返回 false。 */
	public boolean resume(Minecraft client) {
		if (!config.hasTarget) return false;
		disconnectOnThisArrival = config.disconnectOnArrival;
		activate(client);
		return true;
	}

	/** 停其它模块、进升空阶段并尝试开 Meteor 飞行。 */
	private void activate(Minecraft client) {
		exactArrival = false;
		KitClient.prepareForCruise(client);
		releaseKeys(client);
		phase = Phase.ALTITUDE;
		ticks = 0;
		stationarySeconds = 0;
		recentSpeed = 0.0;
		traveledDistance = 0.0;
		plannedDistance = 0.0;
		hasTrackSample = false;
		trackX = Double.NaN;
		trackZ = Double.NaN;
		recentMovedCount = 0;
		recentMovedIndex = 0;
		windowMovedSum = 0.0;
		etaDisplaySeconds = -1;
		java.util.Arrays.fill(recentMoved, 0.0);
		avoidanceActive = false;
		blockedByObstacle = false;
		altitudeOffset = 0.0;
		hasNavLook = false;
		bypassSide = 0;
		lastBypassOffset = 12.0;
		unstickTicksRemaining = 0;
		unstickPhase = 0;
		unstickRound = 0;
		dodgeFromX = Double.NaN;
		dodgeFromZ = Double.NaN;
		lastAltitudeDodgeTick = -200;
		lastObstacleMessageTick = -1000;
		pendingDisconnectReason = null;
		lastCeilingMessageTick = -1000;
		lastHealthWarnTick = -1000;
		if (client.player != null) {
			resetMovementSample(client.player);
			plannedDistance = Math.hypot(config.targetX - client.player.getX(), config.targetZ - client.player.getZ());
		}
		if (ensureMeteorFlight(client.player)) {
			message(client, "已打开 Meteor 飞行");
		} else if (client.player != null && !BorerFlight.isFlying(client.player)) {
			message(client, "没开到 Meteor 飞行，升空会跳。请在 Meteor 里打开飞行");
		}
		message(client, String.format(Locale.ROOT, "开始：目标 %.1f, %.1f，巡航高度 %.1f", config.targetX, config.targetZ, desiredY()));
	}

	/** 停止巡航并松键。 */
	public void stop(Minecraft client, String reason) {
		if (!isActive()) {
			releaseKeys(client);
			return;
		}
		phase = Phase.IDLE;
		avoidanceActive = false;
		blockedByObstacle = false;
		altitudeOffset = 0.0;
		CruiseScreenHud.hide();
		releaseKeys(client);
		message(client, "已停止：" + reason);
	}

	/** 每拍导航：高度、绕障、前进、卡住与到达。 */
	public void tick(Minecraft client) {
		if (!isActive()) return;

		LocalPlayer player = client.player;
		if (player == null || client.level == null) {
			phase = Phase.IDLE;
			releaseKeys(client);
			return;
		}

		if (shouldPauseForScreen(client.screen)) {
			releaseKeys(client);
			return;
		}

		ticks++;
		trackTravel(player);
		ensureMeteorFlight(player);
		if (config.minHealth > 0.0 && player.getHealth() <= config.minHealth && !hasEdibleFood(player)
			&& lastHealthWarnTick < 0) {
			lastHealthWarnTick = ticks;
			message(client, String.format(Locale.ROOT, "生命偏低：%.1f，没有可吃的东西，继续巡航", player.getHealth()));
		}
		if (BorerItems.allMiningToolsWorn(player)) {
			int left = BorerItems.isMiningTool(player.getMainHandItem())
				? BorerItems.remainingDurability(player.getMainHandItem()) : 0;
			disconnect(client, "镐耐久过低（剩余 " + left + "），挖不了，已停止并下线");
			return;
		}

		double finalDx = config.targetX - player.getX();
		double finalDz = config.targetZ - player.getZ();
		double horizontalDistance = Math.hypot(finalDx, finalDz);
		if (horizontalDistance <= config.arrivalRadius) {
			if (exactArrival && Math.abs(config.cruiseY - player.getY()) > 0.7) {
				altitudeOffset = 0.0;
				avoidanceActive = false;
				blockedByObstacle = false;
				releaseKeys(client);
				adjustAltitude(client, player, 0.6);
				return;
			}
			arrive(client);
			return;
		}

		if (avoidanceActive && Math.hypot(avoidanceX - player.getX(), avoidanceZ - player.getZ()) <= 5.0) {
			if (isPathClear(client, player, config.targetX, config.targetZ)) {
				avoidanceActive = false;
				phase = Phase.CRUISE;
				bypassSide = 0;
			} else if (config.obstacleAvoidance) {
				extendAvoidanceWaypoint(client, player);
			} else {
				avoidanceActive = false;
				phase = Phase.CRUISE;
			}
		}

		if (tickUnstick(client, player)) return;

		if (phase != Phase.ALTITUDE && config.obstacleAvoidance && ticks % 5 == 0) {
			checkObstacleAndPlan(client, player);
		}

		maybeRecoverCruiseHeight(client, player);
		if ((bodyBlockedForward(client, player) || blockedByObstacle) && ticks - lastAltitudeDodgeTick >= 20) {
			tryAltitudeDodge(client, player);
		}

		double upTolerance = phase == Phase.ALTITUDE ? config.altitudeTolerance : config.altitudeCorrectionTolerance;
		if (config.clearCeiling && desiredY() - player.getY() > upTolerance
			&& ceilingMiner.tick(client, player, desiredY())) {
			if (ticks - lastCeilingMessageTick >= 80) {
				message(client, ceilingMiner.status());
				lastCeilingMessageTick = ticks;
			}
			if (ticks % 10 == 0) {
				client.gui.setOverlayMessage(Component.literal("twob2tkit | " + ceilingMiner.status()).withColor(0x55FFFF), false);
			}
			return;
		}
		if (ceilingMiner.isMining()) ceilingMiner.release(client);
		if (config.clearCeiling && desiredY() - player.getY() > upTolerance
			&& ceilingMiner.blockedByUnbreakable(client, player)) {
			if (phase == Phase.ALTITUDE) {
				phase = Phase.CRUISE;
				resetMovementSample(player);
				message(client, "头顶挖不掉（基岩一类），已在当前高度前进");
			}
			client.options.keyJump.setDown(false);
		}

		float yawError = faceDestination(player);

		if (phase == Phase.ALTITUDE) {
			client.options.keyUp.setDown(false);
			if (adjustAltitude(client, player, config.altitudeTolerance)) {
				updateAltitudeSample(client, player, desiredY() - player.getY() > config.altitudeTolerance);
				return;
			}
			phase = Phase.CRUISE;
			resetMovementSample(player);
			message(client, String.format(Locale.ROOT, "已到 Y %.0f，开始前进", desiredY()));
			if (config.obstacleAvoidance) checkObstacleAndPlan(client, player);
			if (phase == Phase.ALTITUDE) {
				adjustAltitude(client, player, config.altitudeTolerance);
			}
			return;
		}

		if (isClimbingOver(player) || blockedByObstacle || Math.abs(yawError) > 10.0F) {
			client.options.keyUp.setDown(false);
			adjustAltitude(client, player, config.altitudeCorrectionTolerance);
			if (isClimbingOver(player)) {
				updateAltitudeSample(client, player, desiredY() - player.getY() > config.altitudeCorrectionTolerance);
			} else if (blockedByObstacle) {
				updateMovementSample(client, player);
			} else {
				resetMovementSample(player);
			}
			if (ticks % 10 == 0) showStatus(client, horizontalDistance, player.getY());
			return;
		}

		client.options.keyUp.setDown(true);
		adjustAltitude(client, player, config.altitudeCorrectionTolerance);
		updateMovementSample(client, player);

		if (ticks % 10 == 0) showStatus(client, horizontalDistance, player.getY());
	}

	/** Meteor 改朝向后再写回巡航朝向。 */
	public void reapplyNavigationRotation(Minecraft client) {
		if (!isActive() || client.player == null || client.level == null || shouldPauseForScreen(client.screen)) return;
		if (ceilingMiner.isMining()) {
			ceilingMiner.reapplyLook(client.player);
			return;
		}
		// 只把本 tick 已算好的朝向写回去，不再步进：写回一帧可能跑多次，
		// 重复步进会让实际转速超过设定值。
		if (hasNavLook) RotationAim.apply(client.player, navYaw, navPitch);
	}

	/** 在合适时机执行排队的离线。 */
	public void flushPendingDisconnect(Minecraft client) {
		if (pendingDisconnectReason == null) return;
		String reason = pendingDisconnectReason;
		pendingDisconnectReason = null;
		var expectedLevel = client.level;
		var expectedConnection = client.getConnection();
		if (expectedLevel == null || expectedConnection == null) return;
		// execute() can run inline on the client thread; schedule() always queues between client tasks.
		client.schedule(() -> {
			if (dev.twob2tkit.compat.ClientWorldGuard.sameSession(expectedLevel, client.level, expectedConnection, client.getConnection()))
				disconnectNow(client, reason);
		});
	}

	/** 只有暂停游戏的界面才停（Esc 菜单、断开连接）。聊天、背包、Meteor 菜单继续飞。 */
	private static boolean shouldPauseForScreen(Screen screen) {
		return screen != null && screen.isPauseScreen();
	}

	/** 当前要飞的高度：设定巡航高 ± 临时升降绕障。下界基岩顶下最高飞到 120。 */
	private double desiredY() {
		double y = config.cruiseY + altitudeOffset;
		Minecraft client = Minecraft.getInstance();
		if (client.level == null) return y;
		if (NetherRoofAssist.inNether(client) && client.player != null && !NetherRoofAssist.onRoof(client.player)) {
			y = Math.min(config.cruiseY, NetherRoofAssist.underRoofCruiseY()) + altitudeOffset;
		}
		return Math.min(y, maxSafeFlyY(client));
	}

	/** 按容差升/降到目标高度；返回是否仍在调高。 */
	private boolean adjustAltitude(Minecraft client, LocalPlayer player, double tolerance) {
		double difference = desiredY() - player.getY();
		if (difference > tolerance) {
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
			return true;
		}
		if (difference < -tolerance) {
			client.options.keyJump.setDown(false);
			client.options.keyShift.setDown(true);
			return true;
		}

		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
		return false;
	}

	/**
	 * 朝巡航目标平滑转向：大误差全速收敛，小误差按比例减速，不瞬间甩头。
	 * 每 tick 只在这里步进一次；写回走 {@link #reapplyNavigationRotation} 只写不步进。
	 */
	private float faceDestination(LocalPlayer player) {
		double navigationX = avoidanceActive ? avoidanceX : config.targetX;
		double navigationZ = avoidanceActive ? avoidanceZ : config.targetZ;
		double dx = navigationX - player.getX();
		double dz = navigationZ - player.getZ();
		if (dx * dx + dz * dz < 1.0E-6) return 0.0F;
		float targetYaw = RotationAim.yawToward(dx, dz);
		if (!hasNavLook) {
			navYaw = player.getYRot();
			navPitch = player.getXRot();
			hasNavLook = true;
		}
		navYaw = RotationAim.step(navYaw, targetYaw, (float)config.turnSpeed);
		navPitch = RotationAim.step(navPitch, 0.0F, (float)config.turnSpeed);
		RotationAim.apply(player, navYaw, navPitch);
		return wrapDegrees(targetYaw - navYaw);
	}

	/** 前方有障碍：贴身时先升高越过树冠，远处才水平绕行；找不到绕行也不停车。 */
	private void checkObstacleAndPlan(Minecraft client, LocalPlayer player) {
		double obstacleDistance = firstObstacleDistanceAtY(client, player, 0.0, config.obstacleLookAhead);
		if (obstacleDistance < 0.0) {
			blockedByObstacle = false;
			if (!avoidanceActive && phase == Phase.AVOIDING) phase = Phase.CRUISE;
			return;
		}

		if (isClimbingOver(player)) {
			blockedByObstacle = bodyBlockedForward(client, player);
			return;
		}

		boolean close = obstacleDistance <= 8.0 || bodyBlockedForward(client, player);
		if (close && (beginClimbOver(client, player, obstacleDistance) || raiseCruiseToClear(client, player))) {
			return;
		}

		AvoidanceWaypoint waypoint = findAvoidanceWaypoint(client, player, obstacleDistance);
		if (waypoint != null) {
			avoidanceX = waypoint.x();
			avoidanceZ = waypoint.z();
			avoidanceActive = true;
			blockedByObstacle = false;
			phase = Phase.AVOIDING;
			if (ticks - lastObstacleMessageTick >= 100) {
				message(client, String.format(Locale.ROOT, "前方 %.0f 格有障碍，绕行至 %.0f, %.0f", obstacleDistance, avoidanceX, avoidanceZ));
				lastObstacleMessageTick = ticks;
			}
			return;
		}

		if (!close && (beginClimbOver(client, player, obstacleDistance) || raiseCruiseToClear(client, player))) {
			return;
		}

		avoidanceActive = false;
		blockedByObstacle = true;
		phase = Phase.AVOIDING;
		if (ticks - lastObstacleMessageTick >= 100) {
			message(client, "已升到可飞最高处仍被挡住，暂停前进");
			lastObstacleMessageTick = ticks;
		}
	}

	/** 在左右侧找可绕开的水平路点。 */
	private AvoidanceWaypoint findAvoidanceWaypoint(Minecraft client, LocalPlayer player, double obstacleDistance) {
		double targetDx = config.targetX - player.getX();
		double targetDz = config.targetZ - player.getZ();
		double targetDistance = Math.hypot(targetDx, targetDz);
		if (targetDistance < 0.001) return null;

		double forwardX = targetDx / targetDistance;
		double forwardZ = targetDz / targetDistance;
		double sideX = -forwardZ;
		double sideZ = forwardX;
		double forwardDistance = obstacleDistance + Math.max(8.0, config.obstacleBypassDistance);
		double[] offsets = {8.0, 12.0, 16.0, 24.0, 32.0, 48.0, 64.0};

		AvoidanceWaypoint best = scoreAvoidance(client, player, forwardX, forwardZ, sideX, sideZ, forwardDistance, offsets, bypassSide);
		if (best == null && bypassSide != 0) {
			best = scoreAvoidance(client, player, forwardX, forwardZ, sideX, sideZ, forwardDistance, offsets, -bypassSide);
			if (best != null) bypassSide = -bypassSide;
		}
		if (best == null) {
			best = scoreAvoidance(client, player, forwardX, forwardZ, sideX, sideZ, forwardDistance, offsets, 0);
		}
		return best;
	}

	/** 给候选绕行偏移打分。 */
	private AvoidanceWaypoint scoreAvoidance(
		Minecraft client,
		LocalPlayer player,
		double forwardX,
		double forwardZ,
		double sideX,
		double sideZ,
		double forwardDistance,
		double[] offsets,
		int preferSide
	) {
		AvoidanceWaypoint best = null;
		double bestScore = Double.MAX_VALUE;
		for (double offset : offsets) {
			for (int side : new int[]{-1, 1}) {
				double candidateX = player.getX() + forwardX * forwardDistance + sideX * offset * side;
				double candidateZ = player.getZ() + forwardZ * forwardDistance + sideZ * offset * side;
				if (!isPathClear(client, player, candidateX, candidateZ)) continue;
				double finalDistance = Math.hypot(config.targetX - candidateX, config.targetZ - candidateZ);
				double score = finalDistance + 0.25 * offset;
				if (preferSide != 0 && side == preferSide) score -= 2.0;
				if (score < bestScore) {
					bestScore = score;
					best = new AvoidanceWaypoint(candidateX, candidateZ, side, offset);
				}
			}
		}
		if (best != null && bypassSide == 0) bypassSide = best.side();
		if (best != null) lastBypassOffset = best.offset();
		return best;
	}

	/** 绕障点被挡时再往外推。 */
	private void extendAvoidanceWaypoint(Minecraft client, LocalPlayer player) {
		double targetDx = config.targetX - player.getX();
		double targetDz = config.targetZ - player.getZ();
		double targetDistance = Math.hypot(targetDx, targetDz);
		if (targetDistance < 0.001) {
			avoidanceActive = false;
			return;
		}
		double forwardX = targetDx / targetDistance;
		double forwardZ = targetDz / targetDistance;
		double sideX = -forwardZ;
		double sideZ = forwardX;
		int side = bypassSide != 0 ? bypassSide : 1;
		double forwardDistance = Math.max(8.0, config.obstacleBypassDistance);
		double offset = Math.max(8.0, lastBypassOffset);
		avoidanceX = avoidanceX + forwardX * forwardDistance + sideX * offset * side;
		avoidanceZ = avoidanceZ + forwardZ * forwardDistance + sideZ * offset * side;
		avoidanceActive = true;
		phase = Phase.AVOIDING;
	}

	/** 贴身正前方是否已经撞上东西。 */
	private boolean bodyBlockedForward(Minecraft client, LocalPlayer player) {
		double yaw = Math.toRadians(player.getYRot());
		double fx = -Math.sin(yaw);
		double fz = Math.cos(yaw);
		AABB ahead = player.getBoundingBox().move(fx * 0.45, 0.0, fz * 0.45).inflate(0.02, 0.05, 0.02);
		return !client.level.noCollision(player, ahead);
	}

	/** 正前方贴树或还在往更高巡航高度爬。 */
	private boolean isClimbingOver(LocalPlayer player) {
		return altitudeOffset > 0.5 && player.getY() < desiredY() - Math.max(1.0, config.altitudeTolerance);
	}

	/** 当前高度走不通时，先大幅升高越过树冠，再考虑下降。 */
	private boolean tryAltitudeDodge(Minecraft client, LocalPlayer player) {
		double currentAhead = firstObstacleDistanceAtY(client, player, 0.0, 16.0);
		if (currentAhead < 0.0) currentAhead = 16.0;
		double[] ups = {8.0, 12.0, 16.0, 24.0, 32.0, 48.0, 64.0};
		for (double dy : ups) {
			double probeY = player.getY() + dy;
			if (!yInWorld(client, probeY) || !spaceFreeAtY(client, player, dy)) continue;
			double ahead = firstObstacleDistanceAtY(client, player, dy, 12.0);
			if (ahead < 0.0 || ahead > currentAhead + 3.0) {
				applyClimbHeight(client, player, probeY, "当前高度卡住，升高到 Y %.0f 再继续", true);
				return true;
			}
		}
		double[] downs = {-3.0, -5.0, -8.0};
		for (double dy : downs) {
			double probeY = player.getY() + dy;
			if (!yInWorld(client, probeY) || !pathClearAtY(client, player, dy, 8.0)) continue;
			applyClimbHeight(client, player, probeY, "当前高度卡住，改走 Y %.0f 再继续", false);
			return true;
		}
		if (raiseCruiseToClear(client, player)) return true;
		lastAltitudeDodgeTick = ticks;
		return false;
	}

	/** 探测更高处是否更通；选最低完全畅通高度，否则选前方空隙最大的高度。 */
	private boolean beginClimbOver(Minecraft client, LocalPlayer player, double currentObstacle) {
		double[] ups = {8.0, 12.0, 16.0, 24.0, 32.0, 48.0, 64.0};
		double bestDy = Double.NaN;
		double bestAhead = currentObstacle < 0.0 ? 0.0 : currentObstacle;
		for (double dy : ups) {
			double probeY = player.getY() + dy;
			if (!yInWorld(client, probeY) || !spaceFreeAtY(client, player, dy)) continue;
			double ahead = firstObstacleDistanceAtY(client, player, dy, 16.0);
			if (ahead < 0.0) {
				applyClimbHeight(client, player, probeY, "前方有障碍，升高到 Y %.0f 越过", true);
				return true;
			}
			if (ahead > bestAhead + 4.0) {
				bestAhead = ahead;
				bestDy = dy;
			}
		}
		if (!Double.isNaN(bestDy)) {
			applyClimbHeight(client, player, player.getY() + bestDy, "前方有障碍，升高到 Y %.0f 越过", true);
			return true;
		}
		return false;
	}

	/** 找不到已验证的通路时仍抬高巡航目标，边升边让挖顶处理树叶。 */
	private boolean raiseCruiseToClear(Minecraft client, LocalPlayer player) {
		double next = Math.min(maxSafeFlyY(client), Math.max(player.getY(), desiredY()) + 16.0);
		if (next <= desiredY() + 0.5) return false;
		applyClimbHeight(client, player, next, "巡航高度偏低，升高到 Y %.0f 越过障碍", true);
		return true;
	}

	/** 把巡航目标抬到 probeY：更新高度偏移与绕障状态，必要时切入升空阶段并提示。 */
	private void applyClimbHeight(Minecraft client, LocalPlayer player, double probeY, String format, boolean riseFirst) {
		altitudeOffset = probeY - config.cruiseY;
		dodgeFromX = player.getX();
		dodgeFromZ = player.getZ();
		blockedByObstacle = false;
		lastAltitudeDodgeTick = ticks;
		resetMovementSample(player);
		if (riseFirst) {
			avoidanceActive = false;
			phase = Phase.ALTITUDE;
		}
		if (ticks - lastObstacleMessageTick >= 60) {
			message(client, String.format(Locale.ROOT, format, probeY));
			lastObstacleMessageTick = ticks;
		}
	}

	/** Y 是否在世界高度内。 */
	private boolean yInWorld(Minecraft client, double y) {
		return y >= client.level.getMinY() + 2 && y <= maxSafeFlyY(client);
	}

	/** 下界基岩顶下不往 127 以上盲升；主世界可升到世界顶。 */
	private double maxSafeFlyY(Minecraft client) {
		double cap = client.level.getMaxY() - 2.0;
		if (NetherRoofAssist.inNether(client) && client.player != null && !NetherRoofAssist.onRoof(client.player)) {
			return Math.min(cap, 126.0);
		}
		return cap;
	}

	/** 指定高度偏移处碰撞箱是否空闲。 */
	private boolean spaceFreeAtY(Minecraft client, LocalPlayer player, double dy) {
		double y = player.getY() + dy;
		if (!client.level.hasChunkAt(BlockPos.containing(player.getX(), y, player.getZ()))) return false;
		AABB box = player.getBoundingBox().move(0.0, dy, 0.0).inflate(0.2, 0.1, 0.2);
		return client.level.noCollision(player, box);
	}

	/** 临时升降绕过去之后，原巡航高度若已畅通就回到设定高度。 */
	private void maybeRecoverCruiseHeight(Minecraft client, LocalPlayer player) {
		if (altitudeOffset == 0.0 || isClimbingOver(player)) return;
		if (!Double.isNaN(dodgeFromX) && Math.hypot(player.getX() - dodgeFromX, player.getZ() - dodgeFromZ) < 8.0) {
			return;
		}
		double dy = config.cruiseY - player.getY();
		if (!pathClearAtY(client, player, dy, 20.0)) return;
		altitudeOffset = 0.0;
		dodgeFromX = Double.NaN;
		dodgeFromZ = Double.NaN;
		message(client, "障碍已过，回到巡航高度 " + String.format(Locale.ROOT, "%.0f", config.cruiseY));
	}

	/** 把碰撞箱垂直平移 dy 后，朝目标方向是否畅通。 */
	private boolean pathClearAtY(Minecraft client, LocalPlayer player, double dy, double maximumDistance) {
		double goalX = avoidanceActive ? avoidanceX : config.targetX;
		double goalZ = avoidanceActive ? avoidanceZ : config.targetZ;
		double dx = goalX - player.getX();
		double dz = goalZ - player.getZ();
		double fullDistance = Math.hypot(dx, dz);
		double distance = Math.min(fullDistance, maximumDistance);
		if (distance < 2.0) return true;
		double unitX = dx / fullDistance;
		double unitZ = dz / fullDistance;
		AABB playerBox = player.getBoundingBox().move(0.0, dy, 0.0).inflate(0.2, 0.1, 0.2);
		if (!client.level.noCollision(player, playerBox)) return false;
		for (double step = 1.0; step <= distance; step += 1.0) {
			double x = player.getX() + unitX * step;
			double z = player.getZ() + unitZ * step;
			if (!client.level.hasChunkAt(BlockPos.containing(x, player.getY() + dy, z))) return false;
			if (!client.level.noCollision(player, playerBox.move(unitX * step, 0.0, unitZ * step))) return false;
		}
		return true;
	}

	/** 把碰撞箱垂直平移 dy 后，朝目标方向第一处障碍的距离；畅通返回 -1。 */
	private double firstObstacleDistanceAtY(Minecraft client, LocalPlayer player, double dy, double maximumDistance) {
		double goalX = avoidanceActive ? avoidanceX : config.targetX;
		double goalZ = avoidanceActive ? avoidanceZ : config.targetZ;
		double dx = goalX - player.getX();
		double dz = goalZ - player.getZ();
		double fullDistance = Math.hypot(dx, dz);
		double distance = Math.min(fullDistance, maximumDistance);
		if (distance < 0.8) return -1.0;
		double unitX = dx / fullDistance;
		double unitZ = dz / fullDistance;
		AABB playerBox = player.getBoundingBox().move(0.0, dy, 0.0).inflate(0.25, 0.15, 0.25);
		if (!client.level.noCollision(player, playerBox)) return 0.0;
		for (double step = 0.8; step <= distance; step += 0.8) {
			double x = player.getX() + unitX * step;
			double z = player.getZ() + unitZ * step;
			if (!client.level.hasChunkAt(BlockPos.containing(x, player.getY() + dy, z))) return -1.0;
			if (!client.level.noCollision(player, playerBox.move(unitX * step, 0.0, unitZ * step))) return step;
		}
		return -1.0;
	}

	/** 朝目标 XZ 水平路径是否畅通。 */
	private boolean isPathClear(Minecraft client, LocalPlayer player, double goalX, double goalZ) {
		double dx = goalX - player.getX();
		double dz = goalZ - player.getZ();
		double distance = Math.hypot(dx, dz);
		if (distance < 0.001) return true;
		double unitX = dx / distance;
		double unitZ = dz / distance;
		AABB playerBox = player.getBoundingBox().inflate(0.35, 0.2, 0.35);
		for (double step = 2.0; step <= distance; step += 1.0) {
			double x = player.getX() + unitX * step;
			double z = player.getZ() + unitZ * step;
			if (!client.level.hasChunkAt(BlockPos.containing(x, player.getY(), z))) return false;
			if (!client.level.noCollision(player, playerBox.move(unitX * step, 0.0, unitZ * step))) return false;
		}
		return true;
	}

	/** 累计本趟水平路程。 */
	private void trackTravel(LocalPlayer player) {
		double x = player.getX();
		double z = player.getZ();
		if (hasTrackSample) {
			traveledDistance += Math.hypot(x - trackX, z - trackZ);
		}
		trackX = x;
		trackZ = z;
		hasTrackSample = true;
	}

	/**
	 * 近段窗口水平速度（格/秒）。
	 * 窗口未攒够时用开局以来的均速暖机；仍不够则 0。
	 */
	private double cruiseSpeedBlocksPerSecond() {
		if (recentMovedCount >= 5) {
			return windowMovedSum / recentMovedCount;
		}
		double elapsedSeconds = ticks / 20.0;
		if (elapsedSeconds < 2.0 || traveledDistance < 1.0) return 0.0;
		return traveledDistance / elapsedSeconds;
	}

	/** 写入近 30 秒位移环。 */
	private void pushMovedSample(double moved) {
		if (recentMovedCount < SPEED_WINDOW_SECONDS) {
			recentMoved[recentMovedCount] = moved;
			windowMovedSum += moved;
			recentMovedCount++;
			recentMovedIndex = recentMovedCount % SPEED_WINDOW_SECONDS;
			return;
		}
		windowMovedSum -= recentMoved[recentMovedIndex];
		recentMoved[recentMovedIndex] = moved;
		windowMovedSum += moved;
		recentMovedIndex = (recentMovedIndex + 1) % SPEED_WINDOW_SECONDS;
	}

	/**
	 * 每真实秒推进倒计时：先 −1，再按剩余/近段速度小幅校准。
	 * 比全程均速更跟得上减速，又不会像瞬时速度那样乱跳。
	 */
	private void tickEtaCountdown(double remaining) {
		double speed = cruiseSpeedBlocksPerSecond();
		if (speed < 0.1) {
			etaDisplaySeconds = -1;
			return;
		}
		long estimate = Math.max(0L, Math.round(remaining / speed));
		if (etaDisplaySeconds < 0) {
			etaDisplaySeconds = estimate;
			return;
		}
		long predicted = Math.max(0L, etaDisplaySeconds - 1L);
		long error = estimate - predicted;
		long maxStep = Math.max(3L, Math.abs(error) / 8L);
		if (error > maxStep) predicted += maxStep;
		else if (error < -maxStep) predicted -= maxStep;
		else predicted = estimate;
		etaDisplaySeconds = Math.max(0L, predicted);
	}

	/** HUD/指令用的剩余时间文案。 */
	private String etaLabel() {
		if (etaDisplaySeconds < 0) return "计算中";
		return formatDuration(etaDisplaySeconds);
	}

	/** 指令用紧凑进度：剩余/全程 + 已走/剩余时间。 */
	private String compactProgress(double remaining) {
		double total = plannedDistance > 0.0 ? plannedDistance : remaining;
		long elapsedSeconds = Math.max(0L, ticks / 20L);
		return String.format(Locale.ROOT, "剩余 %.0f/%.0f 格  ·  已走 %s / 剩余 %s",
			remaining, total, formatDuration(elapsedSeconds), etaLabel());
	}

	/** 屏幕 HUD 两行：主行高亮剩余/全程与剩余时间；副行已走时间与阶段、高度。 */
	private void publishProgressHud(double remaining, double y, String healthNote) {
		double total = plannedDistance > 0.0 ? plannedDistance : remaining;
		long elapsedSeconds = Math.max(0L, ticks / 20L);
		String primary = String.format(Locale.ROOT, "剩余 %.0f/%.0f 格  ·  %s", remaining, total, etaLabel());
		String secondary = String.format(Locale.ROOT, "已走 %s  ·  %s  ·  Y %.0f/%.0f%s",
			formatDuration(elapsedSeconds), phase.label, y, desiredY(),
			healthNote == null || healthNote.isEmpty() ? "" : "  ·  " + healthNote);
		CruiseScreenHud.show(primary, secondary);
	}

	/** 采样水平移动，超时卡住则尝试脱困。 */
	private void updateMovementSample(Minecraft client, LocalPlayer player) {
		if (ticks % 20 != 0) return;

		double moved = Math.hypot(player.getX() - sampleX, player.getZ() - sampleZ);
		sampleX = player.getX();
		sampleZ = player.getZ();
		recentSpeed = recentSpeed == 0.0 ? moved : recentSpeed * 0.7 + moved * 0.3;
		pushMovedSample(moved);
		double remaining = Math.hypot(config.targetX - player.getX(), config.targetZ - player.getZ());
		tickEtaCountdown(remaining);

		if (moved < 0.75) {
			stationarySeconds++;
			if (stationarySeconds >= 2 && ticks - lastAltitudeDodgeTick >= 20) {
				tryAltitudeDodge(client, player);
			}
		} else {
			stationarySeconds = 0;
		}

		if (config.stuckSeconds > 0 && stationarySeconds >= config.stuckSeconds) {
			if (tryStartUnstick(client)) return;
			disconnect(client, "连续 " + stationarySeconds + " 秒没有前进");
			return;
		}
		if (stationarySeconds >= 60 && phase != Phase.ALTITUDE) {
			tryStartUnstick(client);
		}
	}

	/** 开始脱困序列。 */
	private boolean tryStartUnstick(Minecraft client) {
		if (phase == Phase.ALTITUDE || unstickRound >= 2) return false;
		if (unstickTicksRemaining > 0) return false;
		unstickRound++;
		unstickPhase = 1;
		unstickTicksRemaining = 10;
		stationarySeconds = Math.max(0, stationarySeconds - 5);
		message(client, "疑似卡住，先后退侧移试试（第 " + unstickRound + " 轮）");
		return true;
	}

	/** 执行脱困阶段按键。 */
	private boolean tickUnstick(Minecraft client, LocalPlayer player) {
		if (unstickTicksRemaining <= 0 || phase == Phase.ALTITUDE) return false;
		unstickTicksRemaining--;
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
		client.options.keyDown.setDown(true);
		client.options.keyLeft.setDown(unstickPhase == 1);
		client.options.keyRight.setDown(unstickPhase == 2);
		if (unstickTicksRemaining == 0) {
			if (unstickPhase == 1) {
				unstickPhase = 2;
				unstickTicksRemaining = 10;
			} else {
				unstickPhase = 0;
				resetMovementSample(player);
			}
		}
		return true;
	}

	/** 重置卡住检测采样。 */
	private void resetMovementSample(LocalPlayer player) {
		stationarySeconds = 0;
		altitudeStuckSeconds = 0;
		sampleX = player.getX();
		sampleZ = player.getZ();
		sampleY = player.getY();
	}

	/** 升空卡住时尝试挖顶。 */
	private void updateAltitudeSample(Minecraft client, LocalPlayer player, boolean tryingToAscend) {
		if (!tryingToAscend) {
			altitudeStuckSeconds = 0;
			sampleY = player.getY();
			return;
		}
		if (ticks % 20 != 0) return;
		double risen = player.getY() - sampleY;
		sampleY = player.getY();
		if (risen < 0.4) altitudeStuckSeconds++;
		else altitudeStuckSeconds = 0;
		if (config.stuckSeconds > 0 && altitudeStuckSeconds >= config.stuckSeconds) {
			String extra = ceilingMiner.status().isEmpty() ? "头顶挡住" : ceilingMiner.status();
			disconnect(client, extra + "，连续 " + altitudeStuckSeconds + " 秒无法升高");
		}
	}

	/** 周期性更新屏幕进度 HUD（不再刷长串 action bar）。 */
	private void showStatus(Minecraft client, double distance, double y) {
		String healthNote = "";
		if (config.minHealth > 0.0 && client.player != null && client.player.getHealth() <= config.minHealth) {
			healthNote = hasEdibleFood(client.player) ? "生命偏低请进食" : "生命偏低无食物";
		}
		publishProgressHud(distance, y, healthNote);
	}

	/** 背包是否有可食食物。 */
	private static boolean hasEdibleFood(LocalPlayer player) {
		return HealingItems.count(player, java.util.Set.of(HealingItems.ANY_FOOD, HealingItems.HEALING_POTION)) > 0;
	}

	/** 到达目标：停飞并按配置离线。 */
	private void arrive(Minecraft client) {
		String reason = String.format(Locale.ROOT, "已到达目标 %.1f, %.1f（半径 %.1f）", config.targetX, config.targetZ, config.arrivalRadius);
		phase = Phase.IDLE;
		avoidanceActive = false;
		blockedByObstacle = false;
		altitudeOffset = 0.0;
		CruiseScreenHud.hide();
		releaseKeys(client);
		if (disconnectOnThisArrival) pendingDisconnectReason = reason;
		else message(client, reason);
	}

	/** 排队安全离线原因。 */
	public void requestLogout(String reason) {
		pendingDisconnectReason = reason;
	}

	/** 标记待离线并在聊天提示。 */
	private void disconnect(Minecraft client, String reason) {
		phase = Phase.IDLE;
		avoidanceActive = false;
		blockedByObstacle = false;
		altitudeOffset = 0.0;
		CruiseScreenHud.hide();
		releaseKeys(client);
		pendingDisconnectReason = reason;
	}

	/** 立刻断开服务器。 */
	private void disconnectNow(Minecraft client, String reason) {
		Component title = Component.literal("twob2tkit 已安全离线");
		Component detail = Component.literal(reason);
		JoinMultiplayerScreen parent = new JoinMultiplayerScreen(new TitleScreen());
		DisconnectedScreen resultScreen = new DisconnectedScreen(parent, title, detail);
		if (client.level != null) {
			client.disconnectFromWorld(ClientLevel.DEFAULT_QUIT_MESSAGE);
			client.setScreen(resultScreen);
		} else {
			client.disconnect(resultScreen, false);
		}
	}

	/**
	 * 尝试打开 Meteor 飞行。
	 * @return true 表示这一拍新打开了
	 */
	private static boolean ensureMeteorFlight(LocalPlayer player) {
		if (player == null) return false;
		if (MeteorModules.enable(MeteorModules.FLIGHT)) return true;
		if (Boolean.TRUE.equals(BorerFlight.meteorFlightActive())) return false;
		BorerFlight.ensureFlying(player, true);
		return false;
	}

	/** 松开本模组按下的移动键。 */
	private void releaseKeys(Minecraft client) {
		ceilingMiner.release(client);
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
	}

	/** 向玩家发系统消息。 */
	private static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[twob2tkit] " + text));
	}

	/** 角度归一到 [-180,180)。 */
	private static float wrapDegrees(float degrees) {
		float result = degrees % 360.0F;
		if (result >= 180.0F) result -= 360.0F;
		if (result < -180.0F) result += 360.0F;
		return result;
	}

	/** 秒数格式为可读时长。 */
	private static String formatDuration(long seconds) {
		long hours = seconds / 3600;
		long minutes = seconds % 3600 / 60;
		long remainder = seconds % 60;
		if (hours > 0) return String.format(Locale.ROOT, "%d:%02d:%02d", hours, minutes, remainder);
		return String.format(Locale.ROOT, "%02d:%02d", minutes, remainder);
	}

	/** 水平绕障路点。 */
	private record AvoidanceWaypoint(double x, double z, int side, double offset) {
		AvoidanceWaypoint(double x, double z) {
			this(x, z, 0, 12.0);
		}
	}
}
