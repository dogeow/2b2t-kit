package dev.twob2tkit;

import java.util.*;

/** Rows of the navigation column: overview, favorites and one group per category, or search results. */
final class UiNavModel {
	static final int ROW_HEIGHT = 13;
	static final String FAVORITES = "FAVORITES";

	enum Kind { OVERVIEW, HEADER, FEATURE }

	/** {@code group} is a category name or {@link #FAVORITES}; {@code feature} is set only for feature rows. */
	record Row(Kind kind, String group, String label, UiFeature feature) {}

	private UiNavModel() {}

	static List<Row> rows(String query, Collection<String> favorites, Collection<String> collapsed) {
		List<Row> rows = new ArrayList<>();
		if (query != null && !query.isBlank()) {
			List<UiFeature> found = UiFeature.visible(UiFeature.Category.HOME, query, null);
			rows.add(new Row(Kind.HEADER, "SEARCH", found.isEmpty() ? "没有匹配功能" : "搜索结果 " + found.size(), null));
			for (UiFeature f : found) rows.add(new Row(Kind.FEATURE, "SEARCH", f.title, f));
			return rows;
		}
		Set<String> closed = collapsed == null ? Set.of() : new HashSet<>(collapsed);
		rows.add(new Row(Kind.OVERVIEW, "", "总览", null));
		List<UiFeature> favored = UiFeature.resolve(favorites);
		if (!favored.isEmpty()) group(rows, FAVORITES, "★ 收藏", favored, closed);
		for (UiFeature.Category category : UiFeature.Category.values())
			if (category != UiFeature.Category.HOME) group(rows, category.name(), category.label, UiFeature.listed(category), closed);
		return rows;
	}

	private static void group(List<Row> rows, String group, String label, List<UiFeature> features, Set<String> closed) {
		boolean open = !closed.contains(group);
		rows.add(new Row(Kind.HEADER, group, (open ? "▾ " : "▸ ") + label, null));
		if (open) for (UiFeature f : features) rows.add(new Row(Kind.FEATURE, group, f.title, f));
	}

	static int contentHeight(List<Row> rows) {
		return rows.size() * ROW_HEIGHT;
	}

	static int clampScroll(int scroll, int contentHeight, int viewHeight) {
		return Math.max(0, Math.min(scroll, Math.max(0, contentHeight - viewHeight)));
	}

	/** Row index under a y offset inside the scrolled list, or -1. */
	static int rowAt(List<Row> rows, int offsetY) {
		int index = Math.floorDiv(offsetY, ROW_HEIGHT);
		return offsetY < 0 || index >= rows.size() ? -1 : index;
	}

	/** Collapsing a group toggles it; collapsing favorites never touches the favorites themselves. */
	static void toggle(Set<String> collapsed, String group) {
		if (!collapsed.add(group)) collapsed.remove(group);
	}
}
