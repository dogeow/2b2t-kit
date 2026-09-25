package dev.twob2tkit.automation;

/** Permit only an owned near-vertical rise while PvE defense has input priority. */
final class GuardEscapePolicy {
    private GuardEscapePolicy() {}

    static boolean currentLease(String currentWorld, long currentRevision,
                                String leaseWorld, long leaseRevision,
                                String requestWorld, long expectedRevision,
                                String leaseJob, String requestJob) {
        return currentWorld != null && !currentWorld.isBlank()
            && currentWorld.equals(leaseWorld) && currentWorld.equals(requestWorld)
            && leaseJob != null && !leaseJob.isBlank() && leaseJob.equals(requestJob)
            && currentRevision > 0 && leaseRevision == currentRevision
            && expectedRevision == currentRevision - 1;
    }

    static boolean allowed(boolean materialLease, boolean guardArmed,
                           double x, double y, double z,
                           double targetX, double targetY, double targetZ) {
        double rise=targetY-y;
        return materialLease && guardArmed
            && Double.isFinite(targetX) && Double.isFinite(targetY) && Double.isFinite(targetZ)
            && rise>=2 && rise<=64
            && Math.hypot(targetX-x,targetZ-z)<=2;
    }

    static boolean underwaterAirReturn(boolean materialLease, boolean guardArmed,
                                       boolean waterThreatZone, boolean clearColumn,
                                       double x, double y, double z,
                                       double targetX, double targetY, double targetZ,
                                       double seaLevel) {
        return waterThreatZone && clearColumn && targetY>=seaLevel+1
            && Math.hypot(targetX-x,targetZ-z)<=.2
            && allowed(materialLease,guardArmed,x,y,z,targetX,targetY,targetZ);
    }
}
