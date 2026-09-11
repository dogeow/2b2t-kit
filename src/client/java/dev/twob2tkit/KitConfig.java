package dev.twob2tkit;

import dev.twob2tkit.surround.SurroundBlocks;

import dev.twob2tkit.structure.StructureLocator;

import dev.twob2tkit.storage.StorageLabels;

import dev.twob2tkit.combat.HealingItems;

import dev.twob2tkit.borer.TunnelBorer;

import dev.twob2tkit.borer.BorerAreaProjects;

import dev.twob2tkit.adventure.ActivityRequirements;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.Level;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * twob2tkit 全部设置：Gson 读写 {@code config/twob2tkit.json}，含迁移与默认值。
 */
public final class KitConfig {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
	private static final Path PATH = FabricLoader.getInstance().getConfigDir().resolve("twob2tkit.json");
	/** 更旧的配置文件名（按优先级尝试迁移）。 */
	private static final Path[] LEGACY_CONFIG_FILES = {
		FabricLoader.getInstance().getConfigDir().resolve("2b2t-kit.json"),
		FabricLoader.getInstance().getConfigDir().resolve("autocruise.json")
	};
	private static final Path CONFIG_DIR = FabricLoader.getInstance().getConfigDir().resolve("twob2tkit");
	private static final Path[] LEGACY_DIRS = {
		FabricLoader.getInstance().getConfigDir().resolve("2b2t-kit"),
		FabricLoader.getInstance().getConfigDir().resolve("autocruise")
	};

