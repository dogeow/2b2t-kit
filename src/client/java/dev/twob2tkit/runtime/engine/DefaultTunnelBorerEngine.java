package dev.twob2tkit.runtime.engine;

import com.mojang.blaze3d.platform.InputConstants;
import dev.twob2tkit.runtime.api.BorerEngine;
import dev.twob2tkit.runtime.api.BorerHost;
import dev.twob2tkit.runtime.api.RotationAim;

import net.minecraft.client.Minecraft;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.gui.screens.DisconnectedScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.gui.screens.multiplayer.JoinMultiplayerScreen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ServerboundMovePlayerPacket;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.util.Mth;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** 热加载盾构机：找矿、挖通道、封液体、拾取勾选矿种掉落物。 */
public final class DefaultTunnelBorerEngine implements BorerEngine {
	private static final Logger LOGGER = LoggerFactory.getLogger("twob2tkit/Borer");
	private static final String RUNTIME_VERSION = "1.7.1";
	private static final int CLEAR_CONFIRM_TICKS = 3;
	private static final int MOVEMENT_RECOVERY_TICKS = 40;
	private static final int MOVEMENT_TIMEOUT_TICKS = 120;
	static final int ROUTE_TIMEOUT_TICKS = 80;
	private static final int MINING_RETRY_TICKS = 40;
	private static final int MINING_STALL_TICKS = 200;
	private static final int DIAGNOSTIC_INTERVAL_TICKS = 40;
	static final int LAVA_TURN_COOLDOWN_TICKS = 20;
	static final int LAVA_LOOK_BLOCKS = 16;
	static final int LAVA_CONTACT_ESCAPE_TICKS = 80;
	private static final int SIDE_WALL_SUPPRESS_TICKS = 20;
	private static final int STALLED_BLOCK_SUPPRESS_TICKS = 60;

	/** 盾构运行模式：向前挖 / 向下挖 / 找矿 / 区域挖。 */
	public enum Mode {
		FORWARD("向前挖"),
		DOWN("向下挖"),
		ORE("自动找矿"),
		AREA("区域挖");

		final String label;

		Mode(String label) {
			this.label = label;
		}

		/** 从配置字符串解析；非法则用默认。 */
		static Mode fromConfig(String value) {
			try {
				return value == null ? FORWARD : valueOf(value);
			} catch (IllegalArgumentException ignored) {
				return FORWARD;
			}
		}
	}

	/** 垂直接近阶段：准备、前进、上爬、下挖。 */
	public enum VerticalMove {
		NONE,
		PREPARE,
		ADVANCE,
		UP,
		DOWN
	}

	final BorerHost host;
	final BorerLoot loot = new BorerLoot(this);
	final BorerHome home = new BorerHome(this);
	final BorerMobs mobs = new BorerMobs(this);
	final BorerOreScan ores = new BorerOreScan(this);
	final BorerArea area = new BorerArea(this);
	final BorerLiquids liquids = new BorerLiquids(this);
	final BorerVertical vertical = new BorerVertical(this);
	final BorerPreview preview = new BorerPreview(this);
	final BorerPlace place = new BorerPlace(this);
	final BorerCorridor corridor = new BorerCorridor(this);
	boolean active;
	Mode mode = Mode.FORWARD;
	Direction forward = Direction.SOUTH;
	/** 选出当前挖块时的通道朝向。找矿每 tick 拧向矿之后仍用这个数判断侧壁。 */
	private Direction corridorHeading;
	/** 选出当前挖块时的身体所在列。贴坑沿或跨格后仍用它判断这块是否属于通道。 */
	private BlockPos corridorOrigin;
	int turnCooldown;
	boolean lastTurnClockwise = true;
	boolean turnedThisTick;
	String status = "";
	private int statusColor = 0xFFFF55;
	private String lastHudAction = "";
	private String lastHudDetail = "";
	BlockPos currentTarget;
	int clearConfirmTicks;
	private int pauseTicks;
	int dropWait;
	boolean holdingShield;
	boolean retreating;
	boolean combatApproaching;
	private int combatPauseTicks;
	BlockPos oreTargetPos;
	BlockPos sideOreTargetPos;
	int oreScanCooldown;
	BlockPos oreScanCenter;
	String oreScanWantedKey;
	int oreScanLayerCursor;
	int oreScanCheckedBlocks;
	int liquidSettleTicks;
	int liquidSealFails;
	BlockPos liquidSealFailPos;
	int lavaBypassTicks;
	int lavaContactTicks;
	BlockPos sealTarget;
	final Map<BlockPos, Block> protectedSealBlocks = new HashMap<>();
	boolean frontOccluded;
	int occludedTicks;
	int areaStallTicks;
	final Map<BlockPos, Long> blockedOreTargets = new HashMap<>();
	/** 普通挡路短期失败记忆；保留矿点，但不在下一 tick 原样重选同一块。 */
	private final Map<BlockPos, Long> suppressedMiningTargets = new HashMap<>();
	/** 真实准星连续未命中的目标；跨 clear/reselect 保留，避免矿石永远达不到超时。 */
	private BlockPos aimMissTarget;
	private int aimMissTicks;
	Vec3 lastForwardPosition;
	boolean attemptedForward;
	int noMovementTicks;
	BlockPos lastMiningTarget;
	int miningTargetTicks;
	int miningRetryCount;
	int lastDestroyStage = -1;
	boolean lastClickWasInsta;
	private final BorerMineTimings mineTimings = new BorerMineTimings();
	private String timingKey;
	private int timingTicks;
	private boolean timingHeld;
	private boolean timingActive;
	private boolean timingVanillaInsta;
	private float timingProgress;
	boolean miningSelectedOre;
	private boolean lastMinedWasCoal;
	private boolean lastMinedWasQuartz;
	String pendingLogoutReason;
	OreTarget lastMinedOre;
	VerticalMove verticalMove = VerticalMove.NONE;
	/** 卡住后补出的前方落脚列；短时间优先走上去，避免下一拍规划又抢走 W。 */
	BlockPos descentBridgeTarget;
	int descentBridgeAdvanceTicks;
	String routeIssue = "";
	BlockPos jumpOrigin;
	int jumpPressTicks;
	int jumpRetryCooldownTicks;
	int jumpAttempts;
	int flyToggleCooldown;
	boolean meteorFlightHeldByEngine;
	private boolean disconnecting;
	BlockPos escapeShaft;
	int shaftScanTicks;
	BlockPos forcedTallObstacleLower;
	/** 找矿时前方液体的绕行点；有值时朝向跟着它，而不是直指矿脉。 */
	BlockPos liquidDetourPos;
	private int diagnosticTicks;
	int discardCooldown;
	/** 刚朝后扔过废石，这几拍不前进，免得踩进掉落物。 */
	int discardPauseTicks;
	private double prevSteerAlong = Double.NaN;
	private double prevSteerSide = Double.NaN;
	private double prevSteerDist = Double.NaN;
	final BorerTrail trail = new BorerTrail();
	boolean goingHome;
	boolean showingHomeRoute;
	boolean showingShaftPreview;
	/** 预览确认后再开挖时沿用第一次按 B 的朝向，不跟当前视角。 */
	boolean keepPreviewHeading;
	boolean showingAreaPreview;
	BlockPos areaMin;
	BlockPos areaMax;
	boolean areaBoundedDown;
	Direction areaStripAxis;
	BlockPos areaWalkTarget;
	BlockPos areaShaftColumn;
	boolean areaRelocating;
	boolean returningToPortal;
	private boolean wasInNether;
	private boolean netherObserverReady;
	private int portalScanTicks;
	int portalReturnLogTicks;
	BlockPos lastLoggedHomeDest;
	boolean lastLoggedHomeMoving;

	/** 绑定稳定宿主提供的设置与围箱接口。 */
	public DefaultTunnelBorerEngine(BorerHost host) {
		this.host = host;
	}

	/** 当前热加载引擎版本号。 */
	@Override
	public String runtimeVersion() {
		return RUNTIME_VERSION;
	}

	/** 用了 RotationAim（宿主 API 2），旧核心加载不了这个包。 */
	@Override
	public int requiredHostApiVersion() {
		return 2;
	}

	/** 盾构机是否正在运行。 */
	@Override
	public boolean isActive() {
		return active;
	}

	/** 当前模式内部名：FORWARD / DOWN / ORE。 */
	@Override
	public String modeName() {
		return mode.name();
	}

	/** 最近一条给玩家看的状态说明。 */
	@Override
	public String status() {
		return status;
	}

	/** 按指定模式启动，并重置挖矿、找矿和拾取状态。 */
	@Override
	public void start(Minecraft client, String modeName) {
		if (client.player == null || client.level == null) return;
		Mode mode = Mode.fromConfig(modeName);
		if (mode == Mode.AREA && !prepareArea(client)) return;
		host.prepareForBorer(client);
		this.mode = mode;
		host.setBorerLastMode(mode.name());
		host.saveSettings();
		if (keepPreviewHeading) {
			forward = BorerShaftPolicy.headingForPreview(forward, headingFromConfig(client.player));
		} else if (mode == Mode.AREA && areaStripAxis != null) {
			forward = areaStripAxis;
		} else {
			forward = headingFromConfig(client.player);
		}
		keepPreviewHeading = false;
		turnCooldown = 0;
		lastTurnClockwise = true;
		active = true;
		pauseTicks = 4;
		dropWait = 0;
		holdingShield = false;
		combatPauseTicks = 0;
		lavaContactTicks = 0;
		currentTarget = null;
		corridorHeading = null;
		corridorOrigin = null;
		clearConfirmTicks = 0;
		oreTargetPos = null;
		sideOreTargetPos = null;
		ores.resetState();
		liquidSettleTicks = 0;
		liquidSealFails = 0;
		liquidSealFailPos = null;
		lavaBypassTicks = 0;
		sealTarget = null;
		frontOccluded = false;
		occludedTicks = 0;
		blockedOreTargets.clear();
		suppressedMiningTargets.clear();
		aimMissTarget = null;
		aimMissTicks = 0;
		lastForwardPosition = client.player.position();
		attemptedForward = false;
		noMovementTicks = 0;
		lastMiningTarget = null;
		miningTargetTicks = 0;
		miningRetryCount = 0;
		lastDestroyStage = -1;
		lastClickWasInsta = false;
		miningSelectedOre = false;
		lastMinedOre = null;
		lastMinedWasCoal = false;
		lastMinedWasQuartz = false;
		loot.clearIgnored();
		verticalMove = VerticalMove.NONE;
		descentBridgeTarget = null;
		descentBridgeAdvanceTicks = 0;
		routeIssue = "";
		resetJumpControl();
		forcedTallObstacleLower = null;
		liquidDetourPos = null;
		flyToggleCooldown = 0;
		meteorFlightHeldByEngine = false;
		diagnosticTicks = 0;
		discardCooldown = 0;
		discardPauseTicks = 0;
		goingHome = false;
		showingHomeRoute = false;
		showingShaftPreview = false;
		showingAreaPreview = false;
		areaWalkTarget = null;
		areaShaftColumn = null;
		areaRelocating = false;
		returningToPortal = false;
		pendingLogoutReason = null;
		escapeShaft = null;
		trail.loadPortalIfMissing(client);
		if (inNether(client) && trail.portal() != null) trail.ensureFirst(trail.portal());
		trail.beginMiningSession(client, client.player, inNether(client));
		status = "盾构机：" + mode.label;
		String miningRule = mode == Mode.ORE
			? "。先按 Z 开启 Meteor Xray；只朝指定矿种开 1×2 通道，挖完会主动靠近并拾取对应掉落物"
			: mode == Mode.AREA
				? "。1×1 竖井逐格往下（" + BorerAreaPolicy.orderLabel(host.borerAreaOrder()) + "），到底后开飞行换下一格"
			: mode == Mode.FORWARD && turnAroundLava()
				? "。只挖看得见的最前层；前方岩浆会提前左右拐弯（可在盾构页关掉改走直线地铁）"
				: "。只挖看得见的最前层；液体会先封堵";
		message(client, status + miningRule + "。苦力怕会举盾或围箱。End 停止");
		mineTimings.load(client);
		resetMineTimingSample();
		area.reset();
		fileLog(client, "start mode=" + mode + " player=" + precisePosition(client.player)
			+ " forward=" + forward + " ore=" + host.borerOreTarget()
			+ (mode == Mode.AREA && areaMin != null && areaMax != null
				? " area=" + format(areaMin) + ".." + format(areaMax) + " bounded=" + areaBoundedDown
				: ""));
	}

	/** 停止盾构并松开所有按键。 */
	@Override
	public void stop(Minecraft client, String reason) {
		mineTimings.save(client);
		resetMineTimingSample();
		trail.save(client);
		showingShaftPreview = false;
		showingAreaPreview = false;
		keepPreviewHeading = false;
		areaWalkTarget = null;
		areaShaftColumn = null;
		areaRelocating = false;
		area.reset();
		BorerScreenHudBridge.hide(host);
		BorerFlight.restoreSpeed(client);
		resetSteer();
		if (!active) {
			releaseAll(client);
			restoreManualAttack(client);
			return;
		}
		active = false;
		currentTarget = null;
		corridorHeading = null;
		corridorOrigin = null;
		clearConfirmTicks = 0;
		dropWait = 0;
		oreTargetPos = null;
		sideOreTargetPos = null;
		ores.resetState();
		liquidSettleTicks = 0;
		liquidSealFails = 0;
		liquidSealFailPos = null;
		lavaBypassTicks = 0;
		sealTarget = null;
		frontOccluded = false;
		occludedTicks = 0;
		blockedOreTargets.clear();
		suppressedMiningTargets.clear();
		aimMissTarget = null;
		aimMissTicks = 0;
		lastForwardPosition = null;
		attemptedForward = false;
		noMovementTicks = 0;
		lastMiningTarget = null;
		miningTargetTicks = 0;
		miningRetryCount = 0;
		lastDestroyStage = -1;
		lastClickWasInsta = false;
		miningSelectedOre = false;
		lastMinedOre = null;
		lastMinedWasCoal = false;
		lastMinedWasQuartz = false;
		loot.clearIgnored();
		verticalMove = VerticalMove.NONE;
		descentBridgeTarget = null;
		descentBridgeAdvanceTicks = 0;
		routeIssue = "";
		resetJumpControl();
		forcedTallObstacleLower = null;
		liquidDetourPos = null;
		if (returningToPortal) meteorFlightHeldByEngine = false;
		else releaseMeteorFlightIfHeld(client);
		flyToggleCooldown = 0;
		diagnosticTicks = 0;
		discardCooldown = 0;
		discardPauseTicks = 0;
		goingHome = false;
		returningToPortal = false;
		pendingLogoutReason = null;
		escapeShaft = null;
		trail.save(client);
		if ("离开世界".equals(reason)) protectedSealBlocks.clear();
		releaseAll(client);
		restoreManualAttack(client);
		status = "已停止：" + reason;
		fileLog(client, "stop reason=" + reason);
		message(client, "盾构机已停止：" + reason);
	}

	/** 镐快坏则下线（若开启）。 */
	private boolean logoutIfToolsWorn(Minecraft client, LocalPlayer player) {
		if (!BorerItems.allMiningToolsWorn(player)) return false;
		ItemStack hand = player.getMainHandItem();
		int left = BorerItems.isMiningTool(hand) ? BorerItems.remainingDurability(hand) : 0;
		String reason = "镐耐久过低（剩余 " + left + "），挖不了";
		return finishSession(client, player, reason, true);
	}

	/** 挖满或镐坏了：优先沿路回家/飞回地狱门，到家后再下线。 */
	boolean finishSession(Minecraft client, LocalPlayer player, String reason, boolean logoutAfterHome) {
		if (goingHome) return false;
		if (!homeOnDone()) {
			stop(client, reason);
			if (logoutAfterHome) disconnectFromServer(client, reason);
			return true;
		}
		if (player != null) trail.record(client, player);
		restorePersistentState(client);
		if (inNether(client) && trail.portal() != null) trail.ensureFirst(trail.portal());
		boolean canReturn = trail.size() >= 2;
		if (!canReturn) {
			stop(client, reason + "，没有回家路线");
			if (logoutAfterHome) disconnectFromServer(client, reason);
			return true;
		}
		pendingLogoutReason = logoutAfterHome ? reason : null;
		boolean fly = inNether(client) && trail.portal() != null;
		if (fly) {
			beginReturn(client, true);
			enableMeteorFlight(player);
			status = reason + "，沿路飞回地狱门（" + trail.size() + " 个路点）";
		} else {
			beginReturn(client, false);
			status = reason + "，沿原路回家（" + trail.size() + " 个路点）";
		}
		message(client, status);
		fileLog(client, "finish-session fly=" + fly + " points=" + trail.size()
			+ " logout=" + logoutAfterHome + " reason=" + reason);
		return true;
	}

	/** 断开服务器连接（镐坏下线等）。 */
	void disconnectFromServer(Minecraft client, String reason) {
		if (disconnecting) return;
		disconnecting = true;
		client.execute(() -> {
			try {
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
			} finally {
				disconnecting = false;
			}
		});
	}

	/** 运行中则停止。向下挖第一次只预览范围，再按一次才开挖。 */
	@Override
	public void toggle(Minecraft client) {
		if (active) {
			stop(client, "按键停止");
			return;
		}
		Mode last = Mode.FORWARD;
		try {
			last = Mode.valueOf(host.borerLastMode());
		} catch (IllegalArgumentException ignored) {
		}
		if (last == Mode.DOWN && !showingShaftPreview) {
			preview.beginShaft(client);
			return;
		}
		if (last == Mode.AREA && !showingAreaPreview) {
			preview.beginArea(client);
			return;
		}
		keepPreviewHeading = showingShaftPreview && last == Mode.DOWN;
		showingShaftPreview = false;
		showingAreaPreview = false;
		start(client, host.borerLastMode());
	}

	/** 区域挖启动前准备；失败返回 false。 */
	boolean prepareArea(Minecraft client) {
		if (!host.borerAreaSet()) {
			message(client, "先点两个角或输入两点坐标，再开始区域挖");
			return false;
		}
		if (BorerAreaPolicy.tooLarge(host.borerAreaAx(), host.borerAreaAz(), host.borerAreaBx(), host.borerAreaBz())) {
			message(client, "区域太大，最大 " + BorerAreaPolicy.MAX_SPAN + "×" + BorerAreaPolicy.MAX_SPAN);
			return false;
		}
		loadAreaFromHost(client.player != null ? headingFromConfig(client.player) : Direction.EAST);
		return true;
	}

	/** 从宿主读入区域两点。 */
	void loadAreaFromHost() {
		loadAreaFromHost(areaStripAxis != null ? areaStripAxis : Direction.EAST);
	}

	/** 从宿主读入区域两点。 */
	void loadAreaFromHost(Direction heading) {
		int ax = host.borerAreaAx();
		int ay = host.borerAreaAy();
		int az = host.borerAreaAz();
		int bx = host.borerAreaBx();
		int by = host.borerAreaBy();
		int bz = host.borerAreaBz();
		areaMin = new BlockPos(Math.min(ax, bx), Math.min(ay, by), Math.min(az, bz));
		areaMax = new BlockPos(Math.max(ax, bx), Math.max(ay, by), Math.max(az, bz));
		areaBoundedDown = BorerAreaPolicy.boundedDown(ay, by);
		areaStripAxis = BorerAreaPolicy.stripAxis(
			areaMin.getX(), areaMin.getZ(), areaMax.getX(), areaMax.getZ(), heading);
		areaWalkTarget = null;
		areaShaftColumn = null;
		areaRelocating = false;
		area.reset();
	}

