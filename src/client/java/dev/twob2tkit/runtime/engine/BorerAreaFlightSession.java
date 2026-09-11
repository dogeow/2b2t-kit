package dev.twob2tkit.runtime.engine;

import net.minecraft.client.player.LocalPlayer;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.util.Objects;

/** 区域挖独占的临时 Flight 设置；只在客户端主线程调用，不改其它 Meteor 模块。 */
public final class BorerAreaFlightSession implements AutoCloseable {
	private static final String MODULES = "meteordevelopment.meteorclient.systems.modules.Modules";
	private static final String FLIGHT = "meteordevelopment.meteorclient.systems.modules.movement.Flight";
	private static final String ANTI_AFK = "meteordevelopment.meteorclient.systems.modules.player.AntiAFK";
	private static final String SCAFFOLD = "meteordevelopment.meteorclient.systems.modules.movement.Scaffold";
	private final ModuleLookup lookup;
	private ModuleHandle flight;
	private ModuleHandle antiAfk;
	private ModuleHandle scaffold;
	private SettingHandle[] antiAfkActions;
	private SettingHandle[] leasedSettings;
	private SettingHandle flightSpeed;
	private boolean enabledByUs;
	private boolean acquired;
	private boolean grounded, originallyActive;
	private BorerFlightSpeedBackup speedBackup;
	private Path preparedPath;

	/** Recover before borrowing settings, also on the first idle world tick after reload/restart. */
	public String prepare(Path path) {
		if (acquired || path.equals(preparedPath)) return null;
		try {
			Object module = requireModule(FLIGHT, "Meteor Flight 尚未就绪");
			SettingHandle speed = new SettingHandle(module, "speed");
			if (!(speed.original instanceof Double current)) throw new IllegalStateException("Flight 速度类型不兼容");
			BorerFlightSpeedBackup backup = new BorerFlightSpeedBackup(path);
			BorerFlightSpeedBackup.Entry entry = backup.read();
			double restored = entry == null ? current : entry.restore(current);
			// Migration for 1.7.2–1.7.4: those releases had no durable backup. Do not touch nonzero manual speeds.
			if (entry == null && current == 0.0
				&& new SettingHandle(module, "mode").original instanceof Enum<?> mode && mode.name().equals("Velocity")
				&& Boolean.TRUE.equals(new SettingHandle(module, "noSneak").original)) restored = 0.1;
			if (restored != current) speed.write(restored);
			backup.clear();
			speedBackup = backup;
			preparedPath = path;
			return restored != current ? "已恢复 Meteor 手动飞行速度 " + restored + "（清理区域挖临时速度）" : null;
		} catch (Exception | LinkageError failure) {
			throw new IllegalStateException("无法恢复区域挖飞行速度备份，未接管飞行", failure);
		}
	}

	private void writeSpeed(double value) throws Exception {
		flightSpeed.checkOwned();
		if (Objects.equals(flightSpeed.lastWritten, value)) return;
		if (speedBackup != null) speedBackup.beforeWrite((Double) flightSpeed.original, (Double) flightSpeed.lastWritten, value);
		flightSpeed.write(value);
	}

	public BorerAreaFlightSession() {
		this(BorerAreaFlightSession::findMeteorModule);
	}

	/** 注入模块查找器也允许用普通对象验证反射、失败回滚和条件恢复。 */
	BorerAreaFlightSession(ModuleLookup lookup) {
		this.lookup = lookup;
	}

	/** 获取或复核会话，失败时已回滚本会话拥有的设置。 */
	public String acquire(LocalPlayer player) {
		if (player == null) {
			close();
			return "玩家尚未就绪，区域飞行未启动";
		}
		return acquire();
	}

