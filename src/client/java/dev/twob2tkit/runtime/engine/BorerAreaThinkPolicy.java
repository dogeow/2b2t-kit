package dev.twob2tkit.runtime.engine;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/**
 * 区域挖卡住时自己试招：只在卡住后想，解开了就给这招加分。
 */
public final class BorerAreaThinkPolicy {
	public static final int STUCK_TICKS = 20;
	public static final int TRY_TICKS = 24;
	public static final int SKIP_COOLDOWN_TICKS = 80;
	/** 顺利挖井后的例行请教：约 2 分钟。 */
	public static final int ASK_COOLDOWN_TICKS = 2400;
	/** 本地招数全失败后：约 10 秒就能问 Grok。 */
	public static final int ASK_FAIL_COOLDOWN_TICKS = 200;
	public static final int ASK_TIMEOUT_TICKS = 1400;
	public static final int PATCH_TIMEOUT_TICKS = 12000;
	public static final int SHAFTS_BEFORE_ASK = 5;
	/** 同一场景反复卡住这么多次（假成功循环）就强制问 Grok。 */
	public static final int REPEAT_STUCK_ASK = 3;
	public static final int LIVE_CREDIT_TICKS = 40;
	public static final double MOVED_DIST_SQR = 0.04;
	/** 想想招数算「成功」至少要挪约半格，防止按跳/下潜抖一下就 win。 */
	public static final double WIN_MOVE_DIST_SQR = 0.25;

	/** 卡住后可试的招：挖挡路、松前进、下潜、平飞/升高、换井。 */
	public enum Move {
		MINE_LOOKED("挖准星挡路"),
		MINE_FRONT("挖贴脸挡路"),
		RELEASE_FORWARD("松开前进"),
		DESCEND("往下挖"),
		FLY_LEVEL("平飞过去"),
		FLY_UP("升高飞"),
		SKIP_SHAFT("换一口井");

		public final String label;

		Move(String label) {
			this.label = label;
		}
	}

	private BorerAreaThinkPolicy() {
	}

	/** 相对位移是否算移动过。 */
	public static boolean moved(double distSqr) {
		return distSqr > MOVED_DIST_SQR;
	}

	/** 想想招数成功：真在挖，或挪了至少约半格（抖一下不算）。 */
	public static boolean acceptThinkWin(boolean miningProgress, double moveDistSqr) {
		return miningProgress || moveDistSqr >= WIN_MOVE_DIST_SQR;
	}

	/** 往下挖必须真的掉下去。飞行下潜抖 0.3 格不算成功。 */
	public static boolean acceptDescendWin(double startY, double nowY) {
		return startY - nowY >= 0.8;
	}

	/** 是否判定卡住。 */
	public static boolean stuck(int stillTicks, boolean miningProgress) {
		return stillTicks >= STUCK_TICKS && !miningProgress;
	}

	/** 封不住水/岩浆时立刻当成卡住，HUD 马上出「想想」，不用再空等 1 秒。 */
	public static int stuckTicksAfterHazard(int stillTicks) {
		return Math.max(stillTicks, STUCK_TICKS);
	}

	/** 本招是否继续试。 */
	public static boolean keepTrying(int ticksOnMove) {
		return ticksOnMove < TRY_TICKS;
	}

	/** 冷却外是否允许跳井。 */
	public static boolean allowSkipShaft(int cooldownTicks) {
		return cooldownTicks <= 0;
	}

	/** 目标相对高度档标签。 */
	public static String destRel(double destMinusFeetY) {
		if (destMinusFeetY > 1.5) return "above";
		if (destMinusFeetY < -1.5) return "below";
		return "same";
	}

	/** 井内往下挖时禁止升高飞，否则会飞到天上再潜下来，循环。 */
	public static boolean allowFlyUp(boolean relocating, String destRel) {
		if (!relocating) return false;
		return destRel == null || !destRel.equals("below");
	}

	/** 准星所见分类标签。 */
	public static String lookKind(boolean hasHit, boolean inArea) {
		if (!hasHit) return "none";
		return inArea ? "in" : "out";
	}

	/** 场景状态键：换井/飞走、相对高度、挡路与准星。 */
	public static String sceneKey(
		boolean relocating,
		boolean flying,
		String destRel,
		boolean frontSolid,
		String lookKind,
		boolean nearDest
	) {
		return String.format(Locale.ROOT, "%s|%s|%s|%s|%s|%s",
			relocating ? "go" : "dig",
			flying ? "fly" : "walk",
			destRel == null ? "same" : destRel,
			frontSolid ? "wall" : "open",
			lookKind == null ? "none" : lookKind,
			nearDest ? "near" : "far");
	}

	/** 成功次数高的在前；没试过的按默认顺序；全失败的排最后。 */
	public static int rank(int wins, int losses, int defaultIndex) {
		if (wins == 0 && losses == 0) return 1000 - defaultIndex;
		if (wins == 0) return -1 - losses;
		return 10_000 + wins * 100 / (wins + losses);
	}

