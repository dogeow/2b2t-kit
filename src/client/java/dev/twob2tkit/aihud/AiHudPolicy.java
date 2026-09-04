package dev.twob2tkit.aihud;

import java.util.ArrayList;
import java.util.List;

/** 屏幕固定 AI 面板：何时显示、等了多久、留几行过程。 */
public final class AiHudPolicy {
	public static final int HOLD_MS = 10_000;
	public static final int MAX_LINES = 6;

	private AiHudPolicy() {
	}

	/** 进行中始终显示；结束后在 hideAt 之前仍短暂保留。 */
	public static boolean visible(boolean running, long nowMs, long hideAtMs) {
		if (running) return true;
		return hideAtMs > nowMs;
	}

	/** 从开始到现在的等待文案（秒或分秒）。 */
	public static String elapsed(long startedAtMs, long nowMs) {
		long sec = Math.max(0L, (nowMs - startedAtMs) / 1000L);
		if (sec < 60L) return "已等 " + sec + " 秒";
		return "已等 " + (sec / 60L) + " 分 " + (sec % 60L) + " 秒";
	}

	/** 只保留末尾若干行过程，避免面板过长。 */
	public static List<String> keepTail(List<String> lines) {
		if (lines == null || lines.isEmpty()) return List.of();
		if (lines.size() <= MAX_LINES) return List.copyOf(lines);
		return List.copyOf(lines.subList(lines.size() - MAX_LINES, lines.size()));
	}

	/** 追加一步过程；与上一行相同则跳过，超出上限时丢掉更早的行。 */
	public static List<String> append(List<String> lines, String step) {
		List<String> next = new ArrayList<>(lines == null ? List.of() : lines);
		if (step != null && !step.isBlank() && (next.isEmpty() || !step.equals(next.getLast()))) {
			next.add(step);
		}
		if (next.size() > MAX_LINES) {
			next = new ArrayList<>(next.subList(next.size() - MAX_LINES, next.size()));
		}
		return next;
	}
}