	@Override
	/** 关掉区域黄框预览。 */
	public void dismissAreaPreview() {
		showingAreaPreview = false;
		areaMin = null;
		areaMax = null;
		areaWalkTarget = null;
		areaShaftColumn = null;
		areaRelocating = false;
		areaShaftColumn = null;
		areaRelocating = false;
		area.reset();
	}

	/** 下界一律飞行沿原路回去，不挖方块（镐坏了也能走已挖的巷道）。 */
	@Override
	public void goHome(Minecraft client) {
		if (client.player == null || client.level == null) return;
		if (inNether(client)) {
			goToPortal(client);
			return;
		}
		restorePersistentState(client);
		if (!inNether(client)) trail.detachPortalAnchor();
		if (trail.size() < 2) {
			status = "没有可返回的挖矿路线（路点 " + trail.size() + "）";
			message(client, status);
			return;
		}
		beginReturn(client, false);
		status = "沿挖矿原路返回（" + trail.size() + " 个路点）";
		message(client, status);
		fileLog(client, "go-home points=" + trail.size());
	}

	@Override
	/** 开关回家路线显示。 */
	public void toggleHomeRoute(Minecraft client) {
		if (client.player == null || client.level == null) return;
		restorePersistentState(client);
		if (!inNether(client)) trail.detachPortalAnchor();
		if (showingHomeRoute) {
			showingHomeRoute = false;
			status = "已关闭回家路线";
			message(client, status);
			return;
		}
		if (trail.size() < 2) {
			status = "没有挖矿路线可显示（路点 " + trail.size() + "）";
			message(client, status);
			return;
		}
		if (active) stop(client, "改为自己沿箭头回家");
		showingHomeRoute = true;
		status = "回家路线已打开，跟着金色箭头走，不自动走（" + trail.size() + " 个路点）";
		message(client, status);
	}

	@Override
	/** 是否正在显示回家路线。 */
	public boolean isShowingHomeRoute() {
		return showingHomeRoute;
	}

	/** 沿走过的巷道飞回记下的地狱门；没路线时只要有门也会直线飞并躲开岩浆。不挖方块。 */
	@Override
	public void goToPortal(Minecraft client) {
		if (client.player == null || client.level == null) return;
		observeWorld(client);
		restorePersistentState(client);
		if (trail.portal() == null) {
			BlockPos found = findNearbyPortal(client, client.player);
			if (found != null) trail.setPortal(client, found);
		}
		if (!inNether(client)) {
			status = "现在不在下界，没法飞回地狱门";
			message(client, status);
			return;
		}
		if (trail.portal() != null) trail.ensureFirst(trail.portal());
		trail.record(client, client.player);
		if (trail.portal() != null
			&& client.player.position().distanceToSqr(Vec3.atCenterOf(trail.portal())) <= 2.4 * 2.4) {
			status = "已经在地狱门旁";
			message(client, status);
			return;
		}
		if (trail.portal() == null && trail.size() < 2) {
			status = "还没有记下地狱门，也没有挖矿路线。穿过传送门后再挖，才会记路";
			message(client, status);
			return;
		}
		beginReturn(client, true);
		enableMeteorFlight(client.player);
		escapeShaft = BorerHazards.nearestSafeAscent(client, client.player, 12, 16);
		String dest = trail.portal() != null ? "地狱门 " + format(trail.portal()) : "挖矿起点";
		status = "飞行沿原路回" + dest + "（" + trail.size() + " 个路点），不挖方块。青色=路，绿色=无岩浆天井";
		message(client, status);
		fileLog(client, "go-portal points=" + trail.size()
			+ " portal=" + trail.portal()
			+ " first=" + trail.first()
			+ " last=" + trail.last()
			+ " shaft=" + escapeShaft
			+ " flying=" + isFlying(client.player)
			+ " meteor=" + BorerFlight.meteorFlightActive()
			+ " player=" + precisePosition(client.player));
	}

	/** 开始沿路回家或飞回门。 */
	private void beginReturn(Minecraft client, boolean flyToPortal) {
		if (!active) {
			host.prepareForBorer(client);
			mode = Mode.fromConfig(host.borerLastMode());
			forward = headingFromConfig(client.player);
			active = true;
			pauseTicks = 2;
		}
		goingHome = true;
		returningToPortal = flyToPortal;
		trail.resetFollow();
		clearMiningTarget(client, "begin-return-home");
		loot.clear();
		oreTargetPos = null;
		sideOreTargetPos = null;
		portalReturnLogTicks = 0;
		lastLoggedHomeDest = null;
		noMovementTicks = 0;
		releaseMine(client);
	}

	@Override
	/** 是否正在回家。 */
	public boolean isGoingHome() {
		return active && goingHome;
	}

	@Override
	/** 是否正在回地狱门。 */
	public boolean isReturningToPortal() {
		return active && returningToPortal;
	}

	@Override
	/** 是否已记地狱门。 */
	public boolean hasNetherPortal() {
		return trail.portal() != null;
	}

	@Override
	/** 路点数量。 */
	public int trailLength() {
		return trail.size();
	}

	@Override
	/** 清路点但留门。 */
	public void clearTrailKeepPortal() {
		trail.clearKeepPortal();
	}

	@Override
	/** 导出路点快照字符串。 */
	public String exportTrailSnapshot() {
		return trail.snapshot();
	}

	@Override
	/** 导入路点快照。 */
	public void importTrailSnapshot(String snapshot) {
		trail.restore(snapshot);
	}

	@Override
	/** 从磁盘恢复路点/门。 */
	public void restorePersistentState(Minecraft client) {
		trail.loadIfEmpty(client);
		trail.loadPortalIfMissing(client);
	}

	@Override
	/** Meteor 改朝向后再写回。 */
	public void reapplyLook(Minecraft client) {
		if (!active || client.player == null) return;
		if (goingHome) {
			BlockPos dest = trail.last();
			if (dest == null && returningToPortal) dest = trail.portal();
			if (dest == null) return;
			double lookY = returningToPortal ? dest.getY() + 0.5 : client.player.getEyeY() + Math.max(-0.4, dest.getY() + 1.0 - client.player.getEyeY());
			lookAt(client.player, new Vec3(dest.getX() + 0.5, lookY, dest.getZ() + 0.5));
			return;
		}
		if (mode == Mode.AREA) area.reapplyFlyLook(client.player);
	}

	/** 过门后立刻找附近地狱门，下界走动时持续记路。 */
	@Override
	public void observeWorld(Minecraft client) {
		if (client.player == null || client.level == null) {
			wasInNether = false;
			netherObserverReady = false;
			portalScanTicks = 0;
			return;
		}
		boolean nether = inNether(client);
		if (!netherObserverReady) {
			netherObserverReady = true;
			wasInNether = nether;
			restorePersistentState(client);
			if (nether) {
				if (trail.portal() != null) trail.ensureFirst(trail.portal());
				portalScanTicks = 80;
				BlockPos found = findNearbyPortal(client, client.player);
				if (found != null) {
					boolean fresh = trail.portal() == null || trail.portal().distSqr(found) > 64.0;
					trail.setPortal(client, found);
					if (fresh) message(client, "已记下地狱门 " + format(found));
					portalScanTicks = 0;
				}
			}
			if (nether && !goingHome && !active && !showingHomeRoute) trail.recordIdle(client, client.player);
			presentHomeRouteIfNeeded(client);
			preview.presentShaftIfNeeded(client);
			preview.presentAreaIfNeeded(client);
			return;
		}
		if (!nether) {
			if (wasInNether) trail.save(client);
			wasInNether = false;
			portalScanTicks = 0;
			presentHomeRouteIfNeeded(client);
			preview.presentShaftIfNeeded(client);
			preview.presentAreaIfNeeded(client);
			return;
		}
		boolean entered = !wasInNether;
		wasInNether = true;
		if (entered) {
			trail.clear();
			portalScanTicks = 80;
			BlockPos found = findNearbyPortal(client, client.player);
			if (found != null) {
				trail.setPortal(client, found);
				trail.record(client, client.player);
				status = "已记下地狱门 " + format(found);
				message(client, status);
				portalScanTicks = 0;
			}
		} else if (portalScanTicks > 0) {
			portalScanTicks--;
			if (portalScanTicks % 4 == 0) {
				BlockPos found = findNearbyPortal(client, client.player);
				if (found != null) {
					trail.setPortal(client, found);
					trail.record(client, client.player);
					status = "已记下地狱门 " + format(found);
					message(client, status);
					portalScanTicks = 0;
				}
			}
			if (portalScanTicks == 0 && trail.portal() == null) {
				trail.loadPortalIfMissing(client);
				if (trail.portal() != null) {
					trail.ensureFirst(trail.portal());
					message(client, "附近没找到新门，沿用上次地狱门 " + format(trail.portal()));
				}
			}
		}
		if (!goingHome && !active && !showingHomeRoute) trail.recordIdle(client, client.player);
		presentHomeRouteIfNeeded(client);
		preview.presentShaftIfNeeded(client);
		preview.presentAreaIfNeeded(client);
	}