	/** 是否已保存巡航目标。 */
	public boolean hasTarget;
	/** UI-only drafts never authorize movement/mining. Keys include server/dimension and stable page id. */
	public java.util.Map<String, UiDraft> uiDrafts = new java.util.LinkedHashMap<>();
	public String workspaceCategory = "HOME";
	public java.util.List<String> recentUiFeatures = new java.util.ArrayList<>();
	public java.util.Set<String> favoriteUiFeatures = new java.util.LinkedHashSet<>();
	/** 巡航目标 X。 */
	public double targetX;
	/** 巡航目标 Z。 */
	public double targetZ;
	/** 巡航高度 Y。 */
	public double cruiseY = 200.0;
	/** Scenery radius is in blocks, independent of the saved point-to-point cruise target. */
	public int sceneryRadiusBlocks = 256;
	/** 到达判定半径（格）。 */
	public double arrivalRadius = 8.0;
	/** 到达后是否自动离线。 */
	public boolean disconnectOnArrival = true;
	/** 挂机时陌生玩家警戒半径；0=关。 */
	public double playerRadius = 64.0;
	/** 挂机最低生命值；0=关。 */
	public double minHealth = 8.0;
	/** 卡住保护秒数；0=关。 */
	public int stuckSeconds = 30;
	public double altitudeTolerance = 1.5;
	public double altitudeCorrectionTolerance = 4.0;
	/** 转向速度（度/tick）。 */
	public double turnSpeed = 12.0;
	/** 前方障碍自动绕行。 */
	public boolean projectionAutoMove = true;
	public int concreteLimit = 0;
	public int concreteDelayTicks = 4;
	public int concreteToolReservePercent = 10;
	public boolean obstacleAvoidance = true;
	/** 升空时挖掉头上挡路方块。 */
	public boolean clearCeiling = true;
	public String ceilingFlyKey = "key.keyboard.c";
	public int cruiseSettingsVersion;
	public double obstacleLookAhead = 48.0;
	public double obstacleBypassDistance = 12.0;
	public boolean healingItemAlert = true;
	public int minimumHealingItems = 2;
	public Set<String> healingItemIds = new HashSet<>(HealingItems.defaultIds());
	public boolean netherGoldArmorAlert = true;
	public boolean totemAlert = false;
	public int minimumTotems = 1;
	public boolean elytraDurabilityAlert = false;
	public int minimumElytraDurability = 40;
	public int survivalAlertCooldownSeconds = 60;
	public String activityProfile = "NONE";
	public int miningChecklistVersion = 0;
	public boolean borerAutoDefend = true;
	/** Destructive discard and automatic storage are explicitly opt-in. */
	public boolean borerAreaDiscardStone;
	public boolean borerAreaStoreDrops;
	public String lastDashboardPage = "home";
	public List<ActivityList> activityLists = new ArrayList<>();
	public boolean autoRestockFromOpenedContainers = false;
	public boolean logReviewEnabled = true;
	public boolean localRecipeHints = true;
	public Set<String> seenRecipeHints = new HashSet<>();
	public Set<String> discoveredRecipeItems = new HashSet<>();
	public Set<String> completedLocalAdvancements = new HashSet<>();
	public boolean recipeBookEnhancementEnabled;
	public String recipeBookMode = "RELATED";
	public boolean recipeDiscoveryInitialized;
	/** 是否记录了死亡点。 */
	public boolean hasDeathPoint;
	public double deathX;
	public double deathY;
	public double deathZ;
	public String deathDimension = "";
	public long deathTimeEpochMillis;
	public String deathKiller = "";
	public String deathMessage = "";
	public String deathActivity = "";
	public long lastAttackTimeEpochMillis;
	public String lastAttacker = "";
	public float lastAttackHealth;
	public String lastAttackActivity = "";
	/** 旧字段：走近敌对曾用来下线。现在只在钓鱼被打中一次才下，此半径不再踢人。 */
	public double afkHostileRadius = 12.0;
	public List<StorageSnapshot> storageSnapshots = new ArrayList<>();
	/** 附近玩家保护白名单。 */
	public List<String> trustedPlayers = new ArrayList<>();
	/** 已存地点。 */
	public List<SavedPlace> savedPlaces = new ArrayList<>();
	public boolean structureHideVisited;
	/** 附近结构搜索半径，单位格。 */
	public int structureSearchRadius = 4096;
	/** ALL 或 N/NE/E/SE/S/SW/W/NW。 */
	public String structureSearchDir = "ALL";
	/** 附近结构上次勾选的类型，按维度存枚举名。空则用该维度默认。 */
	public String structureKindOverworld = "";
	public String structureKindNether = "";
	public String structureKindEnd = "";
	public List<StructureMark> structureMarks = new ArrayList<>();
	/** false = 近战交给 Meteor KillAura，本模块只反火球、拉弓、拉扯。 */
	public boolean brawlerMeleeEnabled = true;
	/** false = 火球也交给 Meteor 的 arrow-dodge 去躲。躲和反弹互斥，只能二选一。 */
	public boolean brawlerDeflectFireball = true;
	/** false = 闪避交给 Meteor 的 arrow-dodge，本模块不再自己左右拉扯。 */
	public boolean brawlerStrafeDodge = true;
	/** 没开打猪人时也反弹火球、射恶魂。不要靠 Meteor Arrow Dodge 把人推开，火没有碰撞会推进柱火里。 */
	public boolean ghastGuardEnabled = true;
	/** 被怪物打了就打开 Meteor KillAura 和 Auto Log。岩浆烫伤不算。 */
	public boolean autoProtectOnHit = true;
	public int autoProtectVersion;
	public double brawlerMeleeReach = 3.0;
	public double brawlerFireballReach = 3.0;
	public double brawlerGhastRange = 56.0;
	public double brawlerCrossbowRange = 32.0;
	public int brawlerBowChargeTicks = 20;
	/** 血量掉到这个值以下就停手，避免站着被打死。0 = 不自动停。 */
	public double brawlerMinHealth = 8.0;
	/** 飞行时至少高出地面猪人这么多格；拿矛的猪人比拿剑的够得远。0 = 不管高度。 */
	public double brawlerHoverHeight = 3.0;
	/** 跟踪恶魂/猪人时每 tick 最多转多少度；越小越稳。 */
	public double brawlerLookDegreesPerTick = 7.0;
	public int borerWidth = 1;
	public int borerHeight = 2;
	public int borerMobRadius = 8;
	public int borerLookAhead = 2;
	public boolean borerStopOnLava = true;
	public boolean borerSealLiquids = true;
	public boolean borerPauseOnMob = true;
	public boolean borerShieldOnMob = true;
	public boolean borerSurroundOnCreeper = false;
	public String borerLastMode = "FORWARD";
	public String borerHeading = "LOOK";
	public String borerOreTarget = "DIAMOND";
	public boolean borerCoalXpMode;
	public boolean borerQuartzXpMode;
	public boolean borerHomeOnDone = true;
	public boolean borerTurnAroundLava = true;
	public boolean borerAxisAim = true;
	public int borerSessionVersion;
	public int borerOreRadius = 24;
	public boolean borerAreaASet;
	public boolean borerAreaBSet;
	/** 未完成的区域表单；不参与挖掘，补齐并校验后才应用到 A/B。 */
	public dev.twob2tkit.borer.AreaDrafts.Draft borerAreaDraft;
	public int borerAreaAx;
	public int borerAreaAy;
	public int borerAreaAz;
	public int borerAreaBx;
	public int borerAreaBy;
	public int borerAreaBz;
	/** 区域挖每次挖几格高。2=普通 1×2 巷道。 */
	public int borerAreaSliceHeight = 2;
	/** 已保存的区域挖工程。 */
	public List<AreaProject> areaProjects = new ArrayList<>();
	/** 当前载入的工程 id，空表示手动标点未绑定工程。 */
	public String activeAreaProjectId = "";
	public boolean hasMachineSite;
	public String machineSiteId = "";
	public int machineSiteX;
	public int machineSiteY;
	public int machineSiteZ;
	public String machineSiteForward = "SOUTH";
	public String surroundBlockId = "minecraft:cobblestone";
	public List<String> surroundBlockIds = new ArrayList<>(SurroundBlocks.DEFAULT_IDS);
	public String surroundMode = "PLUS";
	public boolean surroundKeepRepair = false;
	public int surroundPlacesPerTick = 2;
	public int machinePreviewDistance = 8;
	public int surroundSettingsVersion;
	public String lastUiTab = "CRUISE";
	/** true = 一屏模块栏（像 Meteor Click GUI）；false = 原来的分页。 */
	public boolean clickGui = false;
	public int clickGuiX = -1;
	public int clickGuiY = -1;
	public int clickGuiW = 560;
	public int clickGuiH = 320;
	public int uiSettingsVersion;
	/** 首页快捷按钮顺序，逗号分隔。最近用过的会排到前面。 */
	public String homeRecentActions = DEFAULT_HOME_ACTIONS;
	public static final String DEFAULT_HOME_ACTIONS = "FISH,FEED,HOME_ROUTE,GO_HOME,PORTAL,BORER,SURROUND,PLANT,CHOP";
	public static final List<String> HOME_ACTION_IDS = List.of(
		"FISH", "FEED", "HOME_ROUTE", "GO_HOME", "PORTAL", "BORER", "SURROUND", "PLANT", "CHOP");
	public static final String DEFAULT_FEEDER_ORDER = "cow,sheep,pig,chicken,mooshroom,goat,rabbit";
	public static final List<String> FEEDER_TYPE_IDS = List.of(
		"cow", "sheep", "pig", "chicken", "mooshroom", "goat", "rabbit");

