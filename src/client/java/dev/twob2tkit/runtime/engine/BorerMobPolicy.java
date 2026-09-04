package dev.twob2tkit.runtime.engine;

/**
 * 遇怪停挖。只改这一处。
 * <p>
 * 「遇怪躲开」开着时，配置半径里有会打人的敌对就停镐，切剑举盾，近战交给 Meteor KillAura。
 * 不要等贴到 2.8 格才停，也不要因为钻石/下界合金套把骷髅僵尸当成没事。
 * 通道拐弯仍用装甲过滤，避免满地蜘蛛就改道。
 */
public final class BorerMobPolicy {
	public static final int DEFAULT_RADIUS = 8;
	public static final int MIN_RADIUS = 2;
	public static final int MAX_RADIUS = 24;

	private BorerMobPolicy() {
	}

	/** 把配置半径夹到允许区间。 */
	public static double pauseRadius(int configured) {
		if (configured < MIN_RADIUS) return MIN_RADIUS;
		if (configured > MAX_RADIUS) return MAX_RADIUS;
		return configured;
	}

	/** 开了遇怪躲开、半径里有敌对：停挖。 */
	public static boolean pauseMiningForNearby(boolean pauseOnMob, boolean hostileInRadius) {
		return pauseOnMob && hostileInRadius;
	}
}
