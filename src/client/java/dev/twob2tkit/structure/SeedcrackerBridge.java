package dev.twob2tkit.structure;

import net.fabricmc.loader.api.FabricLoader;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collection;
import java.util.Locale;
import java.util.Set;

/**
 * 反射对接 SeedcrackerX 2.16，不把它编进本 Mod 依赖。
 * <p>
 * 读进度、世界种子、世界生成版本，并在数据够时触发 lifting。
 */
public final class SeedcrackerBridge {
	private static final String MOD_ID = "seedcrackerx";
	private static final String CLASS_NAME = "kaptainwutax.seedcrackerX.SeedCracker";

	/** Seedcracker 当前进度快照。 */
	public record Status(
		boolean installed,
		boolean running,
		double baseBits,
		double liftBits,
		double wantedBits,
		int structureCount,
		int structureSeeds,
		int worldSeeds,
		Long worldSeed
	) {
		/** 一行中文状态（界面/聊天用）。 */
		String line() {
			if (!installed) return "未安装 SeedcrackerX。算种子要靠它，不需要网页 API。";
			if (worldSeed != null) return "SeedcrackerX 已算出世界种子：" + worldSeed;
			String calc = running ? "正在计算" : "还没开始算";
			return String.format(Locale.ROOT,
				"SeedcrackerX：普通 %.1f/%.0f  可提升 %.1f  结构 %d  结构种子 %d  %s",
				baseBits, wantedBits, liftBits, structureCount, structureSeeds, calc);
		}
	}

	private SeedcrackerBridge() {
	}

	/** 是否已装 SeedcrackerX（mod 或类可加载）。 */
	public static boolean installed() {
		if (FabricLoader.getInstance().isModLoaded(MOD_ID)) return true;
		try {
			Class.forName(CLASS_NAME, false, SeedcrackerBridge.class.getClassLoader());
			return true;
		} catch (ClassNotFoundException ignored) {
			return false;
		}
	}

	/** 反射读取当前破解进度；未安装或失败则给空状态。 */
	public static Status snapshot() {
		if (!installed()) return new Status(false, false, 0, 0, 32, 0, 0, 0, null);
		try {
			Object cracker = Class.forName(CLASS_NAME).getMethod("get").invoke(null);
			Object storage = cracker.getClass().getMethod("getDataStorage").invoke(cracker);
			double base = ((Number)storage.getClass().getMethod("getBaseBits").invoke(storage)).doubleValue();
			double lift = ((Number)storage.getClass().getMethod("getLiftingBits").invoke(storage)).doubleValue();
			double wanted = ((Number)storage.getClass().getMethod("getWantedBits").invoke(storage)).doubleValue();
			int structures = 0;
			Object baseData = field(storage, "baseSeedData");
			if (baseData != null) {
				try {
					structures = (Integer)baseData.getClass().getMethod("size").invoke(baseData);
				} catch (ReflectiveOperationException ignored) {
				}
			}
			Object machine = storage.getClass().getMethod("getTimeMachine").invoke(storage);
			boolean running = Boolean.TRUE.equals(field(machine, "isRunning"));
			int structureSeeds = setSize(field(machine, "structureSeeds"));
			Set<Long> worlds = longSet(field(machine, "worldSeeds"));
			Long worldSeed = worlds.isEmpty() ? null : worlds.iterator().next();
			return new Status(true, running, base, lift, wanted, structures, structureSeeds, worlds.size(), worldSeed);
		} catch (ReflectiveOperationException exception) {
			return new Status(true, false, 0, 0, 32, 0, 0, 0, null);
		}
	}

	/** 已算出的世界种子；没有则 null。 */
	public static Long worldSeed() {
		return snapshot().worldSeed;
	}

	/**
	 * SeedcrackerX 配置里的服务器世界生成版本，例如 {@code 1.21.3}。
	 * 客户端是 26.1 也不代表地图是 26.1。
	 */
	public static String worldgenVersion() {
		try {
			Class<?> configClass = Class.forName("kaptainwutax.seedcrackerX.config.Config");
			Object config = configClass.getMethod("get").invoke(null);
			Object version = configClass.getMethod("getVersion").invoke(config);
			String parsed = versionName(version);
			if (parsed != null) return parsed;
		} catch (ReflectiveOperationException ignored) {
		}
		return versionFromFile();
	}