	public boolean fisherLeaveHookToMeteor;
	public int fisherChestRange = 5;
	public int feederSettingsVersion;
	public double feederRange = 12.0;
	public boolean feederWalk = true;
	public boolean feederHideFood = true;
	public boolean feederBreedAdults = true;
	public boolean feederGrowBabies = true;
	public boolean feederCow = true;
	public boolean feederSheep = true;
	public boolean feederPig = true;
	public boolean feederChicken = true;
	public boolean feederMooshroom = true;
	public boolean feederGoat;
	public boolean feederRabbit;
	public String feederOrder = DEFAULT_FEEDER_ORDER;
	public int planterSettingsVersion;
	public double planterRange = 8.0;
	public boolean planterWalk = true;
	public boolean planterTill = true;
	public boolean planterStack;
	public boolean planterHarvest = true;
	public boolean planterPickup = true;
	public int chopperSettingsVersion;
	public double chopperRange = 16.0;
	public boolean chopperWalk = true;
	public boolean chopperLeaves;
	public boolean chopperReplant = true;
	public boolean chopperRequireLeaves = true;
	public boolean chopperPickup = true;
	public boolean villagerScanEnabled;
	public int villagerScanRange = 64;

	/** 从磁盘加载；不存在则新建并保存。 */
	public static KitConfig load() {
		migrateLegacyConfig();
		if (!Files.exists(PATH)) {
			KitConfig config = new KitConfig();
			config.save();
			return config;
		}

		try (Reader reader = Files.newBufferedReader(PATH)) {
			KitConfig config = GSON.fromJson(reader, KitConfig.class);
			if (config == null) return new KitConfig();
			if (config.trustedPlayers == null) config.trustedPlayers = new ArrayList<>();
			if (config.savedPlaces == null) config.savedPlaces = new ArrayList<>();
			migrateSavedPlaceDimensions(config);
			if (config.structureMarks == null) config.structureMarks = new ArrayList<>();
			config.structureSearchRadius = clampStructureRadius(config.structureSearchRadius);
			config.structureSearchDir = normalizeStructureDir(config.structureSearchDir);
			if (config.structureKindOverworld == null) config.structureKindOverworld = "";
			if (config.structureKindNether == null) config.structureKindNether = "";
			if (config.structureKindEnd == null) config.structureKindEnd = "";
			migrateStructureMarkKinds(config);
			if (config.activityProfile == null) config.activityProfile = "NONE";
			ActivityRequirements.ensureLists(config);
			if (config.seenRecipeHints == null) config.seenRecipeHints = new HashSet<>();
			config.healingItemIds = HealingItems.normalize(config.healingItemIds);
			if (config.discoveredRecipeItems == null) config.discoveredRecipeItems = new HashSet<>();
			if (config.completedLocalAdvancements == null) config.completedLocalAdvancements = new HashSet<>();
			if (config.recipeBookMode == null) config.recipeBookMode = "RELATED";
			if (config.deathDimension == null) config.deathDimension = "";
			if (config.deathKiller == null) config.deathKiller = "";
			if (config.deathMessage == null) config.deathMessage = "";
			if (config.deathActivity == null) config.deathActivity = "";
			if (config.lastAttacker == null) config.lastAttacker = "";
			if (config.lastAttackActivity == null) config.lastAttackActivity = "";
			if (config.afkHostileRadius < 0.0 || config.afkHostileRadius > 64.0) config.afkHostileRadius = 12.0;
			if (config.storageSnapshots == null) config.storageSnapshots = new ArrayList<>();
			for (StorageSnapshot snapshot : config.storageSnapshots) {
				if (snapshot.items == null) snapshot.items = new ArrayList<>();
				if (snapshot.title == null) snapshot.title = "箱子";
				if (snapshot.dimension == null) snapshot.dimension = "";
				snapshot.dimension = normalizeDimension(snapshot.dimension);
				if (snapshot.blockId == null) snapshot.blockId = "";
				if (snapshot.colorId == null) snapshot.colorId = "";
				if (snapshot.note == null) snapshot.note = "";
			}
			if (config.machineSiteId == null) config.machineSiteId = "";
			if (config.machineSiteForward == null) config.machineSiteForward = "SOUTH";
			if (config.surroundBlockId == null || config.surroundBlockId.isBlank()) config.surroundBlockId = "minecraft:cobblestone";
			if (config.surroundSettingsVersion < 1) {
				config.surroundKeepRepair = false;
				config.surroundSettingsVersion = 1;
			}
			if (config.surroundSettingsVersion < 2) {
				List<String> migrated = new ArrayList<>(SurroundBlocks.DEFAULT_IDS);
				String previous = SurroundBlocks.canonical(config.surroundBlockId);
				if (previous != null && !previous.equals("minecraft:cobblestone")) {
					migrated.remove(previous);
					migrated.addFirst(previous);
				}
				config.surroundBlockIds = migrated;
				config.surroundSettingsVersion = 2;
				config.save();
			}
			config.surroundBlockIds = SurroundBlocks.normalize(config.surroundBlockIds);
			config.surroundBlockId = config.surroundBlockIds.getFirst();
			if (config.surroundMode == null || config.surroundMode.isBlank() || config.surroundMode.equals("FULL") && config.surroundSettingsVersion < 3) {
				config.surroundMode = "PLUS";
			}
			if (config.surroundSettingsVersion < 3) {
				config.surroundSettingsVersion = 3;
				config.save();
			}
			if (config.surroundPlacesPerTick < 1 || config.surroundPlacesPerTick > 4) config.surroundPlacesPerTick = 2;
			if (config.machinePreviewDistance < 2 || config.machinePreviewDistance > 48) config.machinePreviewDistance = 8;
			if (config.lastUiTab == null || config.lastUiTab.isBlank()) config.lastUiTab = "CRUISE";
			else if (config.lastUiTab.equals("TECH")) config.lastUiTab = "BORER";
			else if (config.lastUiTab.equals("HELP")) config.lastUiTab = "MORE";
			if (config.uiSettingsVersion < 1) {
				config.uiSettingsVersion = 1;
				config.save();
			}
			if (config.clickGuiW < 360 || config.clickGuiW > 1200) config.clickGuiW = 560;
			if (config.clickGuiH < 220 || config.clickGuiH > 800) config.clickGuiH = 320;
			config.homeRecentActions = normalizeHomeActions(config.homeRecentActions);
			if (config.borerLastMode == null || config.borerLastMode.isBlank()) config.borerLastMode = "FORWARD";
			if (config.borerHeading == null || config.borerHeading.isBlank()) config.borerHeading = "LOOK";
			if (config.borerOreTarget == null || config.borerOreTarget.isBlank()) config.borerOreTarget = "DIAMOND";
			else config.borerOreTarget = TunnelBorer.OreTarget.normalize(config.borerOreTarget);
			if (config.borerSessionVersion < 1) {
				config.borerHomeOnDone = true;
				config.borerSessionVersion = 1;
				config.save();
			}
			if (config.borerSessionVersion < 2) {
				config.borerTurnAroundLava = true;
				config.borerSessionVersion = 2;
				config.save();
			}
			if (config.borerSessionVersion < 3) {
				config.borerSurroundOnCreeper = false;
				config.borerSessionVersion = 3;
				config.save();
			}
			if (config.borerWidth < 1 || config.borerWidth > 5) config.borerWidth = 1;
			if (config.borerHeight < 1 || config.borerHeight > 5) config.borerHeight = 2;
			if (config.borerLookAhead < 1 || config.borerLookAhead > 5) config.borerLookAhead = 2;
			if (config.borerOreRadius < 8 || config.borerOreRadius > 32) config.borerOreRadius = 24;
			if (config.borerAreaSliceHeight < 1 || config.borerAreaSliceHeight > 5) config.borerAreaSliceHeight = 2;
			if (config.areaProjects == null) config.areaProjects = new ArrayList<>();
			if (config.activeAreaProjectId == null) config.activeAreaProjectId = "";
			normalizeAreaProjects(config);
			if (config.borerSessionVersion < 4) {
				if (config.areaProjects.isEmpty() && config.borerAreaASet && config.borerAreaBSet) {
					AreaProject migrated = BorerAreaProjects.capture(config, "上次区域", "");
					config.areaProjects.add(migrated);
					config.activeAreaProjectId = migrated.id;
				}
				config.borerSessionVersion = 4;
				config.save();
			}
			if (config.cruiseSettingsVersion < 1) {
				config.clearCeiling = true;
				config.cruiseSettingsVersion = 1;
				config.save();
			}
			if (config.cruiseSettingsVersion < 2) {
				if (config.turnSpeed < 1.0 || config.turnSpeed > 120.0) config.turnSpeed = 12.0;
				config.cruiseSettingsVersion = 2;
				config.save();
			}
			if (config.turnSpeed < 1.0 || config.turnSpeed > 120.0) config.turnSpeed = 12.0;
			if (config.ceilingFlyKey == null || config.ceilingFlyKey.isBlank()) config.ceilingFlyKey = "key.keyboard.c";
			if (config.feederSettingsVersion < 1) {
				config.feederRange = 12.0;
				config.feederWalk = true;
				config.feederHideFood = true;
				config.feederBreedAdults = true;
				config.feederGrowBabies = true;
				config.feederCow = true;
				config.feederSheep = true;
				config.feederPig = true;
				config.feederChicken = true;
				config.feederMooshroom = true;
				config.feederGoat = false;
				config.feederRabbit = false;
				config.feederSettingsVersion = 1;
				config.save();
			}
			if (config.feederSettingsVersion < 2) {
				config.feederOrder = normalizeFeederOrder(config.feederOrder);
				config.feederSettingsVersion = 2;
				config.save();
			}
			config.feederOrder = normalizeFeederOrder(config.feederOrder);
			if (config.feederRange < 3.0 || config.feederRange > 24.0) config.feederRange = 12.0;
			if (config.fisherChestRange < 2 || config.fisherChestRange > 8) config.fisherChestRange = 5;
			if (config.planterSettingsVersion < 1) {
				config.planterRange = 8.0;
				config.planterWalk = true;
				config.planterTill = true;
				config.planterStack = false;
				config.planterSettingsVersion = 1;
				config.save();
			}
			if (config.planterSettingsVersion < 2) {
				config.planterHarvest = true;
				config.planterSettingsVersion = 2;
				config.save();
			}
			if (config.planterSettingsVersion < 3) {
				config.planterPickup = true;
				config.planterSettingsVersion = 3;
				config.save();
			}
			if (config.planterRange < 3.0 || config.planterRange > 24.0) config.planterRange = 8.0;
			if (config.chopperSettingsVersion < 1) {
				config.chopperRange = 16.0;
				config.chopperWalk = true;
				config.chopperLeaves = false;
				config.chopperReplant = true;
				config.chopperRequireLeaves = true;
				config.chopperSettingsVersion = 1;
				config.save();
			}
			if (config.chopperSettingsVersion < 2) {
				config.chopperPickup = true;
				config.chopperSettingsVersion = 2;
				config.save();
			}
			if (config.chopperRange < 4.0 || config.chopperRange > 32.0) config.chopperRange = 16.0;
			if (config.villagerScanRange < 16 || config.villagerScanRange > 96) config.villagerScanRange = 64;
			if (config.autoProtectVersion < 1) {
				config.autoProtectOnHit = true;
				config.autoProtectVersion = 1;
				config.save();
			}
			return config;
		} catch (Exception exception) {
			KitClient.LOGGER.warn("Could not read {}, using defaults", PATH, exception);
			return new KitConfig();
		}
	}

