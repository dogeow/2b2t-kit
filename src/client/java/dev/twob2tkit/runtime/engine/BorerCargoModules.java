package dev.twob2tkit.runtime.engine;

import java.util.ArrayList;
import java.util.List;

/** Temporarily yield conflicting automatic inventory actions during a cargo trip. */
final class BorerCargoModules implements AutoCloseable {
	private final List<Object> paused = new ArrayList<>();
	void acquire() {
		try {
			Class<?> modules = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
			Object registry = modules.getMethod("get").invoke(null);
			for (String name : List.of("misc.InventoryTweaks", "player.AutoReplenish")) {
				Object module = modules.getMethod("get", Class.class).invoke(registry,
					Class.forName("meteordevelopment.meteorclient.systems.modules." + name));
				if (module != null) pause(module);
			}
		} catch (ReflectiveOperationException | LinkageError e) {
			close(); throw new IllegalStateException("无法协调 Meteor 的背包自动操作，未开始卸货", e);
		}
	}
	void pause(Object module) throws ReflectiveOperationException {
		if ((Boolean) module.getClass().getMethod("isActive").invoke(module)) {
			paused.add(module);
			module.getClass().getMethod("toggle").invoke(module);
		}
	}
	@Override public void close() {
		for (Object module : paused) try {
			if (!(Boolean) module.getClass().getMethod("isActive").invoke(module)) module.getClass().getMethod("toggle").invoke(module);
		} catch (ReflectiveOperationException | LinkageError ignored) {}
		paused.clear();
	}
}