	/** 每客户端 tick：避岩浆、封液体、挖挡路、走近矿石并拾取勾选掉落物。 */
	@Override
	public void tick(Minecraft client) {
		if (!active) return;
		if (client.player == null || client.level == null || client.gameMode == null) {
			stop(client, "离开世界");
			return;
		}
		if (client.screen != null) {
			releaseAll(client);
			status = "先关掉界面再挖";
			statusColor = 0xFFFF55;
			presentStatusHud(client);
			return;
		}

		LocalPlayer player = client.player;
		try {
		// 上一拍躲苦力怕按下的后退键，本拍先松开；苦力怕还在的话下面会重新按上。
		// 不松的话它会和前进键相互抵消，表现成「按着前进却不动」。
		if (retreating) {
			retreating = false;
			client.options.keyDown.setDown(false);
		}
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		pruneSuppressedMiningTargets(client);
		diagnosticTicks++;
		if (diagnosticTicks >= DIAGNOSTIC_INTERVAL_TICKS) {
			diagnosticTicks = 0;
			logDiagnostic(client, player, "periodic");
		}
		if (flyToggleCooldown > 0) flyToggleCooldown--;
		if (!goingHome) trail.record(client, player);
		if (returningToPortal) {
			if (pauseTicks > 0) pauseTicks--;
			home.handle(client, player);
			return;
		}
		if (!goingHome && logoutIfToolsWorn(client, player)) return;
		if (handleFallingSand(client, player)) return;
		if (updateForwardProgress(client, player)) return;
		if (pauseTicks > 0) {
			pauseTicks--;
			releaseMine(client);
			return;
		}
		if (!loot.active() && !goingHome) {
			ores.updateTarget(client, player);
			ores.updateSideTarget(client, player);
		}
		boolean hasMiningObjective = goingHome || mode != Mode.ORE || loot.active() || oreTargetPos != null || sideOreTargetPos != null;

		if (host.surroundActive()) {
			releaseMine(client);
			status = "苦力怕围箱中，围好继续挖";
			overlay(client, status, 0xFFFF55);
			return;
		}

		if (liquids.handleLavaContact(client, player)) return;
		if (liquids.handleWaterContact(client, player)) return;
		if (liquids.handleMagmaBurn(client, player)) return;
		if (turnCooldown > 0) turnCooldown--;
		turnedThisTick = false;
		boolean turnedFromLava = mode == Mode.FORWARD && !goingHome && !loot.active()
			&& tryTurnAroundLava(client, player);
		if (liquidSettleTicks > 0) liquidSettleTicks--;
		BlockPos liquid = !turnedFromLava && !loot.active() && hasMiningObjective && host.borerSealLiquids()
			? liquids.findHazard(client, player) : null;
		if (liquid != null) {
			liquids.handle(client, player, liquid);
			if (mode != Mode.AREA || !area.think.active() || currentTarget == null) return;
		}
		sealTarget = null;

		if (!loot.active() && mode == Mode.ORE && (oreTargetPos != null || sideOreTargetPos != null)) {
			if (liquids.skipOrDetour(client, player)) return;
		}

		Creeper creeper = mobs.findCreeper(client, player);
		if (mobs.creeperImminent(player, creeper)) {
			mobs.handleCreeper(client, player, creeper);
			return;
		}

		String combat = BorerThreats.combatPauseReason(player);
		if (combat != null) combatPauseTicks = 40;
		if (combatPauseTicks > 0) {
			combatPauseTicks--;
			releaseMine(client);
			Entity attacker = mobs.closestCombat(client, player, 12.0);
			if (attacker != null) {
				status = mobs.engageNearbyHostile(client, player, attacker);
				if (combat != null) status = combat + "；" + status;
			} else {
				mobs.raiseShield(client, player);
				boolean sword = BorerItems.selectWeapon(client, player);
				status = (combat != null ? combat : "刚被打过")
					+ (sword ? "，已切剑停手，交给你的自动攻击" : "，已停手，交给你的自动攻击");
			}
			overlay(client, status, 0xFF5555);
			return;
		}

		if (host.borerPauseOnMob()) {
			boolean turnedFromMob = mode == Mode.FORWARD && !goingHome && !loot.active()
				&& mobs.tryTurnAround(client, player);
			if (mode == Mode.ORE && !goingHome && !loot.active()) {
				BlockPos ore = sideOreTargetPos != null ? sideOreTargetPos : oreTargetPos;
				if (ore != null && mobs.nearPos(client, player, ore, 6.0)
					&& ores.skipActive(client, "怪物靠近矿脉 " + format(ore) + "，不围墙，改挖别处")) {
					return;
				}
			}
			double radius = BorerMobPolicy.pauseRadius(host.borerMobRadius());
			Entity close = mobs.closestCombat(client, player, radius);
			if (BorerMobPolicy.pauseMiningForNearby(true, close != null) && !turnedFromMob) {
				releaseMine(client);
				status = mobs.engageNearbyHostile(client, player, close);
				overlay(client, status, 0xFF5555);
				fileLog(client, "mob-engage name=" + close.getName().getString()
					+ " dist=" + String.format(Locale.ROOT, "%.2f", player.distanceTo(close))
					+ " radius=" + radius
					+ " player=" + precisePosition(player));
				return;
			}
		}

		mobs.lowerShield(client);
		mobs.releaseCombatMove(client);
		if (!goingHome && !loot.active() && place.continueDescentBridgeAdvance(client, player)) return;
		if (goingHome) {
			if (home.handle(client, player)) return;
		} else {
			if (mode == Mode.ORE) place.discardExcessStone(client, player);
			if (!loot.active() && mode == Mode.ORE && !skipExperienceLoot() && lastMinedOre != null) {
				loot.tryBeginFromNearby(client, player, lastMinedOre);
			}
			if (loot.active() && handleLootCollection(client, player)) return;
			if (mode == Mode.ORE && oreTargetPos == null && sideOreTargetPos == null) {
				clearMiningTarget(client, "no-ore-goal");
				frontOccluded = false;
				occludedTicks = 0;
				releaseMine(client);
				client.options.keyShift.setDown(false);
				status = ores.status(client) + "；附近也没有可顺路采集的勾选矿石，不会盲目前进";
				overlay(client, status, 0xFFFF55);
				return;
			}
		}

		if (dropWait > 0 && (mode == Mode.DOWN || mode == Mode.AREA)) {
			if (mode == Mode.AREA && BorerAreaPolicy.abortFallWait(player.onGround())) {
				dropWait = 0;
			} else {
				dropWait--;
				fallDown(client, player, "下落，接着挖脚底");
				return;
			}
		}

		if (mode != Mode.DOWN && mode != Mode.AREA && !isFlying(player) && !player.onGround()
			&& verticalMove != VerticalMove.UP && verticalMove != VerticalMove.ADVANCE) {
			releaseMine(client);
			client.options.keyUp.setDown(false);
			client.options.keyJump.setDown(false);
			clearMiningTarget(client, "airborne-wait");
			status = "离地，停步等落稳，不挖立足点、不走进空气";
			overlay(client, status, 0xFFFF55);
			return;
		}

		if (currentTarget != null && isUnsafeFloorMine(client, player, currentTarget)) {
			recoverFromUnsafeFloor(client, player);
		}

		if (currentTarget != null && shouldMine(client, currentTarget)) {
			BlockPos openedLava = BorerHazards.lavaOpenedByMining(client, currentTarget);
			if (openedLava != null && handleOpenedLava(client, player, openedLava)) return;
			BlockPos openedWater = BorerHazards.waterOpenedByMining(client, currentTarget);
			if (openedWater != null && handleOpenedWater(client, player, openedWater)) return;
		}
		if (currentTarget != null && (!shouldMine(client, currentTarget) || tapFinished(client))) {
			recordMineTiming(client);
			BlockPos adjacentOre = mode == Mode.ORE ? corridor.adjacentOreToMine(client, player) : null;
			boolean dropsVisible = mode == Mode.ORE && miningSelectedOre && !skipExperienceLoot()
				&& lastMinedOre != null
				&& loot.hasNearby(client, player, currentTarget, lastMinedOre);
			if (adjacentOre != null && !BorerLootPolicy.collectVisibleBeforeAdjacent(dropsVisible)) {
				setMiningTarget(client, player, adjacentOre, "adjacent-ore-after-clear");
			} else {
				int need = BorerInstaPolicy.clearConfirmTicks(lastClickWasInsta, CLEAR_CONFIRM_TICKS);
				if (need > 0 && clearConfirmTicks < need) {
					clearConfirmTicks++;
					releaseMine(client);
					client.options.keyShift.setDown(false);
					status = "确认服务器已挖掉 " + format(currentTarget);
					overlay(client, status, 0xFFFF55);
					return;
				}
				releaseMine(client);
				client.options.keyShift.setDown(false);
				BlockPos clearedTarget = currentTarget.immutable();
				boolean clearedSelectedOre = miningSelectedOre;
				resetAimMissProgress();
				clearMiningTarget(client, "server-cleared-block");
				if (clearedSelectedOre) {
					if (skipExperienceLoot()) {
						status = lastMinedWasQuartz ? "石英已挖，经验模式不捡石英" : "煤矿已挖，经验模式不捡煤";
						overlay(client, status, 0x55FFFF);
					} else {
						beginLootCollection(player, clearedTarget);
						if (handleLootCollection(client, player)) return;
					}
				}
			}
		}
		if (currentTarget != null && (isProtectedSealBlock(client, currentTarget) || !inMiningReach(player, currentTarget))) {
			releaseMine(client);
			clearMiningTarget(client, "protected-or-out-of-reach");
		}

		if (currentTarget == null) {
			frontOccluded = false;
			if (mode == Mode.FORWARD) tryTurnAroundLava(client, player);
			BlockPos planned = nextTarget(client, player);
			if (planned != null) setMiningTarget(client, player, planned, "planner");
		}
		boolean offCorridor = currentTarget != null && isOffCorridorWall(client, player, currentTarget);
		BlockPos projectedBlocker = offCorridor ? findMovementBlocker(client, player) : null;
		boolean blocksProjectedMovement = currentTarget != null && currentTarget.equals(projectedBlocker);
		if (currentTarget != null && BorerMiningPolicy.rejectAsSideWall(offCorridor, blocksProjectedMovement)) {
			fileLog(client, "skip-side-wall target=" + format(currentTarget)
				+ " origin=" + (corridorOrigin == null ? "-" : format(corridorOrigin))
				+ " heading=" + (corridorHeading == null ? "-" : directionLabel(corridorHeading))
				+ " standCol=" + format(standingColumn(client, player))
				+ " player=" + precisePosition(player));
			BlockPos rejected = currentTarget;
			suppressMiningTarget(client, rejected, SIDE_WALL_SUPPRESS_TICKS, "side-wall");
			releaseMine(client);
			clearMiningTarget(client, "side-wall-replan");
			routeIssue = "已排除误选侧墙 " + format(rejected) + "，下一拍重新规划通道";
			frontOccluded = true;
			status = routeIssue;
			overlay(client, status, 0xFFFF55);
			return;
		}
		if (currentTarget != null && offCorridor && blocksProjectedMovement) {
			fileLog(client, "keep-side-wall-movement-blocker target=" + format(currentTarget)
				+ " origin=" + (corridorOrigin == null ? "-" : format(corridorOrigin))
				+ " heading=" + (corridorHeading == null ? "-" : directionLabel(corridorHeading))
				+ " player=" + precisePosition(player));
		}
		if (currentTarget != null && isUnsafeFloorMine(client, player, currentTarget)) {
			recoverFromUnsafeFloor(client, player);
		}
		if (mode == Mode.AREA && area.allowThink() && !area.simpleShaftDown(client, player)) {
			area.think.note(client, player);
			if (area.think.handle(client, player)) return;
		}
		if (currentTarget != null) {
			BlockPos lifted = liftFallingStack(client, player, currentTarget);
			if (lifted != null) replaceMiningTarget(client, lifted, "falling-stack-top");
		}
		if (currentTarget == null && mode == Mode.ORE && oreTargetPos == null && sideOreTargetPos == null) {
			releaseMine(client);
			client.options.keyShift.setDown(false);
			status = "等待 Meteor Xray 中的" + wantedLabel() + "；附近没有可顺路采集的勾选矿石，不会盲目前进";
			overlay(client, status, 0xFFFF55);
			return;
		}
		if (currentTarget != null) {
			BlockPos openedLava = BorerHazards.lavaOpenedByMining(client, currentTarget);
			if (openedLava != null) {
				if (handleOpenedLava(client, player, openedLava)) return;
				clearMiningTarget(client, "lava-replan");
				BlockPos planned = nextTarget(client, player);
				if (planned != null) setMiningTarget(client, player, planned, "after-lava");
			}
		}
		if (currentTarget != null) {
			BlockPos openedWater = BorerHazards.waterOpenedByMining(client, currentTarget);
			if (openedWater != null) {
				if (handleOpenedWater(client, player, openedWater)) return;
				clearMiningTarget(client, "water-replan");
				BlockPos planned = nextTarget(client, player);
				if (planned != null) setMiningTarget(client, player, planned, "after-water");
			}
		}
		if (currentTarget != null) {
			BlockHitResult hit = resolveMiningHit(client, player, currentTarget);
			if (!miningAxisAim()
				&& client.hitResult instanceof BlockHitResult pick
				&& pick.getType() == HitResult.Type.BLOCK
				&& canPlanMine(client, pick.getBlockPos())
				&& BorerAim.hitInReach(player, pick)
				&& !pick.getBlockPos().equals(currentTarget)
				&& !isUnsafeFloorMine(client, player, pick.getBlockPos())
				&& !isBelowFeetNonOre(client, player, pick.getBlockPos())
				&& !isOffCorridorWall(client, player, pick.getBlockPos())
				&& BorerAim.nearestDistanceSqr(player.getEyePosition(), pick.getBlockPos()) + 0.04
					< BorerAim.nearestDistanceSqr(player.getEyePosition(), currentTarget)) {
				replaceMiningTarget(client, pick.getBlockPos(), "closer-crosshair-hit");
				hit = visibleHitResult(client, player, currentTarget);
				if (hit == null) hit = pick;
			}
			if (hit != null && !hit.getBlockPos().equals(currentTarget)
				&& canPlanMine(client, hit.getBlockPos()) && BorerAim.hitInReach(player, hit)
				&& !isUnsafeFloorMine(client, player, hit.getBlockPos())
				&& !isBelowFeetNonOre(client, player, hit.getBlockPos())
				&& (BorerMiningPolicy.mineRealHitTowardInReachOre(
					wantedBlock(client.level.getBlockState(currentTarget)) && BorerAim.inReach(player, currentTarget),
					false,
					true)
					|| !isOffCorridorWall(client, player, hit.getBlockPos()))) {
				replaceMiningTarget(client, hit.getBlockPos(), "real-obstruction-hit");
			}
			boolean newMiningTarget = !currentTarget.equals(lastMiningTarget);
			if (newMiningTarget) {
				lastMiningTarget = currentTarget;
				miningTargetTicks = 0;
				miningRetryCount = 0;
				lastDestroyStage = -1;
				lastMinedOre = mode == Mode.ORE
					? OreTarget.firstMatching(oreConfig(), client.level.getBlockState(currentTarget))
					: null;
				lastMinedWasCoal = mode == Mode.ORE
					&& OreTarget.COAL.matches(client.level.getBlockState(currentTarget));
				lastMinedWasQuartz = mode == Mode.ORE
					&& OreTarget.QUARTZ.matches(client.level.getBlockState(currentTarget));
				miningSelectedOre = lastMinedOre != null;
				fileLog(client, "mining-target target=" + format(currentTarget)
					+ " block=" + blockLabel(client, currentTarget)
					+ " goal=" + goalLabel() + " player=" + precisePosition(player));
			} else {
				int destroyStage = client.gameMode.getDestroyStage();
				if (destroyStage > 0 && destroyStage > lastDestroyStage) {
					lastDestroyStage = destroyStage;
					miningTargetTicks = 0;
					miningRetryCount = 0;
				} else {
					miningTargetTicks++;
				}
			}
			occludedTicks = 0;
			clearConfirmTicks = 0;
			dropWait = 0;
			boolean hitInReach = hit != null && BorerAim.hitInReach(player, hit);
			boolean canBreak = BorerMiningPolicy.allowAttack(
				currentTarget, hit == null ? null : hit.getBlockPos(), hitInReach);
			if (!canBreak) {
				BlockPos blocked = currentTarget;
				boolean inRange = BorerAim.inReach(player, blocked);
				releaseMine(client);
				BlockPos closer = corridor.mineableInFront(client, player);
				if (closer != null && !closer.equals(blocked) && inMiningReach(player, closer)) {
					replaceMiningTarget(client, closer, "aim-miss-visible-blocker");
					status = "改挖眼前挡路 " + format(closer) + BorerAim.reachInfo(player, closer);
					fileLog(client, "cannot-break-closer from=" + format(blocked)
						+ " to=" + format(closer) + " " + BorerAim.reachInfo(player, blocked));
					overlay(client, status, 0xFFFF55);
					return;
				}
				BlockPos realHit = corridor.mineableRealHit(client, player, blocked);
				if (realHit != null && !realHit.equals(blocked)) {
					replaceMiningTarget(client, realHit, "aim-miss-real-hit");
					status = "改挖准星挡路 " + format(realHit) + BorerAim.reachInfo(player, realHit);
					fileLog(client, "cannot-break-real-hit from=" + format(blocked)
						+ " to=" + format(realHit) + " " + BorerAim.reachInfo(player, blocked));
					overlay(client, status, 0xFFFF55);
					return;
				}
				if (mode != Mode.AREA && walkIntoSafeDrop(client, player)) return;
				if (BorerStairPolicy.keepAimingInsteadOfWalking(inRange, aimHitsTarget(client, player, blocked))
					&& keepMiningInReach(client, player, blocked)) {
					status = "对准再挖 " + format(blocked) + BorerAim.reachInfo(player, blocked);
					fileLog(client, "keep-aiming target=" + format(blocked)
						+ " player=" + precisePosition(player) + " " + BorerAim.reachInfo(player, blocked));
					overlay(client, status, 0xFFFF55);
					return;
				}
				if (mode != Mode.AREA
					&& BorerMiningPolicy.shouldWalkAfterAimMiss(!unsafeToWalk(client, player))) {
					if (!inRange && holdForNearbyVerticalOre(client, player)) {
						clearMiningTarget(client, "hold-nearby-vertical-ore");
						return;
					}
					if (BorerApproachPolicy.approachTargetInsteadOfCorridor(inRange)) {
						approachMiningBlock(client, player, blocked);
						status = "目标超出可挖距离，飞近再挖 "
							+ format(blocked) + BorerAim.reachInfo(player, blocked);
						if (miningTargetTicks % 20 == 0) {
							fileLog(client, "cannot-break-approach target=" + format(blocked)
								+ " player=" + precisePosition(player)
								+ " " + BorerAim.reachInfo(player, blocked)
								+ " heading=" + directionLabel(forward));
						}
						overlay(client, status, 0xFFFF55);
						return;
					}
					walkForwardCentered(client, player);
					clearMiningTarget(client, "aim-miss-walk");
					status = "准星未命中，安全走近换角度再挖 "
						+ format(blocked) + BorerAim.reachInfo(player, blocked);
					fileLog(client, "cannot-break-walk target=" + format(blocked) + " inRange=" + inRange
						+ " player=" + precisePosition(player) + " " + BorerAim.reachInfo(player, blocked));
					overlay(client, status, 0xFFFF55);
					return;
				}
				if (recordAimMiss(client, blocked, "aim-miss-unsafe")) return;
				clearMiningTarget(client, "aim-miss-unsafe-replan");
				routeIssue = "准星未命中且前方不安全，已换通道挡路";
				status = (inRange ? "准星打不到且前方不安全，重新规划 " : "目标超出距离且前方不安全，重新规划 ")
					+ format(blocked) + BorerAim.reachInfo(player, blocked);
				fileLog(client, "cannot-break target=" + format(blocked)
					+ " inRange=" + inRange + " standCol=" + format(standingColumn(client, player))
					+ " player=" + precisePosition(player) + " " + BorerAim.reachInfo(player, blocked));
				overlay(client, status, 0xFFFF55);
				return;
			} else {
				boolean tooFar = !BorerAim.inReach(player, currentTarget)
					|| player.getEyePosition().distanceTo(hit.getLocation()) > BorerAim.breakReach(player);
				boolean stalled = !newMiningTarget && miningRetryCount >= 1
					&& client.gameMode.getDestroyStage() < 0;
				if (tooFar || stalled) {
					releaseMine(client);
					BlockPos closer = corridor.mineableInFront(client, player);
					if (closer != null && !closer.equals(currentTarget) && inMiningReach(player, closer)) {
						replaceMiningTarget(client, closer, "stalled-visible-blocker");
						status = "改挖眼前挡路 " + format(closer) + BorerAim.reachInfo(player, closer);
						overlay(client, status, 0xFFFF55);
						return;
					}
					if (walkIntoSafeDrop(client, player)) return;
					if (BorerStairPolicy.keepAimingInsteadOfWalking(
						BorerAim.inReach(player, currentTarget), aimHitsTarget(client, player, currentTarget))
						&& keepMiningInReach(client, player, currentTarget)) {
						status = "对准再挖 " + format(currentTarget) + BorerAim.reachInfo(player, currentTarget);
						overlay(client, status, 0xFFFF55);
						return;
					}
					if (!unsafeToWalk(client, player)) {
						if (holdForNearbyVerticalOre(client, player)) return;
						if (!BorerApproachPolicy.walkCorridorWhenTooFar(mode == Mode.AREA)
							|| !BorerAim.inReach(player, currentTarget)) {
							approachMiningBlock(client, player, currentTarget);
							status = "目标偏远，飞近再挖 "
								+ format(currentTarget) + BorerAim.reachInfo(player, currentTarget);
							overlay(client, status, 0xFFFF55);
							return;
						}
						walkForwardCentered(client, player);
						status = (stalled ? "挖不动，走近再挖 " : "目标偏远，走近再挖 ")
							+ format(currentTarget) + BorerAim.reachInfo(player, currentTarget);
						overlay(client, status, 0xFFFF55);
						return;
					}
					client.options.keyUp.setDown(false);
					BlockPos blockedFar = currentTarget;
					clearMiningTarget(client, "too-far-unsafe-replan");
					status = "目标偏远且前方不能走，改挖通道 " + format(blockedFar) + BorerAim.reachInfo(player, blockedFar);
					fileLog(client, "too-far-unsafe from=" + format(blockedFar)
						+ " player=" + precisePosition(player) + " " + BorerAim.reachInfo(player, blockedFar));
					overlay(client, status, 0xFFFF55);
					return;
				}
				place.selectMiningTool(client, player, currentTarget);
				if (logoutIfToolsWorn(client, player)) return;
				lookAtMiningHit(client, player, hit);
				BlockHitResult freshHit = BorerAim.clipView(client, player);
				boolean freshInReach = freshHit != null && BorerAim.hitInReach(player, freshHit);
				if (!BorerMiningPolicy.allowAttack(
					currentTarget, freshHit == null ? null : freshHit.getBlockPos(), freshInReach)) {
					BlockPos missed = currentTarget;
					releaseMine(client);
					fileLog(client, "aim-miss-before-attack target=" + format(missed)
						+ " actual=" + (freshHit == null ? "-" : format(freshHit.getBlockPos()))
						+ " player=" + precisePosition(player));
					BlockPos realHit = corridor.mineableRealHit(client, player, missed);
					if (realHit == null && mode == Mode.AREA && freshHit != null
						&& BorerAim.hitInReach(player, freshHit)
						&& canPlanMine(client, freshHit.getBlockPos())) {
						BlockPos cand = freshHit.getBlockPos();
						boolean sameShaft = areaShaftColumn != null
							&& cand.getX() == areaShaftColumn.getX()
							&& cand.getZ() == areaShaftColumn.getZ();
						if (BorerAreaPolicy.allowAimMissRetarget(sameShaft)) {
							realHit = cand.immutable();
						}
					}
					if (realHit != null && !realHit.equals(missed)) {
						replaceMiningTarget(client, realHit, "aim-miss-before-attack-real-hit");
						status = "改挖准星挡路 " + format(realHit) + BorerAim.reachInfo(player, realHit);
						overlay(client, status, 0xFFFF55);
						return;
					}
					if (recordAimMiss(client, missed, "aim-changed-before-attack")) return;
					boolean safeWalk = mode != Mode.AREA
						&& BorerMiningPolicy.shouldWalkAfterAimMiss(!unsafeToWalk(client, player));
					if (mode == Mode.AREA) {
						client.options.keyUp.setDown(false);
						client.options.keyDown.setDown(false);
						client.options.keyLeft.setDown(false);
						client.options.keyRight.setDown(false);
						client.options.keyJump.setDown(false);
					} else if (safeWalk) {
						walkForwardCentered(client, player);
					}
					clearMiningTarget(client, "aim-changed-before-attack");
					status = safeWalk
						? "准星没有真正命中，已松开攻击并走近换角度 " + format(missed)
						: "准星没有真正命中，已松开攻击并重新规划 " + format(missed);
					overlay(client, status, 0xFFFF55);
					return;
				}
				hit = freshHit;
				client.hitResult = hit;
				client.crosshairPickEntity = null;
				boolean retryMining = !newMiningTarget && miningTargetTicks > 0
					&& miningTargetTicks % MINING_RETRY_TICKS == 0;
				applyMineCadence(client, player, currentTarget, newMiningTarget, retryMining);
				if (retryMining) {
					miningRetryCount++;
					fileLog(client, "mining-retry count=" + miningRetryCount
						+ " target=" + format(currentTarget)
						+ " block=" + blockLabel(client, currentTarget)
						+ " stage=" + client.gameMode.getDestroyStage()
						+ " hitFace=" + hit.getDirection()
						+ " player=" + precisePosition(player));
				}
				if (mode == Mode.ORE && miningTargetTicks >= MINING_STALL_TICKS) {
					logDiagnostic(client, player, "mining-timeout");
					if (miningSelectedOre) {
						ores.skipActive(client, "遮挡 " + format(currentTarget) + " 重试 " + miningRetryCount + " 次后连续 10 秒没有破坏进度");
					} else {
						releaseMine(client);
						fileLog(client, "abandon-block target=" + format(currentTarget)
							+ " block=" + blockLabel(client, currentTarget)
							+ " reason=10s-no-progress keep-ore=" + goalLabel());
						BlockPos stalledBlock = currentTarget;
						if (BorerMiningPolicy.shouldSuppressRetry(false, true)) {
							suppressMiningTarget(client, stalledBlock, STALLED_BLOCK_SUPPRESS_TICKS, "10s-no-progress");
						}
						clearMiningTarget(client, "non-ore-timeout-replan");
					}
					return;
				}
				resetAimMissProgress();
				client.options.keyUp.setDown(false);
				client.options.keyJump.setDown(false);
				client.options.keyShift.setDown(mode == Mode.DOWN && isFlying(player));
				if (mode == Mode.AREA) {
					client.options.keyDown.setDown(false);
					client.options.keyLeft.setDown(false);
					client.options.keyRight.setDown(false);
				}
				String retryNote = miningRetryCount > 0 ? "，已重试 " + miningRetryCount + " 次" : "";
				status = mode.label + "  " + format(currentTarget) + reachInfo(player, currentTarget) + retryNote;
				if (mode == Mode.ORE && sideOreTargetPos != null && !sideOreTargetPos.equals(currentTarget)) {
					status = "顺路" + blockOreLabel(client, sideOreTargetPos) + " · " + status;
				}
				if (turnedThisTick) status = "拐弯 " + directionLabel(forward) + " · " + status;
				overlay(client, status, 0x55FFFF);
				return;
			}
		}
		lastMiningTarget = null;
		miningTargetTicks = 0;
		miningRetryCount = 0;
		lastDestroyStage = -1;
		miningSelectedOre = false;

		if (mode == Mode.ORE && ores.skipIfHeightOrBedrock(client, player)) return;

		client.options.keyAttack.setDown(false);
		client.gameMode.stopDestroyBlock();
		if (mode == Mode.ORE && verticalMove != VerticalMove.NONE) {
			boolean moving = verticalMove != VerticalMove.PREPARE;
			if (verticalMove == VerticalMove.DOWN) {
				BlockPos adjacent = corridor.adjacentOreToMine(client, player);
				if (adjacent != null) {
					setMiningTarget(client, player, adjacent, "adjacent-ore-instead-of-down");
					verticalMove = VerticalMove.NONE;
					status = "改挖身旁矿 " + format(adjacent) + reachInfo(player, adjacent);
					overlay(client, status, 0xFFFF55);
					return;
				}
				BlockPos front = standingColumn(client, player).relative(forward);
				int drop = BorerHazards.safeFallDepth(client, front);
				if (!BorerStairPolicy.shouldWalkDown(drop)) {
					BlockPos stair = vertical.nextDownStairBlock(client, player, front);
					if (stair != null) {
						setMiningTarget(client, player, stair, "down-stair");
						verticalMove = VerticalMove.NONE;
						status = "向下挖台阶 " + format(stair) + reachInfo(player, stair);
						overlay(client, status, 0xFFFF55);
						return;
					}
				}
				if (drop == 0 && BorerStairPolicy.shouldWalkWhileDescending(drop)) {
					verticalMove = VerticalMove.NONE;
				} else {
					moving = canStepDownSafely(client, player);
				}
			}
			if (verticalMove == VerticalMove.UP && walkableOneBlockStepAhead(client, player)) {
				moving = true;
			}
			if (verticalMove != VerticalMove.NONE) {
				if (moving) {
					faceTowardPathCenter(player);
					nudgeToColumnCenter(client, player);
				}
				else faceForward(player);
				client.options.keyUp.setDown(moving);
				boolean stepping = verticalMove == VerticalMove.UP && walkableOneBlockStepAhead(client, player);
				boolean jumping = verticalMove == VerticalMove.UP && !stepping && vertical.pressJump(client, player);
				client.options.keyJump.setDown(jumping);
				client.options.keyShift.setDown(verticalMove == VerticalMove.DOWN && isFlying(player));
				attemptedForward = moving;
				BlockPos goal = sideOreTargetPos != null ? sideOreTargetPos : oreTargetPos;
				status = switch (verticalMove) {
					case PREPARE -> "临时台阶已放置，正在检查头顶空间";
					case ADVANCE -> "先向前清路，寻找可向上的阶梯位置";
					case UP -> stepping ? "Step 跨上 1 格"
						: jumping ? "短按跳跃，上台阶接近" : "对准台阶，等待安全起跳";
					case DOWN -> moving ? "前方落差，走下去接近" : "向下挖阶梯接近";
					case NONE -> "垂直寻路";
				};
				if (goal != null) status += " " + format(goal) + reachInfo(player, goal);
				overlay(client, status, 0x55FFFF);
				return;
			}
		}
		if (mode == Mode.AREA) {
			area.handleMove(client, player);
		} else if (mode != Mode.DOWN) {
			if (frontOccluded) {
				BlockPos sight = corridor.mineableInFront(client, player);
				if (sight == null) sight = corridor.adjacentOreToMine(client, player);
				if (sight != null) {
					setMiningTarget(client, player, sight, "occluded-visible-blocker");
					frontOccluded = false;
					occludedTicks = 0;
					status = "改挖眼前挡路 " + format(sight) + BorerAim.reachInfo(player, sight);
					overlay(client, status, 0xFFFF55);
					return;
				}
				if (walkIntoSafeDrop(client, player)) {
					frontOccluded = false;
					occludedTicks = 0;
					return;
				}
				if (walkableOneBlockStepAhead(client, player)) {
					frontOccluded = false;
					occludedTicks = 0;
					walkForwardCentered(client, player);
					status = "前方 1 格台阶，走上去接近";
					overlay(client, status, 0x55FFFF);
					return;
				}
				if (mode == Mode.ORE && isPathBlockedReason(routeIssue)) {
					ores.skipActive(client, routeIssue);
					return;
				}
				faceForward(player);
				occludedTicks++;
				client.options.keyUp.setDown(false);
				client.options.keyShift.setDown(false);
				status = routeIssue.isBlank()
					? "最前层仍有方块，但当前没有可挖视线，已原地等待"
					: routeIssue + "，已原地等待";
				if (occludedTicks >= ROUTE_TIMEOUT_TICKS) {
					if (mode == Mode.ORE) ores.skipActive(client,
						routeIssue.isBlank() ? "目标路径连续 4 秒没有可挖视线" : routeIssue);
					else stop(client, "最前层被遮挡，已释放手动挖掘");
					return;
				}
			} else if (unsafeToWalk(client, player)) {
				client.options.keyAttack.setDown(false);
				if (mode == Mode.FORWARD && tryTurnAroundLava(client, player)) {
					client.options.keyUp.setDown(false);
					return;
				}
				BlockPos front = player.blockPosition().relative(forward);
				if (canPlanMine(client, front) && inMiningReach(player, front)
					&& (canSeeBlock(client, player, front) || hasCollision(client, front))) {
					setMiningTarget(client, player, front, "unsafe-walk-blocker");
					occludedTicks = 0;
					client.options.keyUp.setDown(false);
					status = "先挖眼前挡路，再过前方岩浆";
					overlay(client, status, 0xFFFF55);
					return;
				}
				client.options.keyUp.setDown(false);
				if (place.shouldBridgeDrops(player) && place.placeWalkingSupport(client, player)) {
					occludedTicks = 0;
				} else if (occludedTicks >= 8 && !(mode == Mode.FORWARD && turnAroundLava())
					&& place.startJumpOverLava(client, player)) {
					occludedTicks = 0;
					overlay(client, status, 0xFFFF55);
					return;
				} else if (place.shouldBridgeDrops(player)) {
					occludedTicks++;
					if (status.isBlank() || !status.contains("铺路") && !status.contains("岩浆") && !status.contains("跳过")) {
						status = "前方岩浆，正在铺路；铺不成再挖顶跳过";
					}
					if (mode == Mode.ORE && occludedTicks >= ROUTE_TIMEOUT_TICKS) {
						ores.skipActive(client, "目标路线前方地板连续 4 秒不安全，铺路和跳过都没成");
						return;
					}
				} else {
					occludedTicks = 0;
					status = "前方没有立足点，已停步，不往下掉";
				}
			} else {
				BlockPos wall = corridor.nextClearableCorridorBlock(client, player);
				if (wall != null) {
					setMiningTarget(client, player, wall, "clear-corridor-before-walk");
					occludedTicks = 0;
					client.options.keyUp.setDown(false);
					status = "改挖眼前通道 " + format(wall) + BorerAim.reachInfo(player, wall);
					overlay(client, status, 0xFFFF55);
					return;
				}
				occludedTicks = 0;
				resetJumpControl();
				BlockPos floorOre = corridor.adjacentOreToMine(client, player);
				if (floorOre != null) {
					BlockPos stand = standingColumn(client, player);
					if (BorerOrePolicy.mineAdjacentInsteadOfHold(
						Math.abs(floorOre.getX() - stand.getX()) + Math.abs(floorOre.getZ() - stand.getZ()),
						floorOre.getY() - stand.getY(),
						true)) {
						setMiningTarget(client, player, floorOre, "adjacent-ore-instead-of-hold");
						client.options.keyUp.setDown(false);
						status = "改挖身旁矿 " + format(floorOre) + BorerAim.reachInfo(player, floorOre);
						overlay(client, status, 0xFFFF55);
						return;
					}
				}
				if (holdForNearbyVerticalOre(client, player)) return;
				int dropAhead = BorerHazards.safeFallDepth(client, player.blockPosition().relative(forward));
				if (BorerFallPolicy.shouldWalkIntoDrop(dropAhead, vertical.climbingToOre(client, player))) {
					walkForwardCentered(client, player);
				} else if (BorerFallPolicy.climbDropNeedsAscent(dropAhead, vertical.climbingToOre(client, player))) {
					if (vertical.handleClimbDropAscent(client, player, dropAhead)) return;
					walkForwardCentered(client, player);
				} else {
					walkForwardCentered(client, player);
				}
				client.options.keyShift.setDown(BorerHazards.playerOnMagma(client, player));
				status = mode == Mode.ORE && noMovementTicks >= MOVEMENT_RECOVERY_TICKS
					? "前进受阻，正在重新对准通道中心" : oreTravelStatus(player);
				if (dropAhead > 0 && BorerFallPolicy.shouldWalkIntoDrop(dropAhead, vertical.climbingToOre(client, player))) {
					status = "前方 " + dropAhead + " 格落差，直接落下"
						+ (BorerFlight.meteorNoFallActive() ? "（NoFall）" : "")
						+ " · " + status;
				}
			}
		} else if (frontOccluded) {
			occludedTicks++;
			client.options.keyShift.setDown(false);
			status = "脚下前层仍有方块，但当前没有可挖视线，已原地等待";
			if (occludedTicks >= ROUTE_TIMEOUT_TICKS) {
				stop(client, "脚下前层被遮挡，已释放手动挖掘");
				return;
			}
		} else {
			occludedTicks = 0;
			dropWait = 8;
			fallDown(client, player, "脚下已通，下落继续挖");
		}
		if (turnedThisTick) status = "拐弯 " + directionLabel(forward) + (status.isBlank() ? "" : " · " + status);
		overlay(client, status, 0x55FFFF);
		} finally {
			if (discardPauseTicks > 0 && client.player != null && client.options != null) {
				client.options.keyUp.setDown(false);
				discardPauseTicks--;
			}
			presentStatusHud(client);
		}
	}

