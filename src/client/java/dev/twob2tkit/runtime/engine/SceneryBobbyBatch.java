package dev.twob2tkit.runtime.engine;

import java.util.*;
import java.util.concurrent.CompletableFuture;

/** No render-thread joins: wait for native serialization, disk synchronization, then verify each saved tag. */
final class SceneryBobbyBatch {
	record Chunk(int x, int z) {}
	record Saved(int x, int z, long age, boolean complete) {}
	interface Disk {
		CompletableFuture<Void> afterSaves();
		CompletableFuture<Void> flush();
		CompletableFuture<Optional<Saved>> read(Chunk chunk);
	}
	private final Disk disk;
	private final Map<Chunk, Long> pending = new LinkedHashMap<>();
	private CompletableFuture<Void> verification;
	private long lastAdded;
	SceneryBobbyBatch(Disk disk) { this.disk = disk; }
	boolean canAccept() { return verification == null && pending.size() < 32; }
	void accepted(Chunk pos, long requestTime) {
		if (!canAccept()) throw new IllegalStateException("Bobby 上批缓存尚未确认");
		pending.put(pos, requestTime); lastAdded = requestTime;
	}
	int queued() { return verification == null ? pending.size() : 257; }
	boolean idle(long now) {
		if (pending.isEmpty()) return true;
		if (verification == null && (pending.size() >= 32 || now - lastAdded >= 500)) {
			Map<Chunk, Long> expected = Map.copyOf(pending);
			verification = disk.afterSaves().thenCompose(ignored -> disk.flush()).thenCompose(ignored -> {
				List<CompletableFuture<Void>> reads = new ArrayList<>();
				for (var entry : expected.entrySet()) reads.add(disk.read(entry.getKey()).thenAccept(saved -> {
					if (!matches(entry.getKey(), entry.getValue(), saved))
						throw new IllegalStateException("Bobby 缓存读回复核失败：" + entry.getKey() + "，未把该批计为完成");
				}));
				return CompletableFuture.allOf(reads.toArray(CompletableFuture[]::new));
			});
		}
		if (verification == null || !verification.isDone()) return false;
		try { verification.join(); return true; } // Already completed; never blocks the game thread.
		catch (RuntimeException error) { throw new IllegalStateException("Bobby 写入或读回复核失败，已保留未完成进度", error); }
	}
	void committed() {
		if (verification == null || !verification.isDone() || verification.isCompletedExceptionally())
			throw new IllegalStateException("不能提交未确认的 Bobby 缓存");
		pending.clear(); verification = null;
	}
	static boolean matches(Chunk pos, long requestTime, Optional<Saved> actual) {
		return actual.isPresent() && actual.get().complete && actual.get().x == pos.x && actual.get().z == pos.z && actual.get().age >= requestTime;
	}
}
