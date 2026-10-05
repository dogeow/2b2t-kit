package dev.twob2tkit.runtime.engine;
import java.util.List;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
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
    static boolean safetyRiseNeeded(boolean standalone,boolean current,boolean aliveHostile,boolean engaged,
                                    boolean ranged,boolean canAttack,boolean visible,double distance){
        return standalone&&current&&aliveHostile&&engaged&&Double.isFinite(distance)&&distance>=0&&distance<=12
            &&(ranged||!canAttack||!visible);
    }
    static boolean finiteVector(Vec3 value){
        return value!=null&&Double.isFinite(value.x)&&Double.isFinite(value.y)&&Double.isFinite(value.z);
    }
    static boolean finiteBox(AABB box){
        return box!=null&&Double.isFinite(box.minX)&&Double.isFinite(box.minY)&&Double.isFinite(box.minZ)
            &&Double.isFinite(box.maxX)&&Double.isFinite(box.maxY)&&Double.isFinite(box.maxZ)
            &&box.minX<box.maxX&&box.minY<box.maxY&&box.minZ<box.maxZ;
    }
    /** A far above hostile is not a ceiling; a nearby above hostile or body intersection still is. */
    static boolean riseThreatClear(double playerY,double mobY,AABB swept,AABB mob,double radius){
        if(!Double.isFinite(playerY)||!Double.isFinite(mobY)||!Double.isFinite(radius)||radius<=0
            ||!finiteBox(swept)||!finiteBox(mob)||swept.intersects(mob))return false;
        double dx=Math.max(0,Math.max(swept.minX-mob.maxX,mob.minX-swept.maxX));
        double dy=Math.max(0,Math.max(swept.minY-mob.maxY,mob.minY-swept.maxY));
        double dz=Math.max(0,Math.max(swept.minZ-mob.maxZ,mob.minZ-swept.maxZ));
        return dx*dx+dy*dy+dz*dz>radius*radius||StandaloneCreeperPolicy.riseMovesAway(playerY,mobY);
    }
    /** One fixed player-derived ascent for the same unresolved encounter, never currentY+12 each tick. */
    static final class SafetyRise {
        private Object world;private double target=Double.NaN;private long started;private boolean spent;
        double remaining(Object currentWorld,double feet,long tick,boolean trigger){
            if(world!=currentWorld){clear();world=currentWorld;}
            if(currentWorld==null||!Double.isFinite(feet)||tick<0||spent)return 0;
            if(Double.isNaN(target)){
                if(!trigger)return 0;
                target=Math.min(316,feet+12);started=tick;
            }
            if(tick-started>=200||feet>=target-.25){spent=true;return 0;}
            return Math.max(0,target-feet);
        }
        double target(){return target;}
        boolean active(){return !spent&&!Double.isNaN(target);}
        void clear(){world=null;target=Double.NaN;started=0;spent=false;}
    }
    private GuardWeaponPolicy(){}
}
