package dev.twob2tkit.borer;

import dev.twob2tkit.combat.MeteorCombatAssist;

import dev.twob2tkit.KitConfig;

import dev.twob2tkit.KitClient;

import dev.twob2tkit.runtime.api.BorerEngine;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.Items;

import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Set;
import java.util.jar.JarFile;

/**
 * 盾构稳定代理：挖矿实现可热替换，不必重注册 Fabric 回调。
 * <p>
 * 负责加载内置/外部 {@code 2b2t-kit-engine.jar}，并把主机配置桥给引擎。
 */
public final class TunnelBorer {
	private static final String ENGINE_CLASS = "dev.twob2tkit.runtime.engine.DefaultTunnelBorerEngine";
	private static final String BUNDLED_ENGINE = "/runtime/2b2t-kit-engine.jar";
	private static final Path RUNTIME_DIR = FabricLoader.getInstance().getConfigDir().resolve("2b2t-kit/runtime");
	private static final Path ENGINE_PATH = RUNTIME_DIR.resolve("2b2t-kit-engine.jar");
	private static final Path ENGINE_SNAPSHOT = RUNTIME_DIR.resolve("2b2t-kit-engine.loaded.jar");
	private static final String ENGINE_PACKAGE = "dev.twob2tkit.runtime.engine.";

	/** 盾构模式。 */
	public enum Mode {
		FORWARD("向前挖"),
		DOWN("向下挖"),
		ORE("自动找矿"),
		AREA("区域挖");

		public final String label;

		Mode(String label) {
			this.label = label;
		}

		/** 从配置字符串解析；非法则给默认。 */
		public static Mode fromConfig(String value) {
			try {
				return value == null ? FORWARD : valueOf(value);
			} catch (IllegalArgumentException ignored) {
				return FORWARD;
			}
		}
	}

	/** 自动找矿勾选目标。 */
	public enum OreTarget {
		DIAMOND("钻石"), COAL("煤矿"), IRON("铁矿"), GOLD("金矿"), REDSTONE("红石"),
		LAPIS("青金石"), COPPER("铜矿"), EMERALD("绿宝石"), QUARTZ("石英"),
		ANCIENT_DEBRIS("残骸"), ANY("全选");

		public final String label;

		OreTarget(String label) {
			this.label = label;
		}

		/** 找矿目标对应物品图标。 */
		public Item icon() {
			return switch (this) {
				case DIAMOND -> Items.DIAMOND;
				case COAL -> Items.COAL;
				case IRON -> Items.RAW_IRON;
				case GOLD -> Items.RAW_GOLD;
				case REDSTONE -> Items.REDSTONE;
				case LAPIS -> Items.LAPIS_LAZULI;
				case COPPER -> Items.RAW_COPPER;
				case EMERALD -> Items.EMERALD;
				case QUARTZ -> Items.QUARTZ;
				case ANCIENT_DEBRIS -> Items.ANCIENT_DEBRIS;
				case ANY -> Items.COMPASS;
			};
		}

		/** 从配置字符串解析；非法则给默认。 */
		public static OreTarget fromConfig(String value) {
			java.util.List<OreTarget> selected = parseList(value);
			return selected.getFirst();
		}

		/** 解析逗号分隔的找矿目标列表。 */
		public static java.util.List<OreTarget> parseList(String value) {
			java.util.ArrayList<OreTarget> selected = new java.util.ArrayList<>();
			if (value != null) {
				for (String part : value.split("[,;|\\s]+")) {
					if (part.isBlank()) continue;
					try {
						OreTarget target = valueOf(part.trim().toUpperCase(java.util.Locale.ROOT));
						if (!selected.contains(target)) selected.add(target);
					} catch (IllegalArgumentException ignored) {
					}
				}
			}
			if (selected.contains(ANY)) return java.util.List.of(ANY);
			if (selected.isEmpty()) return java.util.List.of(DIAMOND);
			return selected;
		}

