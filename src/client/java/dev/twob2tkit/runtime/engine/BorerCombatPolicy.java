package dev.twob2tkit.runtime.engine;

/**
 * 被打停手。只改这一处。
 * <p>
 * lastHurtByMob 会残留上次打你的骷髅。岩浆块烫伤时 hurtTime 也亮，
 * 不要提示「被骷髅打了」。
 */
public final class BorerCombatPolicy {
	/** 这一下必须是这只怪刚打的，不能用几秒前的残留。hurtTime 大约 10 拍。 */
	public static final int MOB_HIT_WINDOW = 15;

	private BorerCombatPolicy() {
	}

	/**
	 * @param environmental 当前伤害是岩浆块/火/摔落等
	 * @param ticksSinceMobAttack {@code tickCount - lastHurtByMobTimestamp}，没有怪则很大
	 */
	public static boolean treatAsMobHit(boolean recentlyHurt, boolean environmental, int ticksSinceMobAttack) {
		if (!recentlyHurt || environmental) return false;
		return ticksSinceMobAttack >= 0 && ticksSinceMobAttack <= MOB_HIT_WINDOW;
	}

	/** 当前受伤原因的展示文案。 */
	public static String hurtCauseLabel(boolean environmental, String envName, String mobName, boolean mobHitRecent) {
		if (environmental) {
			return envName == null || envName.isBlank() ? "环境伤害" : envName;
		}
		if (mobHitRecent && mobName != null && !mobName.isBlank()) return mobName;
		return null;
	}

	/** 刚被怪打中时停挖。 */
	public static boolean pauseMiningForCombat(boolean mobHitNow) {
		return mobHitNow;
	}
}
