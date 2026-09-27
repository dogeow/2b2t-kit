package dev.twob2tkit.automation;

/** Narrow permission for ordinary underwater gravel mining, separate from dry construction fixes. */
final class UnderwaterGravelPolicy {
	private UnderwaterGravelPolicy() {}

	static String startRejection(boolean gravel, boolean waterAbove, boolean lavaNear,
				boolean underwater, float health, int air, boolean breathing,
				boolean shovel, int durability) {
		return startRejection(gravel,waterAbove,lavaNear,underwater,health,air,breathing,shovel,durability,180);
	}

	static String startRejection(boolean gravel, boolean waterAbove, boolean lavaNear,
				boolean underwater, float health, int air, boolean breathing,
				boolean shovel, int durability, int workFloor) {
			if (!gravel || !waterAbove) return "Only exposed seafloor gravel is allowed";
			if (lavaNear) return "Lava near underwater gravel is protected";
			if (!underwater || health < 19) return "A healthy submerged player is required";
			if (!breathing && air < workFloor) return "Surface before oxygen gets low";
		if (!shovel || durability < 50) return "A durable shovel is required underwater";
		return null;
	}

	static boolean continueMining(boolean underwater, float health, int air, boolean breathing) {
			return continueMining(underwater,health,air,breathing,120);
	}

	static boolean continueMining(boolean underwater, float health, int air, boolean breathing,int returnFloor) {
			return underwater && health >= 18 && (breathing || air >= returnFloor);
	}
}
