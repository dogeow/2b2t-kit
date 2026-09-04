package dev.twob2tkit.combat;

/**
 * 被打后打开 Meteor 保护模块。只改这一处。
 * <p>
 * 岩浆块烫伤不算挨打。不自己挥剑、不自己断线，只打开 KillAura 和 Auto Log。
 */
public final class AutoProtectPolicy {
	private AutoProtectPolicy() {
	}

	/** 勾了自动保护且这次是被怪打中才武装。 */
	public static boolean armOnMobHit(boolean enabled, boolean mobHit) {
		return enabled && mobHit;
	}
}
