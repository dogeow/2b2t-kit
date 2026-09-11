package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import static org.junit.jupiter.api.Assertions.*;

class SceneryBobbyBatchTest {
	static final class Disk implements SceneryBobbyBatch.Disk {
		final CompletableFuture<Void> serialized = new CompletableFuture<>(), flushed = new CompletableFuture<>();
		final Map<SceneryBobbyBatch.Chunk, CompletableFuture<Optional<SceneryBobbyBatch.Saved>>> reads = new HashMap<>();
		final List<String> order = new ArrayList<>();
		public CompletableFuture<Void> afterSaves() { order.add("after-native-saves"); return serialized; }
		public CompletableFuture<Void> flush() { order.add("flush"); return flushed; }
		public CompletableFuture<Optional<SceneryBobbyBatch.Saved>> read(SceneryBobbyBatch.Chunk c) { order.add("read"); return reads.computeIfAbsent(c, _ -> new CompletableFuture<>()); }
	}
	@Test void neverBlocksOrCommitsBeforeNativeSavesFlushAndReadbackAllFinish() {
		var disk = new Disk(); var batch = new SceneryBobbyBatch(disk); var pos = new SceneryBobbyBatch.Chunk(2, -3);
		batch.accepted(pos, 100);
		assertFalse(batch.idle(599)); assertTrue(disk.order.isEmpty());
		assertFalse(batch.idle(600)); assertEquals(List.of("after-native-saves"), disk.order);
		assertFalse(batch.canAccept()); assertEquals(257, batch.queued());
		assertThrows(IllegalStateException.class, batch::committed);
		disk.serialized.complete(null); assertEquals(List.of("after-native-saves", "flush"), disk.order);
		assertFalse(batch.idle(700)); disk.flushed.complete(null); assertEquals(3, disk.order.size());
		assertFalse(batch.idle(800));
		disk.reads.get(pos).complete(Optional.of(new SceneryBobbyBatch.Saved(2, -3, 120, true)));
		assertTrue(batch.idle(801)); assertFalse(batch.canAccept(), "Do not mix a new batch into the quiet confirmation interval");
		batch.committed(); assertTrue(batch.canAccept()); assertEquals(0, batch.queued()); assertTrue(batch.idle(802));
	}
	@Test void missingStaleWrongCoordinatesOrIncompleteTagsCannotConfirmCoverage() {
		var pos = new SceneryBobbyBatch.Chunk(2, -3);
		List<Optional<SceneryBobbyBatch.Saved>> invalid = List.of(Optional.empty(),
			Optional.of(new SceneryBobbyBatch.Saved(2, -3, 99, true)), Optional.of(new SceneryBobbyBatch.Saved(3, -3, 120, true)),
			Optional.of(new SceneryBobbyBatch.Saved(2, 3, 120, true)), Optional.of(new SceneryBobbyBatch.Saved(2, -3, 120, false)));
		for (var saved : invalid) {
			var disk = new Disk(); var batch = new SceneryBobbyBatch(disk); batch.accepted(pos, 100); batch.idle(700);
			disk.serialized.complete(null); disk.flushed.complete(null); disk.reads.get(pos).complete(saved);
			assertThrows(IllegalStateException.class, () -> batch.idle(800)); assertThrows(IllegalStateException.class, batch::committed);
		}
	}
	@Test void aFailedDiskFlushStopsTheBatchAndDoesNotReadAnOldCacheEntry() {
		var disk = new Disk(); var batch = new SceneryBobbyBatch(disk);
		batch.accepted(new SceneryBobbyBatch.Chunk(0, 0), 100); batch.idle(700);
		disk.serialized.complete(null); disk.flushed.completeExceptionally(new java.io.IOException("disk full"));
		assertThrows(IllegalStateException.class, () -> batch.idle(800)); assertTrue(disk.reads.isEmpty());
	}
	@Test void waitsForEveryChunkInABatchAndBoundsTheNativeQueue() {
		var disk = new Disk(); var batch = new SceneryBobbyBatch(disk);
		for (int i = 0; i < 32; i++) batch.accepted(new SceneryBobbyBatch.Chunk(i, 0), 100);
		assertFalse(batch.canAccept()); assertFalse(batch.idle(100));
		disk.serialized.complete(null); disk.flushed.complete(null);
		for (int i = 0; i < 31; i++) disk.reads.get(new SceneryBobbyBatch.Chunk(i, 0)).complete(Optional.of(new SceneryBobbyBatch.Saved(i, 0, 150, true)));
		assertFalse(batch.idle(200)); assertThrows(IllegalStateException.class, batch::committed);
		disk.reads.get(new SceneryBobbyBatch.Chunk(31, 0)).complete(Optional.of(new SceneryBobbyBatch.Saved(31, 0, 150, true)));
		assertTrue(batch.idle(200)); batch.committed(); assertEquals(0, batch.queued());
	}
	@Test void nativeSerializationFailureDoesNotReachDiskOrBecomeSuccess() {
		var disk = new Disk(); var batch = new SceneryBobbyBatch(disk);
		batch.accepted(new SceneryBobbyBatch.Chunk(0, 0), 100); batch.idle(700);
		disk.serialized.completeExceptionally(new IllegalStateException("serializer unavailable"));
		assertThrows(IllegalStateException.class, () -> batch.idle(800)); assertEquals(List.of("after-native-saves"), disk.order);
	}
}