	/** 把结构搜索半径夹到合法范围。 */
	public static int clampStructureRadius(int radius) {
		if (radius <= 0) return 4096;
		return Math.max(256, Math.min(32768, radius));
	}

	/** 规范化方位过滤字符串。 */
	public static String normalizeStructureDir(String dir) {
		if (dir == null || dir.isBlank()) return "ALL";
		return switch (dir.trim().toUpperCase(Locale.ROOT)) {
			case "ALL", "N", "NE", "E", "SE", "S", "SW", "W", "NW" -> dir.trim().toUpperCase(Locale.ROOT);
			default -> "ALL";
		};
	}

	/** 该维度上次勾选的结构类型。 */
	public StructureLocator.Kind lastStructureKind(StructureLocator.Dimension dimension) {
		String stored = switch (dimension) {
			case OVERWORLD -> structureKindOverworld;
			case NETHER -> structureKindNether;
			case END -> structureKindEnd;
		};
		if (stored != null && !stored.isBlank()) {
			try {
				StructureLocator.Kind kind = StructureLocator.Kind.valueOf(stored.trim().toUpperCase(Locale.ROOT));
				if (kind.dimension == dimension) return kind;
			} catch (IllegalArgumentException ignored) {
			}
		}
		return StructureLocator.Kind.defaultFor(dimension);
	}

