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
    static double boxDistanceSquared(AABB first,AABB second){
        if(!finiteBox(first)||!finiteBox(second))return Double.NaN;
        double dx=Math.max(0,Math.max(first.minX-second.maxX,second.minX-first.maxX));
        double dy=Math.max(0,Math.max(first.minY-second.maxY,second.minY-first.maxY));
        double dz=Math.max(0,Math.max(first.minZ-second.maxZ,second.minZ-first.maxZ));
        return dx*dx+dy*dy+dz*dz;
    }
    /** Within reach, no point of the ascent may be closer than the starting body. */
    static boolean riseThreatClear(AABB start,AABB swept,AABB mob,double radius){
        if(!Double.isFinite(radius)||radius<=0||!finiteBox(start)||!finiteBox(swept)
            ||!finiteBox(mob)||swept.intersects(mob))return false;
        double closest=boxDistanceSquared(swept,mob);
        return closest>radius*radius||closest>=boxDistanceSquared(start,mob);
    }
    /** Completion stays latched until the trigger resets or the player descends. */
    static final class SafetyRise {
        private Object world;private double target=Double.NaN,highestFeet=Double.NaN;
        private long lastAttempt=Long.MIN_VALUE;private int attempts;private boolean spent;
        double remaining(Object currentWorld,double feet,long tick,boolean trigger){
            if(world!=currentWorld){clear();world=currentWorld;}
            if(currentWorld==null||!Double.isFinite(feet)||tick<0||!trigger){cancel();return 0;}
            if(feet<highestFeet-1||tick<lastAttempt)cancel();
            if(Double.isNaN(target)){
                target=Math.min(316,feet+12);highestFeet=feet;
            }
            highestFeet=Math.max(highestFeet,feet);
            if(spent||attempts>=200||feet>=target-.25){spent=true;return 0;}
            return Math.min(12,Math.max(0,target-feet));
        }
        void attempted(long tick){if(active()&&tick>=0&&tick!=lastAttempt){attempts++;lastAttempt=tick;}}
        double target(){return target;}
        boolean active(){return !spent&&!Double.isNaN(target);}
        void cancel(){target=highestFeet=Double.NaN;lastAttempt=Long.MIN_VALUE;attempts=0;spent=false;}
        void clear(){world=null;cancel();}
    }
    private GuardWeaponPolicy(){}
}