	/** 向下模式：松开挖掘并下落到下一层。落点不安全（岩浆/水/太深）则停步。 */
	void fallDown(Minecraft client, LocalPlayer player, String why) {
		if (!isFlying(player) && !fallLandingSafe(client, player)) {
			dropWait = 0;
			releaseMine(client);
			client.options.keyUp.setDown(false);
			client.options.keyAttack.setDown(false);
			if (client.gameMode != null) client.gameMode.stopDestroyBlock();
			status = "下方落差不安全，已停步不下落";
			fileLog(client, "fall-abort-unsafe player=" + precisePosition(player)
				+ " standCol=" + format(standingColumn(client, player)));
			overlay(client, status, 0xFF5555);
			return;
		}
		lookAt(player, player.blockPosition().below(2));
		client.options.keyAttack.setDown(false);
		if (client.gameMode != null) client.gameMode.stopDestroyBlock();
		boolean centering = centerOnShaftColumn(client, player, mode == Mode.AREA);
		if (mode == Mode.AREA && centering) {
			client.options.keyShift.setDown(false);
			status = "先对准 1×1 格心，再垂直下潜";
			overlay(client, status, 0xFFFF55);
			return;
		}
		if (!centering) {
			client.options.keyUp.setDown(false);
			client.options.keyDown.setDown(false);
		}
		if (isFlying(player)) {
			client.options.keyShift.setDown(true);
			status = why + (centering ? " 边对准边下" : "（飞行下潜）");
		} else {
			client.options.keyShift.setDown(false);
			status = why;
		}
		overlay(client, status, 0x55FFFF);
	}

	/** 从当前身体格往下扫：3/48 格内要有安全落点，途中不能有水/岩浆。 */
	private boolean fallLandingSafe(Minecraft client, LocalPlayer player) {
		if (client.level == null || player == null) return false;
		BlockPos probe = player.blockPosition();
		for (int dy = 0; dy <= 2; dy++) {
			BlockPos pos = probe.below(dy);
			if (BorerHazards.isLavaFluid(client, pos) || BorerHazards.isWater(client, pos)) return false;
			if (BorerHazards.isMagma(client, pos) && dy <= 1) return false;
		}
		return BorerFallPolicy.canWalk(BorerHazards.safeFallDepth(client, probe));
	}

	/** 检测前进是否卡住；卡住则改挖贴身挡路。 */
	private boolean updateForwardProgress(Minecraft client, LocalPlayer player) {
		Vec3 position = player.position();
		if (attemptedForward && lastForwardPosition != null) {
			double dx = position.x - lastForwardPosition.x;
			double dz = position.z - lastForwardPosition.z;
			if (dx * dx + dz * dz < 0.0004) noMovementTicks++;
			else noMovementTicks = 0;
		} else {
			noMovementTicks = 0;
		}
		attemptedForward = false;
		lastForwardPosition = position;
		if (!goingHome && mode == Mode.ORE && noMovementTicks >= MOVEMENT_RECOVERY_TICKS) {
			int safeDrop = safeDropAhead(client, player);
			if (safeDrop > 0) {
				if (offColumnCenter(client, player)) {
					status = "落差前贴着侧墙，正在回到通道中心";
					overlay(client, status, 0xFFFF55);
					return false;
				}
				BlockPos blocker = findMovementBlocker(client, player);
				if (blocker != null) {
					logDiagnostic(client, player, "stalled-descent-blocker");
					setMiningTarget(client, player, blocker, "stalled-descent-blocker");
					noMovementTicks = 0;
					releaseMine(client);
					status = "落差前被侧角卡住，先挖挡路 " + format(blocker);
					overlay(client, status, 0xFFFF55);
					return false;
				}
				if (BorerFallPolicy.shouldRecoverStalledSafeDrop(safeDrop, noMovementTicks)) {
					logDiagnostic(client, player, "stalled-safe-drop");
					if (place.placeStalledDescentSupport(client, player, safeDrop)) {
						noMovementTicks = 0;
						return true;
					}
					if (enableMeteorFlight(player)) {
						client.options.keyJump.setDown(true);
						walkForwardCentered(client, player);
						status = "落差前垫块失败，已开飞行越过";
						fileLog(client, "stalled-drop-flight drop=" + safeDrop
							+ " player=" + precisePosition(player));
						overlay(client, status, 0xFFFF55);
						noMovementTicks = 0;
						return true;
					}
				}
				if (noMovementTicks >= MOVEMENT_TIMEOUT_TICKS) {
					logDiagnostic(client, player, "stalled-drop-timeout");
					return ores.skipActive(client, "安全落差前连续 6 秒仍无法居中、垫块或飞行通过");
				}
				return false;
			}
			if (offColumnCenter(client, player)) {
				return false;
			}
			BlockPos blocker = findMovementBlocker(client, player);
			if (blocker != null) {
				logDiagnostic(client, player, "movement-blocker");
				setMiningTarget(client, player, blocker, "movement-blocker");
				noMovementTicks = 0;
				releaseMine(client);
				status = "前进受阻，改为清理贴身方块 " + format(blocker);
				overlay(client, status, 0xFFFF55);
				return false;
			}
			if (noMovementTicks >= MOVEMENT_TIMEOUT_TICKS) {
				logDiagnostic(client, player, "movement-timeout");
				return ores.skipActive(client, "连续按前进 6 秒，重新对准通道中心后仍没有移动");
			}
		}
		return false;
	}

	/** 找出挡住碰撞箱、当前够得着的方块。贴脸碰撞不要求视线，避免站在台阶边缘对着头顶石头却判看不见。 */
	BlockPos findMovementBlocker(Minecraft client, LocalPlayer player) {
		BlockPos jammed = collidingHeadBlock(client, player);
		if (jammed != null) return jammed;
		AABB projected = player.getBoundingBox()
			.move(forward.getStepX() * 0.35, 0.0, forward.getStepZ() * 0.35)
			.inflate(0.01);
		return collidingMineable(client, player, projected, true);
	}

	/** 选出下一步该挖的方块：通道、挡路或垂直阶梯。 */
	private BlockPos nextTarget(Minecraft client, LocalPlayer player) {
		verticalMove = VerticalMove.NONE;
		routeIssue = "";
		BlockPos feet = player.blockPosition();
		int width = effectiveWidth();
		int height = effectiveHeight();
		int half = width / 2;
		if (mode == Mode.AREA) return area.nextTarget(client, player);
		if (mode == Mode.DOWN) {
			for (int depth = 0; depth <= 8; depth++) {
				List<BlockPos> layer = new ArrayList<>();
				boolean liquidBelow = false;
				for (BlockPos column : shaftColumns(feet)) {
					BlockPos pos = column.below(depth);
					if (BorerHazards.isWater(client, pos) || BorerHazards.isLavaFluid(client, pos)) liquidBelow = true;
					if ((depth > 0 || !pos.equals(feet)) && canPlanMine(client, pos)) layer.add(pos);
				}
				if (!layer.isEmpty()) {
					layer.sort(Comparator
						.comparingInt((BlockPos pos) -> Math.abs(pos.getX() - feet.getX()) + Math.abs(pos.getZ() - feet.getZ()))
						.thenComparingDouble(pos -> pos.distSqr(feet)));
					for (BlockPos pos : layer) {
						if (inMiningReach(player, pos) && canSeeBlock(client, player, pos)) return pos;
					}
					if (layer.stream().anyMatch(pos -> inMiningReach(player, pos))) frontOccluded = true;
					return null;
				}
				if (liquidBelow) {
					frontOccluded = true;
					routeIssue = "脚下是水，不往下掉，先封";
					return null;
				}
			}
			return null;
		}
		BlockPos oreGoal = sideOreTargetPos != null ? sideOreTargetPos : oreTargetPos;
		BlockPos approach = liquidDetourPos != null ? liquidDetourPos : oreGoal;
		if (mode == Mode.ORE) {
			BlockPos adjacent = corridor.adjacentOreToMine(client, player);
			if (adjacent != null) return adjacent;
			BlockPos jammed = collidingHeadBlock(client, player);
			if (jammed != null) return jammed;
			BlockPos oreCorridor = corridor.nextOreBlock(client, player);
			if (oreCorridor != null) return oreCorridor;
			if (!axisAim()) {
				BlockPos aimed = corridor.aimedMineable(client, player);
				if (aimed != null) return aimed;
			}
		}
		if (mode == Mode.ORE && approach != null && needsVerticalRoute(feet, approach)) {
			BlockPos verticalTarget = vertical.nextRouteTarget(client, player, approach);
			if (verticalTarget != null) return verticalTarget;
			if (canMineDirectly(client, player, approach)) return approach.immutable();
			if (verticalMove != VerticalMove.NONE || frontOccluded) return null;
		}
		if (mode == Mode.ORE && sideOreTargetPos != null && liquidDetourPos == null) {
			if (!axisAim()) {
				BlockPos sideTarget = nextOreOrObstruction(client, player, sideOreTargetPos);
				if (sideTarget != null) return sideTarget;
			}
			int horizontalDistance = Math.abs(sideOreTargetPos.getX() - feet.getX()) + Math.abs(sideOreTargetPos.getZ() - feet.getZ());
			if (horizontalDistance > 1) lockHeadingToward(feet, sideOreTargetPos);
			else sideOreTargetPos = null;
		}
		if (mode == Mode.ORE && sideOreTargetPos == null && approach != null) {
			if (!axisAim()) {
				BlockPos target = nextOreOrObstruction(client, player, approach);
				if (target != null) return target;
			}
			BlockPos adjacent = corridor.adjacentOreToMine(client, player);
			if (adjacent != null) return adjacent;
			int horizontalDistance = Math.abs(approach.getX() - feet.getX()) + Math.abs(approach.getZ() - feet.getZ());
			if (liquidDetourPos == null && horizontalDistance <= 1) {
				BlockPos next = feet.relative(forward);
				if (!hasCollision(client, next) && !hasCollision(client, next.above())) return null;
				frontOccluded = true;
				return null;
			}
		}
		int ahead = effectiveLookAhead();
		for (int dist = 0; dist <= ahead; dist++) {
			List<BlockPos> layer = new ArrayList<>();
			BlockPos protectedBarrier = null;
			for (int dy = 0; dy < height; dy++) {
				for (int dx = -half; dx <= half; dx++) {
					BlockPos pos = offset(feet, dist, dx, dy);
					if (isProtectedSealBlock(client, pos)) {
						if (protectedBarrier == null) protectedBarrier = pos.immutable();
						continue;
					}
					if (canPlanMine(client, pos)) layer.add(pos);
				}
			}
			if (protectedBarrier != null) {
				for (BlockPos pos : layer) {
					if (corridor.canAttemptMine(client, player, pos, dist)) return pos;
				}
				frontOccluded = true;
				routeIssue = "前方封水方块 " + format(protectedBarrier) + " 正在阻止水流，已保留不再挖掉";
				return null;
			}
			if (layer.isEmpty()) continue;
			layer.sort(Comparator
				.comparingInt((BlockPos pos) -> Math.abs(lateralDistance(feet, pos)))
				.thenComparingInt(BlockPos::getY)
				.thenComparingDouble(pos -> pos.distSqr(feet)));
			for (BlockPos pos : layer) {
				if (corridor.canAttemptMine(client, player, pos, dist)) return pos;
			}
			boolean anyReachable = false;
			boolean onlyWalkableSteps = true;
			for (BlockPos pos : layer) {
				if (!inMiningReach(player, pos)) continue;
				anyReachable = true;
				if (!isWalkableOneBlockStep(client, player, pos)) onlyWalkableSteps = false;
			}
			if (BorerStairPolicy.occludeWhenFrontBlocked(anyReachable, onlyWalkableSteps)) {
				frontOccluded = true;
			}
			return null;
		}
		return null;
	}

	/** 沿朝向的轴向距离。 */
	private int alongDistance(BlockPos feet, BlockPos pos, Direction heading) {
		return (pos.getX() - feet.getX()) * heading.getStepX() + (pos.getZ() - feet.getZ()) * heading.getStepZ();
	}

	/** 相对朝向的侧向距离。 */
	int lateralDistance(BlockPos feet, BlockPos pos) {
		return lateralDistance(feet, pos, forward);
	}

	/** 相对朝向的侧向距离。 */
	int lateralDistance(BlockPos feet, BlockPos pos, Direction heading) {
		Direction right = heading.getClockWise();
		return (pos.getX() - feet.getX()) * right.getStepX() + (pos.getZ() - feet.getZ()) * right.getStepZ();
	}

