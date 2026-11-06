package dev.twob2tkit.map;

/** Height floor for a map-initiated cruise; NaN means an ordinary cruise. */
public final class MapCruiseAltitude {
    private MapCruiseAltitude() {}
    public static double floor(double desired, double initialY) {
        return Double.isFinite(initialY) ? Math.max(desired, initialY) : desired;
    }
    public static boolean permits(double candidateY, double initialY) {
        return !Double.isFinite(initialY) || candidateY >= initialY;
    }
}
