package dev.twob2tkit.runtime.engine;

import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.monster.Creeper;

/**
 * 盾构遇怪怎么贴近 / 后撤。只改这一处。
 * <p>
 * 有 Meteor 飞行 + KillAura + 剑时不必带弓：飞过去贴近就能打。
 * 苦力怕要炸时后撤举盾；骷髅等远程在贴近前举盾。
 */
public final class BorerCombatEngagePolicy {
	public static final double MELEE_REACH = 3.5;
	public static final double RANGED_SHIELD_RANGE = 6.0;
	/** 脚比怪头顶 bounding box 再高出多少格。 */
	public static final double HOVER_CLEARANCE = 2.0;
	public static final double ALTITUDE_TOLERANCE = 0.35;

	private BorerCombatEngagePolicy() {
	}

	/** 交战时悬停在怪头顶的脚底 Y。 */
	public static double hoverFeetY(double mobFeetY, double mobHeight, double clearanceAboveHead) {
		return mobFeetY + mobHeight + clearanceAboveHead;
	}

	/** 头顶被挡时降到和怪同一平面（脚同高）。 */
	public static double samePlaneFeetY(double mobFeetY) {
		return mobFeetY;
	}

	/** 头顶通畅悬停怪上；被挡则落到与怪同平面。 */
	public static double resolveHoverFeetY(double mobFeetY, double mobHeight, double clearanceAboveHead,
		boolean headroomBlocked) {
		if (!headroomBlocked) return hoverFeetY(mobFeetY, mobHeight, clearanceAboveHead);
		return samePlaneFeetY(mobFeetY);
	}

	/** 交战高度是否应上升。 */
	public static boolean shouldAscend(double playerFeetY, double targetFeetY) {
		return playerFeetY < targetFeetY - ALTITUDE_TOLERANCE;
	}

	/** 交战高度是否应下降。 */
	public static boolean shouldDescend(double playerFeetY, double targetFeetY) {
		return playerFeetY > targetFeetY + ALTITUDE_TOLERANCE;
	}

	/** 距离是否还需逼近。 */
	public static boolean needsCloser(double distance) {
		return distance > MELEE_REACH;
	}

	/** 该威胁是否应主动靠近。 */
	public static boolean shouldApproach(Entity threat, double distance) {
		return threat != null && threat.isAlive() && needsCloser(distance);
	}

	/** 逼近时是否举盾。 */
	public static boolean shouldRaiseShieldWhileClosing(Entity threat, double distance) {
		return BorerThreats.isRangedCombatThreat(threat) && distance > MELEE_REACH;
	}

	/** 苦力怕是否该拉开。 */
	public static boolean shouldRetreatFromCreeper(Creeper creeper, LocalPlayer player) {
		if (creeper == null || !creeper.isAlive() || player == null) return false;
		double distance = player.distanceTo(creeper);
		boolean swelling = creeper.isIgnited() || creeper.getSwelling(1.0F) > 0.15F || creeper.getSwellDir() > 0;
		return swelling || distance < 4.0 || creeper.isPowered() && distance < 6.0;
	}

	/** 墙后、区块未加载处的怪只凭距离不算可交战威胁，不飞过去贴脸。 */
	public static boolean canEngageThreat(boolean hasLineOfSight) {
		return hasLineOfSight;
	}
}
