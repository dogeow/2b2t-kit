package dev.twob2tkit.runtime.engine;
import java.util.List;
final class GuardWeaponPolicy {
    static final int SWORD_RESERVE=32;
    static boolean usableSword(boolean sword,int remaining){return usableSword(sword,remaining,SWORD_RESERVE);}
    static boolean usableSword(boolean sword,int remaining,int minimum){return sword&&remaining>=minimum;}
    static boolean usableBow(boolean bow,boolean damageable,int remaining){return bow&&(!damageable||remaining>=8);}
    static boolean groundSwordAllowed(boolean standaloneGuard,boolean onlyZombies){
        return !standaloneGuard||!onlyZombies;
    }
    static boolean needsRise(double feet,double mobFeet){return feet<mobFeet+3.0;}
    enum Hover{RISE,DESCEND,HOLD,FALLBACK}
    static Hover hover(double feet,double mobFeet,boolean wholeColumnClear){
        if(feet>mobFeet+3.4)return wholeColumnClear?Hover.DESCEND:Hover.FALLBACK;
        if(needsRise(feet,mobFeet))return wholeColumnClear?Hover.RISE:Hover.FALLBACK;
        return Hover.HOLD;
    }
    /** Conversion candidates and armed drowned retain their existing combat paths. */
    static boolean ordinaryZombie(String type, boolean rangedWeapon) {
        return !rangedWeapon && ("minecraft:zombie".equals(type) || "minecraft:husk".equals(type)
            || "minecraft:drowned".equals(type));
    }
    /** Never descend below the melee safety margin, even with residual downward momentum. */
    static double hoverVerticalStep(double feet, double projectedFeet, double highestMobFeet) {
        double desired = highestMobFeet + 3.1;
        if (feet > desired) return -Math.min(.15, Math.max(0, Math.min(feet, projectedFeet) - desired));
        return Math.min(.15, desired - feet);
    }
	/** A sword swing is allowed only from a stable, flying hover above every nearby zombie. */
	static boolean swordHoverReady(boolean onlyZombies,boolean flight,boolean usableSword,
	                                double feet,double projectedFeet,double highestMobFeet,
	                                double eyeToTarget,double attackRange){
		return onlyZombies&&usableSword&&safeHoverHeight(flight,feet,projectedFeet,highestMobFeet)
			&&eyeToTarget<=attackRange-.2;
	}
	static boolean safeHoverHeight(boolean flight,double feet,double projectedFeet,double highestMobFeet){
		return flight&&feet>=highestMobFeet+3.0&&projectedFeet>=highestMobFeet+3.0
			&&feet<=highestMobFeet+3.4;
	}
	/** Rise before fighting a nearby ranged mob, even when a zombie is also engaged. */
	record Threat(double feetY, boolean ranged, double distance) {}
	static double combatRise(double playerY, List<Threat> threats) {
		double desired = playerY;
		for (Threat threat : threats) {
			if (threat.distance() > (threat.ranged() ? 12.0 : 9.0)) continue;
			desired = Math.max(desired, threat.feetY() + (threat.ranged() ? 6.0 : 4.0));
		}
		return Math.max(0.0, desired - playerY);
	}
    static boolean riseFailureNeedsExit(double health) { return health < 14; }
    private GuardWeaponPolicy(){}
}
