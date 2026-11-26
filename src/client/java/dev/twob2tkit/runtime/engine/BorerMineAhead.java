package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import java.util.*;
import java.util.function.Predicate;

/**
 * Keep digging a proven route while earlier breaks await the server, as a player holding attack does.
 * Vanilla owns the prediction: a refused break turns solid again and is simply dug once more.
 */
final class BorerMineAhead {
	static final int LIMIT = 4, TIMEOUT = 100, MAX_REFUSALS = 3;
	private final Map<BlockPos,Integer> since = new HashMap<>();
	private final Map<BlockPos,Integer> refusals = new HashMap<>();

	/** Returns the blocks the server has just restored. Call once per tick. */
	List<BlockPos> observe(Set<BlockPos> pending, Predicate<BlockPos> air, int tick) {
		var refused = new ArrayList<BlockPos>();
		for (var it = since.keySet().iterator(); it.hasNext();) {
			BlockPos pos = it.next();
			if (pending.contains(pos)) continue;
			it.remove();
			if (air.test(pos)) refusals.remove(pos);
			else { refusals.merge(pos,1,Integer::sum); refused.add(pos); }
		}
		for (var pos : pending) since.putIfAbsent(pos,tick);
		return refused;
	}
	boolean expired(int tick) { return since.values().stream().anyMatch(sent -> tick-sent >= TIMEOUT); }
	BlockPos exhausted() {
		return refusals.entrySet().stream().filter(e -> e.getValue() >= MAX_REFUSALS).map(Map.Entry::getKey).findFirst().orElse(null);
	}
	void clear() { since.clear(); refusals.clear(); }
	/** Only this route's own breaks may stay unconfirmed, and only a few at a time. */
	static boolean allowed(Set<BlockPos> pending, Set<BlockPos> route) {
		return pending.size() < LIMIT && route.containsAll(pending);
	}
}
