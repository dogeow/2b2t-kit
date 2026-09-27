package dev.twob2tkit.cruise;

/** One-line cruise HUD state, independent of rendering and game time. */
public final class CruiseHudState {
	private String status = "";
	private String notice = "";
	private long noticeStartedNanos;
	private long noticeDurationNanos;

	/** A new navigation leg immediately replaces a previous arrival notice. */
	public void begin(String line) {
		clear();
		status(line);
	}

	public void status(String line) {
		status = line == null ? "" : line.strip();
	}

	/** A short phase change temporarily takes priority over live progress. */
	public void notice(String line, long nowNanos, long durationNanos) {
		notice = line == null ? "" : line.strip();
		noticeStartedNanos = nowNanos;
		noticeDurationNanos = Math.max(0, durationNanos);
	}

	/** Arrival/stop leaves only a brief notice, then disappears. */
	public void finish(String line, long nowNanos, long durationNanos) {
		status = "";
		notice(line, nowNanos, durationNanos);
	}

	public String line(long nowNanos) {
		if (!notice.isEmpty() && nowNanos - noticeStartedNanos < noticeDurationNanos) return notice;
		notice = "";
		return status;
	}

	public boolean showingNotice(long nowNanos) {
		return !notice.isEmpty() && nowNanos - noticeStartedNanos < noticeDurationNanos;
	}

	public void clear() {
		status = "";
		notice = "";
		noticeDurationNanos = 0;
	}
}