	/** 不接触玩家的设置事务，供 acquire(LocalPlayer) 和离线验证共用。 */
	String acquire() {
		try {
			if (acquired) {
				checkConflicts();
				if (!flight.active() && !grounded) throw new IllegalStateException("Meteor Flight 已关闭，区域飞行已停止");
				for (SettingHandle setting : leasedSettings) setting.checkOwned();
				return null;
			}

			flight = new ModuleHandle(requireModule(FLIGHT, "区域挖需要 Meteor Flight，不使用原生飞行或模拟 C 键"));
			antiAfk = new ModuleHandle(requireModule(ANTI_AFK, "无法检查 Meteor AntiAFK，区域飞行未启动"));
			scaffold = new ModuleHandle(requireModule(SCAFFOLD, "无法检查 Meteor Scaffold，区域飞行未启动"));
			antiAfkActions = new SettingHandle[] {
				new SettingHandle(antiAfk.module, "jump"), new SettingHandle(antiAfk.module, "sneak"),
				new SettingHandle(antiAfk.module, "strafe"), new SettingHandle(antiAfk.module, "spin")
			};
			checkConflicts();

			// Flight 的 General 和 Anti Kick 都有名为 mode 的设置，必须按字段取，不能按名字搜索。
			SettingHandle mode = new SettingHandle(flight.module, "mode");
			flightSpeed = new SettingHandle(flight.module, "speed");
			SettingHandle vertical = new SettingHandle(flight.module, "verticalSpeedMatch");
			SettingHandle noSneak = new SettingHandle(flight.module, "noSneak");
			leasedSettings = new SettingHandle[] { mode, flightSpeed, vertical, noSneak };
			Object velocity = enumValue(mode.original, "Velocity");
			if (!(flightSpeed.original instanceof Double)
				|| !(vertical.original instanceof Boolean) || !(noSneak.original instanceof Boolean)) {
				throw new IllegalStateException("Meteor Flight 设置类型不兼容，区域飞行未启动");
			}

			mode.write(velocity);
			originallyActive = flight.active();
			writeSpeed(0.0); // 先落盘原速，再悬停；异常退出后仍可恢复。
			vertical.write(false);
			noSneak.write(true);
			if (!flight.active()) {
				enabledByUs = true; // toggle 回调可能先切状态再抛错，回滚仍须关掉本次启动的 Flight。
				flight.toggle();
				if (!flight.active()) throw new IllegalStateException("Meteor Flight 未能启动");
			}
			acquired = true;
			return null;
		} catch (Exception | LinkageError failure) {
			if (acquired) closeKeepingFlight();
			else close();
			return failure instanceof IllegalStateException && failure.getMessage() != null
				? failure.getMessage() : "无法接管 Meteor Flight，区域飞行已停止并尝试恢复原设置";
		}
	}

	/** 本拍飞速；外部修改或写入失败必须让调用方停止本次区域动作。 */
	public void speed(double value) {
		try {
			if (!acquired) throw new IllegalStateException("区域飞行会话未启动");
			if (!Double.isFinite(value) || value < 0.0) throw new IllegalStateException("区域飞行速度无效");
			if (!flight.active() && !grounded) throw new IllegalStateException("Meteor Flight 已关闭，区域飞行已停止");
			checkConflicts();
			for (SettingHandle setting : leasedSettings) setting.checkOwned();
			writeSpeed(value);
		} catch (Exception | LinkageError failure) {
			if (acquired) closeKeepingFlight();
			else close();
			throw new IllegalStateException("区域飞行设置已变化或无法写入，已停止并尝试恢复原设置", failure);
		}
	}

	/** Printing may need ordinary sneak to place against containers; navigation uses non-sneaking descent. */
	public void allowPlacementSneak(boolean allow) {
		if (!acquired) return;
		try { leasedSettings[3].write(!allow); }
		catch (ReflectiveOperationException e) { throw new IllegalStateException("无法切换放置潜行状态", e); }
	}

	/** 暂停时悬停；尚未接管或已经结束的会话不重新启飞。 */
	public void hover() {
		if (acquired) { fly(); speed(0.0); }
	}

	/** Normal mining uses gravity; only this deliberate off state is accepted by acquire(). */
	void digOnFoot() {
		if (!acquired) return;
		try {
			if (flight.active()) flight.toggle();
			grounded = true;
		} catch (ReflectiveOperationException e) { throw new IllegalStateException("无法关闭挖掘飞行", e); }
	}
	void fly() {
		if (!acquired || !grounded) return;
		try {
			if (!flight.active()) { flight.toggle(); enabledByUs |= !originallyActive; }
			grounded = false;
		} catch (ReflectiveOperationException e) { throw new IllegalStateException("无法启动返顶飞行", e); }
	}

	/** 只关闭自己启动的 Flight；用户后来改过的单项设置不覆盖。可重复调用。 */
	@Override
	public void close() {
		release(false);
	}

	/** 空中结束时恢复设置但不关飞行；返回是否保留了本会话启动的 Flight。 */
	public boolean closeKeepingFlight() {
		return release(true);
	}

	private boolean release(boolean keepFlying) {
		if (acquired && grounded && (keepFlying || originallyActive)) {
			try { fly(); } catch (IllegalStateException ignored) {}
		}
		boolean keptOwnFlight = false;
		if (flight != null && enabledByUs) {
			try {
				if (flight.active()) {
					if (keepFlying) keptOwnFlight = true;
					else flight.toggle();
				}
			} catch (Exception | LinkageError ignored) {
				// 一个模块回调失败也不能阻止其它设置恢复。
			}
		}
		if (leasedSettings != null) {
			for (int i = leasedSettings.length - 1; i >= 0; i--) leasedSettings[i].restore();
		}
		if (speedBackup != null && flightSpeed != null) {
			try {
				Object current = flightSpeed.read();
				// Keep the receipt after a normal restore: Meteor may already have saved the temporary value.
				// Only a manual override invalidates ownership of the persisted value.
				if (!Objects.equals(current, flightSpeed.original) && !Objects.equals(current, flightSpeed.lastWritten)) speedBackup.clear();
			} catch (Exception ignored) {}
		}
		if (leasedSettings != null) preparedPath = null;
		flight = null;
		antiAfk = null;
		scaffold = null;
		antiAfkActions = null;
		leasedSettings = null;
		flightSpeed = null;
		enabledByUs = false;
		acquired = false;
		grounded = originallyActive = false;
		return keptOwnFlight;
	}

