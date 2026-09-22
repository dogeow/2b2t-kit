package dev.twob2tkit.runtime.engine;

import java.util.List;
import java.util.Set;

/** Checklist-owned deposit rules, with a separate explicit whitelist for discarding stone. */
final class BorerCargoPolicy {
	static final Set<String> STONE = Set.of("stone", "cobblestone", "granite", "diorite", "andesite",
		"deepslate", "cobbled_deepslate", "tuff", "calcite", "netherrack", "basalt", "smooth_basalt",
		"blackstone", "end_stone", "dripstone_block");
	/** Only used with an old host that cannot supply the checklist's reserve mask. */
	private static final Set<String> MATERIAL = Set.of("coal", "raw_iron", "raw_gold", "raw_copper",
		"iron_ingot", "gold_ingot", "copper_ingot", "iron_nugget", "gold_nugget", "diamond", "emerald",
		"lapis_lazuli", "redstone", "quartz", "ancient_debris", "amethyst_shard", "glowstone_dust",
		"coal_ore", "iron_ore", "gold_ore", "copper_ore", "diamond_ore", "emerald_ore", "lapis_ore", "redstone_ore",
		"deepslate_coal_ore", "deepslate_iron_ore", "deepslate_gold_ore", "deepslate_copper_ore",
		"deepslate_diamond_ore", "deepslate_emerald_ore", "deepslate_lapis_ore", "deepslate_redstone_ore",
		"nether_gold_ore", "nether_quartz_ore", "raw_iron_block", "raw_gold_block", "raw_copper_block",
		"dirt", "coarse_dirt", "gravel", "sand", "red_sand", "sandstone", "red_sandstone",
		"clay_ball", "flint", "obsidian", "crying_obsidian");
	record Stack(String id, int count, boolean special, boolean supply, boolean allDrops) {
		Stack(String id, int count, boolean special) { this(id, count, special, false, false); }
	}
	static boolean stone(String id) { return id.startsWith("minecraft:") && STONE.contains(id.substring(10)); }
	static boolean material(String id) { return stone(id) || id.startsWith("minecraft:") && MATERIAL.contains(id.substring(10)); }
	static boolean depositable(Stack stack) { return stack.allDrops || material(stack.id); }
	static boolean nearFull(int emptySlots) { return emptySlots <= 3; }
	/** Use the host's full supply mask; old hosts keep 64 building blocks and 16 coal. */
	static boolean[] reserved(List<Stack> stacks) {
		boolean[] keep = new boolean[stacks.size()];
		int stone = 64, coal = 16;
		for (int i = 0; i < stacks.size(); i++) {
			Stack s = stacks.get(i);
			if (s.allDrops) { keep[i] = s.special || s.supply; continue; }
			if (s.special) { keep[i] = true; continue; }
			if (s.count > 0 && stone(s.id) && stone > 0) { keep[i] = true; stone -= s.count; }
			if (s.count > 0 && s.id.equals("minecraft:coal") && coal > 0) { keep[i] = true; coal -= s.count; }
		}
		return keep;
	}
	/** The host checklist owns current reserves. Legacy deposit prefers cheap sealing blocks. */
	static boolean[] reservedForStore(List<Stack> stacks) {
		boolean[] keep=new boolean[stacks.size()];
		java.util.ArrayList<Integer> candidates=new java.util.ArrayList<>();int coal=16;
		for(int i=0;i<stacks.size();i++){
			Stack s=stacks.get(i);
			if(s.allDrops){keep[i]=s.special||s.supply;continue;}
			if(s.special){keep[i]=true;continue;}
			if(s.count<=0)continue;
			if(reserveRank(s.id)<3)candidates.add(i);
			if(s.id.equals("minecraft:coal")&&coal>0){keep[i]=true;coal-=s.count;}
		}
		candidates.sort(java.util.Comparator.<Integer>comparingInt(i->reserveRank(stacks.get(i).id))
			.thenComparingInt(i->-stacks.get(i).count).thenComparingInt(i->i));
		for(int i:candidates)if(stacks.get(i).count>=64){keep[i]=true;return keep;}
		int needed=64;
		for(int i:candidates){if(needed<=0)break;keep[i]=true;needed-=stacks.get(i).count;}
		return keep;
	}
	private static int reserveRank(String id){
		if(id.equals("minecraft:dirt")||id.equals("minecraft:coarse_dirt"))return 0;
		if(Set.of("minecraft:cobblestone","minecraft:cobbled_deepslate","minecraft:netherrack").contains(id))return 1;
		return stone(id)?2:3;
	}
	static int next(List<Stack> stacks, boolean discard) {
		return next(stacks, discard, i -> true);
	}
	static int next(List<Stack> stacks, boolean discard, java.util.function.IntPredicate fits) {
		boolean[] keep = discard ? reserved(stacks) : reservedForStore(stacks);
		for (int i = 0; i < stacks.size(); i++) if (!keep[i] && stacks.get(i).count > 0
			&& (discard ? stone(stacks.get(i).id) : depositable(stacks.get(i))) && fits.test(i)) return i;
		return -1;
	}
	static boolean outside(int x, int z, int minX, int minZ, int maxX, int maxZ) {
		return x <= minX - 4 || x >= maxX + 4 || z <= minZ - 4 || z >= maxZ + 4;
	}
	private BorerCargoPolicy() {}
}
