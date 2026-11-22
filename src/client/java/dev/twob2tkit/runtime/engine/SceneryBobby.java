package dev.twob2tkit.runtime.engine;

import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.chunk.storage.SimpleRegionStorage;
import java.lang.reflect.*;
import java.util.Optional;
import java.util.concurrent.*;

/** Native Bobby 5.2.13 adapter; never injects fake terrain, changes renderer settings or bypasses its serializer. */
final class SceneryBobby implements SceneryCache {
	private ClientLevel level;
	private Object bobby, manager, storage;
	private Class<?> extension, fakeChunk;
	private Method nativeSave;
	private SceneryBobbyBatch batch;
	private java.nio.file.Path directory;
	private final java.util.Map<ChunkPos,CompletableFuture<java.util.BitSet>> headers = new java.util.HashMap<>();
	@Override public String name() { return "Bobby"; }
	@Override public String connect(Level world) {
		try {
			if (!(world instanceof ClientLevel client)) throw new IllegalStateException("Bobby 需要客户端世界");
			level = client;
			bobby = Class.forName("de.johni0702.minecraft.bobby.Bobby").getMethod("getInstance").invoke(null);
			if (bobby == null || !(Boolean)bobby.getClass().getMethod("isEnabled").invoke(bobby))
				throw new IllegalStateException("请先启用 Bobby；单人世界还需设置其视距覆盖并重新进入世界");
			extension = Class.forName("de.johni0702.minecraft.bobby.ext.ClientChunkCacheExt");
			manager = extension.getMethod("bobby_getFakeChunkManager").invoke(level.getChunkSource());
			if (manager == null) throw new IllegalStateException("Bobby 世界缓存尚未就绪，请进入世界后重试");
			fakeChunk = Class.forName("de.johni0702.minecraft.bobby.FakeChunk");
			storage = currentStorage();
			if (!(storage instanceof SimpleRegionStorage region) || !Boolean.TRUE.equals(field(storage, "writeable")))
				throw new IllegalStateException("Bobby 当前缓存不可写，未开始飞行");
			Object config = bobby.getClass().getMethod("getConfig").invoke(bobby);
			if (((Number)config.getClass().getMethod("getDeleteUnusedRegionsAfterDays").invoke(config)).intValue() == 0)
				throw new IllegalStateException("Bobby 设置为每次退出清空缓存，请先关闭该清理选项再跑图");
			nativeSave = manager.getClass().getMethod("save", LevelChunk.class);
			ExecutorService executor = (ExecutorService)staticField(manager.getClass(), "saveExecutor");
			// Bobby's native save serializes on this single-thread queue before submitting region writes.
			batch = new SceneryBobbyBatch(new SceneryBobbyBatch.Disk() {
				public CompletableFuture<Void> afterSaves() {
					CompletableFuture<Void> barrier = new CompletableFuture<>();
					try { executor.execute(() -> barrier.complete(null)); } catch (RuntimeException e) { barrier.completeExceptionally(e); }
					return barrier;
				}
				public CompletableFuture<Void> flush() { return region.synchronize(true); }
				public CompletableFuture<Optional<SceneryBobbyBatch.Saved>> read(SceneryBobbyBatch.Chunk pos) {
					return region.read(new ChunkPos(pos.x(), pos.z())).thenApply(tag -> tag.map(SceneryBobby::saved));
				}
			});
			check();
			directory = java.nio.file.Path.of(field(storage, "directory").toString());
			return "bobby|" + directory;
		} catch (ReflectiveOperationException | LinkageError error) { throw new IllegalStateException("当前 Bobby 接口不兼容或缓存无法初始化", error); }
	}
	private Object currentStorage() throws ReflectiveOperationException {
		Object worlds = manager.getClass().getMethod("getWorlds").invoke(manager);
		return worlds == null ? manager.getClass().getMethod("getStorage").invoke(manager) : worlds.getClass().getMethod("getCurrentStorage").invoke(worlds);
	}
	@Override public void check() {
		try {
			if (!(Boolean)bobby.getClass().getMethod("isEnabled").invoke(bobby)) throw new IllegalStateException("Bobby 已关闭，已停止跑图");
			if (extension.getMethod("bobby_getFakeChunkManager").invoke(level.getChunkSource()) != manager || currentStorage() != storage)
				throw new IllegalStateException("Bobby 世界缓存已切换，已停止以免混用进度；请重新开始本世界任务");
		} catch (ReflectiveOperationException error) { throw new IllegalStateException("无法复核 Bobby 缓存状态", error); }
	}
	@Override public boolean supportsReuse() { return true; }

