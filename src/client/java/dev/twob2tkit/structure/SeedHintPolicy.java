package dev.twob2tkit.structure;

/** A stored full seed may rank hints; live server scans alone authorize work. */
final class SeedHintPolicy {
	private SeedHintPolicy() {}
	static boolean available(Long storedFullSeed, boolean currentHashPresent,
		boolean currentHashMatches) {
		// A proxy can change the login hash while the server world remains the
		// same.  Neither hash state upgrades this value beyond a location hint.
		return storedFullSeed != null;
	}
}
