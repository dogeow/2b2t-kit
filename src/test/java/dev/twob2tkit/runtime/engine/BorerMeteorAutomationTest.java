package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class BorerMeteorAutomationTest {
	public enum Mode { Any, Both, Blacklist, Whitelist }
	public static class Setting {
		Object value; Setting(Object value) { this.value = value; }
		public Object get() { return value; }
	}
	public static class Settings {
		final Map<String, Setting> values = new HashMap<>();
		public Setting get(String name) { return values.get(name); }
		void put(String name, Object value) { values.computeIfAbsent(name, _ -> new Setting(value)).value = value; }
	}
	public static class Module {
		public final Settings settings = new Settings();
		boolean active = true, needFood;
		public boolean eating;
		int calls;
		public boolean isActive() { return active; }
		public boolean shouldEat() { calls++; return needFood; }
		Module() {
			settings.put("threshold-mode", Mode.Any); settings.put("health-threshold", 10.0);
			settings.put("hunger-threshold", 16); settings.put("search-inventory", false);
			settings.put("anti-break", true); settings.put("anti-break-percentage", 10);
			settings.put("list-mode", Mode.Blacklist); settings.put("blacklist", List.of()); settings.put("whitelist", List.of("diamond"));
		}
	}
	@Test void delegatesFoodEligibilityToNativePredicateNotJustLowHealthOrHunger() {
		var m = new Module(); var bridge = new BorerMeteorAutomation(_ -> m);
		assertFalse(bridge.meal().requested()); // Native may reject a blacklisted/unavailable food.
		m.needFood = true;
		assertTrue(bridge.meal().requested()); assertEquals(2, m.calls);
		m.eating = true; assertTrue(bridge.meal().eating()); assertEquals(2, m.calls);
	}
	@Test void reflectsChangedLiveThresholdsAndNeverCachesOldSettingsValues() {
		var m = new Module(); var bridge = new BorerMeteorAutomation(_ -> m);
		assertTrue(bridge.meal().settings().contains("hunger=16"));
		m.settings.put("threshold-mode", Mode.Both); m.settings.put("hunger-threshold", 18);
		assertTrue(bridge.meal().settings().contains("mode=Both")); assertTrue(bridge.meal().settings().contains("hunger=18"));
		assertTrue(bridge.tools().allows("diamond", true, 1561, 200));
		m.settings.put("anti-break-percentage", 20);
		assertFalse(bridge.tools().allows("diamond", true, 1561, 200));
	}
	@Test void honorsModuleEnableAndDisableWithoutTogglingAnything() {
		var m = new Module(); var bridge = new BorerMeteorAutomation(_ -> m);
		m.needFood = true; m.active = false;
		assertFalse(bridge.meal().requested()); assertEquals(0, m.calls);
		assertEquals(BorerToolPolicy.DEFAULT, bridge.tools());
		m.active = true; assertTrue(bridge.meal().requested());
		assertTrue(bridge.tools().antiBreak()); assertTrue(m.active);
	}
	@Test void missingMeteorIsOptionalButPresentIncompatibleApiFailsClosed() {
		var absent = new BorerMeteorAutomation(_ -> null);
		assertEquals(BorerMeteorAutomation.Meal.NONE, absent.meal());
		assertEquals(BorerToolPolicy.DEFAULT, absent.tools());
		var broken = new BorerMeteorAutomation(_ -> new Object());
		assertThrows(IllegalStateException.class, broken::meal);
		assertThrows(IllegalStateException.class, broken::tools);
	}
	@Test void honorsLiveToolListsAndDoesNotSilentlyIgnoreMissingProtectionSetting() {
		var m = new Module(); var bridge = new BorerMeteorAutomation(_ -> m);
		m.settings.put("list-mode", Mode.Whitelist);
		assertFalse(bridge.tools().allows("iron", true, 250, 250));
		assertTrue(bridge.tools().allows("diamond", true, 1561, 1500));
		m.settings.get("anti-break-percentage").value = "invalid";
		assertThrows(IllegalStateException.class, bridge::tools);
	}
}
