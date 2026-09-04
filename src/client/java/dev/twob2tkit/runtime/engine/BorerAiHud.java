package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.BorerHost;

/** 通过宿主画 AI 过程。新方法用反射，旧主机不会崩。 */
final class BorerAiHud {
	private BorerAiHud() {
	}

	/** 开始在屏幕上显示 AI 过程标题。 */
	static void begin(BorerHost host, String title) {
		call(host, "beginAiProcess", new Class<?>[]{String.class}, title);
	}

	/** 追加一条 AI 步骤说明。 */
	static void note(BorerHost host, String step) {
		call(host, "noteAiProcess", new Class<?>[]{String.class}, step);
	}

	/** 结束 AI 过程；failed 时面板标红。 */
	static void end(BorerHost host, String result, boolean failed) {
		call(host, "endAiProcess", new Class<?>[]{String.class, boolean.class}, result, failed);
	}

	/** 反射调用宿主方法；旧主机没有则静默忽略。 */
	private static void call(BorerHost host, String name, Class<?>[] types, Object... args) {
		if (host == null) return;
		try {
			host.getClass().getMethod(name, types).invoke(host, args);
		} catch (ReflectiveOperationException ignored) {
		}
	}
}
