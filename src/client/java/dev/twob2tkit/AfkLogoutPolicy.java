package dev.twob2tkit;

/**
 * 钓鱼挂机何时下线。附近有骷髅/溺尸不够，被打中一次才走。
 * 种田/喂养不因此下线。
 * 来源：2026-08-22 「就算有骷髅，没有被攻击过一次也不要下线」。
 */
public final class AfkLogoutPolicy {
	private AfkLogoutPolicy() {
	}

	/** 走近不下线。骷髅站在旁边不算。 */
	public static boolean watchNearbyHostiles(boolean fishing) {
		return false;
	}

	/** 走近不下线，不管是不是近战溺尸。 */
	public static boolean nearbyHostileLogsOut(boolean fishing, boolean meleeDrowned) {
		return false;
	}

	/** 钓鱼时被打中一次就下线。 */
	public static boolean hitLogsOut(boolean fishing) {
		return fishing;
	}
}
