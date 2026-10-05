package dev.twob2tkit.runtime.engine;

import java.util.*;

/** Reversible work suspension, never a kill confirmation or cancellation of unresolved UUIDs. */
final class BorerCombatSeparation {
    static final int QUIET_TICKS=20;
    record Threat(boolean observed,boolean ordinaryCreeper,boolean visible,boolean swelling,
                  double distance,double clearanceBelowFeet,boolean previouslyVerifiedSafe,boolean unarmedZombie) {
        Threat(boolean observed,boolean ordinaryCreeper,boolean visible,boolean swelling,double distance,double clearanceBelowFeet){
            this(observed,ordinaryCreeper,visible,swelling,distance,clearanceBelowFeet,false,false);
        }
        Threat(boolean observed,boolean ordinaryCreeper,boolean visible,boolean swelling,double distance,double clearanceBelowFeet,boolean previouslyVerifiedSafe){
            this(observed,ordinaryCreeper,visible,swelling,distance,clearanceBelowFeet,previouslyVerifiedSafe,false);
        }
    }
    record LastSeen(double x,double y,double z,double topY,boolean ordinaryCreeper,boolean swelling,boolean unarmedZombie) {}
    private final Map<UUID,LastSeen> lastSeen=new HashMap<>();
    private final Set<UUID> verifiedSafeIds=new HashSet<>();
    private Object observationWorld,retainedWorld;
    private long safeSince=Long.MIN_VALUE;
    private boolean yielding;
    static boolean safe(boolean standalone,boolean flight,boolean healthyDryClear,boolean missing,
                        boolean nearbyAttackable,List<Threat> threats){
        return standalone&&flight&&healthyDryClear&&!missing&&!nearbyAttackable&&!threats.isEmpty()
            &&threats.stream().allMatch(t->Double.isFinite(t.distance)&&Double.isFinite(t.clearanceBelowFeet)
                &&!t.swelling&&((t.ordinaryCreeper&&!t.unarmedZombie&&!t.visible
                    &&(t.observed ? t.distance>=8.25&&t.clearanceBelowFeet>=4
                        : t.previouslyVerifiedSafe&&t.distance>=24&&t.clearanceBelowFeet>=16))
                    ||(t.unarmedZombie&&!t.ordinaryCreeper
                        &&(t.observed ? t.distance>=12&&t.clearanceBelowFeet>=6
                            : t.previouslyVerifiedSafe&&t.distance>=24&&t.clearanceBelowFeet>=16))));
    }
    /** Only a currently tracked entity may update this evidence; removed entity references are never sampled. */
    void seen(Object world,UUID id,double x,double y,double z,double topY,boolean ordinaryCreeper,boolean swelling){
        seen(world,id,x,y,z,topY,ordinaryCreeper,swelling,false);
    }
    void seen(Object world,UUID id,double x,double y,double z,double topY,boolean ordinaryCreeper,boolean swelling,boolean unarmedZombie){
        if(world==null)return;
        if(observationWorld!=world){clear();observationWorld=world;}
        if(id==null||!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z)||!Double.isFinite(topY)||topY<y){
            lastSeen.remove(id);verifiedSafeIds.remove(id);return;
        }
        var previous=lastSeen.get(id);
        if(previous!=null&&previous.unarmedZombie!=unarmedZombie)verifiedSafeIds.remove(id);
        if(!lastSeen.containsKey(id)){safeSince=Long.MIN_VALUE;yielding=false;}
        lastSeen.put(id,new LastSeen(x,y,z,topY,ordinaryCreeper,swelling,unarmedZombie));
    }
    void verifyDeferred(Object world,Collection<UUID> currentlyObservedIds){
        if(!yielding||!retain(world))return;
        for(UUID id:currentlyObservedIds){var seen=lastSeen.get(id);if(seen!=null&&(seen.ordinaryCreeper||seen.unarmedZombie)&&!seen.swelling)verifiedSafeIds.add(id);}
    }
    void revokeUnarmed(Object world,UUID id){
        var seen=observationWorld==world?lastSeen.get(id):null;
        if(seen!=null&&seen.unarmedZombie)verifiedSafeIds.remove(id);
    }
    LastSeen lastVerified(Object world,UUID id){return retain(world)&&verifiedSafeIds.contains(id)?lastSeen.get(id):null;}
    Threat unloaded(Object world,UUID id,double playerX,double predictedFeetY,double playerZ){
        var seen=lastVerified(world,id);
        if(seen==null)return new Threat(false,false,false,false,0,0,false);
        double dx=playerX-seen.x,dy=predictedFeetY-seen.y,dz=playerZ-seen.z;
        return new Threat(false,seen.ordinaryCreeper,false,seen.swelling,Math.sqrt(dx*dx+dy*dy+dz*dz),predictedFeetY-seen.topY,true,seen.unarmedZombie);
    }
    boolean observe(Object world,long tick,boolean safe){
        if(world==null){clear();return false;}
        if(observationWorld!=world){clear();observationWorld=world;}
        if(!safe){
            // Aggregate failure restarts the quiet window; UUID evidence is revoked separately.
            safeSince=Long.MIN_VALUE;yielding=false;return false;
        }
        if(safeSince==Long.MIN_VALUE||tick<safeSince)safeSince=tick;
        yielding=tick-safeSince>=QUIET_TICKS;
        if(yielding)retainedWorld=world;
        return yielding;
    }
    boolean yielding(){return yielding;}
    boolean verifying(){return safeSince!=Long.MIN_VALUE&&!yielding;}
    boolean retain(Object world){return world!=null&&world==retainedWorld;}
    void clear(){observationWorld=retainedWorld=null;safeSince=Long.MIN_VALUE;yielding=false;lastSeen.clear();verifiedSafeIds.clear();}
}
