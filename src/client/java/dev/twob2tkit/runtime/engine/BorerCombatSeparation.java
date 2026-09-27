package dev.twob2tkit.runtime.engine;

import java.util.*;

/** Reversible work suspension, never a kill confirmation or cancellation of unresolved UUIDs. */
final class BorerCombatSeparation {
    static final int QUIET_TICKS=20;
    record Threat(boolean observed,boolean ordinaryCreeper,boolean visible,boolean swelling,
                  double distance,double clearanceBelowFeet,boolean previouslyVerifiedSafe) {
        Threat(boolean observed,boolean ordinaryCreeper,boolean visible,boolean swelling,double distance,double clearanceBelowFeet){
            this(observed,ordinaryCreeper,visible,swelling,distance,clearanceBelowFeet,false);
        }
    }
    record LastSeen(double x,double y,double z,double topY,boolean ordinaryCreeper,boolean swelling) {}
    private final Map<UUID,LastSeen> lastSeen=new HashMap<>();
    private final Set<UUID> verifiedSafeIds=new HashSet<>();
    private Object observationWorld,retainedWorld;
    private long safeSince=Long.MIN_VALUE;
    private boolean yielding;
    static boolean safe(boolean standalone,boolean flight,boolean healthyDryClear,boolean missing,
                        boolean nearbyAttackable,List<Threat> threats){
        return standalone&&flight&&healthyDryClear&&!missing&&!nearbyAttackable&&!threats.isEmpty()
            &&threats.stream().allMatch(t->t.ordinaryCreeper&&!t.visible&&!t.swelling
                &&Double.isFinite(t.distance)&&Double.isFinite(t.clearanceBelowFeet)
                &&(t.observed ? t.distance>=8.25&&t.clearanceBelowFeet>=4
                    : t.previouslyVerifiedSafe&&t.distance>=24&&t.clearanceBelowFeet>=16));
    }
    /** Only a currently tracked entity may update this evidence; removed entity references are never sampled. */
    void seen(Object world,UUID id,double x,double y,double z,double topY,boolean ordinaryCreeper,boolean swelling){
        if(world==null)return;
        if(observationWorld!=world){clear();observationWorld=world;}
        if(id==null||!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z)||!Double.isFinite(topY)||topY<y){
            lastSeen.remove(id);verifiedSafeIds.remove(id);return;
        }
        if(!lastSeen.containsKey(id)){safeSince=Long.MIN_VALUE;yielding=false;}
        lastSeen.put(id,new LastSeen(x,y,z,topY,ordinaryCreeper,swelling));
    }
    void verifyDeferred(Object world,Collection<UUID> currentlyObservedIds){
        if(!yielding||!retain(world))return;
        for(UUID id:currentlyObservedIds){var seen=lastSeen.get(id);if(seen!=null&&seen.ordinaryCreeper&&!seen.swelling)verifiedSafeIds.add(id);}
    }
    LastSeen lastVerified(Object world,UUID id){return retain(world)&&verifiedSafeIds.contains(id)?lastSeen.get(id):null;}
    Threat unloaded(Object world,UUID id,double playerX,double predictedFeetY,double playerZ){
        var seen=lastVerified(world,id);
        if(seen==null)return new Threat(false,false,false,false,0,0,false);
        double dx=playerX-seen.x,dy=predictedFeetY-seen.y,dz=playerZ-seen.z;
        return new Threat(false,seen.ordinaryCreeper,false,seen.swelling,Math.sqrt(dx*dx+dy*dy+dz*dz),predictedFeetY-seen.topY,true);
    }
    boolean observe(Object world,long tick,boolean safe){
        if(world==null){clear();return false;}
        if(observationWorld!=world){clear();observationWorld=world;}
        if(!safe){safeSince=Long.MIN_VALUE;yielding=false;return false;}
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
