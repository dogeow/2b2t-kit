package dev.twob2tkit.borer;

/** 外部引擎 jar 换新后，等复制完成再热加载。 */
public final class BorerHotReloadPolicy {
	/** 文件修改时间连续不变多久才算写稳（tick）。 */
	public static final int STABLE_TICKS = 40;

	private BorerHotReloadPolicy() {
	}

	/** 磁盘 jar 是否比已加载副本更新。 */
	public static boolean jarNewer(long loadedMtime, long fileMtime) {
		return fileMtime > loadedMtime;
	}

	/** 同一 mtime 已持续足够 tick，可以安全热加载。 */
	public static boolean stable(int sameMtimeTicks, int needTicks) {
		return sameMtimeTicks >= needTicks;
	}
}
