package dev.twob2tkit.logreview;

/**
 * 游戏里扫各功能日志，卡住才问 Grok。只改这一处。
 * <p>
 * 盾构「想想」已经会问 Grok 改引擎，borer.log 不在这里重复问。其它功能只送日志换课，不改 jar。
 */
public final class LogReviewPolicy {
	public static final int SCAN_EVERY_TICKS = 40;
	public static final int URGENT_COOLDOWN_TICKS = 200;
	public static final int ROUTINE_COOLDOWN_TICKS = 2400;
	public static final int TAIL_BYTES = 24 * 1024;

	private LogReviewPolicy() {
	}

	/** 每隔若干 tick 扫一次日志。 */
	public static boolean scanThisTick(int ticks) {
		return ticks > 0 && ticks % SCAN_EVERY_TICKS == 0;
	}

	/** 盾构已有「想想」，这里不再复审 borer。 */
	public static boolean reviewable(String module) {
		return module != null && !module.equals("borer");
	}

	/** 模块 id 转中文标签。 */
	public static String label(String module) {
		if (module == null) return "";
		return switch (module) {
			case "chopper" -> "挖树";
			case "planter" -> "种田";
			case "feeder" -> "喂养";
			case "fisher" -> "钓鱼";
			case "cruise" -> "巡航";
			case "surround" -> "围箱";
			case "brawler" -> "打猪人";
			case "nether-roof" -> "下界顶";
			case "combat" -> "战斗";
			case "builder" -> "建造";
			case "borer" -> "盾构";
			default -> module;
		};
	}

	/** 尾部日志是否出现卡住/缺工具等紧急信号。 */
	public static boolean urgent(String chunk) {
		if (chunk == null || chunk.isBlank()) return false;
		int stall = count(chunk, "stall skip=");
		int stand = count(chunk, "stand-skip") + count(chunk, "停住砍");
		int clip = count(chunk, "clip-miss");
		int shears = count(chunk, "shears-worn");
		int stuck = count(chunk, "approach-stuck") + count(chunk, "approach-abandon");
		int harvest = count(chunk, "harvest-stall");
		int cannot = count(chunk, "cannot-break");
		int unstick = count(chunk, "unstick");
		int noBlock = count(chunk, "no-block") + count(chunk, "没有可用");
		int noTool = count(chunk, "no-rod") + count(chunk, "no-ammo") + count(chunk, "no-bow")
			+ count(chunk, "no-pearl") + count(chunk, "stuck-bow");
		int pearlFail = count(chunk, "pearl-fail");
		int placeFail = count(chunk, "place-fail");
		int death = count(chunk, "death killer=");
		int full = count(chunk, "inventory-full");
		return stall >= 2 || stand >= 1 || clip >= 8 || shears >= 1 || stuck >= 1
			|| harvest >= 1 || cannot >= 1 || unstick >= 1 || noBlock >= 1
			|| noTool >= 1 || pearlFail >= 1 || placeFail >= 1 || death >= 1 || full >= 1;
	}

	/** 开着复审、能问、不忙、且紧急，且距上次提问已过冷却。 */
	public static boolean shouldAsk(boolean enabled, boolean canAsk, boolean busy, int ticksSinceAsk, boolean urgent) {
		if (!enabled || !canAsk || busy || !urgent) return false;
		return ticksSinceAsk >= URGENT_COOLDOWN_TICKS;
	}

	/** 统计 needle 在文本中出现次数。 */
	public static int count(String haystack, String needle) {
		if (haystack == null || needle == null || needle.isEmpty()) return 0;
		int n = 0;
		int from = 0;
		while (true) {
			int at = haystack.indexOf(needle, from);
			if (at < 0) return n;
			n++;
			from = at + needle.length();
		}
	}
}
