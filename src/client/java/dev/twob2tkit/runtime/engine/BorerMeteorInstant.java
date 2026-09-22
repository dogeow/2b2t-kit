package dev.twob2tkit.runtime.engine;

import net.minecraft.world.level.block.Block;

/** Read the installed Meteor module's public instamine/filter contract; never change its settings. */
final class BorerMeteorInstant {
	interface Lookup { Object find(String name) throws ReflectiveOperationException; }
	private final Lookup lookup;
	BorerMeteorInstant() { this(BorerMeteorInstant::find); }
	BorerMeteorInstant(Lookup lookup) { this.lookup = lookup; }
	private Object module;
	private java.lang.reflect.Method instamine, filter;
	private Object repeat;
	private java.lang.reflect.Field repeatPosition, repeatDirection, repeatPick;
	private java.lang.reflect.Method repeatSend, repeatActive;
	boolean allows(Block block, float progress) {
		if (progress >= 1) return true;
		if (!(progress > .5f)) return false;
		try {
			if (module == null) {
				module = lookup.find("SpeedMine");
				if (module == null) return false;
				Class<?> type = module.getClass();
				instamine = type.getMethod("instamine"); filter = type.getMethod("filter", Block.class);
			}
			return module != null && Boolean.TRUE.equals(instamine.invoke(module)) && Boolean.TRUE.equals(filter.invoke(module, block));
		} catch (ReflectiveOperationException | LinkageError unavailable) { return false; }
	}
	private static Object find(String name) throws ReflectiveOperationException {
		Class<?> registry = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
		Class<?> type = Class.forName("meteordevelopment.meteorclient.systems.modules.player." + name);
		return registry.getMethod("get",Class.class).invoke(registry.getMethod("get").invoke(null),type);
	}
	boolean repeatAllows(boolean pickaxe) {
		try {
			if (repeat == null) {
				repeat = lookup.find("InstantRebreak"); if (repeat == null) return false;
				var type = repeat.getClass();
				repeatPosition = type.getField("blockPos");
				repeatDirection = type.getDeclaredField("direction"); repeatDirection.setAccessible(true);
				repeatPick = type.getDeclaredField("pick"); repeatPick.setAccessible(true);
				repeatSend = type.getMethod("sendPacket"); repeatActive = type.getMethod("isActive");
			}
			var setting = repeatPick.get(repeat);
			return pickaxe || !Boolean.TRUE.equals(setting.getClass().getMethod("get").invoke(setting));
		} catch (ReflectiveOperationException | LinkageError unsupported) { repeat = null; return false; }
	}
	/** Delegate exactly one verified click to Meteor while its background loop is paused by our lease.
	 * Restore its original target fields immediately; pause/food/combat/stop cannot leave it mining. */
	void finishRepeat(net.minecraft.core.BlockPos pos, net.minecraft.core.Direction direction) {
		try {
			if (repeat == null) throw new IllegalStateException("瞬时破坏尚未接入");
			if (Boolean.TRUE.equals(repeatActive.invoke(repeat))) {
				var target = (net.minecraft.core.BlockPos.MutableBlockPos) repeatPosition.get(repeat);
				if (target.equals(pos)) target.set(0,Integer.MIN_VALUE,0); // Cancel only our just-started target.
				throw new IllegalStateException("瞬时破坏存在另一个运行循环，请暂停区域挖后再开始");
			}
			var mutable = (net.minecraft.core.BlockPos.MutableBlockPos) repeatPosition.get(repeat);
			var previous = mutable.immutable(); var previousDirection = repeatDirection.get(repeat);
			try { mutable.set(pos); repeatDirection.set(repeat,direction); repeatSend.invoke(repeat); }
			finally { mutable.set(previous); repeatDirection.set(repeat,previousDirection); }
		} catch (ReflectiveOperationException e) { throw new IllegalStateException("无法调用 Meteor 瞬时破坏，未继续点下一格",e); }
	}
}
