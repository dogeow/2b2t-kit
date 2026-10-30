package dev.twob2tkit.combat;

/** Regenerable known heat damage can remain work instead of an unknown stuck-damage incident. */
public final class MinorThermalWorkPolicy {
    private MinorThermalWorkPolicy() {}
    public static boolean allow(boolean knownContact, double health, int food, boolean foodAvailable,
                                boolean inLava, boolean underwater) {
        return knownContact && Double.isFinite(health) && health >= 18 && food >= 16
            && (food >= 18 || foodAvailable) && !inLava && !underwater;
    }
}
