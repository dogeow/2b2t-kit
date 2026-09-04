package dev.twob2tkit;

import net.minecraft.client.Minecraft;

/** 单个功能的诊断日志：start/stop/periodic/once。 */
public final class SessionLog {
	private final String module;
	private String last = "";
	private int ticks;

	public SessionLog(String module) {
		this.module = module;
	}

	/** 清上次文案与周期计数。 */
	public void reset() {
		last = "";
		ticks = 0;
	}

	/** 无条件写一行并记作上次文案。 */
	public void append(Minecraft client, String line) {
		ModuleFileLog.append(client, module, line);
		last = line;
	}

	/** 与上次相同则跳过，避免刷屏。 */
	public void once(Minecraft client, String line) {
		if (line.equals(last)) return;
		append(client, line);
	}

	/** 每约 2 秒（40 tick）为 true，供周期摘要。 */
	public boolean due() {
		ticks++;
		return ticks % 40 == 0;
	}
}
