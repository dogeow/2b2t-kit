package dev.twob2tkit.runtime.engine;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Aggression starts a fight; observed death, verified calm, or explicit cancellation ends it. */
final class BorerCombatSession<T> {
	static final int NO_PROGRESS_TICKS = 600;
	private static final class Entry<T> {
		T entity;
		float lowestHealth;
		long progressAt;
		long observedAt;
        long calmSince = Long.MIN_VALUE;
		boolean attackable;
		int repositionAttempts;
		boolean trialMeleeRetry;
		Entry(T entity, float health, long now) {
			this.entity = entity; lowestHealth = health; progressAt = observedAt = now;
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
		entry.observedAt = now;
		entry.attackable = attackable;
		// A shot, aim, movement or healing is not proof that an attack succeeded.
		if (health < entry.lowestHealth) {
			entry.lowestHealth = health;
			entry.progressAt = now;
		}
		return false;
	}
	boolean pending() { return !unresolved.isEmpty(); }
    /** Current neutral-state evidence releases aggression, never confirms a kill. */
    boolean releaseObservedCalm(UUID id, boolean current, boolean calm) {
        var entry=unresolved.get(id);
        if(entry==null)return false;
        if(!current||!calm||entry.observedAt!=now){entry.calmSince=Long.MIN_VALUE;return false;}
        entry.attackable=false;
        if(entry.calmSince==Long.MIN_VALUE||now<entry.calmSince)entry.calmSince=now;
        if(now-entry.calmSince<20)return false;
        unresolved.remove(id);return true;
    }
	boolean contains(UUID id) { return unresolved.containsKey(id); }
	List<T> targets() { return unresolved.values().stream().map(e -> e.entity).toList(); }
	boolean canAttack(UUID id) {
		var e = unresolved.get(id);
		return pausedAt == Long.MIN_VALUE && e != null && e.attackable && now - e.progressAt < NO_PROGRESS_TICKS;
	}
	boolean timedOut() { return unresolved.values().stream().anyMatch(e -> now - e.progressAt >= NO_PROGRESS_TICKS); }
	boolean needsReposition(UUID id) {
		var e=unresolved.get(id);
		return pausedAt==Long.MIN_VALUE&&e!=null&&e.observedAt==now&&e.lowestHealth>0
			&&(!e.attackable||now-e.progressAt>=NO_PROGRESS_TICKS)&&e.repositionAttempts<2;
	}
	/** A verified different firing position allows a bounded retry, never a completion claim. */
	boolean repositioned(UUID id) {
		var e=unresolved.get(id);
		if(e==null||!e.attackable||e.repositionAttempts>=2)return false;
		e.repositionAttempts++;e.progressAt=now;return true;
	}
	/** A newly available trial-only melee capability gets one budget retry; never erase the threat. */
	boolean retryTrialMelee(UUID id, boolean capabilityVerified) {
		var e = unresolved.get(id);
		if (!capabilityVerified || pausedAt != Long.MIN_VALUE || e == null || !e.attackable
				|| e.trialMeleeRetry || now - e.progressAt < NO_PROGRESS_TICKS) return false;
		e.trialMeleeRetry = true;
		e.progressAt = now;
		return true;
	}
	boolean canRetryTrialMelee(UUID id) {
		var e = unresolved.get(id);
		return pausedAt == Long.MIN_VALUE && e != null && e.attackable && !e.trialMeleeRetry
			&& now - e.progressAt >= NO_PROGRESS_TICKS;
	}
	void pause(long tick) { if (pausedAt == Long.MIN_VALUE) pausedAt = tick; }
	void clear() { unresolved.clear(); pausedAt = Long.MIN_VALUE; }
}
