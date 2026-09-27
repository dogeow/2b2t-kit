package dev.twob2tkit.runtime.engine;

import java.util.Set;

/** Non-colliding ordinary vegetation is not a solid wall around a quarry entry. */
final class BorerAreaVegetation {
	private static final Set<String> SAFE = Set.of(
		"minecraft:short_grass", "minecraft:tall_grass", "minecraft:fern", "minecraft:large_fern",
		"minecraft:dead_bush", "minecraft:bush", "minecraft:short_dry_grass", "minecraft:tall_dry_grass",
		"minecraft:dandelion", "minecraft:poppy", "minecraft:blue_orchid", "minecraft:allium",
		"minecraft:azure_bluet", "minecraft:red_tulip", "minecraft:orange_tulip", "minecraft:white_tulip",
		"minecraft:pink_tulip", "minecraft:oxeye_daisy", "minecraft:cornflower", "minecraft:lily_of_the_valley",
		"minecraft:sunflower", "minecraft:lilac", "minecraft:rose_bush", "minecraft:peony",
		"minecraft:pink_petals", "minecraft:wildflowers", "minecraft:leaf_litter", "minecraft:firefly_bush");

	static BorerAreaPlan.Cell classify(BorerAreaPlan.Cell existing, String blockId,
			boolean emptyCollision, boolean emptyFluid) {
		// Protection, unknown chunks and liquids always win. Do not generalize to
		// every empty collision shape: portals, fire, webs and harmful plants exist.
		return existing == BorerAreaPlan.Cell.SOLID && emptyCollision && emptyFluid && SAFE.contains(blockId)
			? BorerAreaPlan.Cell.AIR : existing;
	}

	private BorerAreaVegetation() {}
}
