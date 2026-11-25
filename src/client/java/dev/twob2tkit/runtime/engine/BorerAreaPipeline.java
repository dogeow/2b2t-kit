package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import java.util.*;
import java.util.function.Function;

/** Track independent clicks until each block is confirmed. */
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
	private final int limit;
	BorerAreaPipeline() { this(LIMIT); }
	BorerAreaPipeline(int limit) { this.limit = limit; }
	boolean canClick(long tick) { return pending.size() < limit && (lastClick == Long.MIN_VALUE || tick - lastClick >= CLICK_INTERVAL); }
	void submitted(BlockPos p, long tick) {
		if (!canClick(tick) || contains(p)) throw new IllegalStateException("区域挖待确认队列已满或方块重复");
		pending.put(p.immutable(), new Pending(tick)); lastClick = tick;
	}
	/** A single ore-tunnel slice may submit its other, vertically adjacent face in this tick. */
	void submitTunnelClick(BlockPos pos, long tick) {
		if (pending.size()==1 && tick==lastClick) {
			BlockPos first=pending.keySet().iterator().next();
			if (first.above().equals(pos) || first.below().equals(pos)) {
				pending.put(pos.immutable(),new Pending(tick));
				return;
			}
		}
		submitted(pos,tick);
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
	void discardCorrected(BlockPos pos) { pending.remove(pos); }
	void clear() { pending.clear(); lastClick = Long.MIN_VALUE; }
}
