package dev.twob2tkit.cruise;

/** Arrival rules for manual cruise and precise owned material navigation. */
public final class CruiseArrivalPolicy {
    private CruiseArrivalPolicy() {}

    public static double manualRadius(double configured) {
        return Double.isFinite(configured) ? Math.max(1.0, Math.min(128.0, configured)) : 8.0;
    }

    /** Resolve an exact task's optional radius without mutating the user setting. */
    public static double scriptRadius(boolean specified, double temporary, double configured) {
        return specified ? temporary : configured;
    }

    public static boolean reached(boolean exact, double previousX, double previousZ,
                                  double x, double z, double targetX, double targetZ, double radius) {
        if (!Double.isFinite(x) || !Double.isFinite(z) || !Double.isFinite(targetX)
                || !Double.isFinite(targetZ) || !Double.isFinite(radius) || radius <= 0) return false;
        if (Math.hypot(x-targetX, z-targetZ) <= radius) return true;
        if (exact || !Double.isFinite(previousX) || !Double.isFinite(previousZ)) return false;
        double dx=x-previousX, dz=z-previousZ, length2=dx*dx+dz*dz;
        // A large gap can be a teleport or stale observation, not a continuous flight.
        if (length2 < 1.0e-12 || length2 > 64.0) return false;
        double t=((targetX-previousX)*dx+(targetZ-previousZ)*dz)/length2;
        t=Math.max(0.0, Math.min(1.0, t));
        return Math.hypot(previousX+t*dx-targetX, previousZ+t*dz-targetZ) <= radius;
    }
}
