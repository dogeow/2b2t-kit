package dev.twob2tkit.runtime.engine;

import java.util.List;
import java.util.TreeSet;

/** Capacity observed in the owned server menu, not guessed from a chest block entity. */
record BorerCargoCapacity(boolean full, List<String> accepts) {
	record Slot(String id, int count, int max, boolean ordinary) {}
	static BorerCargoCapacity of(List<Slot> slots) {
		if (slots.isEmpty()) throw new IllegalArgumentException("No container slots");
		boolean full = true, empty = false;
		var partial = new TreeSet<String>();
		for (Slot slot : slots) {
			if (slot.count <= 0) { empty = true; full = false; }
			else if (slot.count < slot.max) {
				full = false;
				if (slot.ordinary && BorerCargoPolicy.material(slot.id)) partial.add(slot.id);
			}
		}
		return new BorerCargoCapacity(full, empty ? null : List.copyOf(partial));
	}
}
