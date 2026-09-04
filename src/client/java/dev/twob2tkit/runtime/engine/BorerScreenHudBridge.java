package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.BorerHost;

/** 把挖矿提示交给宿主画在屏幕上。旧主机没有这两个方法就退回准星 billboard。 */
final class BorerScreenHudBridge {
	private BorerScreenHudBridge() {
	}

	/** 反射调用宿主屏幕 HUD；失败返回 false。 */
	static boolean show(BorerHost host, String action, int color, String detail) {
		if (host == null) return false;
		try {
			host.getClass()
				.getMethod("showBorerHud", String.class, int.class, String.class)
				.invoke(host, action == null ? "" : action, color, detail == null ? "" : detail);
			return true;
		} catch (ReflectiveOperationException ignored) {
			return false;
		}
	}

	/** 反射隐藏宿主屏幕 HUD。 */
	static void hide(BorerHost host) {
		if (host == null) return;
		try {
			host.getClass().getMethod("hideBorerHud").invoke(host);
		} catch (ReflectiveOperationException ignored) {
		}
	}
}
