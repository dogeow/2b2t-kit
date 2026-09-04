package dev.twob2tkit;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.CommonPlayerSpawnInfo;
import dev.twob2tkit.adventure.AdventureMonitor;
import dev.twob2tkit.adventure.LocalAdvancementManager;
import dev.twob2tkit.borer.BorerAreaMarks;
import dev.twob2tkit.borer.TunnelBorer;
import dev.twob2tkit.builder.MachineBuilder;
import dev.twob2tkit.chopper.AutoChopper;
import dev.twob2tkit.combat.CombatWatch;
import dev.twob2tkit.feeder.AutoFeeder;
import dev.twob2tkit.fisher.AutoFisher;
import dev.twob2tkit.nether.NetherRoofAssist;
import dev.twob2tkit.piglin.PiglinBrawler;
import dev.twob2tkit.planter.AutoPlanter;
import dev.twob2tkit.recipe.LocalRecipeBookInjector;
import dev.twob2tkit.recipe.RecipeDiscoveryTracker;
import dev.twob2tkit.storage.ContainerAssistant;
import dev.twob2tkit.structure.SeedScout;
import dev.twob2tkit.structure.StructureGuide;
import dev.twob2tkit.surround.AutoSurround;
import dev.twob2tkit.survival.SurvivalAlertMonitor;
import dev.twob2tkit.villager.VillagerScanner;

/**
 * 客户端入口：加载配置、注册按键/指令、tick 分发与各模块开关编排。
 */
public final class KitClient implements ClientModInitializer {
	public static final String MOD_ID = "2b2t-kit";
	public static final org.slf4j.Logger LOGGER = org.slf4j.LoggerFactory.getLogger(MOD_ID);

	private KitConfig config;
	private KitController controller;
	private SurvivalAlertMonitor survivalAlertMonitor;
	private AdventureMonitor adventureMonitor;
	private CombatWatch combatWatch;
	private ContainerAssistant containerAssistant;
	private RecipeDiscoveryTracker recipeDiscoveryTracker;
	private MachineBuilder machineBuilder;
	private TunnelBorer tunnelBorer;
	private AutoSurround autoSurround;
	private AutoFeeder autoFeeder;
	private AutoPlanter autoPlanter;
	private AutoChopper autoChopper;
	private AutoFisher autoFisher;
	private SeedScout seedScout;
	private NetherRoofAssist netherRoofAssist;
	private StructureGuide structureGuide;
	private PiglinBrawler piglinBrawler;
	private VillagerScanner villagerScanner;
	private boolean frozeForDeath;
	private static KitClient instance;
	private boolean emergencyWasDown;
	private static boolean forceSneakForPlacement;
	private int lastSurroundToggleTick = Integer.MIN_VALUE;
	private int lastFeederToggleTick = Integer.MIN_VALUE;
	private int lastPlanterToggleTick = Integer.MIN_VALUE;
	private int lastChopperToggleTick = Integer.MIN_VALUE;
	private int lastFisherToggleTick = Integer.MIN_VALUE;
	private int lastVillagerScanToggleTick = Integer.MIN_VALUE;
	/** 1=下一次左键为点A，2=点B。 */
	private int pickingAreaCorner;

	/** 初始化模块、按键、指令与 tick 回调。 */
	@Override
	public void onInitializeClient() {
		instance = this;
		config = KitConfig.load();
		controller = new KitController(config);
		survivalAlertMonitor = new SurvivalAlertMonitor(config);
		adventureMonitor = new AdventureMonitor(config);
		combatWatch = new CombatWatch(config);
		containerAssistant = new ContainerAssistant(config);
		recipeDiscoveryTracker = new RecipeDiscoveryTracker(config);
		machineBuilder = new MachineBuilder();
		tunnelBorer = new TunnelBorer(config);
		autoSurround = new AutoSurround(config);
		autoFeeder = new AutoFeeder(config);
		autoPlanter = new AutoPlanter(config);
		autoChopper = new AutoChopper(config);
		autoFisher = new AutoFisher(config);
		seedScout = new SeedScout();
		seedScout.load();
		netherRoofAssist = new NetherRoofAssist();
		structureGuide = new StructureGuide();
		piglinBrawler = new PiglinBrawler(config);
		villagerScanner = new VillagerScanner(config);
		LocalRecipeBookInjector.initialize(config);
		LocalAdvancementManager.initialize(config);
		KitKeys.register();
		ClientTickEvents.END_CLIENT_TICK.register(this::onEndTick);
		ClientCommandRegistrationCallback.EVENT.register((dispatcher, registryAccess) ->
			KitCommands.register(dispatcher, config, controller, machineBuilder));
		LOGGER.info("2b2t-kit loaded. Use /2b2t-kit help");
	}