	/** 按胜负排招数尝试顺序。 */
	public static List<Move> order(int[] wins, int[] losses) {
		Move[] all = Move.values();
		Integer[] idx = new Integer[all.length];
		for (int i = 0; i < all.length; i++) idx[i] = i;
		Arrays.sort(idx, Comparator
			.comparingInt((Integer i) -> -rank(at(wins, i), at(losses, i), i))
			.thenComparingInt(i -> i));
		List<Move> ordered = new ArrayList<>(all.length);
		for (int i : idx) ordered.add(all[i]);
		return ordered;
	}

	/** 安全取数组元素。 */
	private static int at(int[] arr, int i) {
		if (arr == null || i < 0 || i >= arr.length) return 0;
		return arr[i];
	}

	/**
	 * 合适才问本机 Grok：已经能问（登录过 grok 或有密钥）、没在问，
	 * 并且本地招数用尽 / 同场景反复卡住 / 已经顺利挖过几口井。
	 * 紧急（全失败或反复卡住）用短冷却，例行请教仍用约 2 分钟。
	 */
	public static boolean shouldAskAi(
		boolean canAsk,
		boolean asking,
		int ticksSinceAsk,
		boolean allMovesFailed,
		int shaftsSinceAsk
	) {
		return shouldAskAi(canAsk, asking, ticksSinceAsk, allMovesFailed, shaftsSinceAsk, 0);
	}

	/** 含反复卡住次数的完整判定。 */
	public static boolean shouldAskAi(
		boolean canAsk,
		boolean asking,
		int ticksSinceAsk,
		boolean allMovesFailed,
		int shaftsSinceAsk,
		int repeatStuckCycles
	) {
		if (!canAsk || asking) return false;
		boolean urgent = allMovesFailed || repeatStuckCycles >= REPEAT_STUCK_ASK;
		int cooldown = urgent ? ASK_FAIL_COOLDOWN_TICKS : ASK_COOLDOWN_TICKS;
		if (ticksSinceAsk < cooldown) return false;
		return allMovesFailed
			|| shaftsSinceAsk >= SHAFTS_BEFORE_ASK
			|| repeatStuckCycles >= REPEAT_STUCK_ASK;
	}

	/** 跳过 ask 的原因，供日志排查（含 busy）。 */
	public static String askSkipReason(
		boolean busy,
		boolean canAsk,
		boolean asking,
		int ticksSinceAsk,
		boolean allMovesFailed,
		int shaftsSinceAsk,
		int repeatStuckCycles
	) {
		if (busy) return "busy";
		if (!canAsk) return "no-grok-or-key";
		if (asking) return "asking";
		boolean urgent = allMovesFailed || repeatStuckCycles >= REPEAT_STUCK_ASK;
		int cooldown = urgent ? ASK_FAIL_COOLDOWN_TICKS : ASK_COOLDOWN_TICKS;
		if (ticksSinceAsk < cooldown) return "cooldown-" + ticksSinceAsk + "/" + cooldown;
		return "wait-fail-or-shafts";
	}

	/** 询问是否超时。 */
	public static boolean askTimedOut(int askingTicks) {
		return askTimedOut(askingTicks, false);
	}

	/** 询问是否超时。 */
	public static boolean askTimedOut(int askingTicks, boolean patching) {
		return askingTicks >= (patching ? PATCH_TIMEOUT_TICKS : ASK_TIMEOUT_TICKS);
	}

	/** 本地招数用尽才改 Java；顺利挖过几口井只更新记忆，不动代码。 */
	public static boolean shouldPatchCode(boolean grokAvailable, boolean hasRepo, boolean allMovesFailed) {
		return grokAvailable && hasRepo && allMovesFailed;
	}

	/** 路径是否像本仓库。 */
	public static boolean looksLikeRepo(Path root) {
		if (root == null) return false;
		return Files.isRegularFile(root.resolve("gradlew"))
			&& Files.isDirectory(root.resolve("src/client/java/dev/twob2tkit/runtime/engine"));
	}

	/** 解析源码根目录。 */
	public static Path sourceRoot(String env, Path markerFile, Path fallback) {
		Path fromEnv = parsePath(env);
		if (looksLikeRepo(fromEnv)) return fromEnv.toAbsolutePath();
		Path fromMarker = readMarker(markerFile);
		if (looksLikeRepo(fromMarker)) return fromMarker.toAbsolutePath();
		if (looksLikeRepo(fallback)) return fallback.toAbsolutePath();
		return null;
	}

	/** 默认源码根猜测。 */
	public static Path defaultSourceRoot(Path userHome) {
		if (userHome == null) return null;
		return userHome.resolve("Code/DogeOW/minecraft-kit/2b2t-kit");
	}