	/** 从枚举/字符串解析出版本号。 */
	private static String versionName(Object version) {
		if (version == null) return null;
		try {
			Object name = version.getClass().getField("name").get(version);
			if (name instanceof String text && !text.isBlank()) return text.trim();
		} catch (ReflectiveOperationException ignored) {
		}
		String text = version.toString();
		if (text == null || text.isBlank()) return null;
		text = text.trim();
		if (text.startsWith("v") && text.length() > 1 && Character.isDigit(text.charAt(1))) {
			text = text.substring(1).replace('_', '.');
		}
		return text;
	}

	/** 从 seedcracker.json 读 version 字段。 */
	private static String versionFromFile() {
		try {
			Path path = FabricLoader.getInstance().getConfigDir().resolve("seedcracker.json");
			if (!Files.isRegularFile(path)) return null;
			String json = Files.readString(path);
			int key = json.indexOf("\"version\"");
			if (key < 0) return null;
			int colon = json.indexOf(':', key);
			int quote = json.indexOf('"', colon + 1);
			int end = json.indexOf('"', quote + 1);
			if (quote < 0 || end < 0) return null;
			return versionName(json.substring(quote + 1, end));
		} catch (Exception ignored) {
			return null;
		}
	}

	/**
	 * 数据够时让 SeedcrackerX 开始 lifting。
	 *
	 * @return 中文结果说明
	 */
	public static String pokeIfReady() {
		Status status = snapshot();
		if (!status.installed) return "还没装 SeedcrackerX。";
		if (status.worldSeed != null) return "已经有世界种子：" + status.worldSeed;
		if (status.baseBits + 0.01 < status.wantedBits && status.liftBits < 40) {
			return status.line() + "。还要让它自己识别更多神殿/小屋/沉船，twob2tkit 记的条数不算它的进度。";
		}
		try {
			Object cracker = Class.forName(CLASS_NAME).getMethod("get").invoke(null);
			Object storage = cracker.getClass().getMethod("getDataStorage").invoke(cracker);
			Object machine = storage.getClass().getMethod("getTimeMachine").invoke(storage);
			Class<?> phase = Class.forName("kaptainwutax.seedcrackerX.cracker.storage.TimeMachine$Phase");
			@SuppressWarnings({"unchecked", "rawtypes"})
			Object lifting = Enum.valueOf((Class<Enum>)phase, "LIFTING");
			machine.getClass().getMethod("poke", phase).invoke(machine, lifting);
			return "已让 SeedcrackerX 开始计算。" + snapshot().line();
		} catch (ReflectiveOperationException exception) {
			return "无法启动 SeedcrackerX 计算：" + exception.getMessage();
		}
	}

	/** 读公开字段；失败返回 null。 */
	private static Object field(Object object, String name) {
		if (object == null) return null;
		try {
			Field field = object.getClass().getField(name);
			return field.get(object);
		} catch (ReflectiveOperationException ignored) {
			return null;
		}
	}

	/** Collection 大小；否则 0。 */
	private static int setSize(Object value) {
		if (value instanceof Collection<?> collection) return collection.size();
		return 0;
	}

	/** 转成 Long 集合；类型不对则空集。 */
	@SuppressWarnings("unchecked")
	private static Set<Long> longSet(Object value) {
		if (value instanceof Set<?> set && !set.isEmpty() && set.iterator().next() instanceof Long) {
			return (Set<Long>)set;
		}
		return Set.of();
	}

	/** 兼容旧调用：等同 {@link #worldSeed()}。 */
	public static Long readWorldSeedLegacy() {
		return worldSeed();
	}

	/** 无参反射调用（保留备用）。 */
	@SuppressWarnings("unused")
	private static Object invokeNoArg(Class<?> type, Object target, String name) throws ReflectiveOperationException {
		Method method = type.getMethod(name);
		return method.invoke(target);
	}
}
