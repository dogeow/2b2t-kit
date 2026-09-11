package dev.twob2tkit.runtime.engine;

import java.util.List;
import java.util.Set;

/** Explicit vanilla material IDs: no substring matching that could mistake lapis/ore for stone. */
final class BorerCargoPolicy {
	static final Set<String> STONE = Set.of("stone", "cobblestone", "granite", "diorite", "andesite",
		"deepslate", "cobbled_deepslate", "tuff", "calcite", "netherrack", "basalt", "smooth_basalt",
		"blackstone", "end_stone", "dripstone_block");
	private static final Set<String> MATERIAL = Set.of("coal", "raw_iron", "raw_gold", "raw_copper",
		"iron_ingot", "gold_ingot", "copper_ingot", "iron_nugget", "gold_nugget", "diamond", "emerald",
		"lapis_lazuli", "redstone", "quartz", "ancient_debris", "amethyst_shard", "glowstone_dust",
		"coal_ore", "iron_ore", "gold_ore", "copper_ore", "diamond_ore", "emerald_ore", "lapis_ore", "redstone_ore",
		"deepslate_coal_ore", "deepslate_iron_ore", "deepslate_gold_ore", "deepslate_copper_ore",
		"deepslate_diamond_ore", "deepslate_emerald_ore", "deepslate_lapis_ore", "deepslate_redstone_ore",
		"nether_gold_ore", "nether_quartz_ore", "raw_iron_block", "raw_gold_block", "raw_copper_block",
		"dirt", "coarse_dirt", "gravel", "sand", "red_sand", "clay_ball", "flint", "obsidian", "crying_obsidian");
	record Stack(String id, int count, boolean special) {}
	static boolean stone(String id) { return id.startsWith("minecraft:") && STONE.contains(id.substring(10)); }
	static boolean material(String id) { return stone(id) || id.startsWith("minecraft:") && MATERIAL.contains(id.substring(10)); }
	static boolean nearFull(int emptySlots) { return emptySlots <= 3; }
	/** Reserve whole stacks containing at least 64 ordinary building blocks and 16 coal for torches. */
	static boolean[] reserved(List<Stack> stacks) {
		boolean[] keep = new boolean[stacks.size()];
		int stone = 64, coal = 16;
		for (int i = 0; i < stacks.size(); i++) {
			Stack s = stacks.get(i);
			if (s.special) { keep[i] = true; continue; }
			if (s.count > 0 && stone(s.id) && stone > 0) { keep[i] = true; stone -= s.count; }
			if (s.count > 0 && s.id.equals("minecraft:coal") && coal > 0) { keep[i] = true; coal -= s.count; }
		}
		return keep;
	}
	static int next(List<Stack> stacks, boolean discard) {
		return next(stacks, discard, i -> true);
	}
	static int next(List<Stack> stacks, boolean discard, java.util.function.IntPredicate fits) {
		boolean[] keep = reserved(stacks);
		for (int i = 0; i < stacks.size(); i++) if (!keep[i] && stacks.get(i).count > 0
			&& (discard ? stone(stacks.get(i).id) : material(stacks.get(i).id)) && fits.test(i)) return i;
		return -1;
	}
	static boolean outside(int x, int z, int minX, int minZ, int maxX, int maxZ) {
		return x <= minX - 4 || x >= maxX + 4 || z <= minZ - 4 || z >= maxZ + 4;
	}
	private BorerCargoPolicy() {}
}