		/** 找矿目标列表写成配置串。 */
		public static String formatList(java.util.List<OreTarget> selected) {
			if (selected == null || selected.isEmpty()) return DIAMOND.name();
			if (selected.contains(ANY)) return ANY.name();
			StringBuilder text = new StringBuilder();
			for (OreTarget target : selected) {
				if (target == ANY) continue;
				if (!text.isEmpty()) text.append(',');
				text.append(target.name());
			}
			return text.isEmpty() ? DIAMOND.name() : text.toString();
		}

		/** 找矿目标中文名列表。 */
		public static String labels(String value) {
			java.util.List<OreTarget> selected = parseList(value);
			if (selected.contains(ANY)) return ANY.label;
			StringBuilder text = new StringBuilder();
			for (OreTarget target : selected) {
				if (!text.isEmpty()) text.append('、');
				text.append(target.label);
			}
			return text.toString();
		}

		/** 规范化找矿目标配置串。 */
		public static String normalize(String value) {
			return formatList(parseList(value));
		}

		/** 切换单个找矿目标是否勾选。 */
		public static String toggle(String value, OreTarget target) {
			if (target == ANY) return ANY.name();
			java.util.ArrayList<OreTarget> selected = new java.util.ArrayList<>(parseList(value));
			selected.remove(ANY);
			if (selected.contains(target)) {
				if (selected.size() > 1) selected.remove(target);
			} else {
				selected.add(target);
			}
			return formatList(selected);
		}

		/** 配置串是否包含该找矿目标。 */
		public static boolean contains(String value, OreTarget target) {
			return parseList(value).contains(target);
		}
	}

	/** 热加载/安装结果。 */
	public record ReloadResult(boolean success, String message) {
	}

	private final KitConfig config;
	private final HostBridge host;
	private BorerEngine engine;
	private URLClassLoader engineLoader;
	private String loadSource = "内置";

	public TunnelBorer(KitConfig config) {
		this.config = config;
		this.host = new HostBridge(config);
		migrateLegacyEngineJar();
		this.engine = loadBuiltIn();
		String bundledVersion = engine.runtimeVersion();
		if (Files.isRegularFile(ENGINE_PATH)) {
			try {
				LoadedEngine loaded = loadExternalEngine();
				String externalVersion = loaded.engine().runtimeVersion();
				if (compareVersions(externalVersion, bundledVersion) >= 0) {
					this.engine = loaded.engine();
					this.engineLoader = loaded.loader();
					this.loadSource = "外部功能包";
				} else {
					closeQuietly(loaded.loader());
					KitClient.LOGGER.info(
						"Ignoring older external borer engine {} in favor of bundled {}",
						externalVersion, bundledVersion
					);
				}
			} catch (Throwable throwable) {
				KitClient.LOGGER.warn("Could not load saved borer engine from {}; using bundled engine", ENGINE_PATH, throwable);
			}
		}
	}

	/** 把旧版 autocruise-engine.jar 拷到新路径（若新文件尚不存在）。 */
	private static void migrateLegacyEngineJar() {
		try {
			if (Files.isRegularFile(ENGINE_PATH)) return;
			Path legacy = FabricLoader.getInstance().getConfigDir().resolve("autocruise/runtime/autocruise-engine.jar");
			if (!Files.isRegularFile(legacy)) return;
			Files.createDirectories(RUNTIME_DIR);
			Files.copy(legacy, ENGINE_PATH);
			KitClient.LOGGER.info("Migrated legacy engine jar to {}", ENGINE_PATH);
		} catch (IOException exception) {
			KitClient.LOGGER.warn("Could not migrate legacy engine jar", exception);
		}
	}

	/** 引擎是否正在挖。 */
	public boolean isActive() {
		return engine.isActive();
	}

	/** 当前盾构模式。 */
	public Mode mode() {
		return Mode.fromConfig(engine.modeName());
	}

