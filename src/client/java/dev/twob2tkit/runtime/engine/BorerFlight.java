package dev.twob2tkit.runtime.engine;

import com.mojang.blaze3d.platform.InputConstants;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** Meteor Flight 反射开关，宿主没有飞行 API 时引擎自己调。 */
public final class BorerFlight {
	private BorerFlight() {
	}

	/** 玩家是否在飞。 */
	public static boolean isFlying(LocalPlayer player) {
		Boolean meteor = meteorFlightActive();
		if (meteor != null) return meteor;
		return player.getAbilities().flying || player.isFallFlying();
	}

	/** Meteor Flight 是否开着（查不到则 null）。 */
	public static Boolean meteorFlightActive() {
		return meteorModuleActive("meteordevelopment.meteorclient.systems.modules.movement.Flight");
	}

	/** Meteor NoFall 是否开着。 */
	public static boolean meteorNoFallActive() {
		return Boolean.TRUE.equals(meteorModuleActive("meteordevelopment.meteorclient.systems.modules.movement.NoFall"));
	}

	/** Meteor Step 是否开着。 */
	public static boolean meteorStepActive() {
		return Boolean.TRUE.equals(meteorModuleActive("meteordevelopment.meteorclient.systems.modules.movement.Step"));
	}

	/** Meteor AutoFish 是否开着。 */
	public static boolean meteorAutoFishActive() {
		return Boolean.TRUE.equals(meteorModuleActive("meteordevelopment.meteorclient.systems.modules.player.AutoFish"));
	}

	public static final String SCAFFOLD = "meteordevelopment.meteorclient.systems.modules.movement.Scaffold";

	/** Meteor Scaffold 是否开着。 */
	public static boolean meteorScaffoldActive() {
		return Boolean.TRUE.equals(meteorModuleActive(SCAFFOLD));
	}

	/** 需要垫脚时打开 Meteor Scaffold；已经开着就沿用。找不到模组返回 false。 */
	public static boolean ensureScaffold(boolean wantOn) {
		Boolean active = meteorModuleActive(SCAFFOLD);
		if (active == null) return false;
		if (active == wantOn) return true;
		return toggleMeteorModule(SCAFFOLD);
	}

	/** Meteor Step 默认 1.25，或玩家当前步高已经够跨 1 格。 */
	public static boolean canStepOneBlock(LocalPlayer player) {
		if (player == null) return false;
		if (meteorStepActive()) return true;
		return player.maxUpStep() >= 0.999F;
	}

	/** 反射查 Meteor 模块是否激活。 */
	private static Boolean meteorModuleActive(String className) {
		try {
			Class<?> modulesClz = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
			Object modules = modulesClz.getMethod("get").invoke(null);
			if (modules == null) return null;
			Class<?> moduleClz = Class.forName(className);
			Object module = modulesClz.getMethod("get", Class.class).invoke(modules, moduleClz);
			if (module == null) return null;
			return (Boolean) module.getClass().getMethod("isActive").invoke(module);
		} catch (Throwable ignored) {
			return null;
		}
	}

	/** 切换 Meteor Flight。 */
	public static boolean toggleMeteorFlight() {
		return toggleMeteorModule("meteordevelopment.meteorclient.systems.modules.movement.Flight");
	}

	/** 反射切换指定 Meteor 模块开关。 */
	private static boolean toggleMeteorModule(String className) {
		try {
			Class<?> modulesClz = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
			Object modules = modulesClz.getMethod("get").invoke(null);
			if (modules == null) return false;
			Class<?> moduleClz = Class.forName(className);
			Object module = modulesClz.getMethod("get", Class.class).invoke(modules, moduleClz);
			if (module == null) return false;
			module.getClass().getMethod("toggle").invoke(module);
			return true;
		} catch (Throwable ignored) {
			return false;
		}
	}

	/** 需要飞时打开 Meteor Flight；找不到模组则按 C（Meteor 默认飞行键）。 */
	public static boolean ensureFlying(LocalPlayer player, boolean wantFly) {
		if (isFlying(player) == wantFly) return true;
		if (toggleMeteorFlight()) return true;
		try {
			KeyMapping.click(InputConstants.getKey("key.keyboard.c"));
			return true;
		} catch (RuntimeException ignored) {
			return false;
		}
	}

	/** 精细走位时把 Meteor Flight speed 降下来；原值写到 bak，停挖时还原。 */
	public static void slowForPrecision(Minecraft client) {
		Double current = readFlightSpeed();
		if (current == null || !BorerSteerPolicy.shouldSlowFlight(current)) return;
		Path bak = speedBak(client);
		if (bak == null || Files.isRegularFile(bak)) return;
		try {
			Files.createDirectories(bak.getParent());
			Files.writeString(bak, current.toString(), StandardCharsets.UTF_8);
			writeFlightSpeed(BorerSteerPolicy.PRECISE_FLIGHT_SPEED);
		} catch (Exception ignored) {
		}
	}

	/** 从备份恢复 Meteor Flight 速度并删掉备份文件。 */
	public static void restoreSpeed(Minecraft client) {
		Path bak = speedBak(client);
		if (bak == null || !Files.isRegularFile(bak)) return;
		try {
			String raw = Files.readString(bak, StandardCharsets.UTF_8).trim();
			double saved = Double.parseDouble(raw);
			writeFlightSpeed(saved);
			Files.deleteIfExists(bak);
		} catch (Exception ignored) {
		}
	}

	/** 读取 Meteor Flight 的 speed 设置；读不到返回 null。 */
	static Double readFlightSpeed() {
		try {
			Object setting = flightSpeedSetting();
			if (setting == null) return null;
			Object value = setting.getClass().getMethod("get").invoke(setting);
			if (value instanceof Number number) return number.doubleValue();
		} catch (Throwable ignored) {
		}
		return null;
	}

	/** 写入 Meteor Flight 的 speed 设置；成功返回 true。 */
	static boolean writeFlightSpeed(double speed) {
		try {
			Object setting = flightSpeedSetting();
			if (setting == null) return false;
			Double value = Double.valueOf(speed);
			try {
				setting.getClass().getMethod("set", Object.class).invoke(setting, value);
				return true;
			} catch (NoSuchMethodException ignored) {
				for (java.lang.reflect.Method method : setting.getClass().getMethods()) {
					if (!method.getName().equals("set") || method.getParameterCount() != 1) continue;
					method.invoke(setting, value);
					return true;
				}
			}
		} catch (Throwable ignored) {
		}
		return false;
	}

	/** 反射拿到 Meteor Flight 的 speed 设置对象。 */
	private static Object flightSpeedSetting() throws Exception {
		Class<?> modulesClz = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
		Object modules = modulesClz.getMethod("get").invoke(null);
		if (modules == null) return null;
		Class<?> flightClz = Class.forName("meteordevelopment.meteorclient.systems.modules.movement.Flight");
		Object module = modulesClz.getMethod("get", Class.class).invoke(modules, flightClz);
		if (module == null) return null;
		Object settings = module.getClass().getField("settings").get(module);
		return settings.getClass().getMethod("get", String.class).invoke(settings, "speed");
	}

	/** 飞速临时备份文件路径。 */
	private static Path speedBak(Minecraft client) {
		if (client == null || client.gameDirectory == null) return null;
		return client.gameDirectory.toPath().resolve("config/twob2tkit/flight-speed.bak");
	}
}