	/** 竖井截面：宽度×高度的整层矩形（含斜角），以脚下为原点。偶数边长多出来的在右/前。 */
	List<BlockPos> shaftColumns(BlockPos feet) {
		int wide = effectiveWidth();
		int along = effectiveHeight();
		Direction right = forward.getClockWise();
		int startRight = BorerShaftPolicy.startOffset(wide);
		int startForward = BorerShaftPolicy.startOffset(along);
		List<BlockPos> columns = new ArrayList<>();
		for (int z = 0; z < along; z++) {
			for (int x = 0; x < wide; x++) {
				columns.add(feet.relative(right, startRight + x).relative(forward, startForward + z));
			}
		}
		return columns;
	}

	/** 从配置解析锁定朝向。 */
	Direction headingFromConfig(LocalPlayer player) {
		String configuredHeading = host.borerHeading();
		String heading = configuredHeading == null ? "LOOK" : configuredHeading.toUpperCase();
		if (!heading.equals("LOOK")) {
			try {
				Direction locked = Direction.valueOf(heading);
				if (locked.getAxis() != Direction.Axis.Y) return locked;
			} catch (IllegalArgumentException ignored) {
			}
		}
		Direction look = player.getDirection();
		return look.getAxis() == Direction.Axis.Y ? Direction.SOUTH : look;
	}

	/** 相对脚底按朝向偏移后的格。 */
	BlockPos offset(BlockPos feet, int dist, int dx, int dy) {
		return offset(feet, forward, dist, dx, dy);
	}

	/** 相对脚底按朝向偏移后的格。 */
	BlockPos offset(BlockPos feet, Direction dir, int dist, int dx, int dy) {
		Direction right = dir.getClockWise();
		return feet.offset(
			dir.getStepX() * dist + right.getStepX() * dx,
			dy,
			dir.getStepZ() * dist + right.getStepZ() * dx
		);
	}

	/** 该格是否可挖：不是空气、基岩、箱子或受保护封路块。 */
	boolean shouldMine(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		if (isProtectedSealBlock(client, pos)) return false;
		if (state.isAir() || !state.getFluidState().isEmpty()) return false;
		if (state.getDestroySpeed(client.level, pos) < 0.0F) return false;
		if (state.is(Blocks.BEDROCK) || state.is(Blocks.BARRIER) || state.is(Blocks.END_PORTAL) || state.is(Blocks.END_PORTAL_FRAME)
			|| state.is(Blocks.NETHER_PORTAL)) {
			return false;
		}
		if (state.is(Blocks.CHEST) || state.is(Blocks.TRAPPED_CHEST) || state.is(Blocks.SPAWNER)) return false;
		if (BorerHazards.wouldOpenLava(client, pos) || BorerHazards.wouldOpenWater(client, pos)) return false;
		return !client.player.blockActionRestricted(client.level, pos, client.gameMode.getPlayerMode());
	}

	/** 是否为受保护的封堵块。 */
	private boolean isProtectedSealBlock(Minecraft client, BlockPos pos) {
		Block expected = protectedSealBlocks.get(pos);
		if (expected == null) return false;
		if (client.level.getBlockState(pos).is(expected)) return true;
		protectedSealBlocks.remove(pos);
		return false;
	}

	/** 指向目标的主轴朝向。 */
	Direction headingToward(BlockPos from, BlockPos dest) {
		if (from == null || dest == null) return null;
		return BorerCenterPolicy.stableAxisHeading(
			dest.getX() - from.getX(), dest.getZ() - from.getZ(), forward);
	}

	/** 把前进朝向锁向目标。 */
	void lockHeadingToward(BlockPos from, BlockPos target) {
		BlockPos dest = liquidDetourPos != null ? liquidDetourPos : target;
		Direction heading = headingToward(from, dest);
		if (heading != null) forward = heading;
	}

	/** 找矿行进状态短文。 */
	String oreTravelStatus(LocalPlayer player) {
		if (mode != Mode.ORE) return "通道已通，前进中";
		if (sideOreTargetPos != null) return "靠近顺路" + wantedLabel() + " " + format(sideOreTargetPos) + reachInfo(player, sideOreTargetPos);
		return oreTargetPos == null
			? "正在分批扫描完整纵向范围内的" + wantedLabel()
			: "发现" + wantedLabel() + " " + format(oreTargetPos) + "，正在开 1×2 最小通道接近";
	}


	/** 相对方位短文本。 */
	private static String compass(BlockPos from, BlockPos to) {
		return BorerText.compass(from, to);
	}

	/** 旧主机没有这个方法时不能直接调用，否则热加载会 NoSuchMethodError 崩游戏。 */
	boolean coalXpMode() {
		try {
			Object value = host.getClass().getMethod("borerCoalXpMode").invoke(host);
			return value instanceof Boolean flag && flag;
		} catch (ReflectiveOperationException ignored) {
			return false;
		}
	}

	/** 是否下界石英只拿经验。 */
	boolean quartzXpMode() {
		try {
			Object value = host.getClass().getMethod("borerQuartzXpMode").invoke(host);
			return value instanceof Boolean flag && flag;
		} catch (ReflectiveOperationException ignored) {
			return false;
		}
	}

	/** 完成后是否自动回家。 */
	private boolean homeOnDone() {
		try {
			Object value = host.getClass().getMethod("borerHomeOnDone").invoke(host);
			if (value instanceof Boolean flag) return flag;
		} catch (ReflectiveOperationException ignored) {
		}
		return true;
	}

	/** 旧主机没有这个方法时默认开：向前挖遇岩浆提前拐弯。 */
	boolean turnAroundLava() {
		try {
			Object value = host.getClass().getMethod("borerTurnAroundLava").invoke(host);
			if (value instanceof Boolean flag) return flag;
		} catch (ReflectiveOperationException ignored) {
		}
		return true;
	}

	/** 默认轴向瞄准。旧主机没有方法时也当开。 */
	boolean axisAim() {
		try {
			Object value = host.getClass().getMethod("borerAxisAim").invoke(host);
			if (value instanceof Boolean flag) return flag;
		} catch (ReflectiveOperationException ignored) {
		}
		return true;
	}

	/** 挖方块时是否锁东西南北。区域挖目标在条带内任意位置，必须自由瞄准。 */
	boolean miningAxisAim() {
		if (mode == Mode.AREA && BorerAreaPolicy.freeAimMining()) return false;
		return axisAim();
	}

	/**
	 * 向前挖时前方通道有岩浆则改朝更干净的一侧。
	 * @return 本 tick 已经改了朝向
	 */
	boolean tryTurnAroundLava(Minecraft client, LocalPlayer player) {
		return tryTurnAroundLava(client, player, false);
	}

	/** 遇岩浆尝试拐弯；成功返回 true。 */
	boolean tryTurnAroundLava(Minecraft client, LocalPlayer player, boolean ignoreCooldown) {
		if (mode != Mode.FORWARD || goingHome || player == null || client.level == null) return false;
		if (!turnAroundLava() || !ignoreCooldown && turnCooldown > 0) return false;
		int maxDist = Math.max(effectiveLookAhead() + 2, LAVA_LOOK_BLOCKS);
		int ahead = lavaAheadCount(client, player, forward, maxDist);
		if (ahead == 0) return false;
		Direction cw = forward.getClockWise();
		Direction ccw = forward.getCounterClockWise();
		int cwScore = lavaAheadCount(client, player, cw, maxDist);
		int ccwScore = lavaAheadCount(client, player, ccw, maxDist);
		boolean clockwise;
		if (cwScore != ccwScore) clockwise = cwScore < ccwScore;
		else clockwise = !lastTurnClockwise;
		int chosenScore = clockwise ? cwScore : ccwScore;
		if (chosenScore > ahead) return false;
		Direction chosen = clockwise ? cw : ccw;
		Direction was = forward;
		commitTurn(client, player, chosen, clockwise);
		status = "前方岩浆或水，拐弯 " + directionLabel(forward);
		overlay(client, status, 0x55FFFF);
		fileLog(client, "lava-turn from=" + was + " to=" + forward
			+ " ahead=" + ahead + " cwScore=" + cwScore + " ccwScore=" + ccwScore
			+ " player=" + precisePosition(player));
		return true;
	}


	/** 确认并应用拐弯朝向。 */
	void commitTurn(Minecraft client, LocalPlayer player, Direction chosen, boolean clockwise) {
		if (currentTarget != null) releaseMine(client);
		client.options.keyUp.setDown(false);
		clearMiningTarget(client, "commit-turn");
		forward = chosen;
		lastTurnClockwise = clockwise;
		turnCooldown = LAVA_TURN_COOLDOWN_TICKS;
		turnedThisTick = true;
		frontOccluded = false;
		occludedTicks = 0;
	}

	/** 候选朝向上通道内岩浆/水，以及会挖开液体的方块数。 */
	private int lavaAheadCount(Minecraft client, LocalPlayer player, Direction dir, int maxDist) {
		BlockPos feet = player.blockPosition();
		int width = effectiveWidth();
		int height = effectiveHeight();
		int half = width / 2;
		int count = 0;
		for (int dist = 1; dist <= maxDist; dist++) {
			for (int dy = -1; dy < height; dy++) {
				for (int dx = -half; dx <= half; dx++) {
					BlockPos pos = offset(feet, dir, dist, dx, dy);
					if (!client.level.hasChunkAt(pos)) continue;
					int weight = maxDist - dist + 1;
					if (BorerHazards.isLavaFluid(client, pos) || BorerHazards.isWater(client, pos)) {
						count += weight;
						continue;
					}
					if (dy < 0 && BorerHazards.isMagma(client, pos)) {
						count += weight;
						continue;
					}
					if (dy >= 0 && !isReplaceable(client, pos)
						&& (BorerHazards.wouldOpenLava(client, pos) || BorerHazards.wouldOpenWater(client, pos))) {
						count += weight;
					}
				}
			}
		}
		return count;
	}

	/** 方向中文标签。 */
	private String directionLabel(Direction dir) {
		return BorerText.direction(dir);
	}

	/** 挖当前目标会放出岩浆：找矿改绕开；向前挖可拐弯则转弯，否则停步。 */
	private boolean handleOpenedLava(Minecraft client, LocalPlayer player, BlockPos openedLava) {
		if (mode == Mode.ORE) {
			ores.skipActive(client, "继续挖 " + format(currentTarget) + " 会放出岩浆 " + format(openedLava) + "，不挖这块，改绕开等待");
			return true;
		}
		BlockPos blockedTarget = currentTarget;
		releaseMine(client);
		clearMiningTarget(client, "opened-lava");
		client.options.keyUp.setDown(false);
		if (mode == Mode.AREA) {
			boolean skipped = area.skipCurrentShaft(client, blockedTarget, "opened-lava");
			if (skipped || !active) {
				if (active) {
					status = "当前竖井继续挖会放出岩浆，已记录并沿原井返顶";
					overlay(client, status, 0xFFFF55);
				}
				return true;
			}
		}
		if (mode == Mode.FORWARD && tryTurnAroundLava(client, player)) return false;
		status = "不挖岩浆下的方块，前方 " + format(openedLava) + " 有岩浆，已停步等待";
		overlay(client, status, 0xFFFF55);
		return true;
	}

	/** 挖当前目标会放水：停挖，让封水逻辑接手，不要走进去继续挖。 */
	private boolean handleOpenedWater(Minecraft client, LocalPlayer player, BlockPos openedWater) {
		BlockPos blockedTarget = currentTarget;
		releaseMine(client);
		clearMiningTarget(client, "opened-water");
		client.options.keyUp.setDown(false);
		if (mode == Mode.ORE) {
			ores.skipActive(client, "继续挖会放水 " + format(openedWater) + "，不挖这块，改绕开");
			return true;
		}
		if (mode == Mode.AREA) {
			boolean skipped = area.skipCurrentShaft(client, blockedTarget, "opened-water");
			if (skipped || !active) {
				if (active) {
					status = "当前竖井继续挖会进水，已记录并沿原井返顶";
					overlay(client, status, 0xFFFF55);
				}
				return true;
			}
		}
		status = "挖这块会进水 " + format(openedWater) + "，先封水，不往里挖";
		overlay(client, status, 0xFFFF55);
		return true;
	}

	/** 煤/石英经验模式：只挖拿经验，不走近捡、不因掉落物满包停机。 */
	private boolean skipExperienceLoot() {
		return lastMinedWasCoal && coalXpMode() || lastMinedWasQuartz && quartzXpMode();
	}

	/** 开始捡本轮勾选矿掉落物。 */
	void beginLootCollection(LocalPlayer player, BlockPos origin) {
		lastMiningTarget = null;
		miningTargetTicks = 0;
		miningRetryCount = 0;
		lastDestroyStage = -1;
		noMovementTicks = 0;
		attemptedForward = false;
		OreTarget ore = lastMinedOre != null ? lastMinedOre : OreTarget.fromConfig(oreConfig());
		loot.begin(player, origin, ore);
	}

	/** 挖矿目标。 */
	void clearMiningTarget() {
		clearMiningTarget(Minecraft.getInstance(), "engine-helper");
	}

	/** 推进拾取；已接管返回 true。 */
	boolean handleLootCollection(Minecraft client, LocalPlayer player) {
		return loot.handle(client, player);
	}

	/** 当前模式有效巷道宽。 */
	int effectiveWidth() {
		return mode == Mode.ORE ? 1 : Math.max(1, Math.min(5, host.borerWidth()));
	}

	/** 当前模式有效巷道高。 */
	int effectiveHeight() {
		if (mode == Mode.ORE) return 2;
		if (mode == Mode.DOWN) return Math.max(1, Math.min(5, host.borerHeight()));
		if (mode == Mode.AREA) return areaSliceHeight();
		return Math.max(2, Math.min(5, host.borerHeight()));
	}

	/** 区域挖切片高度。 */
	int areaSliceHeight() {
		return BorerAreaPolicy.clampSliceHeight(host.borerAreaSliceHeight());
	}

	/** 区域挖条带宽度。 */
	int areaStripWidth() {
		return BorerAreaPolicy.clampWidth(host.borerWidth());
	}

	/** 朝向前方。 */
	int effectiveLookAhead() {
		return mode == Mode.ORE ? 1 : Math.max(1, Math.min(5, host.borerLookAhead()));
	}

	/** 勾选矿种配置字符串。 */
	String oreConfig() {
		return host.borerOreTarget();
	}

	/** 方块是否匹配勾选矿。 */
	boolean wantedBlock(BlockState state) {
		return OreTarget.selectedMatches(oreConfig(), state);
	}

	/** 勾选矿种展示名。 */
	String wantedLabel() {
		return OreTarget.selectedLabel(oreConfig());
	}

	/** 方块矿种标签。 */
	private String blockOreLabel(Minecraft client, BlockPos pos) {
		OreTarget match = OreTarget.firstMatching(oreConfig(), client.level.getBlockState(pos));
		return match != null ? match.label : wantedLabel();
	}

	/** 够得着信息短文。 */
	private String reachInfo(LocalPlayer player, BlockPos pos) {
		return BorerAim.reachInfo(player, pos);
	}

	/** 原因是否表示路被堵。 */
	private static boolean isPathBlockedReason(String reason) {
		return reason != null && (reason.contains("封水") || reason.contains("放水") || reason.contains("基岩"));
	}

	/** 玩家碰撞箱是否碰到该格。 */
	boolean playerTouchesBlock(LocalPlayer player, BlockPos pos) {
		return BorerAim.touches(player, pos);
	}

	/** 是否可直接够着挖。 */
	private boolean canMineDirectly(Minecraft client, LocalPlayer player, BlockPos target) {
		if (!shouldMine(client, target) || !inMiningReach(player, target)) return false;
		if (canSeeBlock(client, player, target)) return true;
		BlockHitResult toward = firstMineableHitToward(client, player, target);
		return toward != null && toward.getBlockPos().equals(target);
	}

	/** 是否需要垂直寻路。 */
	private boolean needsVerticalRoute(BlockPos feet, BlockPos target) {
		return BorerStairPolicy.needsVerticalRoute(target.getY() - feet.getY());
	}

	/** 该格是否有碰撞形状。 */
	boolean hasCollision(Minecraft client, BlockPos pos) {
		return !client.level.getBlockState(pos).getCollisionShape(client.level, pos).isEmpty();
	}

	/** 沙子/沙砾会砸下来时：能挖柱顶就先挖，来不及就开飞行躲开。 */
	private boolean handleFallingSand(Minecraft client, LocalPlayer player) {
		if (BorerHazards.fallingEntityThreat(client, player)) {
			dodgeFallingSand(client, player, "沙子/沙砾正在下落，已开飞行躲开");
			return true;
		}
		BlockPos loose = BorerHazards.unsupportedFallingAbove(client, player, currentTarget);
		if (loose == null) return false;
		if (canPlanMine(client, loose) && inMiningReach(player, loose)
			&& (canSeeBlock(client, player, loose) || playerTouchesBlock(player, loose) || hasCollision(client, loose))) {
			replaceMiningTarget(client, loose, "falling-block-threat");
			client.options.keyUp.setDown(false);
			return false;
		}
		dodgeFallingSand(client, player, "头顶沙子/沙砾要掉下来，已开飞行躲开");
		return true;
	}

	/** 躲开下落沙砾。 */
	private void dodgeFallingSand(Minecraft client, LocalPlayer player, String reason) {
		releaseMine(client);
		enableMeteorFlight(player);
		client.options.keyJump.setDown(true);
		client.options.keyUp.setDown(false);
		client.options.keyShift.setDown(false);
		client.options.keyAttack.setDown(false);
		overlay(client, reason, 0xFFFF55);
	}

	/** 躲开或处理头顶下落方块堆。 */
	BlockPos liftFallingStack(Minecraft client, LocalPlayer player, BlockPos pos) {
		BlockPos top = BorerHazards.topFallingBlock(client, pos, 8);
		if (top == null) top = BorerHazards.topFallingBlock(client, pos.above(), 8);
		if (top == null || top.equals(pos)) return null;
		BlockPos feet = standingColumn(client, player);
		int dist = Math.abs(top.getX() - feet.getX()) + Math.abs(top.getZ() - feet.getZ());
		int dy = top.getY() - feet.getY();
		if (BorerStairPolicy.ignoreOverheadFalling(dist, dy, effectiveHeight())) return null;
		if (canPlanMine(client, top) && inMiningReach(player, top)) return top;
		return null;
	}

	/** 打开 Meteor Flight；成功返回 true。 */
	boolean enableMeteorFlight(LocalPlayer player) {
		if (flyToggleCooldown > 0) return BorerFlight.isFlying(player);
		boolean already = BorerFlight.isFlying(player);
		if (already) return true;
		if (!BorerFlight.ensureFlying(player, true)) return false;
		meteorFlightHeldByEngine = true;
		flyToggleCooldown = 8;
		fileLog(Minecraft.getInstance(), "enabled Meteor Flight to clear a step");
		return true;
	}

	/** 本模块代开的飞行则关掉。 */
	private void releaseMeteorFlightIfHeld(Minecraft client) {
		if (!meteorFlightHeldByEngine) return;
		if (client.player != null) BorerFlight.ensureFlying(client.player, false);
		meteorFlightHeldByEngine = false;
	}

	/** 复位跳跃相关控制。 */
	void resetJumpControl() {
		jumpOrigin = null;
		jumpPressTicks = 0;
		jumpRetryCooldownTicks = 0;
		jumpAttempts = 0;
	}

	/** 该格是否可立足。 */
	boolean isStandable(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		if (state.is(Blocks.MAGMA_BLOCK)) return false;
		if (state.isAir() || state.canBeReplaced() || !state.getFluidState().isEmpty()) return false;
		return BorerHazards.isUnbreakable(client, pos) || state.getDestroySpeed(client.level, pos) >= 0.0F;
	}

