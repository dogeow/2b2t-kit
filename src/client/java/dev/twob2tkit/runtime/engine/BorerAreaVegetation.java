package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;

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

	/** A non-colliding grass tuft can still intercept the outline ray to the solid block under it. */
	static boolean clearableRayOccluder(BlockPos target, BlockPos hit, BlockPos min, BlockPos max,
		String blockId, boolean emptyCollision, boolean emptyFluid) {
		return target != null && hit != null && min != null && max != null
			&& hit.equals(target.above())
			&& hit.getX() >= min.getX() && hit.getX() <= max.getX()
			&& hit.getY() >= min.getY() && hit.getY() <= max.getY()
			&& hit.getZ() >= min.getZ() && hit.getZ() <= max.getZ()
			&& "minecraft:short_grass".equals(blockId) && emptyCollision && emptyFluid;
	}

	/** A matching two-block grass stem must fit entirely inside the selected shaft bounds. */
	static boolean clearableTallGrassPair(BlockPos target, BlockPos upper, BlockPos min, BlockPos max) {
		if (target == null || upper == null || min == null || max == null || !upper.equals(target.above(2))) return false;
		BlockPos lower = target.above();
		return lower.getX() >= min.getX() && lower.getX() <= max.getX()
			&& lower.getZ() >= min.getZ() && lower.getZ() <= max.getZ()
			&& lower.getY() >= min.getY() && upper.getY() <= max.getY();
	}

	/** A descending shaft may choose either digging action before meeting the same outline-only plant. */
	static boolean clearableAction(BorerAreaPlan.Phase phase, BorerAreaPlan.Action action) {
		return phase == BorerAreaPlan.Phase.DIG
			&& (action == BorerAreaPlan.Action.MINE || action == BorerAreaPlan.Action.MINE_DOWN);
	}

	private BorerAreaVegetation() {}
}
