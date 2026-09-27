package dev.twob2tkit.automation;

/** Narrow external-material pause and local parking updates, with no task creation. */
final class MaterialJobControlPolicy {
    private MaterialJobControlPolicy() {}
    static boolean owned(String task,String leaseTask,String world,String leaseWorld,
                         long requestRevision,long currentRevision,long leaseRevision,long expiry,
                         boolean nativeOwner,boolean materialLease,boolean manualMovement) {
        return task!=null&&!task.isBlank()&&task.equals(leaseTask)&&world.equals(leaseWorld)
            &&requestRevision==currentRevision&&leaseRevision==currentRevision&&expiry>=0&&expiry<=15000
            &&!nativeOwner&&materialLease&&!manualMovement;
    }
    static boolean localPark(double x,double y,double z,double tx,double ty,double tz,
                             int ground,float health,boolean flight,boolean pveGuard,boolean clearLoadedDryPath) {
        return Double.isFinite(x)&&Double.isFinite(y)&&Double.isFinite(z)
            &&Double.isFinite(tx)&&Double.isFinite(ty)&&Double.isFinite(tz)
            &&Math.hypot(tx-x,tz-z)<=2&&ty>=y&&ty<320&&clearLoadedDryPath
            // This validates the proposed destination. highGuardPark later
            // checks the actual player pose after a separately requested move.
            &&GuardParkingPolicy.ready(tx,ty,tz,tx,ty,tz,ground,health,flight,pveGuard);
    }
    static boolean resumableParking(String kind,String world,String currentWorld,long leaseRevision,long revision,
                                    boolean verifiedHighPark,boolean pveGuard,boolean defending){
        return "parking".equals(kind)&&world.equals(currentWorld)&&leaseRevision==revision
            &&verifiedHighPark&&pveGuard&&!defending;
    }
    static double arrival(double requested,boolean materialOwned){
        if(!Double.isFinite(requested))throw new IllegalArgumentException("Invalid arrival radius");
        return Math.max(materialOwned?.2:1,Math.min(8,requested));
    }
}