	/** 站在方块边缘时 blockPosition 会落到洞里；用碰撞箱压着的那列作为立足点。 */
	BlockPos standingColumn(Minecraft client, LocalPlayer player) {
		if (player == null) return BlockPos.ZERO;
		BlockPos fallback = player.blockPosition();
		if (isFlying(player) || !player.onGround()) return fallback;
		AABB box = player.getBoundingBox();
		int floorY = Mth.floor(box.minY - 0.001);
		BlockPos best = null;
		double bestArea = 0.0;
		for (int x = Mth.floor(box.minX); x <= Mth.floor(box.maxX - 1.0E-5); x++) {
			for (int z = Mth.floor(box.minZ); z <= Mth.floor(box.maxZ - 1.0E-5); z++) {
				BlockPos floor = new BlockPos(x, floorY, z);
				if (!isStandable(client, floor)) continue;
				double overlapX = Math.min(box.maxX, x + 1.0) - Math.max(box.minX, x);
				double overlapZ = Math.min(box.maxZ, z + 1.0) - Math.max(box.minZ, z);
				double area = Math.max(0.0, overlapX) * Math.max(0.0, overlapZ);
				if (area > bestArea) {
					bestArea = area;
					best = floor.above();
				}
			}
		}
		return best != null ? best : fallback;
	}

	/** 当前碰撞箱压着的实心块：挖掉会直接掉下去。只认立足点那一列，擦到隔壁地板不算。 */
	boolean isStandingSupport(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (pos == null || player == null) return false;
		return pos.equals(standingColumn(client, player).below());
	}

	/** 通道地板不能挖：改挖眼前 1×2，不要原地空走。 */
	private void recoverFromUnsafeFloor(Minecraft client, LocalPlayer player) {
		fileLog(client, "skip-floor-mine target=" + format(currentTarget)
			+ " standCol=" + format(standingColumn(client, player))
			+ " player=" + precisePosition(player));
		releaseMine(client);
		clearMiningTarget(client, "unsafe-floor");
		BlockPos replacement = mode == Mode.ORE ? corridor.adjacentOreToMine(client, player) : null;
		if (replacement == null || isUnsafeFloorMine(client, player, replacement)) {
			replacement = corridor.nextClearableCorridorBlock(client, player);
		}
		if (replacement != null && !isUnsafeFloorMine(client, player, replacement)) {
			setMiningTarget(client, player, replacement, "unsafe-floor-replacement");
		}
		if (currentTarget == null) faceTowardPathCenter(player);
	}

	/**
	 * 只拦会让人掉下去的块：立足点、当前列往下的竖井、通道地板。
	 * 勾选矿在脚下/身旁地板：落地安全（无岩浆/虚空/超深）就挖。
	 */
	boolean isUnsafeFloorMine(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (mode == Mode.DOWN || mode == Mode.AREA || pos == null || player == null) return false;
		BlockPos feet = standingColumn(client, player);
		int horiz = Math.abs(pos.getX() - feet.getX()) + Math.abs(pos.getZ() - feet.getZ());
		int dy = pos.getY() - feet.getY();
		boolean standingSupport = isStandingSupport(client, player, pos);
		boolean landingSafe = BorerFallPolicy.canMineFloorIfLandingSafe(landingDropIfMined(client, player, pos));
		if (wantedBlock(client.level.getBlockState(pos))
			&& BorerOrePolicy.mineAdjacentInsteadOfWait(horiz, dy)) {
			return dy == -1 && !landingSafe;
		}
		if (standingSupport) return true;
		if (pos.getX() == feet.getX() && pos.getZ() == feet.getZ() && pos.getY() < feet.getY()) return true;
		if (!isWalkwayFloor(feet, pos) || wantedBlock(client.level.getBlockState(pos))) return false;
		return !vertical.descendingToOre(client, player);
	}

	/** 挖掉这块之后人会落下几格。立足点/同列下方按当前脚列算；通道地板按那一列算。 */
	int landingDropIfMined(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (pos == null || player == null) return -1;
		BlockPos feet = standingColumn(client, player);
		if (isStandingSupport(client, player, pos)
			|| pos.getX() == feet.getX() && pos.getZ() == feet.getZ() && pos.getY() < feet.getY()) {
			return BorerHazards.safeFallDepthTreatingAir(client, feet, pos);
		}
		if (isWalkwayFloor(feet, pos)) {
			return BorerHazards.safeFallDepthTreatingAir(client, pos.above(), pos);
		}
		return 0;
	}

	/** 脚下一格、四向相邻的通道地板。挖掉会在前方开洞。 */
	private boolean isWalkwayFloor(BlockPos feet, BlockPos pos) {
		if (pos.getY() != feet.getY() - 1) return false;
		return Math.abs(pos.getX() - feet.getX()) + Math.abs(pos.getZ() - feet.getZ()) == 1;
	}

	/** 准星扫到坑里的石头时不要改挖它；勾选矿种除外。 */
	boolean isBelowFeetNonOre(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (pos == null || player == null || mode == Mode.DOWN || mode == Mode.AREA) return false;
		if (pos.getY() >= standingColumn(client, player).getY()) return false;
		if (vertical.descendingToOre(client, player) && isWalkwayFloor(standingColumn(client, player), pos)) return false;
		return !wantedBlock(client.level.getBlockState(pos));
	}

	/** 头或上半身卡进方块时优先挖它，不要求视线。 */
	BlockPos collidingHeadBlock(Minecraft client, LocalPlayer player) {
		AABB box = player.getBoundingBox().move(forward.getStepX() * 0.12, 0.0, forward.getStepZ() * 0.12);
		AABB upper = new AABB(box.minX, box.minY + 0.9, box.minZ, box.maxX, box.maxY + 0.08, box.maxZ);
		return collidingMineable(client, player, upper, true);
	}

	/** 碰撞箱内可挖方块。 */
	private BlockPos collidingMineable(Minecraft client, LocalPlayer player, AABB box, boolean skipFoothold) {
		if (client.level == null) return null;
		BlockPos best = null;
		int bestY = Integer.MIN_VALUE;
		double bestDist = Double.MAX_VALUE;
		Vec3 eye = player.getEyePosition();
		for (int x = Mth.floor(box.minX); x <= Mth.floor(box.maxX - 1.0E-5); x++) {
			for (int y = Mth.floor(box.minY); y <= Mth.floor(box.maxY - 1.0E-5); y++) {
				for (int z = Mth.floor(box.minZ); z <= Mth.floor(box.maxZ - 1.0E-5); z++) {
					BlockPos pos = new BlockPos(x, y, z);
					if (!canPlanMine(client, pos) || !inMiningReach(player, pos)) continue;
					if (skipFoothold && vertical.isClimbFoothold(client, player, pos)) continue;
					BlockState state = client.level.getBlockState(pos);
					boolean intersects = state.getCollisionShape(client.level, pos).toAabbs().stream()
						.map(aabb -> aabb.move(pos))
						.anyMatch(box::intersects);
					if (!intersects) continue;
					double dist = eye.distanceToSqr(Vec3.atCenterOf(pos));
					if (pos.getY() > bestY || pos.getY() == bestY && dist < bestDist) {
						best = pos.immutable();
						bestY = pos.getY();
						bestDist = dist;
					}
				}
			}
		}
		return best;
	}

	/** 该格是否可替换（空气/草等）。 */
	boolean isReplaceable(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		return (state.isAir() || state.canBeReplaced()) && state.getFluidState().isEmpty();
	}

	/** 空气、可替换方块，或岩浆/水：可以铺石头盖住。 */
	boolean canFillWalkway(Minecraft client, BlockPos pos) {
		if (client.level == null) return false;
		BlockState state = client.level.getBlockState(pos);
		if (state.is(Blocks.BEDROCK) || state.is(Blocks.BARRIER)) return false;
		if (!state.getFluidState().isEmpty()) return true;
		return state.isAir() || state.canBeReplaced();
	}

	/** 下一矿或挡路方块。 */
	BlockPos nextOreOrObstruction(Minecraft client, LocalPlayer player, BlockPos target) {
		BlockHitResult hit = firstMineableHitToward(client, player, target);
		if (hit == null) return null;
		BlockPos pos = hit.getBlockPos();
		if (isUnsafeFloorMine(client, player, pos) || isBelowFeetNonOre(client, player, pos)) return null;
		if (!inMiningReach(player, pos)) return null;
		if (vertical.climbingToOre(client, player) && pos.getY() < standingColumn(client, player).getY()) return null;
		return vertical.climbTargetInsteadOfFoothold(client, player, pos);
	}

	/** 朝目标可见的挡路格。 */
	BlockPos visibleObstructionToward(Minecraft client, LocalPlayer player, BlockPos target) {
		BlockHitResult hit = firstMineableHitToward(client, player, target);
		if (hit == null || hit.getBlockPos().equals(target)) return null;
		return hit.getBlockPos().immutable();
	}

	/** 是否在挖掘距离内。 */
	boolean inMiningReach(LocalPlayer player, BlockPos pos) {
		return BorerAim.inReach(player, pos);
	}

	/** 视线是否通到该格。 */
	boolean canSeeBlock(Minecraft client, LocalPlayer player, BlockPos pos) {
		return visibleHitResult(client, player, pos) != null;
	}

	/** 解析挖这块的准星命中。 */
	private BlockHitResult resolveMiningHit(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (miningAxisAim()) {
			if (!inMiningReach(player, pos)) return null;
			BorerAim.lookAxis(player, pos);
			BlockHitResult axisHit = BorerAim.clipView(client, player);
			boolean axisHits = axisHit != null
				&& axisHit.getBlockPos().equals(pos)
				&& BorerAim.hitInReach(player, axisHit);
			if (axisHits) return axisHit;
			BlockHitResult visible = visibleHitResult(client, player, pos);
			if (visible != null
				&& BorerMiningPolicy.useVisibleFaceWhenAxisMisses(true, false, true)) {
				return visible;
			}
			BlockHitResult toward = firstMineableHitToward(client, player, pos);
			if (toward != null) return toward;
			return axisHit;
		}
		BlockHitResult direct = visibleHitResult(client, player, pos);
		if (direct != null) return direct;
		if (client.hitResult instanceof BlockHitResult pick
			&& pick.getType() == HitResult.Type.BLOCK
			&& pick.getBlockPos().equals(pos)
			&& BorerAim.hitInReach(player, pick)) {
			Vec3 look = BorerAim.lookAlongRay(player.getEyePosition(), pick);
			BlockHitResult verified = BorerAim.verifiedHit(client, player, look, pos);
			if (verified != null) return verified;
			return pick;
		}
		BlockPos goal = sideOreTargetPos != null ? sideOreTargetPos : oreTargetPos;
		if (goal != null) {
			BlockHitResult towardGoal = firstMineableHitToward(client, player, goal);
			if (towardGoal != null) return towardGoal;
		}
		return firstMineableHitToward(client, player, pos);
	}

	/** 可挖命中朝。 */
	BlockHitResult firstMineableHitToward(Minecraft client, LocalPlayer player, BlockPos target) {
		return BorerAim.firstMineable(client, player, target, minePos -> canPlanMine(client, minePos));
	}

	/** 可见命中结果。 */
	private BlockHitResult visibleHitResult(Minecraft client, LocalPlayer player, BlockPos pos) {
		return BorerAim.visibleHit(client, player, pos, minePos -> shouldMine(client, minePos));
	}

	/** 更新覆盖提示。 */
	void overlay(Minecraft client, String text, int color) {
		status = text;
		if (color == 0xFF5555 || color == 0x55FF55 || color == 0x55FFFF) statusColor = color;
		else statusColor = 0xFFFF55;
	}

	/** 刷新状态 HUD。 */
	private void presentStatusHud(Minecraft client) {
		if (!active || client.player == null) return;
		try {
			preview.emitActive(client);
		} catch (IllegalStateException ignored) {
		}
	}

	/** 发出状态 HUD。 */
	private void emitStatusHud(Minecraft client) {
		if (active && client.player != null) {
			presentHud(client, status, statusColor, hudDetailLine(client));
			return;
		}
		if (showingShaftPreview && !active) {
			presentHud(client, "预览竖井  再按B开挖", 0xFFFFCC33, preview.shaftHint());
			return;
		}
		if (showingHomeRoute && client.player != null) {
			presentHud(client, "回家路线 跟着金色箭头", 0xFFFFCC33, homeRouteDetail(client));
			return;
		}
		BorerScreenHudBridge.hide(host);
	}

	/** 展示指定动作 HUD。 */
	private void presentHud(Minecraft client, String action, int color, String detail) {
		String text = action == null ? "" : action;
		String extra = detail == null ? "" : detail;
		if (BorerScreenHudBridge.show(host, text, color, extra)) return;
		if (client.player == null) return;
		try {
			BorerHud.draw(client.player, text, color, extra);
		} catch (IllegalStateException ignored) {
			if (text.equals(lastHudAction) && extra.equals(lastHudDetail)) return;
			lastHudAction = text;
			lastHudDetail = extra;
			String combined = extra.isBlank() ? "[盾构机] " + text : "[盾构机] " + text + "  |  " + extra;
			client.gui.setOverlayMessage(Component.literal(combined).withColor(color), false);
		}
	}

	/** HUD 详情行。 */
	private String hudDetailLine(Minecraft client) {
		if (goingHome) {
			LocalPlayer player = client.player;
			if (returningToPortal) {
				String portal = trail.portal() == null || player == null
					? "沿路点飞回"
					: "门 " + compass(player.blockPosition(), trail.portal());
				boolean lavaAbove = player != null && (isLava(client, player.blockPosition().above(2))
					|| isLava(client, player.blockPosition().above(3)));
				String path = lavaAbove
					? (escapeShaft == null ? "沿巷道躲开岩浆" : "↑天井 " + compass(player.blockPosition(), escapeShaft))
					: "沿挖过的巷道飞回";
				return portal + "  |  " + path + "  |  剩余 " + trail.remainingTowardHome(client, player);
			}
			return "沿挖过的原路返回  |  剩余 " + trail.remainingTowardHome(client, player) + " 路点";
		}
		String lootDetail = loot.hudDetail();
		if (lootDetail != null) return lootDetail;
		if (mode == Mode.ORE) {
			BlockPos goal = sideOreTargetPos != null ? sideOreTargetPos : oreTargetPos;
			if (goal != null) {
				String kind = sideOreTargetPos != null ? "顺路" : "目标";
				return mode.label + " " + wantedLabel() + "  " + kind + " " + format(goal);
			}
			return ores.status(client);
		}
		return mode.label + "  朝向 " + directionLabel(forward);
	}

	/** 封堵/铺路选用的物品、方块与手。 */
	public static final class SealChoice {
		final Item item;
		final Block block;
		final InteractionHand hand;

		SealChoice(Item item, Block block, InteractionHand hand) {
			this.item = item;
			this.block = block;
			this.hand = hand;
		}

		/** 选用的物品。 */
		Item item() {
			return item;
		}

		/** 对应方块。 */
		Block block() {
			return block;
		}

		/** 用哪只手放置。 */
		InteractionHand hand() {
			return hand;
		}
	}

	/** 该格是否为岩浆流体。 */
	boolean isLava(Minecraft client, BlockPos pos) {
		return BorerHazards.isLavaFluid(client, pos);
	}

	/** 脚下或前方没有实体立足点、或前面是岩浆/水，就不能按前进。安全落差可以走：默认最多 3 格，Meteor NoFall 开着则更深。 */
	boolean unsafeToWalk(Minecraft client, LocalPlayer player) {
		BlockPos feet = player.blockPosition();
		BlockPos next = feet.relative(forward);
		if (isLava(client, next) || isLava(client, next.below()) || isLava(client, feet.below())) return true;
		if (BorerHazards.isWater(client, next) || BorerHazards.isWater(client, next.below()) || BorerHazards.isWater(client, feet.below())) return true;
		if (BorerHazards.isMagma(client, next.below()) || BorerHazards.isMagma(client, feet.below())) return true;
		if (isFlying(player)) return false;
		if (!player.onGround()) return true;
		if (mode == Mode.DOWN || mode == Mode.AREA) return !BorerHazards.canWalkOrFallInto(client, next);
		return !BorerFallPolicy.canWalk(BorerHazards.safeFallDepth(client, next));
	}

	/** 前方能平走过，或落差在允许范围内（默认 3 格，Meteor NoFall 开着则更深）。 */
	private boolean canStepDownSafely(Minecraft client, LocalPlayer player) {
		return columnWalkableForDescend(client, standingColumn(client, player).relative(forward))
			|| columnWalkableForDescend(client, player.blockPosition().relative(forward));
	}

	/** 前方柱是否可下。 */
	private boolean columnWalkableForDescend(Minecraft client, BlockPos front) {
		if (isLava(client, front) || isLava(client, front.below()) || isLava(client, front.below(2))) return false;
		if (BorerHazards.isWater(client, front) || BorerHazards.isWater(client, front.below()) || BorerHazards.isWater(client, front.below(2))) return false;
		if (BorerHazards.isMagma(client, front.below()) || BorerHazards.isMagma(client, front.below(2))) return false;
		return BorerStairPolicy.shouldWalkWhileDescending(BorerHazards.safeFallDepth(client, front));
	}

	/** 前方一格台阶是否可走。 */
	private boolean walkableOneBlockStepAhead(Minecraft client, LocalPlayer player) {
		return isWalkableOneBlockStep(client, player, standingColumn(client, player).relative(forward));
	}

	/** Meteor Step 能跨的 1 格高台阶：头顶两格已通才走，1×2 天花板挡住就还是挖。 */
	boolean isWalkableOneBlockStep(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (pos == null || player == null) return false;
		BlockPos feet = standingColumn(client, player);
		if (pos.getY() != feet.getY()) return false;
		if (Math.abs(pos.getX() - feet.getX()) + Math.abs(pos.getZ() - feet.getZ()) != 1) return false;
		if (!isStandable(client, pos)) return false;
		boolean headroom = isReplaceable(client, pos.above()) && isReplaceable(client, pos.above(2));
		return BorerStairPolicy.walkUpOneBlockStep(
			BorerFlight.canStepOneBlock(player), true, headroom, vertical.climbingToOre(client, player));
	}

	/** 只允许安全落差：默认最多 3 格，开了 NoFall 则跟盾构同一套判定。 */
	boolean safeShortDropTowardLoot(Minecraft client, LocalPlayer player) {
		BlockPos next = player.blockPosition().relative(forward);
		if (isLava(client, next) || isLava(client, next.below()) || isLava(client, next.below(2))) return false;
		if (BorerHazards.isWater(client, next) || BorerHazards.isWater(client, next.below()) || BorerHazards.isWater(client, next.below(2))) return false;
		return BorerHazards.canWalkOrFallInto(client, next);
	}

	/** 玩家是否在飞。 */
	private static boolean isFlying(LocalPlayer player) {
		return BorerFlight.isFlying(player);
	}

	/** 是否在下界。 */
	private static boolean inNether(Minecraft client) {
		return client.level != null && client.level.dimension().equals(Level.NETHER);
	}

	/** 过门后在身边扫紫色门方块，记下最近的一格。 */
	private static BlockPos findNearbyPortal(Minecraft client, LocalPlayer player) {
		if (client.level == null || player == null) return null;
		BlockPos feet = player.blockPosition();
		BlockPos best = null;
		double bestDist = Double.MAX_VALUE;
		int radius = 16;
		for (int dy = -10; dy <= 10; dy++) {
			for (int dx = -radius; dx <= radius; dx++) {
				for (int dz = -radius; dz <= radius; dz++) {
					BlockPos pos = feet.offset(dx, dy, dz);
					if (!client.level.hasChunkAt(pos)) continue;
					if (!client.level.getBlockState(pos).is(Blocks.NETHER_PORTAL)) continue;
					double distance = player.position().distanceToSqr(Vec3.atCenterOf(pos));
					if (distance < bestDist) {
						bestDist = distance;
						best = pos.immutable();
					}
				}
			}
		}
		return best;
	}