	/** 最近状态文案。 */
	public String status() {
		return engine.status();
	}

	/** 内置/外部引擎版本说明。 */
	public String runtimeLabel() {
		return engine.runtimeVersion() + " · " + loadSource;
	}

	/** 按模式启动盾构引擎。 */
	public void start(Minecraft client, Mode mode) {
		engine.start(client, mode.name());
	}

	/** 停止盾构并说明原因。 */
	public void stop(Minecraft client, String reason) {
		engine.stop(client, reason);
	}

	/** 热键切换：开则停，停则按上次模式开。 */
	public void toggle(Minecraft client) {
		engine.toggle(client);
	}

	/** 沿挖矿原路返回起点。 */
	public void goHome(Minecraft client) {
		engine.goHome(client);
	}

	/** 只显示回家箭头，不自动走。 */
	public void toggleHomeRoute(Minecraft client) {
		engine.toggleHomeRoute(client);
	}

	/** 是否正在显示回家路线。 */
	public boolean isShowingHomeRoute() {
		return engine.isShowingHomeRoute();
	}

	/** 沿走过的路飞回记下的地狱门。 */
	public void goToPortal(Minecraft client) {
		engine.goToPortal(client);
	}

	/** 未挖时也观察世界（门/路点等）。 */
	public void observeWorld(Minecraft client) {
		engine.observeWorld(client);
	}

	/** 是否正在自动回家。 */
	public boolean isGoingHome() {
		return engine.isGoingHome();
	}

	/** 是否正在飞回地狱门。 */
	public boolean isReturningToPortal() {
		return engine.isReturningToPortal();
	}

	/** 是否记过地狱门。 */
	public boolean hasNetherPortal() {
		return engine.hasNetherPortal();
	}

	/** 路点数量。 */
	public int trailLength() {
		return engine.trailLength();
	}

	/** 清空路点但保留门坐标。 */
	public void clearTrailKeepPortal() {
		engine.clearTrailKeepPortal();
	}

	/** Meteor 改朝向后写回引擎瞄准。 */
	public void reapplyLook(Minecraft client) {
		engine.reapplyLook(client);
	}

	/** 每拍交给引擎。 */
	public void tick(Minecraft client) {
		engine.tick(client);
	}

	/** 画区域框/路点等世界 gizmos。 */
	public void emitFrameGizmos(Minecraft client) {
		engine.emitFrameGizmos(client);
	}

	/** 关掉区域预览框。 */
	public void dismissAreaPreview() {
		engine.dismissAreaPreview();
	}

