package dev.twob2tkit.automation;

/** Restore an explicitly armed PvE guard only after returning to the same play site. */
final class GuardReconnectPolicy {
	static final long MAX_AGE_MS = 10 * 60 * 1000L;
	record Pending(String server, String dimension, double x, double z, long savedAt) {}
	private GuardReconnectPolicy() {}

	static Pending capture(boolean armed, boolean pveOnly, boolean autoReconnect,
			float health, String server, String dimension, double x, double z, long now) {
		if (!armed || !pveOnly || !autoReconnect || health < 18
				|| server == null || dimension == null || !Double.isFinite(x) || !Double.isFinite(z)) return null;
		return new Pending(server, dimension, x, z, now);
	}

	static boolean restoreHere(Pending pending, String server, String dimension,
			double x, double z, float health, boolean manualInput, boolean screenOpen, long now) {
		return pending != null && now >= pending.savedAt() && now - pending.savedAt() <= MAX_AGE_MS
			&& pending.server().equals(server) && pending.dimension().equals(dimension)
			&& Double.isFinite(x) && Double.isFinite(z)
			&& Math.hypot(x - pending.x(), z - pending.z()) <= 32
			&& health >= 18 && !manualInput && !screenOpen;
	}
}