	/** 帧尾：热键、监视器、围箱与观察类逻辑。 */
	private void onEndTick(Minecraft client) {
		handleHeldKeys(client);
		if (KitKeys.suppressHotkeys) {
			while (KitKeys.EMERGENCY_STOP.consumeClick()) {
			}
			while (KitKeys.OPEN_GUI.consumeClick()) {
			}
			while (KitKeys.START_STOP.consumeClick()) {
			}
			while (KitKeys.TOGGLE_BORER.consumeClick()) {
			}
			while (KitKeys.BORER_HOME.consumeClick()) {
			}
			while (KitKeys.PORTAL_HOME.consumeClick()) {
			}
			while (KitKeys.TOGGLE_SURROUND.consumeClick()) {
			}
			while (KitKeys.TOGGLE_FEEDER.consumeClick()) {
			}
			while (KitKeys.TOGGLE_PLANTER.consumeClick()) {
			}
			while (KitKeys.TOGGLE_CHOPPER.consumeClick()) {
			}
			while (KitKeys.TOGGLE_FISHER.consumeClick()) {
			}
			while (KitKeys.TOGGLE_VILLAGER_SCAN.consumeClick()) {
			}
		} else {
			while (KitKeys.EMERGENCY_STOP.consumeClick()) emergencyStop("按下紧急停止键");
			while (KitKeys.OPEN_GUI.consumeClick()) openGui(client);
			while (KitKeys.START_STOP.consumeClick()) toggleCruiseFromKey(client);
			while (KitKeys.TOGGLE_BORER.consumeClick()) toggleBorer(client);
			while (KitKeys.BORER_HOME.consumeClick()) goBorerHome(client);
			while (KitKeys.PORTAL_HOME.consumeClick()) goNetherPortal(client);
			while (KitKeys.TOGGLE_SURROUND.consumeClick()) toggleSurround(client);
			while (KitKeys.TOGGLE_FEEDER.consumeClick()) toggleFeeder(client);
			while (KitKeys.TOGGLE_PLANTER.consumeClick()) togglePlanter(client);
			while (KitKeys.TOGGLE_CHOPPER.consumeClick()) toggleChopper(client);
			while (KitKeys.TOGGLE_FISHER.consumeClick()) toggleFisher(client);
			while (KitKeys.TOGGLE_VILLAGER_SCAN.consumeClick()) toggleVillagerScan(client);
		}
		if (combatWatch != null) combatWatch.tick(client);
		if (client.player != null && client.player.isDeadOrDying()) {
			freezeForDeath(client);
			if (adventureMonitor != null) adventureMonitor.tick(client);
			return;
		}
		frozeForDeath = false;
		controller.flushPendingDisconnect(client);
		survivalAlertMonitor.tick(client);
		adventureMonitor.tick(client);
		containerAssistant.tick(client);
		recipeDiscoveryTracker.tick(client);
		LocalAdvancementManager.tick(client);
		machineBuilder.tick(client);
		autoSurround.tick(client);
		if (seedScout != null) seedScout.tick(client);
		if (structureGuide != null) structureGuide.tick(client);
		if (villagerScanner != null) villagerScanner.tick(client);
		if (tunnelBorer != null) tunnelBorer.observeWorld(client);
		if (controller != null && controller.isActive()) controller.reapplyNavigationRotation(client);
	}

