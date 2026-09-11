package dev.twob2tkit.runtime.engine;

final class BorerDefensePolicy {
	record Candidate(int id, int priority, double distance, boolean recentAttacker) {
		Candidate(int id, int priority, double distance) { this(id, priority, distance, false); }
	}
	static int choose(java.util.List<Candidate> candidates, int currentId) {
		Candidate best = candidates.stream().min(java.util.Comparator.comparingInt(Candidate::priority)
			.thenComparingInt(c -> c.recentAttacker ? 0 : 1)
			.thenComparingDouble(Candidate::distance).thenComparingInt(Candidate::id)).orElse(null);
		if (best == null) return -1;
		Candidate current = candidates.stream().filter(c -> c.id == currentId).findFirst().orElse(null);
		if (current != null && current.priority == best.priority && current.recentAttacker == best.recentAttacker && current.distance <= best.distance + 4) return current.id;
		return best.id;
	}
	static int priority(boolean creeper, boolean ranged) { return creeper ? 0 : ranged ? 1 : 2; }
	/** Seeing an idle mob is not aggression. Only observable threats interrupt work. */
	static boolean engaged(boolean visible, boolean recentAttacker, boolean targetingOther,
		boolean targetingPlayer, boolean approaching, boolean attackingPose, boolean imminentBlast,
		double distance, double verticalGap) {
		if (recentAttacker || imminentBlast) return true;
		if (!visible || targetingOther) return false;
		return attackingPose || targetingPlayer && distance <= 10
			|| approaching && distance <= 10 && Math.abs(verticalGap) <= 3;
	}
	static boolean approaching(double moveX, double moveZ, double towardX, double towardZ) {
		double movement = Math.hypot(moveX, moveZ), distance = Math.hypot(towardX, towardZ);
		if (movement < .25 || distance < .01) return false;
		double closing = (moveX * towardX + moveZ * towardZ) / distance;
		return closing >= .25 && closing / movement >= .8;
	}
	static boolean blastThreat(boolean swelling, boolean powered, double distance) { return swelling && distance <= (powered ? 12 : 6); }
	static boolean eligible(boolean hostile, boolean alive, boolean visible, int priority, double distance) {
		return hostile && alive && visible && distance <= (priority == 0 ? 24 : priority == 1 ? 40 : 10);
	}
	static boolean releaseArrow(int chargeTicks, boolean sameTarget, boolean clearShot) {
		return chargeTicks >= 20 && sameTarget && clearShot;
	}
	private BorerDefensePolicy() {}
}