	/** 记住该维度勾选的结构类型。 */
	public void setLastStructureKind(StructureLocator.Kind kind) {
		if (kind == null) return;
		String name = kind.name();
		switch (kind.dimension) {
			case OVERWORLD -> structureKindOverworld = name;
			case NETHER -> structureKindNether = name;
			case END -> structureKindEnd = name;
		}
	}

	/** 写回 twob2tkit.json。 */
	public void save() {
		try {
			Files.createDirectories(PATH.getParent());
			try (Writer writer = Files.newBufferedWriter(PATH)) {
				GSON.toJson(this, writer);
			}
		} catch (IOException exception) {
			KitClient.LOGGER.warn("Could not save {}", PATH, exception);
		}
	}

	/** 首次从旧版 2b2t-kit / AutoCruise 复制配置（不覆盖已有新文件）。 */
	private static void migrateLegacyConfig() {
		try {
			if (!Files.exists(PATH)) {
				for (Path legacy : LEGACY_CONFIG_FILES) {
					if (!Files.isRegularFile(legacy)) continue;
					Files.copy(legacy, PATH);
					KitClient.LOGGER.info("Migrated config {} -> {}", legacy.getFileName(), PATH.getFileName());
					break;
				}
			}
			Files.createDirectories(CONFIG_DIR);
			for (Path legacyDir : LEGACY_DIRS) {
				if (!Files.isDirectory(legacyDir)) continue;
				try (var walk = Files.walk(legacyDir)) {
					for (Path src : walk.filter(Files::isRegularFile).toList()) {
						Path rel = legacyDir.relativize(src);
						String name = rel.toString().replace('\\', '/')
							.replace("autocruise-engine", "twob2tkit-engine")
							.replace("2b2t-kit-engine", "twob2tkit-engine");
						Path dest = CONFIG_DIR.resolve(name);
						if (Files.exists(dest)) continue;
						Files.createDirectories(dest.getParent());
						Files.copy(src, dest);
					}
				}
			}
		} catch (IOException exception) {
			KitClient.LOGGER.warn("Could not migrate legacy config", exception);
		}
	}

	/** 规范化喂养种类顺序，补全缺项。 */
	public static String normalizeFeederOrder(String raw) {
		List<String> order = new ArrayList<>();
		if (raw != null && !raw.isBlank()) {
			for (String part : raw.split(",")) {
				String id = part.trim().toLowerCase(Locale.ROOT);
				if (FEEDER_TYPE_IDS.contains(id) && !order.contains(id)) order.add(id);
			}
		}
		for (String id : FEEDER_TYPE_IDS) {
			if (!order.contains(id)) order.add(id);
		}
		return String.join(",", order);
	}

	/** 规范化首页快捷按钮顺序。 */
	public static String normalizeHomeActions(String raw) {
		List<String> out = new ArrayList<>();
		if (raw != null && !raw.isBlank()) {
			for (String part : raw.split(",")) {
				String id = part.trim().toUpperCase(Locale.ROOT);
				if (HOME_ACTION_IDS.contains(id) && !out.contains(id)) out.add(id);
			}
		}
		for (String id : HOME_ACTION_IDS) {
			if (!out.contains(id)) out.add(id);
		}
		return String.join(",", out);
	}

	/** 首页快捷动作 id 列表。 */
	public List<String> homeActionOrder() {
		return List.of(normalizeHomeActions(homeRecentActions).split(","));
	}

	/** 把动作提到首页顺序最前。 */
	public void rememberHomeAction(String id) {
		if (id == null || !HOME_ACTION_IDS.contains(id)) return;
		List<String> order = new ArrayList<>(homeActionOrder());
		order.remove(id);
		order.add(0, id);
		homeRecentActions = String.join(",", order);
	}

	/** 喂养种类顺序。 */
	public List<String> feederTypeOrder() {
		return List.of(normalizeFeederOrder(feederOrder).split(","));
	}

