package dev.twob2tkit.chopper;

/**
 * 挖树遇战。只改这一处。
 * <p>
 * 铁傀儡不是 {@code Enemy}；只在有实际交战证据时停砍，避免把和平傀儡当成敌人。
 */
public final class ChopperCombatPolicy {
	/** 附近威胁扫描半径（格）。 */
	public static final double RADIUS = 8.0;

	private ChopperCombatPolicy() {
	}

	/** 开启 KillAura 本身不算证据，必须是它当前实际选中的傀儡。 */
	public static boolean isThreat(boolean enemy, boolean ironGolem, boolean targetingPlayer,
		boolean recentAttacker, boolean activeAuraTarget) {
		return enemy || ironGolem && (targetingPlayer || recentAttacker || activeAuraTarget);
	}

	/** 只保留近期且时间有效的受击记录，不能把旧仇恨无限延长。 */
	public static boolean recentAttacker(boolean sameAttacker, int ageTicks) {
		return sameAttacker && ageTicks >= 0 && ageTicks <= 100;
	}

	/** 刚被打或身边有威胁：暂停挖树。 */
	public static boolean shouldPause(boolean hurtReason, boolean nearbyThreat) {
		return hurtReason || nearbyThreat;
	}
}