	/** 物理按住紧急停止（含界面内）。 */
	private void handleHeldKeys(Minecraft client) {
		boolean emergencyDown = KitKeys.isPhysicallyDown(client, KitKeys.EMERGENCY_STOP);
		boolean typingInOtherScreen = client.screen != null
			&& !(client.screen instanceof KitHudScreen)
			&& client.screen.getFocused() instanceof EditBox box
			&& box.canConsumeInput();
		if (!KitKeys.suppressHotkeys && !typingInOtherScreen && emergencyDown && !emergencyWasDown) {
			emergencyStop("按下紧急停止键");
			if (client.screen instanceof KitHudScreen) client.setScreen(null);
		}
		emergencyWasDown = emergencyDown;
	}

	/** 建造对着容器潜行放置时由 MachineBuilder 置位。 */
	public static void setForceSneakForPlacement(boolean value) {
		forceSneakForPlacement = value;
	}

	/** 放漏斗/箱子时强制潜行，让 isShiftKeyDown 保持为真。 */
	public static boolean forceSneakForPlacement() {
		return forceSneakForPlacement;
	}

	/** 停掉所有自动动作。 */
	public static void emergencyStop(String reason) {
		if (instance == null) return;
		Minecraft client = Minecraft.getInstance();
		instance.machineBuilder.cancel(client, reason);
		instance.tunnelBorer.stop(client, reason);
		instance.autoSurround.stop(client, reason);
		instance.autoFeeder.stop(client, reason);
		instance.autoPlanter.stop(client, reason);
		instance.autoChopper.stop(client, reason);
		instance.autoFisher.stop(client, reason);
		if (instance.netherRoofAssist != null) instance.netherRoofAssist.stop(client, reason);
		if (instance.piglinBrawler != null) instance.piglinBrawler.stop(client, reason);
		instance.controller.stop(client, reason);
		if (instance.structureGuide != null) instance.structureGuide.stop();
	}

	/** 死亡时停动作并提示关掉 Auto Respawn。 */
	private static void freezeForDeath(Minecraft client) {
		if (instance == null || instance.frozeForDeath) return;
		instance.frozeForDeath = true;
		emergencyStop("已死亡");
		if (client.player != null) {
			client.player.sendSystemMessage(Component.literal(
				"[2b2t-kit] 已死亡，所有自动动作已停，停在死亡界面。请自己点重生去捡物。如果没点就活了，关掉 Meteor 的 Auto Respawn，否则掉落物会在出生点刷新"
			).withColor(0xFF5555));
		}
	}

	/** 结构指引实例。 */
	public static StructureGuide structureGuide() {
		return instance == null ? null : instance.structureGuide;
	}

	/** 世界每帧收集 gizmo 时调用，指引箭头跟镜头走，不会叠两拍。 */
	public static void emitFrameGizmos(Minecraft client) {
		if (instance == null) return;
		try {
			if (instance.structureGuide != null) instance.structureGuide.render(client);
		} catch (IllegalStateException ignored) {
		}
		try {
			if (instance.tunnelBorer != null) instance.tunnelBorer.emitFrameGizmos(client);
		} catch (IllegalStateException ignored) {
		}
	}

	/** 盾构实例。 */
	public static TunnelBorer borer() {
		return instance == null ? null : instance.tunnelBorer;
	}

	/** 盾构正在挖且非回家。 */
	public static boolean borerIsBreaking() {
		TunnelBorer borer = borer();
		return borer != null && borer.isActive() && !borer.isGoingHome();
	}

	/** 记住刚点的容器坐标。 */
	public static void noteStorageClick(BlockPos pos) {
		if (instance != null && instance.containerAssistant != null) {
			instance.containerAssistant.rememberClickedStorage(pos);
		}
	}

	/** 围箱实例。 */
	public static AutoSurround surround() {
		return instance == null ? null : instance.autoSurround;
	}

	/** 喂养实例。 */
	public static AutoFeeder feeder() {
		return instance == null ? null : instance.autoFeeder;
	}

	/** 种田实例。 */
	public static AutoPlanter planter() {
		return instance == null ? null : instance.autoPlanter;
	}

	/** 挖树实例。 */
	public static AutoChopper chopper() {
		return instance == null ? null : instance.autoChopper;
	}

	/** 钓鱼实例。 */
	public static AutoFisher fisher() {
		return instance == null ? null : instance.autoFisher;
	}