	/** 上下移动喂养种类优先级。 */
	public void moveFeederType(String typeId, int delta) {
		List<String> order = new ArrayList<>(feederTypeOrder());
		int index = order.indexOf(typeId);
		if (index < 0) return;
		int next = index + delta;
		if (next < 0 || next >= order.size()) return;
		Collections.swap(order, index, next);
		feederOrder = String.join(",", order);
	}

	/** 该动物种类是否勾选喂养。 */
	public boolean feederTypeEnabled(String typeId) {
		if ("cow".equals(typeId)) return feederCow;
		if ("sheep".equals(typeId)) return feederSheep;
		if ("pig".equals(typeId)) return feederPig;
		if ("chicken".equals(typeId)) return feederChicken;
		if ("mooshroom".equals(typeId)) return feederMooshroom;
		if ("goat".equals(typeId)) return feederGoat;
		if ("rabbit".equals(typeId)) return feederRabbit;
		return false;
	}

	/** 设置该动物种类是否喂养。 */
	public void setFeederTypeEnabled(String typeId, boolean enabled) {
		if ("cow".equals(typeId)) feederCow = enabled;
		else if ("sheep".equals(typeId)) feederSheep = enabled;
		else if ("pig".equals(typeId)) feederPig = enabled;
		else if ("chicken".equals(typeId)) feederChicken = enabled;
		else if ("mooshroom".equals(typeId)) feederMooshroom = enabled;
		else if ("goat".equals(typeId)) feederGoat = enabled;
		else if ("rabbit".equals(typeId)) feederRabbit = enabled;
	}

	/** 喂养种类中文名。 */
	public static String feederTypeLabel(String typeId) {
		return switch (typeId) {
			case "cow" -> "牛";
			case "sheep" -> "羊";
			case "pig" -> "猪";
			case "chicken" -> "鸡";
			case "mooshroom" -> "蘑菇牛";
			case "goat" -> "山羊";
			case "rabbit" -> "兔子";
			default -> typeId;
		};
	}

	/** 玩家名是否在白名单（忽略大小写）。 */
	public boolean isTrusted(String playerName) {
		return trustedPlayers.stream().anyMatch(name -> name.equalsIgnoreCase(playerName));
	}

	/** 加入白名单并保存；已存在返回 false。 */
	public boolean addTrusted(String playerName) {
		if (isTrusted(playerName)) return false;
		trustedPlayers.add(playerName);
		trustedPlayers.sort(String.CASE_INSENSITIVE_ORDER);
		save();
		return true;
	}

	/** 移出白名单并保存。 */
	public boolean removeTrusted(String playerName) {
		boolean removed = trustedPlayers.removeIf(name -> name.equalsIgnoreCase(playerName));
		if (removed) save();
		return removed;
	}

	/** 新增或更新地点（维度空则猜）。 */
	public boolean upsertPlace(String name, double x, double z, double y) {
		return upsertPlace(name, x, z, y, "");
	}

	/** 新增或更新地点含维度。 */
	public boolean upsertPlace(String name, double x, double z, double y, String dimension) {
		SavedPlace existing = savedPlaces.stream().filter(place -> place.name.equalsIgnoreCase(name)).findFirst().orElse(null);
		boolean added = existing == null;
		String dim = normalizeDimension(dimension);
		if (dim.isEmpty()) dim = guessDimensionFromName(name);
		if (added) savedPlaces.add(new SavedPlace(name, x, z, y, dim));
		else {
			existing.name = name;
			existing.x = x;
			existing.z = z;
			existing.cruiseY = y;
			if (!dim.isEmpty()) existing.dimension = dim;
		}
		sortSavedPlaces();
		save();
		return added;
	}

	/** 按名删除地点。 */
	public boolean removePlace(String name) {
		boolean removed = savedPlaces.removeIf(place -> place.name.equalsIgnoreCase(name));
		if (removed) save();
		return removed;
	}

	/** 按 id 找区域工程。 */
	public AreaProject areaProjectById(String id) {
		if (id == null || id.isBlank()) return null;
		for (AreaProject project : areaProjects) {
			if (id.equals(project.id)) return project;
		}
		return null;
	}

	/** 按名找区域工程（忽略大小写）。 */
	public AreaProject areaProjectByName(String name) {
		if (name == null || name.isBlank()) return null;
		for (AreaProject project : areaProjects) {
			if (name.equalsIgnoreCase(project.name)) return project;
		}
		return null;
	}

	/** 把当前点 A/B 和断面写入工程；同名覆盖坐标。 */
	public boolean upsertAreaProject(String name, String dimension) {
		String trimmed = name == null ? "" : name.trim();
		if (trimmed.isEmpty()) return false;
		if (!borerAreaASet || !borerAreaBSet) return false;
		AreaProject existing = areaProjectByName(trimmed);
		String dim = normalizeDimension(dimension);
		if (dim.isEmpty()) dim = guessDimensionFromName(trimmed);
		boolean added = existing == null;
		AreaProject project = added ? BorerAreaProjects.capture(this, trimmed, dim) : existing;
		if (!added) {
			project.ax = borerAreaAx;
			project.ay = borerAreaAy;
			project.az = borerAreaAz;
			project.bx = borerAreaBx;
			project.by = borerAreaBy;
			project.bz = borerAreaBz;
			project.stripWidth = Math.max(1, Math.min(5, borerWidth));
			project.sliceHeight = Math.max(1, Math.min(5, borerAreaSliceHeight));
			if (!dim.isEmpty()) project.dimension = dim;
			project.updatedAt = System.currentTimeMillis();
		}
		if (added) areaProjects.add(project);
		activeAreaProjectId = project.id;
		sortAreaProjects();
		save();
		return added;
	}