	/** 把视角对准目标。 */
	void lookAt(LocalPlayer player, BlockPos pos) {
		if (mode == Mode.AREA && BorerAreaPolicy.freeAimMining()) {
			BorerAim.lookAtBlockCenter(player, pos);
			return;
		}
		if (miningAxisAim()) {
			BorerAim.lookAxis(player, pos);
			return;
		}
		lookFree(player, Vec3.atCenterOf(pos));
	}

	/** 轴向能打到就轴向；打不到但可见面能打到就对着可见面。 */
	private void lookAtMiningHit(Minecraft client, LocalPlayer player, BlockHitResult hit) {
		if (hit == null) return;
		if (mode == Mode.AREA && BorerAreaPolicy.freeAimMining()) {
			BorerAim.lookAtBlockCenter(player, hit.getBlockPos());
			return;
		}
		if (miningAxisAim()) {
			BorerAim.lookAxis(player, hit.getBlockPos());
			BlockHitResult after = BorerAim.clipView(client, player);
			if (after != null
				&& after.getBlockPos().equals(hit.getBlockPos())
				&& BorerAim.hitInReach(player, after)) {
				return;
			}
		}
		lookFree(player, BorerAim.lookPoint(hit));
	}

	/** 已经在可挖距离内：对准再挖，不要走过去把视角拧向矿。 */
	private boolean keepMiningInReach(Minecraft client, LocalPlayer player, BlockPos pos) {
		BlockHitResult hit = resolveMiningHit(client, player, pos);
		if (hit == null || !hit.getBlockPos().equals(pos)) {
			releaseMine(client);
			fileLog(client, "aim-miss-real target=" + format(pos)
				+ " actual=" + (hit == null ? "-" : format(hit.getBlockPos()))
				+ " player=" + precisePosition(player));
			return false;
		}
		lookAtMiningHit(client, player, hit);
		hit = BorerAim.clipView(client, player);
		boolean inReach = hit != null && BorerAim.hitInReach(player, hit);
		if (!BorerMiningPolicy.allowAttack(pos, hit == null ? null : hit.getBlockPos(), inReach)) {
			releaseMine(client);
			fileLog(client, "aim-miss-real target=" + format(pos)
				+ " actual=" + (hit == null ? "-" : format(hit.getBlockPos()))
				+ " player=" + precisePosition(player));
			return false;
		}
		client.hitResult = hit;
		client.crosshairPickEntity = null;
		place.selectMiningTool(client, player, pos);
		applyMineCadence(client, player, pos, !timingActive || currentTarget == null || !pos.equals(currentTarget), false);
		client.options.keyUp.setDown(false);
		if (mode == Mode.AREA) {
			// 够得到就悬停挖，松方向键；不要边挖边横移晃身子。
			client.options.keyDown.setDown(false);
			client.options.keyLeft.setDown(false);
			client.options.keyRight.setDown(false);
			client.options.keyJump.setDown(false);
			if (!BorerAreaPolicy.hoverWhileMining(true)) {
				nudgeToColumnCenter(client, player);
			}
		}
		return true;
	}

	/** 准星是否打到目标。 */
	private boolean aimHitsTarget(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (pos == null || player == null || client.level == null) return false;
		BlockHitResult hit = resolveMiningHit(client, player, pos);
		if (hit == null || !hit.getBlockPos().equals(pos)) return false;
		lookAtMiningHit(client, player, hit);
		hit = BorerAim.clipView(client, player);
		return BorerMiningPolicy.allowAttack(pos, hit == null ? null : hit.getBlockPos(),
			hit != null && BorerAim.hitInReach(player, hit));
	}

	/** 把视角对准目标。 */
	void lookAt(LocalPlayer player, Vec3 target) {
		if (mode == Mode.AREA && currentTarget != null && BorerAreaPolicy.freeAimMining()) {
			BorerAim.lookAtBlockCenter(player, currentTarget);
			return;
		}
		if (miningAxisAim() && currentTarget != null) {
			BorerAim.lookAxis(player, currentTarget);
			return;
		}
		lookFree(player, target);
	}

	/** 自由瞄准（非轴向）。 */
	private static void lookFree(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}

	/** 面朝当前前进方向。 */
	void faceForward(LocalPlayer player) {
		RotationAim.apply(player, BorerAim.yawOf(forward), 0.0F);
	}

	/** 朝路径中心。 */
	void faceTowardPathCenter(LocalPlayer player) {
		if (axisAim()) {
			faceForward(player);
			return;
		}
		BlockPos ahead = player.blockPosition().relative(forward);
		Vec3 target = new Vec3(ahead.getX() + 0.5, player.getEyeY(), ahead.getZ() + 0.5);
		Vec3 delta = target.subtract(player.getEyePosition());
		RotationAim.apply(player, RotationAim.yawToward(delta.x, delta.z), 0.0F);
	}

	/** 居中后按前进。 */
	void walkForwardCentered(Minecraft client, LocalPlayer player) {
		faceTowardPathCenter(player);
		nudgeToColumnCenter(client, player);
		client.options.keyUp.setDown(true);
		attemptedForward = true;
	}

	/** 飞向当前目标块，不沿巷道朝向按 W。 */
	void approachMiningBlock(Minecraft client, LocalPlayer player, BlockPos dest) {
		if (dest == null || player == null) return;
		BlockPos feet = player.blockPosition();
		boolean sameCol = feet.getX() == dest.getX() && feet.getZ() == dest.getZ();
		boolean below = BorerApproachPolicy.descend(dest.getY(), player.getY());
		if (BorerApproachPolicy.dropDownSameColumn(sameCol, below)) {
			fallDown(client, player, "竖井够不着，下去再挖");
			clearMiningTarget(client, "out-of-reach-drop");
			return;
		}
		if (BorerApproachPolicy.enableFlight(isFlying(player), dest.getY(), player.getY())) {
			enableMeteorFlight(player);
		}
		lockHeadingToward(feet, dest);
		RotationAim.apply(player, RotationAim.lookAt(player, Vec3.atCenterOf(dest)));
		double horiz = Math.hypot(dest.getX() + 0.5 - player.getX(), dest.getZ() + 0.5 - player.getZ());
		boolean go = BorerApproachPolicy.holdForward(horiz);
		boolean up = BorerApproachPolicy.ascend(dest.getY(), player.getY()) && isFlying(player);
		boolean down = below && isFlying(player);
		client.options.keyAttack.setDown(false);
		client.options.keyUp.setDown(go);
		client.options.keyJump.setDown(up);
		client.options.keyShift.setDown(down && !up);
		attemptedForward = go;
	}

	/** 矿就在附近更高/更低处：站住挖阶梯，不要沿已挖通道走回头。 */
	private boolean holdForNearbyVerticalOre(Minecraft client, LocalPlayer player) {
		if (mode != Mode.ORE) return false;
		BlockPos goal = sideOreTargetPos != null ? sideOreTargetPos : oreTargetPos;
		if (goal == null) return false;
		BlockPos feet = standingColumn(client, player);
		int dx = goal.getX() - feet.getX();
		int dz = goal.getZ() - feet.getZ();
		int horiz = Math.abs(dx) + Math.abs(dz);
		boolean needVertical = needsVerticalRoute(feet, goal);
		if (BorerCenterPolicy.stayAndClimb(horiz, needVertical)) {
			client.options.keyUp.setDown(false);
			client.options.keyLeft.setDown(false);
			client.options.keyRight.setDown(false);
			boolean frontOpen = !hasCollision(client, standingColumn(client, player).relative(forward))
				&& !hasCollision(client, standingColumn(client, player).relative(forward).above());
			BlockPos adjacent = corridor.adjacentOreToMine(client, player);
			if (adjacent != null && BorerOrePolicy.mineAdjacentInsteadOfHold(horiz,
				goal.getY() - feet.getY(), frontOpen)) {
				setMiningTarget(client, player, adjacent, "adjacent-ore-instead-of-hold");
				status = "改挖身旁矿 " + format(adjacent) + BorerAim.reachInfo(player, adjacent);
				overlay(client, status, 0xFFFF55);
				return true;
			}
			status = "矿在附近" + (goal.getY() > feet.getY() ? "更高处" : "更低处") + "，不退出通道 " + format(goal);
			overlay(client, status, 0xFFFF55);
			return true;
		}
		if (!BorerCenterPolicy.headingReducesDistance(forward.getStepX(), forward.getStepZ(), dx, dz)) {
			lockHeadingToward(feet, goal);
			if (!BorerCenterPolicy.headingReducesDistance(forward.getStepX(), forward.getStepZ(), dx, dz)) {
				client.options.keyUp.setDown(false);
				return true;
			}
		}
		return false;
	}

	/** 是否偏出格子中心。 */
	private boolean offColumnCenter(Minecraft client, LocalPlayer player) {
		BlockPos feet = standingColumn(client, player);
		Direction right = forward.getClockWise();
		double side = BorerCenterPolicy.sideOffset(
			player.getX(), player.getZ(), feet.getX(), feet.getZ(), right.getStepX(), right.getStepZ());
		return BorerCenterPolicy.overlapsSideWall(side);
	}

	/**
	 * 统一选定一块要挖的方块，并保存「当时的身体列 + 通道朝向」。
	 * 后续找矿可以继续转头，但不能再用新朝向把已选的正前方误判成侧墙。
	 */
	void setMiningTarget(Minecraft client, LocalPlayer player, BlockPos target, String reason) {
		if (target == null) {
			clearMiningTarget(client, reason);
			return;
		}
		BlockPos selected = target.immutable();
		boolean changed = currentTarget == null || !currentTarget.equals(selected);
		currentTarget = selected;
		clearConfirmTicks = 0;
		if (changed) {
			if (aimMissTarget != null && !aimMissTarget.equals(selected)) resetAimMissProgress();
			corridorHeading = forward;
			corridorOrigin = player.blockPosition().immutable();
			lastMiningTarget = null;
			miningTargetTicks = 0;
			miningRetryCount = 0;
			lastDestroyStage = -1;
			fileLog(client, "target-set reason=" + reason
				+ " target=" + format(selected)
				+ " origin=" + format(corridorOrigin)
				+ " heading=" + directionLabel(corridorHeading)
				+ " player=" + precisePosition(player));
		}
	}

	/** 方块仍是同一条路径的一部分时换到它，保留原始通道上下文。 */
	private void replaceMiningTarget(Minecraft client, BlockPos target, String reason) {
		if (target == null) {
			clearMiningTarget(client, reason);
			return;
		}
		BlockPos selected = target.immutable();
		if (selected.equals(currentTarget)) return;
		BlockPos previous = currentTarget;
		currentTarget = selected;
		if (aimMissTarget != null && !aimMissTarget.equals(selected)) resetAimMissProgress();
		if (corridorHeading == null) corridorHeading = forward;
		if (corridorOrigin == null && client.player != null) corridorOrigin = client.player.blockPosition().immutable();
		lastMiningTarget = null;
		miningTargetTicks = 0;
		miningRetryCount = 0;
		lastDestroyStage = -1;
		clearConfirmTicks = 0;
		miningSelectedOre = false;
		fileLog(client, "target-replace reason=" + reason
			+ " from=" + (previous == null ? "-" : format(previous))
			+ " to=" + format(selected)
			+ " origin=" + (corridorOrigin == null ? "-" : format(corridorOrigin))
			+ " heading=" + (corridorHeading == null ? "-" : directionLabel(corridorHeading)));
	}

	/** 挖矿目标。 */
	void clearMiningTarget(Minecraft client, String reason) {
		if (currentTarget != null) {
			fileLog(client, "target-clear reason=" + reason
				+ " target=" + format(currentTarget)
				+ " origin=" + (corridorOrigin == null ? "-" : format(corridorOrigin))
				+ " heading=" + (corridorHeading == null ? "-" : directionLabel(corridorHeading))
				+ " crosshair=" + crosshairLabel(client));
		}
		currentTarget = null;
		corridorHeading = null;
		corridorOrigin = null;
		lastMiningTarget = null;
		miningTargetTicks = 0;
		miningRetryCount = 0;
		lastDestroyStage = -1;
		clearConfirmTicks = 0;
		miningSelectedOre = false;
		resetMineTimingSample();
	}

	/** 按记忆应用点/按挖矿节奏。 */
	private void applyMineCadence(Minecraft client, LocalPlayer player, BlockPos pos, boolean newTarget, boolean retry) {
		float progress = destroyProgress(player, pos);
		if (newTarget || timingKey == null || !timingActive) {
			timingKey = mineTimingKey(player, pos);
			timingTicks = 0;
			timingHeld = false;
			timingActive = true;
			timingProgress = progress;
			timingVanillaInsta = BorerInstaPolicy.oneClickBreaks(progress);
			lastClickWasInsta = BorerMineTimingPolicy.tapSized(progress);
		}
		timingProgress = Math.max(timingProgress, progress);
		timingVanillaInsta = timingVanillaInsta || BorerInstaPolicy.oneClickBreaks(progress);
		BorerMineTimingPolicy.Memory remembered = mineTimings.get(timingKey);
		boolean crack = client.gameMode != null && BorerMineTimingPolicy.crackComplete(client.gameMode.getDestroyStage());
		boolean click = BorerMineTimingPolicy.shouldClick(remembered, progress, newTarget, retry, timingTicks);
		boolean hold = BorerMineTimingPolicy.shouldHold(remembered, progress, timingTicks, crack);
		if (click) {
			KeyMapping.click(InputConstants.getKey(client.options.keyAttack.saveString()));
		}
		client.options.keyAttack.setDown(hold);
		if (hold) {
			timingHeld = true;
			if (!BorerMineTimingPolicy.tapSized(progress)) lastClickWasInsta = false;
		}
		timingTicks++;
	}

	/** 点一下节奏是否结束。 */
	private boolean tapFinished(Minecraft client) {
		if (!timingActive || currentTarget == null || client.gameMode == null) return false;
		boolean crack = BorerMineTimingPolicy.crackComplete(client.gameMode.getDestroyStage());
		return BorerMineTimingPolicy.doneWithBlock(timingTicks, timingProgress, crack);
	}

	/** 对该格的破坏进度。 */
	private static float destroyProgress(LocalPlayer player, BlockPos pos) {
		if (player == null || pos == null || player.level() == null) return 0.0f;
		BlockState state = player.level().getBlockState(pos);
		if (state.isAir()) return 0.0f;
		return state.getDestroyProgress(player, player.level(), pos);
	}

	/** 本工具+方块的节奏键。 */
	private String mineTimingKey(LocalPlayer player, BlockPos pos) {
		if (player == null || pos == null || player.level() == null) {
			return BorerMineTimingPolicy.key("hand", "", 0, 0, false, "unknown");
		}
		ItemStack stack = player.getMainHandItem();
		String tool = stack.isEmpty() ? "hand" : BuiltInRegistries.ITEM.getKey(stack.getItem()).toString();
		String block = BorerText.blockId(player.level().getBlockState(pos));
		return BorerMineTimingPolicy.key(
			tool,
			BorerItems.enchantSignature(stack),
			BorerItems.hasteLevel(player),
			BorerItems.conduitLevel(player),
			player.isUnderWater(),
			block);
	}

	/** 记下本格挖矿节奏。 */
	private void recordMineTiming(Minecraft client) {
		if (!timingActive || timingKey == null) return;
		BorerMineTimingPolicy.Memory observed = BorerMineTimingPolicy.remember(timingHeld, timingTicks, timingProgress);
		if (observed != null && mineTimings.put(timingKey, observed)) {
			fileLog(client, "mine-timing key=" + timingKey
				+ " insta=" + observed.insta()
				+ " holdTicks=" + observed.holdTicks());
			mineTimings.save(client);
		}
		resetMineTimingSample();
	}

	/** 清空本格节奏采样。 */
	private void resetMineTimingSample() {
		timingKey = null;
		timingTicks = 0;
		timingHeld = false;
		timingActive = false;
		timingVanillaInsta = false;
		timingProgress = 0.0f;
	}

	/** 是否允许规划挖该格。 */
	boolean canPlanMine(Minecraft client, BlockPos pos) {
		if (mode == Mode.AREA && areaMin != null && areaMax != null) {
			if (!area.allowsMiningTarget(pos)) return false;
			return canMineFlightObstruction(client, pos);
		}
		return BorerMiningPolicy.canSelectTarget(
			shouldMine(client, pos), isMiningTargetSuppressed(client, pos));
	}

	/**
	 * 扫区域里「这口井还有没有可挖」：只看区域边界与可挖性，不锁当前竖井列。
	 * 换井时若走 {@link #canPlanMine}，别的列全被当成空，会误报「竖井已全部挖完」。
	 */
	boolean canSurveyAreaMine(Minecraft client, BlockPos pos) {
		if (mode != Mode.AREA || areaMin == null || areaMax == null) {
			return canPlanMine(client, pos);
		}
		if (!BorerAreaPolicy.containsXZ(
			pos.getX(), pos.getZ(),
			areaMin.getX(), areaMin.getZ(), areaMax.getX(), areaMax.getZ())) {
			return false;
		}
		if (pos.getY() > areaMax.getY()) return false;
		if (BorerAreaPolicy.belowBottom(areaBoundedDown, pos.getY(), areaMin.getY())) {
			return false;
		}
		return BorerMiningPolicy.canSelectTarget(
			shouldMine(client, pos), isMiningTargetSuppressed(client, pos));
	}

	/** 飞换井挡路：不受区域边界限制。头顶土在 areaMax 之上也要挖。 */
	boolean canMineFlightObstruction(Minecraft client, BlockPos pos) {
		return BorerMiningPolicy.canSelectTarget(
			shouldMine(client, pos), isMiningTargetSuppressed(client, pos));
	}

	/** 清理过期抑制目标。 */
	private void pruneSuppressedMiningTargets(Minecraft client) {
		if (client.level == null || suppressedMiningTargets.isEmpty()) return;
		long now = client.level.getGameTime();
		suppressedMiningTargets.entrySet().removeIf(entry ->
			!BorerMiningPolicy.suppressionActive(now, entry.getValue()));
	}

	/** 目标是否被抑制。 */
	private boolean isMiningTargetSuppressed(Minecraft client, BlockPos pos) {
		if (client.level == null || pos == null) return false;
		Long until = suppressedMiningTargets.get(pos);
		if (until == null) return false;
		if (!BorerMiningPolicy.suppressionActive(client.level.getGameTime(), until)) {
			suppressedMiningTargets.remove(pos);
			return false;
		}
		return true;
	}

	/** 暂时跳过该挖矿目标。 */
	private void suppressMiningTarget(Minecraft client, BlockPos pos, int ticks, String reason) {
		if (client.level == null || pos == null || wantedBlock(client.level.getBlockState(pos))) return;
		long until = client.level.getGameTime() + Math.max(1, ticks);
		suppressedMiningTargets.put(pos.immutable(), until);
		fileLog(client, "target-suppress reason=" + reason + " target=" + format(pos) + " until=" + until);
	}

	/**
	 * 跨 clear/reselect 累计真实准星失败。普通挡路到 10 秒后短期排除；
	 * 勾选矿本身到 10 秒后走矿脉 skip 流程，不能每 tick 重置成永不超时。
	 */
	private boolean recordAimMiss(Minecraft client, BlockPos pos, String reason) {
		if (client.level == null || pos == null) return false;
		if (!pos.equals(aimMissTarget)) {
			aimMissTarget = pos.immutable();
			aimMissTicks = 1;
		} else {
			aimMissTicks++;
		}
		if (aimMissTicks == 1 || aimMissTicks % MINING_RETRY_TICKS == 0) {
			fileLog(client, "aim-miss-progress reason=" + reason + " target=" + format(pos)
				+ " ticks=" + aimMissTicks + " crosshair=" + crosshairLabel(client));
		}
		if (aimMissTicks < MINING_STALL_TICKS) return false;
		boolean selectedOre = wantedBlock(client.level.getBlockState(pos));
		resetAimMissProgress();
		if (selectedOre) {
			return ores.skipActive(client, "真实准星连续 10 秒未命中矿石 " + format(pos));
		}
		if (BorerMiningPolicy.shouldSuppressRetry(false, true)) {
			suppressMiningTarget(client, pos, STALLED_BLOCK_SUPPRESS_TICKS, "10s-real-aim-miss");
		}
		return false;
	}

