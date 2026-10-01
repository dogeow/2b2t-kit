package dev.twob2tkit;

import java.util.List;

/** Pure selection policy for the one global home among saved places. */
final class SavedPlaceHomePolicy {
	private SavedPlaceHomePolicy() {
	}

	static int selectedIndex(List<String> names, String wanted) {
		if (names == null || wanted == null || wanted.isBlank()) return -1;
		for (int index = 0; index < names.size(); index++) {
			String name = names.get(index);
			if (name != null && name.equalsIgnoreCase(wanted)) return index;
		}
		return -1;
	}
}
