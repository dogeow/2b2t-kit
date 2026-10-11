package dev.twob2tkit.runtime.engine;

/** Wait through food-to-food gaps. A stuck use animation alone is not nutrition progress. */
final class BorerMealPolicy {
	enum Action { WORK, PAUSE, RESUME, BLOCKED }
	private boolean paused;
	private int quietTicks, idleTicks, food = -1;
	private float health = -1;
	boolean paused() { return paused; }
	static boolean guardPause(boolean requested,boolean eating,boolean usingFood,boolean manualFood,
		boolean creeperEmergency,boolean immediateThreat,float health,float maxHealth) {
		if(manualFood||usingFood||eating)return true;
		boolean injured=Float.isFinite(health)&&Float.isFinite(maxHealth)&&health>0&&health<maxHealth;
		return requested&&!creeperEmergency&&(!immediateThreat||injured);
	}
	void reset() { paused = false; quietTicks = idleTicks = 0; food = -1; health = -1; }
	Action tick(boolean requested, boolean eating, boolean usingFood, int foodLevel, float hp) {
		boolean wanted = requested || eating || usingFood;
		if (!paused && !wanted) return Action.WORK;
		if (!paused) { paused = true; food = foodLevel; health = hp; idleTicks = 0; }
		if (foodLevel > food || hp > health) idleTicks = 0;
		else idleTicks++;
		food = foodLevel; health = hp;
		if (wanted) quietTicks = 0;
		else if (++quietTicks >= 2) { reset(); return Action.RESUME; }
		// Covers no free hotbar slot, rejected use and a stuck animation without fighting Meteor.
		return idleTicks >= 200 ? Action.BLOCKED : Action.PAUSE;
	}
}
