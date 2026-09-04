package dev.twob2tkit.recipe;

/** 配方指南 tab 互斥分类：每条配方只进一个 tab，「全部」= 各分类条数之和。 */
public final class RecipeCategoryPolicy {
	private RecipeCategoryPolicy() {
	}

	/** 把 JSON 分类落到指南 tab（建筑/红石/装备/食物/方块/杂项）。 */
	public static String displayCategory(String jsonCategory, boolean blockOutput, boolean foodOutput) {
		return switch (jsonCategory) {
			case "building", "redstone", "equipment" -> jsonCategory;
			case "food" -> "food";
			default -> {
				if (foodOutput) yield "food";
				if (blockOutput) yield "blocks";
				yield "misc";
			}
		};
	}

	/** 当前筛选是否包含该配方；空或 all 表示全部。 */
	public static boolean matches(String filter, String jsonCategory, boolean blockOutput, boolean foodOutput) {
		if (filter == null || filter.isBlank() || filter.equals("all")) return true;
		return displayCategory(jsonCategory, blockOutput, foodOutput).equals(filter);
	}
}
