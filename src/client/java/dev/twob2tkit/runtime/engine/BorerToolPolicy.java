package dev.twob2tkit.runtime.engine;

import java.util.List;
import java.util.Set;

/** One live AutoTool policy for both selecting reserves and deciding to log out. */
record BorerToolPolicy(boolean antiBreak, int percentage, String listMode, Set<?> items) {
	static final BorerToolPolicy DEFAULT = new BorerToolPolicy(false, 0, "None", Set.of());
	BorerToolPolicy {
		if (percentage < 0 || percentage > 100) throw new IllegalArgumentException("Invalid anti-break percentage");
		if (!Set.of("None", "Whitelist", "Blacklist").contains(listMode)) throw new IllegalArgumentException("Unknown tool list mode");
		items = Set.copyOf(items);
	}
	boolean allows(Object item, boolean damageable, int maxDamage, int remaining) {
		boolean listed = items.contains(item);
		if (listMode.equals("Whitelist") && !listed || listMode.equals("Blacklist") && listed) return false;
		if (!damageable) return true;
		// Meteor 26.1.2 uses integer division and STRICT less-than, not <= percentage.
		return remaining > 8 && (!antiBreak || remaining >= (long) maxDamage * percentage / 100);
	}
	record Candidate(int slot, boolean pickaxe, boolean usable, float score) {}
	static boolean exhausted(List<Candidate> tools) {
		return tools.stream().anyMatch(Candidate::pickaxe)
			&& tools.stream().noneMatch(t -> t.pickaxe() && t.usable());
	}
	static int choose(List<Candidate> tools, int selected) {
		int best = -1;
		float score = -1;
		for (Candidate tool : tools) {
			if (!tool.usable() || tool.score() < 0) continue;
			if (tool.score() > score + 0.01F || tool.slot() == selected && Math.abs(tool.score() - score) <= 0.01F) {
				best = tool.slot(); score = tool.score();
			}
		}
		return best;
	}
	String describe() { return "antiBreak=" + antiBreak + " percentage=" + percentage + " list=" + listMode; }
}
