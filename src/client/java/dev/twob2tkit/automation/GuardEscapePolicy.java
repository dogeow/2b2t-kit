package dev.twob2tkit.automation;

/** Permit only an owned near-vertical rise while PvE defense has input priority. */
final class GuardEscapePolicy {
    private GuardEscapePolicy() {}

    static boolean allowed(boolean materialLease, boolean guardArmed,
                           double x, double y, double z,
                           double targetX, double targetY, double targetZ) {
        double rise=targetY-y;
        return materialLease && guardArmed
            && Double.isFinite(targetX) && Double.isFinite(targetY) && Double.isFinite(targetZ)
            && rise>=2 && rise<=64
            && Math.hypot(targetX-x,targetZ-z)<=2;
    }
}