	/** 加载工程到当前点 A/B 与断面。 */
	public boolean loadAreaProject(String nameOrId) {
		if (nameOrId == null || nameOrId.isBlank()) return false;
		AreaProject project = areaProjectByName(nameOrId);
		if (project == null) project = areaProjectById(nameOrId);
		if (project == null) return false;
		BorerAreaProjects.apply(this, project);
		project.updatedAt = System.currentTimeMillis();
		sortAreaProjects();
		save();
		return true;
	}

	/** 删除区域工程。 */
	public boolean removeAreaProject(String nameOrId) {
		if (nameOrId == null || nameOrId.isBlank()) return false;
		AreaProject project = areaProjectByName(nameOrId);
		if (project == null) project = areaProjectById(nameOrId);
		if (project == null) return false;
		boolean removed = areaProjects.remove(project);
		if (removed && project.id.equals(activeAreaProjectId)) activeAreaProjectId = "";
		if (removed) save();
		return removed;
	}

	/** 按更新时间倒序排工程。 */
	public void sortAreaProjects() {
		areaProjects.sort((first, second) -> Long.compare(second.updatedAt, first.updatedAt));
	}

	/** 补齐工程字段并校正活动 id。 */
	private static void normalizeAreaProjects(KitConfig config) {
		for (AreaProject project : config.areaProjects) {
			if (project.id == null || project.id.isBlank()) project.id = java.util.UUID.randomUUID().toString();
			if (project.name == null) project.name = "";
			if (project.dimension == null) project.dimension = "";
			project.dimension = normalizeDimension(project.dimension);
			if (project.stripWidth < 1 || project.stripWidth > 5) project.stripWidth = 1;
			if (project.sliceHeight < 1 || project.sliceHeight > 5) project.sliceHeight = 2;
		}
		config.sortAreaProjects();
		if (config.activeAreaProjectId != null && !config.activeAreaProjectId.isBlank()
			&& config.areaProjectById(config.activeAreaProjectId) == null) {
			config.activeAreaProjectId = "";
		}
	}

	/** 老配置用枚举名当 key，换成稳定 id，免得以后重命名枚举把标记弄丢。 */
	private static void migrateStructureMarkKinds(KitConfig config) {
		for (StructureMark mark : config.structureMarks) {
			if (mark.kind == null) {
				mark.kind = "";
				continue;
			}
			for (StructureLocator.Kind kind : StructureLocator.Kind.values()) {
				if (kind.name().equals(mark.kind)) {
					mark.kind = kind.stableId();
					break;
				}
			}
		}
	}

	/** 按类型与 xz 找结构标记。 */
	public StructureMark structureMark(String kind, int x, int z) {
		for (StructureMark mark : structureMarks) {
			if (mark.x == x && mark.z == z && kind.equals(mark.kind)) return mark;
		}
		return null;
	}

	/** 没有则新建结构标记。 */
	public StructureMark ensureStructureMark(String kind, int x, int z) {
		StructureMark mark = structureMark(kind, x, z);
		if (mark == null) {
			mark = new StructureMark();
			mark.kind = kind;
			mark.x = x;
			mark.z = z;
			structureMarks.add(mark);
		}
		return mark;
	}

	/** 删除一条结构标记。 */
	public void removeStructureMark(StructureMark mark) {
		structureMarks.remove(mark);
		save();
	}

	/** 清空全部结构标记。 */
	public void clearStructureMarks() {
		structureMarks.clear();
		save();
	}

	/** 没去过且没备注的条目直接清掉，别让配置文件越攒越大。 */
	public void saveStructureMarks() {
		structureMarks.removeIf(mark -> !mark.visited && (mark.note == null || mark.note.isBlank()));
		save();
	}

	/** 写入仓库快照，最多保留 50 条。 */
	public void upsertStorageSnapshot(StorageSnapshot snapshot) {
		storageSnapshots.removeIf(existing -> existing.key().equals(snapshot.key()));
		storageSnapshots.add(0, snapshot);
		while (storageSnapshots.size() > 50) storageSnapshots.remove(storageSnapshots.size() - 1);
		save();
	}

	/** 当前维度已加载的区块里，箱子/潜影盒没了就把记录删掉。 */
	public int pruneMissingStorage(Level level, String dimension) {
		if (level == null || dimension == null || dimension.isBlank()) return 0;
		String currentDimension = normalizeDimension(dimension);
		int before = storageSnapshots.size();
		storageSnapshots.removeIf(snapshot -> {
			if (!currentDimension.equals(normalizeDimension(snapshot.dimension))) return false;
			BlockPos pos = new BlockPos(snapshot.x, snapshot.y, snapshot.z);
			return StorageLabels.shouldPruneMissingRecord(level, pos);
		});
		int removed = before - storageSnapshots.size();
		if (removed > 0) save();
		return removed;
	}

	/** 更新已有快照的备注/颜色/标题。 */
	public void patchStorageLabels(StorageSnapshot snapshot) {
		if (snapshot == null) return;
		for (StorageSnapshot existing : storageSnapshots) {
			if (!existing.key().equals(snapshot.key())) continue;
			boolean changed = !safe(existing.note).equals(safe(snapshot.note))
				|| !safe(existing.colorId).equals(safe(snapshot.colorId))
				|| !safe(existing.blockId).equals(safe(snapshot.blockId))
				|| !safe(existing.title).equals(safe(snapshot.title));
			if (!changed) return;
			existing.note = safe(snapshot.note);
			existing.colorId = safe(snapshot.colorId);
			existing.blockId = safe(snapshot.blockId);
			if (!safe(snapshot.title).isEmpty()) existing.title = snapshot.title;
			save();
			return;
		}
	}