	/** 把内置引擎 jar 写出到 runtime 目录。 */
	public ReloadResult installBundledUpdate(Minecraft client) {
		Path temp = ENGINE_PATH.resolveSibling("2b2t-kit-engine.jar.new");
		try (InputStream input = TunnelBorer.class.getResourceAsStream(BUNDLED_ENGINE)) {
			if (input == null) return new ReloadResult(false, "当前核心 JAR 没有内置运行引擎");
			Files.createDirectories(RUNTIME_DIR);
			Files.deleteIfExists(temp);
			Files.copy(input, temp, StandardCopyOption.REPLACE_EXISTING);
			try {
				Files.move(temp, ENGINE_PATH, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
			} catch (AtomicMoveNotSupportedException ignored) {
				Files.move(temp, ENGINE_PATH, StandardCopyOption.REPLACE_EXISTING);
			}
		} catch (IOException exception) {
			try {
				Files.deleteIfExists(temp);
			} catch (IOException cleanupException) {
				exception.addSuppressed(cleanupException);
			}
			KitClient.LOGGER.warn("Could not install bundled borer engine", exception);
			return new ReloadResult(false, "写入更新失败：" + exception.getMessage());
		}
		ReloadResult result = reload(client);
		if (!result.success()) return result;
		loadSource = "内置恢复包";
		return new ReloadResult(true, "已恢复并加载内置盾构运行引擎 " + engine.runtimeVersion() + "，无需退出游戏");
	}

	/** 热加载外部引擎 jar，尽量带走路点。 */
	public ReloadResult reload(Minecraft client) {
		if (!Files.isRegularFile(ENGINE_PATH)) {
			return new ReloadResult(false, "没有找到 " + ENGINE_PATH.getFileName() + "；可先点“恢复内置版本”生成一份");
		}
		BorerEngine oldEngine = engine;
		URLClassLoader oldLoader = engineLoader;
		try {
			LoadedEngine loaded = loadExternalEngine();
			BorerEngine candidate = loaded.engine();
			String candidateVersion = candidate.runtimeVersion();
			String snapshot = exportTrailSafely(oldEngine);
			persistTrailSafely(oldEngine, client);
			oldEngine.stop(client, "重新加载运行引擎");
			engine = candidate;
			engineLoader = loaded.loader();
			loadSource = "外部热加载";
			if (snapshot != null && !snapshot.isBlank()) candidate.importTrailSnapshot(snapshot);
			candidate.restorePersistentState(client);
			closeQuietly(oldLoader);
			return new ReloadResult(true, "已加载盾构运行引擎 " + candidateVersion + "，无需退出游戏");
		} catch (Throwable throwable) {
			engine = oldEngine;
			engineLoader = oldLoader;
			KitClient.LOGGER.warn("Could not reload borer engine from {}", ENGINE_PATH, throwable);
			return new ReloadResult(false, "加载失败，已继续使用原引擎：" + concise(throwable));
		}
	}

	/** 热加载前尽量把旧引擎内存里的路点带走；1.6.92 没有 snapshot 接口时改走反射。 */
	private static String exportTrailSafely(BorerEngine engine) {
		try {
			String snapshot = engine.exportTrailSnapshot();
			if (snapshot != null && !snapshot.isBlank()) return snapshot;
		} catch (Throwable ignored) {
		}
		try {
			Object trail = trailObject(engine);
			if (trail == null) return "";
			try {
				var snapshot = trail.getClass().getDeclaredMethod("snapshot");
				snapshot.setAccessible(true);
				Object value = snapshot.invoke(trail);
				return value != null ? value.toString() : "";
			} catch (NoSuchMethodException ignored) {
			}
			var pointsField = trail.getClass().getDeclaredField("points");
			pointsField.setAccessible(true);
			Object points = pointsField.get(trail);
			if (!(points instanceof java.util.List<?> list) || list.isEmpty()) return "";
			StringBuilder text = new StringBuilder();
			for (Object pos : list) {
				if (pos instanceof BlockPos block) {
					text.append(block.getX()).append(' ').append(block.getY()).append(' ').append(block.getZ()).append('\n');
				}
			}
			return text.toString();
		} catch (Throwable ignored) {
			return "";
		}
	}

	/** 把路点写回配置（兼容旧引擎反射）。 */
	private static void persistTrailSafely(BorerEngine engine, Minecraft client) {
		try {
			Object trail = trailObject(engine);
			if (trail == null) return;
			var save = trail.getClass().getDeclaredMethod("save", Minecraft.class);
			save.setAccessible(true);
			save.invoke(trail, client);
		} catch (Throwable ignored) {
		}
	}

	/** 反射取引擎内部 trail 对象。 */
	private static Object trailObject(BorerEngine engine) {
		try {
			var field = engine.getClass().getDeclaredField("trail");
			field.setAccessible(true);
			return field.get(engine);
		} catch (Throwable ignored) {
			return null;
		}
	}

	/** 从 runtime 目录加载外部引擎。 */
	private LoadedEngine loadExternalEngine() throws Throwable {
		Files.createDirectories(RUNTIME_DIR);
		Files.copy(ENGINE_PATH, ENGINE_SNAPSHOT, StandardCopyOption.REPLACE_EXISTING);
		URLClassLoader loader = new ChildFirstEngineLoader(
			new URL[]{ENGINE_SNAPSHOT.toUri().toURL()}, TunnelBorer.class.getClassLoader()
		);
		try {
			preloadEngineClasses(ENGINE_SNAPSHOT, loader);
			Class<?> engineClass = Class.forName(ENGINE_CLASS, true, loader);
			if (engineClass.getClassLoader() != loader) {
				throw new IllegalArgumentException("功能包中缺少 " + ENGINE_CLASS);
			}
			BorerEngine candidate = (BorerEngine) engineClass
				.getConstructor(dev.twob2tkit.runtime.api.BorerHost.class)
				.newInstance(host);
			if (candidate.requiredHostApiVersion() > host.apiVersion()) {
				throw new IllegalArgumentException("功能包需要加载器 API " + candidate.requiredHostApiVersion()
					+ "，当前只有 " + host.apiVersion());
			}
			String version = candidate.runtimeVersion();
			if (version == null || version.isBlank()) throw new IllegalArgumentException("功能包没有版本号");
			return new LoadedEngine(candidate, loader);
		} catch (Throwable throwable) {
			closeQuietly(loader);
			throw throwable;
		}
	}

	/** 预加载 jar 内 engine 包，避免懒加载踩坑。 */
	private static void preloadEngineClasses(Path jar, ClassLoader loader) throws Exception {
		try (JarFile file = new JarFile(jar.toFile())) {
			var names = file.stream()
				.map(entry -> entry.getName())
				.filter(name -> name.startsWith("dev/twob2tkit/runtime/engine/") && name.endsWith(".class"))
				.map(name -> name.substring(0, name.length() - 6).replace('/', '.'))
				.toList();
			for (String name : names) {
				Class<?> loaded = Class.forName(name, true, loader);
				if (loaded.getClassLoader() != loader) {
					throw new IllegalArgumentException("功能包类被错误地交给主模组加载：" + name);
				}
			}
		}
	}

	/** 用本 Mod 类加载器装内置引擎。 */
	private BorerEngine loadBuiltIn() {
		try {
			Class<?> engineClass = Class.forName(ENGINE_CLASS);
			return (BorerEngine) engineClass.getConstructor(dev.twob2tkit.runtime.api.BorerHost.class).newInstance(host);
		} catch (ReflectiveOperationException exception) {
			throw new IllegalStateException("Bundled borer engine is missing", exception);
		}
	}

	/** 点分版本号比较。 */
	private static int compareVersions(String left, String right) {
		String[] leftParts = left.split("[^0-9]+");
		String[] rightParts = right.split("[^0-9]+");
		int n = Math.max(leftParts.length, rightParts.length);
		for (int i = 0; i < n; i++) {
			int a = i < leftParts.length && !leftParts[i].isEmpty() ? Integer.parseInt(leftParts[i]) : 0;
			int b = i < rightParts.length && !rightParts[i].isEmpty() ? Integer.parseInt(rightParts[i]) : 0;
			if (a != b) return Integer.compare(a, b);
		}
		return 0;
	}

	/** 异常短消息。 */
	private static String concise(Throwable throwable) {
		Throwable cause = throwable;
		while (cause.getCause() != null) cause = cause.getCause();
		String message = cause.getMessage();
		return cause.getClass().getSimpleName() + (message == null || message.isBlank() ? "" : "：" + message);
	}

	/** 安静关闭 ClassLoader。 */
	private static void closeQuietly(URLClassLoader loader) {
		if (loader == null) return;
		try {
			loader.close();
		} catch (IOException exception) {
			KitClient.LOGGER.debug("Could not close old borer engine loader", exception);
		}
	}

	/** 外部引擎实例与其 ClassLoader。 */
	private record LoadedEngine(BorerEngine engine, URLClassLoader loader) {
	}

	/** 子优先 ClassLoader：只隔离 engine 包。 */
	private static final class ChildFirstEngineLoader extends URLClassLoader {
		private static final Set<String> PARENT_FIRST = Set.of(
			"java.", "javax.", "jdk.", "sun.", "net.minecraft.", "net.fabricmc.", "org.slf4j.",
			"dev.twob2tkit.runtime.api."
		);

		ChildFirstEngineLoader(URL[] urls, ClassLoader parent) {
			super(urls, parent);
		}

		@Override
		protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
			if (PARENT_FIRST.stream().anyMatch(name::startsWith)) return super.loadClass(name, resolve);
			synchronized (getClassLoadingLock(name)) {
				Class<?> loaded = findLoadedClass(name);
				if (loaded == null) {
					try {
						loaded = findClass(name);
					} catch (ClassNotFoundException missing) {
						if (name.startsWith(ENGINE_PACKAGE)) throw missing;
						loaded = super.loadClass(name, false);
					}
				}
				if (resolve) resolveClass(loaded);
				return loaded;
			}
		}
	}