	/**
	 * 游戏进程的 {@code user.home} 可能不是终端 HOME。
	 * 优先 GROK_HOME，再 HOME/.grok，再 user.home/.grok；有 auth.json 的优先。
	 */
	public static Path discoverGrokHome(String grokHomeEnv, String homeEnv, String userHomeProp) {
		Path[] candidates = {
			parsePath(grokHomeEnv),
			homeEnv == null || homeEnv.isBlank() ? null : Path.of(homeEnv.trim(), ".grok"),
			userHomeProp == null || userHomeProp.isBlank() ? null : Path.of(userHomeProp.trim(), ".grok")
		};
		Path fallback = null;
		for (Path path : candidates) {
			if (path == null) continue;
			Path abs = path.toAbsolutePath();
			if (fallback == null) fallback = abs;
			if (Files.isRegularFile(abs.resolve("auth.json"))) return abs;
		}
		return fallback;
	}

	/** 发现 Grok 可执行文件。 */
	public static Path discoverGrokBin(Path grokHome, String grokBinEnv) {
		Path fromEnv = parsePath(grokBinEnv);
		if (isGrokBin(fromEnv)) return fromEnv.toAbsolutePath();
		if (grokHome == null) return null;
		Path bin = grokHome.resolve("bin/grok");
		return isGrokBin(bin) ? bin.toAbsolutePath() : null;
	}

	/** 符号链接、普通文件都算；不要只认 isExecutable，HMCL 启动的 JRE 对 symlink 会判失败。 */
	public static boolean isGrokBin(Path path) {
		if (path == null) return false;
		try {
			if (!Files.exists(path) || Files.isDirectory(path)) return false;
			return Files.isSymbolicLink(path) || Files.isRegularFile(path) || Files.isExecutable(path);
		} catch (RuntimeException ignored) {
			return false;
		}
	}

	/**
	 * 子进程 stdin 必须是可读重定向。{@code Redirect.DISCARD} 类型是 WRITE，
	 * {@code redirectInput(DISCARD)} 会抛 {@code Redirect invalid for reading: WRITE}，Grok 根本起不来。
	 */
	public static void discardStdin(ProcessBuilder builder) {
		if (builder == null) return;
		builder.redirectInput(ProcessBuilder.Redirect.from(nullDevice()));
	}

	/** 空设备文件。 */
	public static File nullDevice() {
		String os = System.getProperty("os.name", "");
		return new File(os.toLowerCase(Locale.ROOT).contains("win") ? "NUL" : "/dev/null");
	}

	/**
	 * HMCL 的 {@code user.home} 可能是 {@code /Applications}。Grok CLI 认 HOME，
	 * 不要把已经正确的 {@code HOME=/Users/sam} 覆盖掉。
	 */
	public static String realHome(Path grokHome, String homeEnv, String userHomeProp) {
		if (homeEnv != null && !homeEnv.isBlank()) return homeEnv.trim();
		if (grokHome != null && grokHome.getParent() != null) return grokHome.getParent().toString();
		return userHomeProp == null ? "" : userHomeProp;
	}

	/** 解析路径字符串。 */
	private static Path parsePath(String text) {
		if (text == null || text.isBlank()) return null;
		try {
			return Path.of(text.trim());
		} catch (RuntimeException ignored) {
			return null;
		}
	}

	/** 读标记文件里的路径。 */
	private static Path readMarker(Path markerFile) {
		if (markerFile == null || !Files.isRegularFile(markerFile)) return null;
		try {
			for (String line : Files.readAllLines(markerFile, StandardCharsets.UTF_8)) {
				String trimmed = line.trim();
				if (!trimmed.isEmpty() && !trimmed.startsWith("#")) return Path.of(trimmed);
			}
		} catch (Exception ignored) {
			return null;
		}
		return null;
	}

	/** 根据现场状态推断当前招。 */
	public static Move liveMove(boolean relocating, boolean mining, boolean flying, boolean destBelow) {
		if (mining) return relocating ? Move.MINE_FRONT : Move.MINE_LOOKED;
		if (relocating && destBelow) return Move.DESCEND;
		if (relocating && flying) return Move.FLY_LEVEL;
		return null;
	}

	/** 去掉 markdown 代码围栏。 */
	public static String stripJsonFence(String text) {
		if (text == null) return "";
		String trimmed = text.trim();
		if (trimmed.startsWith("```")) {
			int start = trimmed.indexOf('\n');
			int end = trimmed.lastIndexOf("```");
			if (start >= 0 && end > start) trimmed = trimmed.substring(start + 1, end).trim();
		}
		return trimmed;
	}

	/** 招数名解析为枚举。 */
	public static Move parseMove(String name) {
		if (name == null || name.isBlank()) return null;
		try {
			return Move.valueOf(name.trim().toUpperCase(Locale.ROOT));
		} catch (IllegalArgumentException ignored) {
			return null;
		}
	}
}
