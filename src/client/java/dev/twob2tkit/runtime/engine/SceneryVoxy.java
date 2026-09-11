package dev.twob2tkit.runtime.engine;

import net.minecraft.world.level.Level;
import net.minecraft.world.level.chunk.LevelChunk;
import java.lang.reflect.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Optional adapter verified against Voxy 0.2.18-beta / MC 26.1.2; no replacement storage or forced chunk loads. */
final class SceneryVoxy implements SceneryCache {
	private Object instance, ingest, saving, identifier;
	private Method submit;
	@Override public String name() { return "Voxy"; }
	@Override public String connect(Level level) {
		try {
			instance = Class.forName("me.cortex.voxy.commonImpl.VoxyCommon").getMethod("getInstance").invoke(null);
			if (instance == null) throw new IllegalStateException("Voxy 未通过系统初始化；Mac 当前图形环境不兼容时，请安装并启用 Bobby");
			Class<?> id = Class.forName("me.cortex.voxy.commonImpl.WorldIdentifier");
			identifier = id.getMethod("of", Level.class).invoke(null, level);
			ingest = instance.getClass().getMethod("getIngestService").invoke(instance);
			saving = field(instance, "savingService");
			submit = ingest.getClass().getMethod("tryIngestChunk", id, LevelChunk.class);
			check(); idle(); // Check all required compatibility before borrowing flight.
			return instance.getClass().getMethod("getStorageBasePath").invoke(instance) + "|" + id.getMethod("getWorldId").invoke(identifier);
		} catch (ReflectiveOperationException | LinkageError e) { throw new IllegalStateException("需要兼容的 Voxy 并开启地形记录；当前接口无法读取", e); }
	}
	@Override public void check() {
		try {
			if (!(Boolean)instance.getClass().getMethod("isRunning").invoke(instance)
				|| !(Boolean)instance.getClass().getMethod("isIngestEnabled", identifier.getClass()).invoke(instance, identifier))
				throw new IllegalStateException("Voxy 地形记录已关闭，已暂停预加载");
		} catch (ReflectiveOperationException e) { throw new IllegalStateException("无法读取 Voxy 地形记录状态", e); }
	}
	@Override public boolean accept(LevelChunk chunk) {
		try { return (Boolean)submit.invoke(null, identifier, chunk); }
		catch (ReflectiveOperationException e) { throw new IllegalStateException("Voxy 拒绝接收区块", e); }
	}
	@Override public boolean idle() { return idleService(ingest) && idleService(saving); }
	@Override public int queued() {
		try { return ((Number)ingest.getClass().getMethod("getTaskCount").invoke(ingest)).intValue(); }
		catch (ReflectiveOperationException e) { throw new IllegalStateException("无法读取 Voxy 队列", e); }
	}
	static boolean idleService(Object owner) {
		try {
			Object service = field(owner, "service");
			if (!(Boolean)service.getClass().getMethod("isLive").invoke(service)) throw new IllegalStateException("Voxy 后台服务已停止");
			// A zero queued count alone excludes jobs already executing. Verify those too.
			return ((Number)service.getClass().getMethod("numJobs").invoke(service)).intValue() == 0
				&& ((AtomicInteger)field(field(service, "executor"), "currentRunning")).get() == 0;
		} catch (ReflectiveOperationException e) { throw new IllegalStateException("无法核对 Voxy 后台工作状态", e); }
	}
	private static Object field(Object value, String name) throws ReflectiveOperationException {
		for (Class<?> c = value.getClass(); c != null; c = c.getSuperclass()) try {
			Field field = c.getDeclaredField(name); field.setAccessible(true); return field.get(value);
		} catch (NoSuchFieldException ignored) {}
		throw new NoSuchFieldException(name);
	}
}
