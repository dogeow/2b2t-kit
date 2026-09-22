package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import java.util.*;
import java.util.function.Function;

/** Two independent clicks may be outstanding; movement never treats them as cleared. */
final class BorerAreaPipeline {
	static final int LIMIT = 2, CLICK_INTERVAL = 2, TIMEOUT = 100;
	record Observation(boolean air, boolean predictionPending) {}
	private static final class Pending {
		final long sentAt;
		int airSamples;
		long sampledAt = Long.MIN_VALUE;
		Pending(long tick) { sentAt = tick; }
	}
	private final Map<BlockPos, Pending> pending = new LinkedHashMap<>();
	private long lastClick = Long.MIN_VALUE;
	boolean active() { return !pending.isEmpty(); }
	boolean contains(BlockPos p) { return pending.containsKey(p); }
	int size() { return pending.size(); }
	List<BlockPos> positions() { return List.copyOf(pending.keySet()); }
	boolean canClick(long tick) { return pending.size() < LIMIT && (lastClick == Long.MIN_VALUE || tick - lastClick >= CLICK_INTERVAL); }
	void submitted(BlockPos p, long tick) {
		if (!canClick(tick) || contains(p)) throw new IllegalStateException("区域挖待确认队列已满或方块重复");
		pending.put(p.immutable(), new Pending(tick)); lastClick = tick;
	}
	List<BlockPos> update(long tick, Function<BlockPos, Observation> observations) {
		var confirmed = new ArrayList<BlockPos>();
		var it = pending.entrySet().iterator();
		while (it.hasNext()) {
			var e = it.next(); var state = e.getValue();
			if (state.sampledAt == tick) continue;
			state.sampledAt = tick;
			var observed = observations.apply(e.getKey());
			if (observed.air && !observed.predictionPending) state.airSamples++; else state.airSamples = 0;
			if (state.airSamples >= 2) { confirmed.add(e.getKey()); it.remove(); }
		}
		return confirmed;
	}
	BlockPos expired(long tick) {
		return pending.entrySet().stream().filter(e -> tick - e.getValue().sentAt >= TIMEOUT).map(Map.Entry::getKey).findFirst().orElse(null);
	}
	boolean blocksRay(Vec3 eye, Vec3 hit) {
		return blocksRay(eye,hit,null);
	}
	boolean blocksRay(Vec3 eye, Vec3 hit, BlockPos except) {
		return pending.keySet().stream().filter(p -> !p.equals(except)).anyMatch(p -> new AABB(p).inflate(.001).clip(eye,hit).isPresent());
	}
	void clear() { pending.clear(); lastClick = Long.MIN_VALUE; }
}