	@Override public CompletableFuture<Boolean> hasSaved(SceneryCoverage.Chunk pos) {
		var key=new ChunkPos(Math.floorDiv(pos.x(),32),Math.floorDiv(pos.z(),32));
		var header=headers.computeIfAbsent(key,k->CompletableFuture.supplyAsync(
			()->readHeader(directory.resolve("r."+k.x()+"."+k.z()+".mca"))));
		int slot=Math.floorMod(pos.x(),32)+32*Math.floorMod(pos.z(),32);
		return header.thenCompose(index->!index.get(slot) ? CompletableFuture.completedFuture(false)
			: ((SimpleRegionStorage) storage).read(new ChunkPos(pos.x(),pos.z()))
				.thenApply(tag->tag.map(SceneryBobby::saved).filter(s->s.complete() && s.x()==pos.x() && s.z()==pos.z()).isPresent()))
			.exceptionally(error->false);
	}

	static java.util.BitSet readHeader(java.nio.file.Path file) {
		var present=new java.util.BitSet(1024);
		try (var input=new java.io.DataInputStream(java.nio.file.Files.newInputStream(file))) {
			for (int slot=0;slot<1024;slot++) {
				int entry=input.readInt();
				if (entry>>>8>=2 && (entry&255)>0) present.set(slot);
			}
		} catch (java.io.IOException unreadable) { present.clear(); }
		return present;
	}

	@Override public boolean isReal(LevelChunk chunk) {
		return LoadedServerChunkEvidence.isServerChunk(level, chunk, fakeChunk);
	}
	@Override public boolean accept(LevelChunk chunk) {
		if (!isReal(chunk) || !batch.canAccept()) return false;
		try {
			long requested = System.currentTimeMillis();
			nativeSave.invoke(manager, chunk); // Its returned Supplier installs a fake chunk: intentionally NOT executed.
			batch.accepted(new SceneryBobbyBatch.Chunk(chunk.getPos().x(), chunk.getPos().z()), requested);
			return true;
		} catch (ReflectiveOperationException error) { throw new IllegalStateException("Bobby 拒绝保存区块", error); }
	}
	@Override public boolean idle() { return batch.idle(System.currentTimeMillis()); }
	@Override public int queued() { return batch.queued(); }
	@Override public void batchCommitted() { batch.committed(); }
	static SceneryBobbyBatch.Saved saved(CompoundTag tag) {
		return new SceneryBobbyBatch.Saved(tag.getIntOr("xPos", Integer.MIN_VALUE), tag.getIntOr("zPos", Integer.MIN_VALUE),
			tag.getLongOr("age", Long.MIN_VALUE), tag.getList("sections").isPresent() && tag.getBooleanOr("isLightOn", false)
				&& tag.getStringOr("Status", "").equals("full") && tag.getIntOr("DataVersion", 0) > 0);
	}
	private static Object staticField(Class<?> type, String name) throws ReflectiveOperationException {
		Field field = type.getDeclaredField(name); field.setAccessible(true); return field.get(null);
	}
	private static Object field(Object object, String name) throws ReflectiveOperationException {
		if (object == null) return null;
		for (Class<?> type = object.getClass(); type != null; type = type.getSuperclass()) try {
			Field field = type.getDeclaredField(name); field.setAccessible(true); return field.get(object);
		} catch (NoSuchFieldException ignored) {}
		throw new NoSuchFieldException(name);
	}
}
