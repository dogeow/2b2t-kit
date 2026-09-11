package dev.twob2tkit.runtime.engine;

import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Optional live Meteor integration. Never changes its food thresholds or anti-break settings. */
final class BorerMeteorAutomation {
	interface Lookup { Object get(String name) throws ReflectiveOperationException; }
	record Meal(boolean requested, boolean eating, String settings) {
		static final Meal NONE = new Meal(false, false, "disabled");
	}
	private final Lookup lookup;
	private Handle eat, tool;
	BorerMeteorAutomation() { this(BorerMeteorAutomation::find); }
	BorerMeteorAutomation(Lookup lookup) { this.lookup = lookup; }

	Meal meal() {
		try {
			if (eat == null) eat = handle("player.AutoEat");
			return eat == null ? Meal.NONE : eat.meal();
		} catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
			throw new IllegalStateException("无法读取 Meteor 自动吃状态，已停挖以免打断进食", error);
		}
	}
	BorerToolPolicy tools() {
		try {
			if (tool == null) tool = handle("player.AutoTool");
			if (tool == null || !tool.active()) return BorerToolPolicy.DEFAULT;
			boolean protect = (Boolean) tool.value("anti-break");
			int percent = ((Number) tool.value("anti-break-percentage")).intValue();
			String mode = ((Enum<?>) tool.value("list-mode")).name();
			Set<?> items = Set.copyOf((List<?>) tool.value(mode.equals("Whitelist") ? "whitelist" : "blacklist"));
			return new BorerToolPolicy(protect, percent, mode, items);
		} catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
			throw new IllegalStateException("无法读取 Meteor 自动工具防破设置，已停挖保护工具", error);
		}
	}
	private Handle handle(String name) throws ReflectiveOperationException {
		Object module = lookup.get(name);
		return module == null ? null : new Handle(module);
	}
	private static Object find(String name) throws ReflectiveOperationException {
		Class<?> registry;
		try { registry = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules"); }
		catch (ClassNotFoundException absent) { return null; }
		Object modules = registry.getMethod("get").invoke(null);
		if (modules == null) return null;
		return registry.getMethod("get", Class.class).invoke(modules,
			Class.forName("meteordevelopment.meteorclient.systems.modules." + name));
	}
	private static final class Handle {
		private final Object module;
		private final Method active;
		private final Map<String, Object> settings = new HashMap<>();
		Handle(Object module) throws ReflectiveOperationException {
			this.module = module; active = module.getClass().getMethod("isActive");
		}
		boolean active() throws ReflectiveOperationException { return (Boolean) active.invoke(module); }
		Object value(String name) throws ReflectiveOperationException {
			Object setting = settings.get(name);
			if (setting == null) {
				Object group = module.getClass().getField("settings").get(module);
				setting = group.getClass().getMethod("get", String.class).invoke(group, name);
				if (setting == null) throw new IllegalStateException("Missing Meteor setting " + name);
				settings.put(name, setting);
			}
			return setting.getClass().getMethod("get").invoke(setting);
		}
		Meal meal() throws ReflectiveOperationException {
			if (!active()) return Meal.NONE;
			boolean eating = module.getClass().getField("eating").getBoolean(module);
			// Native predicate includes <= thresholds, Any/Both, blacklist, hunger and available food.
			// While eating, leave its internal selected food slot alone.
			boolean requested = eating || (Boolean) module.getClass().getMethod("shouldEat").invoke(module);
			String description = "mode=" + value("threshold-mode") + " health=" + value("health-threshold")
				+ " hunger=" + value("hunger-threshold") + " inventory=" + value("search-inventory");
			return new Meal(requested, eating, description);
		}
	}
}
