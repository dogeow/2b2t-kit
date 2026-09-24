package dev.twob2tkit.automation;

/** One-shot, world-scoped handoff from a guarded material session to the ore miner. */
final class BorerControlPolicy {
	private BorerControlPolicy() {}

	static String startRejection(boolean materialOwned, boolean gravelOnly, boolean healthy,
			boolean grounded, boolean quiet, boolean free, boolean guarded) {
		if (!materialOwned) return "Material session required for ore-miner handoff";
		if (!gravelOnly) return "Only the selected gravel-only ore mode can start through this bridge";
		if (!healthy) return "Health and food must be safe before starting gravel mining";
		if (!grounded) return "Gravel miner must start from a verified ground stand";
		if (!quiet) return "Hostile or defense active near the gravel stand";
		if (!free) return "Another mining or construction task is active";
		if (!guarded) return "PvE guard must be armed for the handoff";
		return null;
	}

	static boolean ownsStop(String activeSession, String suppliedSession, boolean active) {
		return active && activeSession != null && !activeSession.isBlank()
			&& activeSession.equals(suppliedSession);
	}
}