	/** 瞄准进度。 */
	void resetAimMissProgress() {
		aimMissTarget = null;
		aimMissTicks = 0;
	}

	/** 是否通道侧壁不该挖。 */
	private boolean isOffCorridorWall(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (mode == Mode.AREA) return false;
		if (pos == null || player == null || client.level == null) return false;
		if (wantedBlock(client.level.getBlockState(pos))) return false;
		boolean current = pos.equals(currentTarget) && corridorOrigin != null && corridorHeading != null;
		BlockPos feet = current ? corridorOrigin : player.blockPosition();
		Direction heading = current ? corridorHeading : forward;
		Direction right = heading.getClockWise();
		return BorerCenterPolicy.isOffCorridorWall(
			feet.getX(), feet.getZ(), pos.getX(), pos.getZ(),
			heading.getStepX(), heading.getStepZ(), right.getStepX(), right.getStepZ(), effectiveWidth());
	}

	/** 前方 1×2 是空气且落差在允许范围内。0 表示平地或不能走。 */
	int safeDropAhead(Minecraft client, LocalPlayer player) {
		if (player == null || isFlying(player)) return 0;
		BlockPos next = player.blockPosition().relative(forward);
		if (hasCollision(client, next) || hasCollision(client, next.above())) return 0;
		int drop = BorerHazards.safeFallDepth(client, next);
		return BorerFallPolicy.shouldWalkIntoDrop(drop, vertical.climbingToOre(client, player)) ? drop : 0;
	}

	/** 松开潜行、对齐通道中心，走进安全落差。有 NoFall 时更深的坑也走。 */
	private boolean walkIntoSafeDrop(Minecraft client, LocalPlayer player) {
		int drop = safeDropAhead(client, player);
		if (!BorerFallPolicy.abandonMineAndWalkDrop(drop, true)) return false;
		releaseMine(client);
		clearMiningTarget(client, "walk-safe-drop");
		client.options.keyShift.setDown(false);
		faceForward(player);
		nudgeToColumnCenter(client, player);
		client.options.keyUp.setDown(true);
		attemptedForward = true;
		status = "前方 " + drop + " 格落差，直接落下"
			+ (BorerFlight.meteorNoFallActive() ? "（NoFall）" : "");
		overlay(client, status, 0x55FFFF);
		fileLog(client, "walk-drop drop=" + drop
			+ " nofall=" + BorerFlight.meteorNoFallActive()
			+ " front=" + format(player.blockPosition().relative(forward))
			+ " player=" + precisePosition(player));
		return true;
	}

	/** 碰撞箱略偏出当前格时会卡住坑沿侧块；先横移回格子中心再往前走。 */
	void nudgeToColumnCenter(Minecraft client, LocalPlayer player) {
		if (mode == Mode.AREA && centerOnShaftColumn(client, player, true)) return;
		Direction right = forward.getClockWise();
		if (nudgeToAreaBandCenter(client, player, right)) return;
		BlockPos feet = standingColumn(client, player);
		double dx = feet.getX() + 0.5 - player.getX();
		double dz = feet.getZ() + 0.5 - player.getZ();
		double side = dx * right.getStepX() + dz * right.getStepZ();
		client.options.keyRight.setDown(BorerCenterPolicy.shouldPressRight(side));
		client.options.keyLeft.setDown(BorerCenterPolicy.shouldPressLeft(side));
	}

	/**
	 * 1×1 竖井必须站到格心才能掉下去。偏 0.2 格碰撞箱就会卡井沿。
	 * @return true 还在往格心挪，先别下落
	 */
	boolean centerOnShaftColumn(Minecraft client, LocalPlayer player) {
		return centerOnShaftColumn(client, player, true);
	}

	/** 把人居中到竖井柱；需要则返回 true。 */
	boolean centerOnShaftColumn(Minecraft client, LocalPlayer player, boolean hold) {
		if (player == null || client.options == null) return false;
		// Save the player's yaw BEFORE faceForward overwrites it.
		// WASD movement in Minecraft is relative to the player's yaw (horizontal
		// facing), not the look vector. Meteor controls the yaw each tick; our
		// HEAD mixin runs before Meteor, so the yaw at this point is Meteor's
		// yaw from the previous tick — the best approximation of what Minecraft
		// will use for WASD this tick. faceForward would overwrite it to east,
		// and getViewVector would then return east too, causing WASD to move
		// the player in the wrong direction when Meteor's yaw differs.
		float activeYaw = player.getYRot();
		if (mode == Mode.AREA) faceForward(player);
		int cx = areaShaftColumn != null ? areaShaftColumn.getX() : player.blockPosition().getX();
		int cz = areaShaftColumn != null ? areaShaftColumn.getZ() : player.blockPosition().getZ();
		double dx = cx + 0.5 - player.getX();
		double dz = cz + 0.5 - player.getZ();
		boolean need = BorerSteerPolicy.needMove(dx, dz);
		if (!need) {
			BorerFlight.restoreSpeed(client);
			resetSteer();
			if (hold) {
				client.options.keyUp.setDown(false);
				client.options.keyDown.setDown(false);
				client.options.keyLeft.setDown(false);
				client.options.keyRight.setDown(false);
			}
			return false;
		}
		BorerFlight.slowForPrecision(client);
		// Decompose WASD relative to the player's actual yaw (set by Meteor),
		// not the engine's forward direction. Minecraft interprets WASD keys
		// relative to the player's yaw, so the decomposition must match.
		double yawRad = Math.toRadians(activeYaw);
		double fwdX = -Math.sin(yawRad);
		double fwdZ = Math.cos(yawRad);
		double along = dx * fwdX + dz * fwdZ;
		double side = dx * (-fwdZ) + dz * fwdX;
		// Simple threshold-based keys: always press toward the target.
		// Do NOT use shouldBrake / pressPositive / pressNegative here.
		// Those use errorGrew reversal which misfires when Meteor Flight
		// pushes the player away from the target — the error grows even
		// when correct keys are pressed, causing a reversal loop.
		boolean up = along > BorerSteerPolicy.DEADZONE;
		boolean down = along < -BorerSteerPolicy.DEADZONE;
		boolean right = side > BorerSteerPolicy.DEADZONE;
		boolean left = side < -BorerSteerPolicy.DEADZONE;
		client.options.keyUp.setDown(up);
		client.options.keyDown.setDown(down);
		client.options.keyRight.setDown(right);
		client.options.keyLeft.setDown(left);
		client.options.keyJump.setDown(false);
		client.options.keyAttack.setDown(false);
		if (hold) {
			status = String.format(java.util.Locale.ROOT, "对准格心 偏 %.2f,%.2f yaw %.0f→%.0f", dx, dz, activeYaw, player.getYRot());
			overlay(client, status, 0xFFFF55);
		}
		return hold;
	}

	/** 记住走位误差供闭环。 */
	private void rememberSteer(double along, double side, double dist) {
		prevSteerAlong = along;
		prevSteerSide = side;
		prevSteerDist = dist;
	}

	/** 清空走位闭环记忆。 */
	void resetSteer() {
		prevSteerAlong = Double.NaN;
		prevSteerSide = Double.NaN;
		prevSteerDist = Double.NaN;
	}

	/** 3×2 走条带中间，旁边一列的掉落才进原版拾取。中间还是实心就先挖，不要往墙上贴。 */
	private boolean nudgeToAreaBandCenter(Minecraft client, LocalPlayer player, Direction right) {
		if (mode != Mode.AREA || areaMin == null || areaMax == null) return false;
		if (!BorerAreaPolicy.areaShaftUsesBandNudge()) {
			return false;
		}
		int width = areaStripWidth();
		if (!BorerAreaPolicy.walkCenteredStrip(width)) return false;
		Direction axis = areaStripAxis != null ? areaStripAxis : forward;
		BlockPos feet = player.blockPosition();
		int alongHere = BorerAreaPolicy.along(axis, feet.getX(), feet.getZ());
		int rowHere = BorerAreaPolicy.row(axis, feet.getX(), feet.getZ());
		int minRow = BorerAreaPolicy.minRow(axis, areaMin.getX(), areaMin.getZ(), areaMax.getX(), areaMax.getZ());
		int maxRow = BorerAreaPolicy.maxRow(axis, areaMin.getX(), areaMin.getZ(), areaMax.getX(), areaMax.getZ());
		double cx = BorerAreaPolicy.bandCenterX(axis, alongHere, rowHere, minRow, maxRow, width);
		double cz = BorerAreaPolicy.bandCenterZ(axis, alongHere, rowHere, minRow, maxRow, width);
		if (!bandCenterWalkable(client, player, cx, cz)) {
			client.options.keyRight.setDown(false);
			client.options.keyLeft.setDown(false);
			return true;
		}
		double side = BorerCenterPolicy.sideOffsetTo(
			player.getX(), player.getZ(), cx, cz, right.getStepX(), right.getStepZ());
		client.options.keyRight.setDown(BorerCenterPolicy.shouldPressRightToward(side));
		client.options.keyLeft.setDown(BorerCenterPolicy.shouldPressLeftToward(side));
		return true;
	}

	/** 条带中心是否可走。 */
	private boolean bandCenterWalkable(Minecraft client, LocalPlayer player, double cx, double cz) {
		BlockPos dest = BlockPos.containing(cx, player.getY() + 0.01, cz);
		if (hasCollision(client, dest) || hasCollision(client, dest.above())) return false;
		if (hasCollision(client, dest.below())) return true;
		return BorerHazards.canWalkOrFallInto(client, dest);
	}

	/** 写一条诊断日志。 */
	void logDiagnostic(Minecraft client, LocalPlayer player, String trigger) {
		BlockPos feet = player.blockPosition();
		BlockPos front = feet.relative(forward);
		Vec3 velocity = player.getDeltaMovement();
		String action = goingHome ? (returningToPortal ? "FLY_HOME" : "WALK_HOME")
			: loot.active() ? "COLLECT_LOOT"
			: currentTarget != null ? "MINE"
			: verticalMove != VerticalMove.NONE ? "VERTICAL_" + verticalMove
			: frontOccluded ? "WAIT_OCCLUDED"
			: attemptedForward ? "MOVE"
			: "WAIT";
		String summary = String.format(Locale.ROOT,
			"trigger=%s action=%s pos=%s feet=%s standCol=%s velocity=%.3f,%.3f,%.3f goal=%s target=%s targetBlock=%s "
				+ "targetOrigin=%s targetHeading=%s suppressed=%d aimMiss=%s/%d stage=%d mineStallTicks=%d retries=%d forward=%s vertical=%s moveStallTicks=%d occludedTicks=%d "
				+ "onGround=%s flying=%s meteorFlight=%s meteorStep=%s meteorNoFall=%s maxUpStep=%.2f bridgeAdvance=%s/%d "
				+ "jumpOrigin=%s jumpAttempts=%d jumpPress=%d jumpCooldown=%d forcedTallLower=%s "
				+ "oreScanCenter=%s oreScanLayer=%d oreScanChecked=%d lootOrigin=%s lootOre=%s lootTicks=%d lootSeen=%s "
					+ "keys=attack:%s,up:%s,down:%s,left:%s,right:%s,jump:%s,shift:%s yaw=%.1f areaState=%s crosshair=%s "
				+ "front=%s frontHead=%s ceiling=%s floor=%s routeIssue=%s status=%s",
			trigger, action, precisePosition(player), format(feet), format(standingColumn(client, player)),
			velocity.x, velocity.y, velocity.z,
			goalLabel(), currentTarget == null ? "-" : format(currentTarget),
			currentTarget == null ? "-" : blockLabel(client, currentTarget),
			corridorOrigin == null ? "-" : format(corridorOrigin),
			corridorHeading == null ? "-" : corridorHeading, suppressedMiningTargets.size(),
			aimMissTarget == null ? "-" : format(aimMissTarget), aimMissTicks,
			client.gameMode.getDestroyStage(), miningTargetTicks, miningRetryCount, forward, verticalMove,
			noMovementTicks, occludedTicks, player.onGround(), isFlying(player),
			BorerFlight.meteorFlightActive(), BorerFlight.meteorStepActive(), BorerFlight.meteorNoFallActive(),
			player.maxUpStep(), descentBridgeTarget == null ? "-" : format(descentBridgeTarget), descentBridgeAdvanceTicks,
			jumpOrigin == null ? "-" : format(jumpOrigin), jumpAttempts, jumpPressTicks, jumpRetryCooldownTicks,
			forcedTallObstacleLower == null ? "-" : format(forcedTallObstacleLower),
			oreScanCenter == null ? "-" : format(oreScanCenter), oreScanLayerCursor, oreScanCheckedBlocks,
			loot.origin() == null ? "-" : format(loot.origin()), loot.wanted() == null ? "-" : loot.wanted(), loot.ticks(), loot.seen(),
			client.options.keyAttack.isDown(), client.options.keyUp.isDown(),
			client.options.keyDown.isDown(), client.options.keyLeft.isDown(), client.options.keyRight.isDown(),
			client.options.keyJump.isDown(),
			client.options.keyShift.isDown(), player.getYRot(), mode == Mode.AREA ? area.diagnosticState() : "-", crosshairLabel(client), blockAt(client, front),
			blockAt(client, front.above()), blockAt(client, feet.above(2)), blockAt(client, front.below()),
			routeIssue.isBlank() ? "-" : routeIssue, status.isBlank() ? "-" : status);
		fileLog(client, summary);
	}

	/** 当前目标标签。 */
	private String goalLabel() {
		if (goingHome) {
			BlockPos dest = trail.last();
			if (dest == null && returningToPortal) dest = trail.portal();
			return (returningToPortal ? "portal@" : "home@") + (dest == null ? "-" : format(dest));
		}
		if (loot.active()) return loot.goalLabel();
		BlockPos goal = sideOreTargetPos != null ? sideOreTargetPos : oreTargetPos;
		return goal == null ? "-" : format(goal);
	}

	/** 准星所见标签。 */
	private String crosshairLabel(Minecraft client) {
		if (client.hitResult instanceof BlockHitResult hit) {
			return format(hit.getBlockPos()) + "/" + hit.getDirection();
		}
		return client.hitResult == null ? "-" : client.hitResult.getType().name();
	}

	/** 读取该格方块状态。 */
	String blockAt(Minecraft client, BlockPos pos) {
		return format(pos) + "=" + blockLabel(client, pos);
	}

	/** 方块短标签。 */
	private String blockLabel(Minecraft client, BlockPos pos) {
		return BorerText.blockId(client.level.getBlockState(pos));
	}

	/** 实体精确坐标。 */
	private String precisePosition(Entity entity) {
		return BorerText.precise(entity);
	}

	@Override
	/** 每帧画世界标记。 */
	public void emitFrameGizmos(Minecraft client) {
		if (client == null || client.player == null || client.level == null) return;
		preview.emitAreaPreviewGizmosIfNeeded(client);
		emitStatusHud(client);
		if (!showingHomeRoute && !goingHome) return;
		emitHomeRouteGizmos(client);
		if (goingHome && trail.portal() != null) {
			BorerGizmos.holdOnTop(Gizmos.cuboid(trail.portal(), GizmoStyle.strokeAndFill(0xFF66FFFF, 4.0F, 0x4466FFFF)));
		}
	}

	/** 需要时展示回家路线。 */
	private void presentHomeRouteIfNeeded(Minecraft client) {
		if (!showingHomeRoute || active || client.player == null) return;
		if (!inNether(client)) trail.detachPortalAnchor();
		if (trail.size() < 2) {
			showingHomeRoute = false;
			return;
		}
		if (trail.arrivedHome(client, client.player)) {
			showingHomeRoute = false;
			status = "已到挖矿起点";
			message(client, "已到挖矿起点，回家路线已关");
		}
	}

	/** 回家路线详情。 */
	private String homeRouteDetail(Minecraft client) {
		if (client.player == null) return "";
		BlockPos next = trail.nextTowardHome(client, client.player);
		int remain = trail.remainingTowardHome(client, client.player);
		BlockPos feet = client.player.blockPosition();
		String dest;
		if (next == null) dest = "起点";
		else if (!BorerTrailPolicy.drawSegmentNearPlayer(
			Math.abs(next.getX() - feet.getX()) + Math.abs(next.getZ() - feet.getZ()),
			Math.abs(next.getY() - feet.getY()))) {
			BlockPos home = trail.first();
			dest = home == null
				? "从你这儿走，金色箭头只画当前这层巷道"
				: "家在" + compass(feet, home) + "，箭头只画当前这层巷道";
		} else if (!BorerTrailPolicy.isCorridorSegment(feet.distManhattan(next))) {
			dest = "下一段还没记下，边走边记";
		} else dest = compass(feet, next);
		return dest + "  剩" + remain + "路点";
	}

	/** 画回家箭头。 */
	private void emitHomeRouteGizmos(Minecraft client) {
		if (client.player == null) return;
		BlockPos next = trail.emitHomeRoute(client, client.player);
		if (next == null) return;
		BlockPos feet = client.player.blockPosition();
		boolean near = BorerTrailPolicy.drawSegmentNearPlayer(
			Math.abs(next.getX() - feet.getX()) + Math.abs(next.getZ() - feet.getZ()),
			Math.abs(next.getY() - feet.getY()));
		boolean inCorridor = near && BorerTrailPolicy.isCorridorSegment(feet.distManhattan(next));
		Vec3 from = Vec3.atCenterOf(feet).add(0.0, 0.4, 0.0);
		Vec3 to = Vec3.atCenterOf(next);
		if (inCorridor) {
			BorerGizmos.holdOnTop(Gizmos.arrow(from, to, 0xFFFFCC33, 3.6F));
			BorerGizmos.holdOnTop(Gizmos.cuboid(next, GizmoStyle.strokeAndFill(0xFFFFAA00, 3.2F, 0x55FFAA00)));
		}
	}

	/** 松开挖掘键。 */
	void releaseMine(Minecraft client) {
		if (client.options == null) return;
		retreating = false;
		client.options.keyAttack.setDown(false);
		client.options.keyUp.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
		client.options.keyDown.setDown(false);
		client.options.keyJump.setDown(false);
		if (client.gameMode != null) client.gameMode.stopDestroyBlock();
	}

	/** 松开全部输入。 */
	private void releaseAll(Minecraft client) {
		releaseMine(client);
		if (client.options == null) return;
		client.options.keyShift.setDown(false);
		client.options.keyUse.setDown(false);
		holdingShield = false;
	}

	/** 恢复玩家手动攻击状态。 */
	private void restoreManualAttack(Minecraft client) {
		if (client.options == null) return;
		if (client.player != null) {
			client.hitResult = client.player.pick(client.player.blockInteractionRange(), 1.0F, false);
			client.crosshairPickEntity = null;
		}
		KeyMapping.setAll();
	}

	/** 坐标/对象短文本。 */
	private static String format(BlockPos pos) {
		return BorerText.block(pos);
	}

	/** 向玩家发聊天消息。 */
	static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[盾构机] " + text));
	}

	/** 追加一行 borer 文件日志。 */
	void fileLog(Minecraft client, String line) {
		LOGGER.info("[twob2tkit/Borer {}] {}", RUNTIME_VERSION, line);
		BorerFileLog.append(client, RUNTIME_VERSION + " " + line);
	}
}
