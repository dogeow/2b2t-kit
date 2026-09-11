package dev.twob2tkit;

/** 反射打开已装的 Meteor 模块。找不到模组就当没装，不报错。 */
public final class MeteorModules {
	/** KillAura 全类名。 */
	public static final String KILL_AURA = "meteordevelopment.meteorclient.systems.modules.combat.KillAura";
	/** AutoLog 全类名。 */
	public static final String AUTO_LOG = "meteordevelopment.meteorclient.systems.modules.combat.AutoLog";
	/** Flight 全类名。 */
	public static final String FLIGHT = "meteordevelopment.meteorclient.systems.modules.movement.Flight";

	private MeteorModules() {
	}

	/** 该 Meteor 模块是否已开启。 */
	public static boolean isActive(String className) {
		Object module = module(className);
		if (module == null) return false;
		try {
			return Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module));
		} catch (ReflectiveOperationException ignored) {
			return false;
		}
	}

	/**
	 * 尝试打开模块；已开则不动。
	 * @return true 表示这一拍新打开了
	 */
	public static boolean enable(String className) {
		Object module = module(className);
		if (module == null) return false;
		try {
			if (Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module))) return false;
			try {
				module.getClass().getMethod("enable").invoke(module);
			} catch (NoSuchMethodException ignored) {
				module.getClass().getMethod("toggle").invoke(module);
			}
			return Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module));
		} catch (ReflectiveOperationException ignored) {
			return false;
		}
	}
	public static boolean disable(String className) {
		Object module = module(className);
		if (module == null) return false;
		try {
			if (!Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module))) return false;
			module.getClass().getMethod("toggle").invoke(module);
			return !Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module));
		} catch (ReflectiveOperationException ignored) { return false; }
	}

	/** 从 Modules 单例按类名取模块实例；未装 Meteor 返回 null。 */
	private static Object module(String className) {
		try {
			Class<?> modulesClz = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
			Object modules = modulesClz.getMethod("get").invoke(null);
			if (modules == null) return null;
			Class<?> moduleClz = Class.forName(className);
			return modulesClz.getMethod("get", Class.class).invoke(modules, moduleClz);
		} catch (Throwable ignored) {
			return null;
		}
	}
}