	/** 打猪人实例。 */
	public static PiglinBrawler brawler() {
		return instance == null ? null : instance.piglinBrawler;
	}

	/** 种子侦察实例。 */
	public static SeedScout seedScout() {
		return instance == null ? null : instance.seedScout;
	}

	/** 村民扫描实例。 */
	public static VillagerScanner villagerScanner() {
		return instance == null ? null : instance.villagerScanner;
	}

	/** 画屏幕层 HUD（村庄、建造等）。 */
	public static void renderScreenHud(Minecraft client, net.minecraft.client.gui.GuiGraphicsExtractor graphics) {
		if (instance == null) return;
		if (instance.villagerScanner != null) instance.villagerScanner.renderHud(client, graphics);
		if (instance.machineBuilder != null) instance.machineBuilder.renderHud(client, graphics);
	}

	/** 停下冲突模块后开始上基岩顶。 */
	public static void startNetherRoof(Minecraft client, boolean thenCruise, double x, double z, double y) {
		if (instance == null || instance.netherRoofAssist == null) return;
		if (instance.tunnelBorer.isActive()) instance.tunnelBorer.stop(client, "上基岩顶");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "上基岩顶");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "上基岩顶");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "上基岩顶");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "上基岩顶");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "上基岩顶");
		if (instance.piglinBrawler.isActive()) instance.piglinBrawler.stop(client, "上基岩顶");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "上基岩顶");
		}
		instance.netherRoofAssist.start(client, thenCruise, x, z, y);
		if (client.screen instanceof KitHudScreen) client.setScreen(null);
	}

	/** 登录时捕获种子哈希。 */
	public static void captureSpawnSeed(CommonPlayerSpawnInfo info) {
		if (instance != null && instance.seedScout != null) instance.seedScout.captureSpawnInfo(info);
	}

	/** 投影建造实例。 */
	public static MachineBuilder machines() {
		return instance == null ? null : instance.machineBuilder;
	}

	/** 配置实例。 */
	public static KitConfig config() {
		return instance == null ? null : instance.config;
	}

	/** 巡航控制器。 */
	public static KitController controller() {
		return instance == null ? null : instance.controller;
	}

	/** 是否有挂机类自动在跑（巡航/盾构/钓等）。 */
	public static boolean anyAfkAuto() {
		if (instance == null) return false;
		return instance.controller != null && instance.controller.isActive()
			|| instance.tunnelBorer != null && instance.tunnelBorer.isActive()
			|| instance.autoFisher != null && instance.autoFisher.isActive()
			|| instance.autoChopper != null && instance.autoChopper.isActive()
			|| instance.autoPlanter != null && instance.autoPlanter.isActive()
			|| instance.autoFeeder != null && instance.autoFeeder.isActive()
			|| instance.netherRoofAssist != null && instance.netherRoofAssist.isActive();
	}

	/** 紧急停止并排队离线。 */
	public static void safeLogout(Minecraft client, String reason) {
		if (instance == null || client == null) return;
		emergencyStop(reason);
		instance.controller.requestLogout(reason);
		if (client.player != null) {
			client.player.sendSystemMessage(Component.literal("[2b2t-kit] " + reason).withColor(0xFF5555));
		}
	}

	/** 热加载或恢复内置盾构引擎。 */
	public static TunnelBorer.ReloadResult reloadBorerRuntime(Minecraft client, boolean installBundled) {
		if (instance == null || instance.tunnelBorer == null) {
			return new TunnelBorer.ReloadResult(false, "2b2t-kit 尚未初始化");
		}
		return installBundled
			? instance.tunnelBorer.installBundledUpdate(client)
			: instance.tunnelBorer.reload(client);
	}

	/** 开始巡航前停冲突模块。 */
	public static void prepareForCruise(Minecraft client) {
		if (instance == null) return;
		if (instance.tunnelBorer.isActive()) instance.tunnelBorer.stop(client, "开始巡航");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "开始巡航");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "开始巡航");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "开始巡航");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "开始巡航");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "开始巡航");
		if (instance.netherRoofAssist != null && instance.netherRoofAssist.isActive()) {
			instance.netherRoofAssist.stop(client, "开始巡航");
		}
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "开始巡航");
		}
	}

	/** 开始投影建造前停冲突模块。 */
	public static void prepareForMachine(Minecraft client) {
		if (instance == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "开始投影建造");
		if (instance.tunnelBorer.isActive()) instance.tunnelBorer.stop(client, "开始投影建造");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "开始投影建造");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "开始投影建造");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "开始投影建造");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "开始投影建造");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "开始投影建造");
	}

	/** 开始盾构前停冲突模块。 */
	public static void prepareForBorer(Minecraft client) {
		if (instance == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "开始盾构");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "开始盾构");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "开始盾构");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "开始盾构");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "开始盾构");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "开始盾构");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "开始盾构");
		}
	}

	/** 打开或关闭主界面（模块栏或分页）。 */
	public static void openGui(Minecraft client) {
		if (client.player == null) return;
		if (client.screen instanceof KitHudScreen) {
			client.setScreen(null);
			return;
		}
		if (client.screen == null) {
			if (instance.config.clickGui) {
				client.setScreen(new ClickGuiScreen(instance.config, instance.controller));
			} else {
				client.setScreen(KitTab.home(instance.config, instance.controller));
			}
		}
	}

	/** 热键开关盾构。 */
	public static void toggleBorer(Minecraft client) {
		if (instance == null || client.player == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "开始盾构，已停巡航");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "开始盾构，已停围箱");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "开始盾构，已停喂养");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "开始盾构，已停种田");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "开始盾构，已停挖树");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "开始盾构，已停钓鱼");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "开始盾构，已停建造");
		}
		instance.tunnelBorer.toggle(client);
	}

	/** 沿挖矿原路返回起点。 */
	public static void goBorerHome(Minecraft client) {
		if (instance == null || client.player == null || instance.tunnelBorer == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "盾构回家，已停巡航");
		instance.tunnelBorer.goHome(client);
	}

	/** 沿走过的路飞回记下的地狱门。 */
	public static void goNetherPortal(Minecraft client) {
		if (instance == null || client.player == null || instance.tunnelBorer == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "回地狱门，已停巡航");
		if (instance.netherRoofAssist != null && instance.netherRoofAssist.isActive()) {
			instance.netherRoofAssist.stop(client, "回地狱门");
		}
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "回地狱门");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "回地狱门");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "回地狱门");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "回地狱门");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "回地狱门");
		}
		instance.tunnelBorer.goToPortal(client);
		if (client.screen instanceof KitHudScreen) client.setScreen(null);
	}

	/** 热键开关围箱（同 tick 去重）。 */
	public static void toggleSurround(Minecraft client) {
		if (instance == null || client.player == null) return;
		int tick = client.player.tickCount;
		if (instance.lastSurroundToggleTick == tick) return;
		instance.lastSurroundToggleTick = tick;
		if (instance.autoSurround.isActive()) {
			instance.autoSurround.stop(client, "按键停止");
			return;
		}
		startSurround(client, AutoSurround.Mode.fromConfig(instance.config.surroundMode));
	}

	/** 按模式开始围箱（可停盾构）。 */
	public static void startSurround(Minecraft client, AutoSurround.Mode mode) {
		startSurround(client, mode, true);
	}

	/** 盾构遇苦力怕时跟脚围箱，不停盾构。 */
	public static void startSurroundFromBorer(Minecraft client) {
		startSurround(client, AutoSurround.Mode.PLUS, false);
	}

	/** 开始围箱；stopBorer 控制是否停盾构。 */
	public static void startSurround(Minecraft client, AutoSurround.Mode mode, boolean stopBorer) {
		if (instance == null || client.player == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "开始围箱，已停巡航");
		if (stopBorer && instance.tunnelBorer.isActive()) instance.tunnelBorer.stop(client, "开始围箱，已停盾构");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "开始围箱，已停喂养");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "开始围箱，已停种田");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "开始围箱，已停挖树");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "开始围箱，已停钓鱼");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "开始围箱，已停建造");
		}
		instance.autoSurround.start(client, mode);
		if (client.screen instanceof KitHudScreen) client.setScreen(null);
	}

	/** 热键开关喂养。 */
	public static void toggleFeeder(Minecraft client) {
		if (instance == null || client.player == null) return;
		int tick = client.player.tickCount;
		if (instance.lastFeederToggleTick == tick) return;
		instance.lastFeederToggleTick = tick;
		if (instance.autoFeeder.isActive()) {
			instance.autoFeeder.stop(client, "按键停止");
			return;
		}
		startFeeder(client);
	}

	/** 停下冲突后开始喂养。 */
	public static void startFeeder(Minecraft client) {
		if (instance == null || client.player == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "开始喂养，已停巡航");
		if (instance.tunnelBorer.isActive()) instance.tunnelBorer.stop(client, "开始喂养，已停盾构");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "开始喂养，已停围箱");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "开始喂养，已停种田");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "开始喂养，已停挖树");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "开始喂养，已停钓鱼");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "开始喂养，已停建造");
		}
		instance.autoFeeder.start(client);
		if (client.screen instanceof KitHudScreen) client.setScreen(null);
	}

	/** 热键开关种田。 */
	public static void togglePlanter(Minecraft client) {
		if (instance == null || client.player == null) return;
		int tick = client.player.tickCount;
		if (instance.lastPlanterToggleTick == tick) return;
		instance.lastPlanterToggleTick = tick;
		if (instance.autoPlanter.isActive()) {
			instance.autoPlanter.stop(client, "按键停止");
			return;
		}
		startPlanter(client);
	}

	/** 停下冲突后开始种田。 */
	public static void startPlanter(Minecraft client) {
		if (instance == null || client.player == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "开始种田，已停巡航");
		if (instance.tunnelBorer.isActive()) instance.tunnelBorer.stop(client, "开始种田，已停盾构");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "开始种田，已停围箱");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "开始种田，已停喂养");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "开始种田，已停挖树");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "开始种田，已停钓鱼");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "开始种田，已停建造");
		}
		instance.autoPlanter.start(client);
		if (client.screen instanceof KitHudScreen) client.setScreen(null);
	}

	/** 热键开关挖树。 */
	public static void toggleChopper(Minecraft client) {
		if (instance == null || client.player == null) return;
		int tick = client.player.tickCount;
		if (instance.lastChopperToggleTick == tick) return;
		instance.lastChopperToggleTick = tick;
		if (instance.autoChopper.isActive()) {
			instance.autoChopper.stop(client, "按键停止");
			return;
		}
		startChopper(client);
	}

	/** 停下冲突后开始挖树。 */
	public static void startChopper(Minecraft client) {
		if (instance == null || client.player == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "开始挖树，已停巡航");
		if (instance.tunnelBorer.isActive()) instance.tunnelBorer.stop(client, "开始挖树，已停盾构");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "开始挖树，已停围箱");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "开始挖树，已停喂养");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "开始挖树，已停种田");
		if (instance.autoFisher.isActive()) instance.autoFisher.stop(client, "开始挖树，已停钓鱼");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "开始挖树，已停建造");
		}
		instance.autoChopper.start(client);
		if (client.screen instanceof KitHudScreen) client.setScreen(null);
	}

	/** 热键开关钓鱼。 */
	public static void toggleFisher(Minecraft client) {
		if (instance == null || client.player == null) return;
		int tick = client.player.tickCount;
		if (instance.lastFisherToggleTick == tick) return;
		instance.lastFisherToggleTick = tick;
		if (instance.autoFisher.isActive()) {
			instance.autoFisher.stop(client, "按键停止");
			return;
		}
		startFisher(client);
	}

	/** 停下冲突后开始钓鱼。 */
	public static void startFisher(Minecraft client) {
		if (instance == null || client.player == null) return;
		if (instance.controller.isActive()) instance.controller.stop(client, "开始钓鱼，已停巡航");
		if (instance.tunnelBorer.isActive()) instance.tunnelBorer.stop(client, "开始钓鱼，已停盾构");
		if (instance.autoSurround.isActive()) instance.autoSurround.stop(client, "开始钓鱼，已停围箱");
		if (instance.autoFeeder.isActive()) instance.autoFeeder.stop(client, "开始钓鱼，已停喂养");
		if (instance.autoPlanter.isActive()) instance.autoPlanter.stop(client, "开始钓鱼，已停种田");
		if (instance.autoChopper.isActive()) instance.autoChopper.stop(client, "开始钓鱼，已停挖树");
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "开始钓鱼，已停建造");
		}
		instance.autoFisher.start(client);
		if (client.screen instanceof KitHudScreen) client.setScreen(null);
	}

	/** 热键开关村民扫描。 */
	public static void toggleVillagerScan(Minecraft client) {
		if (instance == null || instance.villagerScanner == null) return;
		if (client.player != null) {
			int tick = client.player.tickCount;
			if (instance.lastVillagerScanToggleTick == tick) return;
			instance.lastVillagerScanToggleTick = tick;
		}
		instance.villagerScanner.toggle(client);
	}

	/** 开始/停止键：优先停当前自动，否则恢复巡航。 */
	public static void toggleCruiseFromKey(Minecraft client) {
		if (instance == null || client.player == null) return;
		if (instance.netherRoofAssist != null && instance.netherRoofAssist.isActive()) {
			instance.netherRoofAssist.stop(client, "按键停止上顶");
			return;
		}
		if (instance.autoChopper.isActive()) {
			instance.autoChopper.stop(client, "按键停止挖树");
			return;
		}
		if (instance.autoFisher.isActive()) {
			instance.autoFisher.stop(client, "按键停止钓鱼");
			return;
		}
		if (instance.autoPlanter.isActive()) {
			instance.autoPlanter.stop(client, "按键停止种田");
			return;
		}
		if (instance.autoFeeder.isActive()) {
			instance.autoFeeder.stop(client, "按键停止喂养");
			return;
		}
		if (instance.autoSurround.isActive()) {
			instance.autoSurround.stop(client, "按键停止围箱");
			return;
		}
		if (instance.machineBuilder.isPlacing()) {
			instance.machineBuilder.cancel(client, "按键停止建造");
			return;
		}
		if (instance.controller.isActive()) {
			instance.controller.stop(client, "按键停止巡航");
			return;
		}
		if (NetherRoofAssist.inNether(client) && !NetherRoofAssist.onRoof(client.player)) {
			if (!instance.controller.resume(client)) {
				instance.controller.start(client, client.player.getX(), client.player.getZ(), NetherRoofAssist.underRoofCruiseY());
			}
			return;
		}
		if (instance.tunnelBorer.isActive()) {
			instance.tunnelBorer.stop(client, "按键停止盾构");
			return;
		}
		if (!instance.controller.resume(client)) {
			if (client.player != null) {
				client.player.sendSystemMessage(Component.literal("[2b2t-kit] 还没有保存过目标，请先在界面填写坐标或按 "
					+ KitKeys.boundLabel(KitKeys.OPEN_GUI) + " 打开设置"));
			}
		}
	}

	/** 全息预览滚轮钩子（当前恒 false）。 */
	public static boolean handlePreviewScroll(double yoffset) {
		return false;
	}

	/** 由 Minecraft.tick HEAD mixin 调用：在玩家采样按键之前写入导航输入。 */
	public static void tickNavigation(Minecraft client) {
		if (instance == null || instance.controller == null) return;
		handleAreaPick(client);
		if (client.player != null && client.player.isDeadOrDying()) {
			freezeForDeath(client);
			return;
		}
		if (instance.machineBuilder.isPlacing()) return;
		if (instance.piglinBrawler != null && instance.piglinBrawler.isActive()) {
			instance.piglinBrawler.tick(client);
			return;
		}
		boolean otherAuto = instance.tunnelBorer.isActive()
			|| instance.autoSurround.isActive()
			|| instance.autoFeeder.isActive()
			|| instance.autoPlanter.isActive()
			|| instance.autoChopper.isActive()
			|| instance.autoFisher.isActive()
			|| instance.netherRoofAssist != null && instance.netherRoofAssist.isActive()
			|| instance.controller.isActive();
		if (instance.piglinBrawler != null && instance.piglinBrawler.tickGhastGuard(client, !otherAuto)) return;
		if (instance.tunnelBorer.isActive()) {
			instance.tunnelBorer.tick(client);
			return;
		}
		if (instance.autoSurround.isActive()) return;
		if (instance.autoFeeder.isActive()) {
			instance.autoFeeder.tick(client);
			return;
		}
		if (instance.autoPlanter.isActive()) {
			instance.autoPlanter.tick(client);
			return;
		}
		if (instance.autoChopper.isActive()) {
			instance.autoChopper.tick(client);
			return;
		}
		if (instance.autoFisher.isActive()) {
			instance.autoFisher.tick(client);
			return;
		}
		if (instance.netherRoofAssist != null && instance.netherRoofAssist.isActive()) {
			instance.netherRoofAssist.tick(client);
			return;
		}
		instance.controller.tick(client);
	}

	/** 按优先级把当前模块的朝向再写回。 */
	public static void reapplyNavigationRotation(Minecraft client) {
		if (instance == null || instance.controller == null) return;
		if (client.player != null && client.player.isDeadOrDying()) return;
		if (instance.piglinBrawler != null && instance.piglinBrawler.hasLook()) {
			instance.piglinBrawler.reapplyLook(client);
			return;
		}
		if (instance.machineBuilder.isPlacing()) return;
		if (instance.tunnelBorer.isActive()) {
			instance.tunnelBorer.reapplyLook(client);
			return;
		}
		if (instance.autoSurround.isActive()) return;
		if (instance.autoFeeder != null && instance.autoFeeder.isActive()) {
			instance.autoFeeder.reapplyLook(client);
			return;
		}
		if (instance.autoPlanter != null && instance.autoPlanter.isActive()) {
			instance.autoPlanter.reapplyLook(client);
			return;
		}
		if (instance.autoChopper != null && instance.autoChopper.isActive()) {
			instance.autoChopper.reapplyLook(client);
			return;
		}
		if (instance.autoFisher != null && instance.autoFisher.isActive()) {
			instance.autoFisher.reapplyLook(client);
			return;
		}
		if (instance.netherRoofAssist != null && instance.netherRoofAssist.isActive()) {
			instance.netherRoofAssist.reapplyLook(client);
			return;
		}
		if (instance.piglinBrawler != null && instance.piglinBrawler.isActive()) {
			instance.piglinBrawler.reapplyLook(client);
			return;
		}
		instance.controller.reapplyNavigationRotation(client);
	}

	/** 关掉区域预览框。 */
	public static void dismissAreaPreview() {
		if (instance != null && instance.tunnelBorer != null) {
			instance.tunnelBorer.dismissAreaPreview();
		}
	}

	/** 进入下次左键标点 A/B。 */
	public static void beginPickingArea(Minecraft client, int corner) {
		if (instance == null) return;
		instance.pickingAreaCorner = corner == 2 ? 2 : 1;
		BorerAreaMarks.tell(client, corner == 2
			? "看向目标方块后点左键，设为区域点B（最远 " + BorerAreaMarks.PICK_RANGE + " 格）"
			: "看向目标方块后点左键，设为区域点A（最远 " + BorerAreaMarks.PICK_RANGE + " 格）");
	}

	/** 正在标的角：0 无，1=A，2=B。 */
	public static int pickingAreaCorner() {
		return instance == null ? 0 : instance.pickingAreaCorner;
	}

	/** 消费左键把准星方块写入点 A/B。 */
	private static void handleAreaPick(Minecraft client) {
		if (instance == null || instance.pickingAreaCorner == 0 || client == null) return;
		if (client.screen != null || client.player == null || client.options == null) return;
		if (!client.options.keyAttack.consumeClick()) return;
		BlockPos hit = BorerAreaMarks.lookBlock(client);
		if (hit == null) {
			BorerAreaMarks.tell(client, "准星没有方块，再看远一点或输入坐标");
			return;
		}
		int corner = instance.pickingAreaCorner;
		instance.pickingAreaCorner = 0;
		if (corner == 2) BorerAreaMarks.setB(instance.config, hit);
		else BorerAreaMarks.setA(instance.config, hit);
		client.options.keyAttack.setDown(false);
		BorerAreaMarks.tell(client, (corner == 2 ? "点B " : "点A ") + hit.getX() + " " + hit.getY() + " " + hit.getZ()
			+ "  " + BorerAreaMarks.sizeLabel(instance.config));
	}
}
