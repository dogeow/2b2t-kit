package dev.twob2tkit.runtime.engine;

import java.util.*;

/** Temporarily give Kit exclusive mining ownership; combat, food and fall protection remain independent. */
public final class BorerMiningModules {
	interface Module { boolean active(); void enable(); void disable(); }
	interface Lookup { Module find(String name) throws ReflectiveOperationException; }
	private final Lookup lookup;
	private final List<Module> owned = new ArrayList<>();
	private boolean acquired, preservingSpeedMine;
	private boolean repeatRequested;
	private Module pausedSpeedMine;

	boolean hasPausedSpeedMine() { return pausedSpeedMine != null; }

	boolean withSpeedMine(java.util.function.BooleanSupplier clicks) {
		Module module=pausedSpeedMine;
		if (module==null || module.active()) return clicks.getAsBoolean();
		module.enable();
		try { return clicks.getAsBoolean(); }
		finally { module.disable(); }
	}
	/** Give the player's own SpeedMine back while every break is registered by us; pause it again otherwise. */
	void holdSpeedMine(boolean held) {
		Module module=pausedSpeedMine;
		if (module==null || module.active()==held) return;
		if (held) module.enable(); else module.disable();
	}
	boolean instantRebreakRequested() { return repeatRequested; }
	public BorerMiningModules() { this(BorerMiningModules::find); }
	BorerMiningModules(Lookup lookup) { this.lookup = lookup; }
	public int acquire() {
		return acquire(false);
	}
	/** Area clicks register vanilla predictions and can therefore cooperate with SpeedMine. */
	public int acquire(boolean preserveSpeedMine) {
		if (acquired && preservingSpeedMine == preserveSpeedMine) return owned.size();
		if (acquired) release();
		try {
			for (String name : List.of("SpeedMine", "InstantRebreak")) {
				if (preserveSpeedMine && name.equals("SpeedMine")) continue;
				Module module = lookup.find(name);
				if (name.equals("InstantRebreak")) repeatRequested = module != null && module.active();
				if (module != null && module.active()) {
					owned.add(module);
					if (name.equals("SpeedMine")) pausedSpeedMine=module;
					module.disable();
				}
			}
			acquired = true; preservingSpeedMine = preserveSpeedMine;
			return owned.size();
		} catch (ReflectiveOperationException | RuntimeException e) { release(); throw new IllegalStateException("无法协调其他挖掘模块，未启动", e); }
	}
	public void release() {
		RuntimeException failure = null;
		for (Module module : owned) try { if (!module.active()) module.enable(); }
		catch (RuntimeException e) { failure = e; }
		owned.clear();
		acquired = false;
		repeatRequested = false;
		pausedSpeedMine = null;
		if (failure != null) throw failure;
	}
	private static Module find(String name) throws ReflectiveOperationException {
		Class<?> registry;
		try { registry = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules"); }
		catch (ClassNotFoundException missing) { return null; }
		Class<?> type = Class.forName("meteordevelopment.meteorclient.systems.modules.player." + name);
		Object module = registry.getMethod("get", Class.class).invoke(registry.getMethod("get").invoke(null), type);
		if (module == null) return null;
		var active = type.getMethod("isActive"); var enable = type.getMethod("enable"); var disable = type.getMethod("disable");
		return new Module() {
			private Object call(java.lang.reflect.Method method) {
				try { return method.invoke(module); }
				catch (ReflectiveOperationException e) { throw new IllegalStateException(e); }
			}
			public boolean active() { return (Boolean) call(active); }
			public void enable() { call(enable); }
			public void disable() { call(disable); }
		};
	}
}
