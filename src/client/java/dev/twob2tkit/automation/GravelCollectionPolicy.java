package dev.twob2tkit.automation;

import java.util.Locale;

/** Small decisions shared by the UI collector and its regression tests. */
public final class GravelCollectionPolicy {
    private GravelCollectionPolicy() {}
    public static boolean allowedWorld(boolean local, String address) {
        if(local)return true;
        String host=address==null?"":address.toLowerCase(Locale.ROOT).trim();
        if(host.endsWith(":25565"))host=host.substring(0,host.length()-6);
        return host.equals("simpcraft.com")||host.equals("31.25.11.102");
    }
    static boolean reachable(double feetY,int blockY,double horizontal,double eyeDistance,double reach) {
        return feetY-blockY>=.99&&feetY-blockY<=4.5&&horizontal<=1.25&&eyeDistance<=reach;
    }
    static boolean complete(int collected,int limit,int room) {
        return room<=0||limit>0&&collected>=limit;
    }
    static int credited(int before,int current) {return Math.max(0,current-before);}
    static boolean confirmedPickup(boolean blockRemoved,int inventoryGain,boolean freshDropRemaining){
        return blockRemoved&&inventoryGain>0&&!freshDropRemaining;
    }
    static boolean boundedDropApproach(double horizontal,boolean clearPickupColumn){
        // Reaching a drifting drop from another column invalidates the armed
        // vertical escape. Return with the carried batch instead of redive.
        return Double.isFinite(horizontal)&&horizontal>=0&&horizontal<=1.5&&clearPickupColumn;
    }
    static boolean boundedPickupRebase(double horizontal,boolean provedRoute,int air,int workFloor,
                                        float health,boolean underwater,int rebases){
        return Double.isFinite(horizontal)&&horizontal>1.5&&horizontal<=6
            &&provedRoute&&health>=19&&underwater&&workFloor>=1
            &&air>=workFloor+40&&rebases>=0&&rebases<4;
    }
    static boolean sameColumn(double x,double z,int blockX,int blockZ){
        return Math.floor(x)==blockX&&Math.floor(z)==blockZ;
    }
    static int pickupStartFloor(int observedFloor){
        return pickupStartFloor(observedFloor,false);
    }
    static int pickupStartFloor(int observedFloor,boolean currentObservedRoute){
        // Native descent may switch to its fallback return floor mid-action.
        // A proved calibration that remains valid throughout the bounded
        // descent can use its actual floor instead of the initial fallback.
        if(currentObservedRoute&&observedFloor>0&&observedFloor<=300)return observedFloor+15;
        return Math.max(265,observedFloor+15);
    }
    static boolean recoverableDescentAirStop(String detail,float health){
        if(health<19||detail==null)return false;
        return detail.contains("Guarded water descent")
            ||detail.contains("water descent stopped for surface air");
    }
    static boolean skipUnstartedMine(String detail,boolean unchanged,int inventoryDelta){
        return unchanged&&inventoryDelta==0&&java.util.Set.of(
            "mining target is occluded","mining target moved out of reach",
            "Mining target out of reach","Current footing is protected").contains(detail);
    }
    enum PickupAction {WAIT,RETRY,SKIP,STOP}
    static PickupAction pickupAction(int waitedTicks,int retries,int failures,boolean visible,boolean enoughAir){
        if(waitedTicks>=40&&visible&&enoughAir&&retries<2)return PickupAction.RETRY;
        if(waitedTicks<100)return PickupAction.WAIT;
        return failures<2?PickupAction.SKIP:PickupAction.STOP;
    }
}
