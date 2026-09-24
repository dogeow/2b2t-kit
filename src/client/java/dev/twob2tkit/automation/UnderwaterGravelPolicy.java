package dev.twob2tkit.automation;

/** Narrow permission for ordinary underwater gravel mining, separate from dry construction fixes. */
final class UnderwaterGravelPolicy {
	private UnderwaterGravelPolicy() {}

	static String startRejection(boolean gravel, boolean waterAbove, boolean lavaNear,
			boolean underwater, float health, int air, boolean breathing,
			boolean shovel, int durability) {
		if (!gravel || !waterAbove) return "Only exposed seafloor gravel is allowed";
		if (lavaNear) return "Lava near underwater gravel is protected";
		if (!underwater || health < 19) return "A healthy submerged player is required";
		if (!breathing && air < 180) return "Surface before oxygen gets low";
		if (!shovel || durability < 50) return "A durable shovel is required underwater";
		return null;
	}

	static boolean continueMining(boolean underwater, float health, int air, boolean breathing) {
		return underwater && health >= 18 && (breathing || air >= 120);
	}
}