	/** 把 KitConfig 桥成引擎可读的 BorerHost。 */
	private static final class HostBridge implements dev.twob2tkit.runtime.api.BorerHost {
		private final KitConfig config;

		HostBridge(KitConfig config) {
			this.config = config;
		}

		@Override public int apiVersion() { return 2; }
		@Override public void prepareForBorer(Minecraft client) { KitClient.prepareForBorer(client); }
		@Override public boolean surroundActive() { return KitClient.surround() != null && KitClient.surround().isActive(); }
		@Override public void startEmergencySurround(Minecraft client) { KitClient.startSurroundFromBorer(client); }
		@Override public String borerLastMode() { return config.borerLastMode; }
		@Override public void setBorerLastMode(String value) { config.borerLastMode = value; }
		@Override public String borerHeading() { return config.borerHeading; }
		@Override public String borerOreTarget() { return config.borerOreTarget; }
		@Override public boolean borerCoalXpMode() { return config.borerCoalXpMode; }
		@Override public boolean borerQuartzXpMode() { return config.borerQuartzXpMode; }
		@Override public boolean borerHomeOnDone() { return config.borerHomeOnDone; }
		@Override public boolean borerTurnAroundLava() { return config.borerTurnAroundLava; }
		@Override public boolean borerAxisAim() { return config.borerAxisAim; }
		@Override public int borerWidth() { return config.borerWidth; }
		@Override public int borerHeight() { return config.borerHeight; }
		@Override public int borerLookAhead() { return config.borerLookAhead; }
		@Override public int borerMobRadius() { return config.borerMobRadius; }
		@Override public int borerOreRadius() { return config.borerOreRadius; }
		@Override public boolean borerAreaSet() { return config.borerAreaASet && config.borerAreaBSet; }
		@Override public int borerAreaAx() { return config.borerAreaAx; }
		@Override public int borerAreaAy() { return config.borerAreaAy; }
		@Override public int borerAreaAz() { return config.borerAreaAz; }
		@Override public int borerAreaBx() { return config.borerAreaBx; }
		@Override public int borerAreaBy() { return config.borerAreaBy; }
		@Override public int borerAreaBz() { return config.borerAreaBz; }
		@Override public int borerAreaSliceHeight() { return config.borerAreaSliceHeight; }
		@Override public boolean borerStopOnLava() { return config.borerStopOnLava; }
		@Override public boolean borerSealLiquids() { return config.borerSealLiquids; }
		@Override public boolean borerPauseOnMob() { return config.borerPauseOnMob; }
		@Override public boolean borerShieldOnMob() { return config.borerShieldOnMob; }
		@Override public boolean borerSurroundOnCreeper() { return config.borerSurroundOnCreeper; }
		@Override public void armAutoProtectIfEnabled(Minecraft client) {
			if (!config.autoProtectOnHit) return;
			MeteorCombatAssist.arm(client);
		}
		@Override public void saveSettings() { config.save(); }
	}
}