	private Object requireModule(String className, String message) throws Exception {
		Object module = lookup.find(className);
		if (module == null) throw new IllegalStateException(message);
		return module;
	}

	private void checkConflicts() throws Exception {
		if (scaffold.active()) throw new IllegalStateException("请先关闭 Meteor Scaffold，避免区域挖时自动垫方块");
		if (!antiAfk.active()) return;
		for (SettingHandle action : antiAfkActions) {
			Object value = action.read();
			if (!(value instanceof Boolean)) throw new IllegalStateException("无法检查 Meteor AntiAFK 动作设置");
			if (Boolean.TRUE.equals(value)) {
				throw new IllegalStateException("请先关闭 Meteor AntiAFK 的跳跃、潜行、横移和旋转，避免区域飞行输入冲突");
			}
		}
	}

	private static Object findMeteorModule(String className) throws Exception {
		Class<?> modulesClass;
		try {
			modulesClass = Class.forName(MODULES);
		} catch (ClassNotFoundException missingMeteor) {
			return null;
		}
		Object modules = modulesClass.getMethod("get").invoke(null);
		if (modules == null) return null;
		return modulesClass.getMethod("get", Class.class).invoke(modules, Class.forName(className));
	}

	private static Object enumValue(Object original, String name) {
		if (original instanceof Enum<?> enumeration) {
			for (Object value : enumeration.getDeclaringClass().getEnumConstants()) {
				if (((Enum<?>) value).name().equals(name)) return value;
			}
		}
		throw new IllegalStateException("Meteor Flight 不支持 Velocity 模式");
	}

	private static Field field(Class<?> type, String name) throws NoSuchFieldException {
		for (Class<?> current = type; current != null; current = current.getSuperclass()) {
			try {
				Field result = current.getDeclaredField(name);
				result.setAccessible(true);
				return result;
			} catch (NoSuchFieldException ignored) {
			}
		}
		throw new NoSuchFieldException(name);
	}

	@FunctionalInterface
	interface ModuleLookup {
		Object find(String className) throws Exception;
	}

	private static final class ModuleHandle {
		final Object module;
		final Method isActive;
		final Method toggle;

		ModuleHandle(Object module) throws ReflectiveOperationException {
			this.module = module;
			isActive = module.getClass().getMethod("isActive");
			toggle = module.getClass().getMethod("toggle");
		}

		boolean active() throws ReflectiveOperationException {
			Object value = isActive.invoke(module);
			if (!(value instanceof Boolean)) throw new IllegalStateException("无法读取 Meteor 模块开关状态");
			return (Boolean) value;
		}

		void toggle() throws ReflectiveOperationException {
			toggle.invoke(module);
		}
	}

	private static final class SettingHandle {
		final String name;
		final Object setting;
		final Method getter;
		final Method setter;
		final Object original;
		Object lastWritten;
		boolean written;

		SettingHandle(Object module, String name) throws ReflectiveOperationException {
			this.name = name;
			setting = field(module.getClass(), name).get(module);
			if (setting == null) throw new IllegalStateException("Meteor 设置缺失：" + name);
			getter = setting.getClass().getMethod("get");
			setter = setting.getClass().getMethod("set", Object.class);
			original = read();
			lastWritten = original;
		}

		Object read() throws ReflectiveOperationException {
			return getter.invoke(setting);
		}

		void checkOwned() throws ReflectiveOperationException {
			if (!Objects.equals(read(), lastWritten)) {
				throw new IllegalStateException("Meteor Flight 设置已由外部修改：" + name + "，区域飞行已停止");
			}
		}

		void write(Object value) throws ReflectiveOperationException {
			checkOwned();
			if (Objects.equals(lastWritten, value)) return;
			try {
				Object result = setter.invoke(setting, value);
				if (Boolean.FALSE.equals(result) || !Objects.equals(read(), value)) {
					throw new IllegalStateException("Meteor Flight 拒绝设置：" + name);
				}
			} finally {
				// Setting.set 先保存 value 再跑回调；回调抛错也要记住已写值，保证 acquire 能回滚。
				if (Objects.equals(read(), value)) {
					lastWritten = value;
					written = true;
				}
			}
		}

		void restore() {
			try {
				if (written && Objects.equals(read(), lastWritten)) setter.invoke(setting, original);
			} catch (Exception | LinkageError ignored) {
				// 按项尽力恢复；不能覆盖用户已经改过的值，也不能挡住其它项恢复。
			}
		}
	}
}
