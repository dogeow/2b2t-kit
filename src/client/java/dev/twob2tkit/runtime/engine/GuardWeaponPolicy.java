package dev.twob2tkit.runtime.engine;
import java.util.List;
final class GuardWeaponPolicy {
    static boolean usableBow(boolean bow,boolean damageable,int remaining){return bow&&(!damageable||remaining>=8);}
    static boolean needsRise(double feet,double mobFeet){return feet<mobFeet+3.0;}
    enum Hover{RISE,HOLD,FALLBACK}
    static Hover hover(double feet,double mobFeet,boolean wholeColumnClear){
        if(feet>mobFeet+3.4)return Hover.FALLBACK;
        if(needsRise(feet,mobFeet))return wholeColumnClear?Hover.RISE:Hover.FALLBACK;
        return Hover.HOLD;
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
    private GuardWeaponPolicy(){}
}
