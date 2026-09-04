package dev.twob2tkit.chopper;

/**
 * 挖树遇战。只改这一处。
 * <p>
 * 铁傀儡不是 {@code Enemy}，只扫敌对会漏掉。Meteor KillAura 开着打傀儡时，
 * 本模块还在换剪刀砍树叶，就会拿剪刀抽傀儡、不切剑、不飞起来。
 */
public final class ChopperCombatPolicy {
	/** 附近威胁扫描半径（格）。 */
	public static final double RADIUS = 8.0;
	/** 铁傀儡实体类型 id（中立但可能被 KillAura 打）。 */
	public static final String IRON_GOLEM = "iron_golem";

	private ChopperCombatPolicy() {
	}

	/** 敌对生物，或需要特殊处理的中立傀儡，都算威胁类型。 */
	public static boolean isThreatType(boolean enemy, String typeId) {
		if (enemy) return true;
		return isNeutralGolem(typeId);
	}

	/** 是否为铁傀儡（不是 Enemy，但挖树时常被误伤）。 */
	public static boolean isNeutralGolem(String typeId) {
		return IRON_GOLEM.equals(typeId);
	}

	/** KillAura 会打附近傀儡，或傀儡已经在打你：都要停砍切剑。 */
	public static boolean shouldEngageNeutral(boolean killAuraOn, boolean targetingPlayer) {
		return killAuraOn || targetingPlayer;
	}

	/** 刚被打或身边有威胁：暂停挖树。 */
	public static boolean shouldPause(boolean hurtReason, boolean nearbyThreat) {
		return hurtReason || nearbyThreat;
	}
}