	/** null 当空串。 */
	private static String safe(String value) {
		return value == null ? "" : value;
	}

	/** 清除死亡点相关字段。 */
	public void clearDeathPoint() {
		hasDeathPoint = false;
		deathDimension = "";
		deathKiller = "";
		deathMessage = "";
		deathActivity = "";
		save();
	}

	/** 行动清单分组。 */
	public static final class ActivityList {
		public String id = "";
		public String label = "";
		public List<ActivityNeed> needs = new ArrayList<>();
	}

	/** 行动清单一条需求。 */
	public static final class ActivityNeed {
		public String match = "";
		public String label = "";
		public int target = 1;
	}

	public static final String DIM_OVERWORLD = "minecraft:overworld";
	public static final String DIM_NETHER = "minecraft:the_nether";
	public static final String DIM_END = "minecraft:the_end";

	/** 把各种写法归一成 overworld/nether/end id。 */
	public static String normalizeDimension(String raw) {
		if (raw == null || raw.isBlank()) return "";
		String value = raw.trim().toLowerCase(Locale.ROOT);
		if (value.endsWith("the_nether") || value.equals("nether") || value.contains("nether")) return DIM_NETHER;
		if (value.endsWith("the_end") || value.equals("end") || value.equals("the_end")) return DIM_END;
		if (value.endsWith("overworld") || value.equals("overworld") || value.equals("world")) return DIM_OVERWORLD;
		return raw.trim();
	}

	/** 从地点名猜维度。 */
	public static String guessDimensionFromName(String name) {
		if (name == null || name.isBlank()) return "";
		String n = name.toLowerCase(Locale.ROOT);
		if (n.contains("下界") || n.contains("地狱") || n.contains("nether")) return DIM_NETHER;
		if (n.contains("末地") || n.contains("the_end")) return DIM_END;
		if (n.contains("主世界") || n.contains("overworld")) return DIM_OVERWORLD;
		return "";
	}

	/** 维度中文标签。 */
	public static String dimensionLabel(String dimension) {
		return switch (normalizeDimension(dimension)) {
			case DIM_OVERWORLD -> "主世界";
			case DIM_NETHER -> "下界";
			case DIM_END -> "末地";
			default -> "未标注";
		};
	}

	/** 主世界→下界→末地→主世界循环。 */
	public static String nextDimension(String dimension) {
		return switch (normalizeDimension(dimension)) {
			case DIM_OVERWORLD -> DIM_NETHER;
			case DIM_NETHER -> DIM_END;
			default -> DIM_OVERWORLD;
		};
	}

	/** 排序用维度序号。 */
	public static int dimensionOrder(String dimension) {
		return switch (normalizeDimension(dimension)) {
			case DIM_OVERWORLD -> 0;
			case DIM_NETHER -> 1;
			case DIM_END -> 2;
			default -> 3;
		};
	}

	/** 先按维度再按名排序地点。 */
	private void sortSavedPlaces() {
		savedPlaces.sort((first, second) -> {
			int dim = Integer.compare(dimensionOrder(first.dimension), dimensionOrder(second.dimension));
			if (dim != 0) return dim;
			return String.CASE_INSENSITIVE_ORDER.compare(first.name, second.name);
		});
	}

	/** 迁移旧地点缺维度字段。 */
	private static void migrateSavedPlaceDimensions(KitConfig config) {
		boolean changed = false;
		for (SavedPlace place : config.savedPlaces) {
			if (place.dimension == null) place.dimension = "";
			String normalized = normalizeDimension(place.dimension);
			if (normalized.isEmpty()) normalized = guessDimensionFromName(place.name);
			if (!normalized.equals(place.dimension)) {
				place.dimension = normalized;
				changed = true;
			}
		}
		if (changed) {
			config.sortSavedPlaces();
			config.save();
		}
	}

	/** 已存巡航地点。 */
	public static final class SavedPlace {
		String name = "";
		double x;
		double z;
		double cruiseY = 200.0;
		String dimension = "";

		SavedPlace() {
		}

		SavedPlace(String name, double x, double z, double cruiseY) {
			this(name, x, z, cruiseY, "");
		}

		SavedPlace(String name, double x, double z, double cruiseY, String dimension) {
			this.name = name;
			this.x = x;
			this.z = z;
			this.cruiseY = cruiseY;
			this.dimension = normalizeDimension(dimension);
		}
	}

	/** 附近结构去过/备注标记。 */
	public static final class StructureMark {
		public String kind = "";
		public int x;
		public int z;
		public boolean visited;
		public String note = "";
	}

	/** 区域挖工程：两点与断面。 */
	public static final class AreaProject {
		public String id = java.util.UUID.randomUUID().toString();
		public String name = "";
		public int ax;
		public int ay;
		public int az;
		public int bx;
		public int by;
		public int bz;
		public int stripWidth = 1;
		public int sliceHeight = 2;
		public String dimension = "";
		public long updatedAt;
	}

	/** 开过的容器快照。 */
	public static final class StorageSnapshot {
		public String dimension = "";
		public int x;
		public int y;
		public int z;
		public String title = "箱子";
		public String blockId = "";
		public String colorId = "";
		public String note = "";
		public long lastSeenEpochMillis;
		public List<StoredItem> items = new ArrayList<>();

		/** 维度+坐标唯一键。 */
		public String key() {
			return dimension + ":" + x + ":" + y + ":" + z;
		}
	}

	/** 快照里的物品条目。 */
	public static final class StoredItem {
		public String id = "";
		public String name = "";
		public int count;

		public StoredItem() {
		}

		public StoredItem(String id, String name, int count) {
			this.id = id;
			this.name = name;
			this.count = count;
		}
	}
}
