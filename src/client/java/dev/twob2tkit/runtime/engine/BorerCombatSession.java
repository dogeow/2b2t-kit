package dev.twob2tkit.runtime.engine;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Aggression starts a fight; only observed death or an explicit cancellation ends it. */
final class BorerCombatSession<T> {
	static final int NO_PROGRESS_TICKS = 600;
	private static final class Entry<T> {
		T entity;
		float lowestHealth;
		long progressAt;
		boolean attackable;
		int repositionAttempts;
		Entry(T entity, float health, long now) {
			this.entity = entity; lowestHealth = health; progressAt = now;
		}
	}
	private final Map<UUID, Entry<T>> unresolved = new LinkedHashMap<>();
	private long now, pausedAt = Long.MIN_VALUE;
	void beginTick(long tick) {
		if (pausedAt != Long.MIN_VALUE) {
			long duration = Math.max(0, tick - pausedAt);
			unresolved.values().forEach(e -> e.progressAt += duration);
			pausedAt = Long.MIN_VALUE;
		}
		now = tick;
		// An absent observation must never retain permission to shoot a stale entity.
		unresolved.values().forEach(e -> e.attackable = false);
	}
	boolean observe(UUID id, T entity, boolean engaged, boolean confirmedDead, boolean attackable, float health) {
		if (confirmedDead) return unresolved.remove(id) != null;
		Entry<T> entry = unresolved.get(id);
		if (entry == null) {
			if (!engaged) return false;
			entry = new Entry<>(entity, health, now);
			unresolved.put(id, entry);
		}
		entry.entity = entity;
		entry.attackable = attackable;
		// A shot, aim, movement or healing is not proof that an attack succeeded.
		if (health < entry.lowestHealth) {
			entry.lowestHealth = health;
			entry.progressAt = now;
		}
		return false;
	}
	boolean pending() { return !unresolved.isEmpty(); }
	boolean contains(UUID id) { return unresolved.containsKey(id); }
	List<T> targets() { return unresolved.values().stream().map(e -> e.entity).toList(); }
	boolean canAttack(UUID id) {
		var e = unresolved.get(id);
		return pausedAt == Long.MIN_VALUE && e != null && e.attackable && now - e.progressAt < NO_PROGRESS_TICKS;
	}
	boolean timedOut() { return unresolved.values().stream().anyMatch(e -> now - e.progressAt >= NO_PROGRESS_TICKS); }
	/** A verified different firing position allows a bounded retry, never a completion claim. */
	boolean repositioned(UUID id) {
		var e=unresolved.get(id);
		if(e==null||!e.attackable||e.repositionAttempts>=2)return false;
		e.repositionAttempts++;e.progressAt=now;return true;
	}
	void pause(long tick) { if (pausedAt == Long.MIN_VALUE) pausedAt = tick; }
	void clear() { unresolved.clear(); pausedAt = Long.MIN_VALUE; }
}
