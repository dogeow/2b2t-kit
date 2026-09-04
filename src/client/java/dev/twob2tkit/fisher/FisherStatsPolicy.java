package dev.twob2tkit.fisher;

import java.util.Locale;

/**
 * 钓鱼字幕只报统计，不报等咬钩/上钩。自己能看见浮标。
 */
public final class FisherStatsPolicy {
	private FisherStatsPolicy() {
	}

	/** 字幕：条数、平均每条耗时、已钓时长。 */
	public static String hud(int catches, long elapsedMs) {
		String time = formatDuration(elapsedMs);
		if (catches <= 0) return "0条  已钓 " + time + "  平均 —";
		return String.format(Locale.ROOT, "%d条  平均 %s/条  已钓 %s",
			catches, formatSeconds(elapsedMs / 1000.0 / catches), time);
	}

	/** 秒数格式成「N秒」或「M分S秒」。 */
	public static String formatSeconds(double seconds) {
		if (seconds < 60.0) return String.format(Locale.ROOT, "%.0f秒", seconds);
		int total = (int)Math.round(seconds);
		return (total / 60) + "分" + (total % 60) + "秒";
	}

	/** 已钓时长：有小时用 H:MM:SS，否则 M:SS。 */
	public static String formatDuration(long elapsedMs) {
		long seconds = Math.max(0L, elapsedMs / 1000L);
		long hours = seconds / 3600L;
		long minutes = (seconds % 3600L) / 60L;
		long secs = seconds % 60L;
		if (hours > 0L) {
			return String.format(Locale.ROOT, "%d:%02d:%02d", hours, minutes, secs);
		}
		return String.format(Locale.ROOT, "%d:%02d", minutes, secs);
	}
}
