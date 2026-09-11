package dev.twob2tkit.recipe;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;
import dev.twob2tkit.ItemIconButton;

/** 本地配方指南界面。 */
public final class RecipeGuideScreen extends KitHudScreen {
	private static final int PANEL_W = 400;
	private static final int SEARCH_W = 196;
	private static final RecipeCategory[] CATEGORIES = RecipeCategory.values();

	private final KitConfig config;
	private EditBox search;
	private String draftQuery = "";
	private String selectedId = "";
	private String selectedCategory = "all";
	private int page;

	/** 打开本地配方指南屏。 */
	public RecipeGuideScreen(Screen parent, KitConfig config) {
		super(Component.literal("twob2tkit 本地配方指南"), parent);
		this.config = config;
	}

	@Override
	/** 分类、搜索与配方列表。 */
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirect("RECIPES", parent)) return;
		int left = panelLeft(PANEL_W);
		if (search != null) draftQuery = search.getValue();

		int searchY = bodyTop(36);
		int catY = bodyTop(44);
		search = addRenderableWidget(KitUi.field(this.font, left, searchY, SEARCH_W, "搜索", draftQuery, 40));
		search.setHint(Component.literal("例如 熔炉"));
		search.setResponder(query -> {
			if (query.equals(draftQuery)) return;
			draftQuery = query;
			page = 0;
			selectedId = "";
			rebuildWidgets();
		});
		addRenderableWidget(Button.builder(Component.literal("手里的"), button -> useHeldItem())
			.bounds(left + SEARCH_W + 6, searchY, 64, 20)
			.tooltip(Tooltip.create(Component.literal("按主手物品列出：怎么做它，以及用它能做什么。")))
			.build());

		int catW = 48;
		int catGap = 2;
		for (int i = 0; i < CATEGORIES.length; i++) {
			RecipeCategory cat = CATEGORIES[i];
			int x = left + i * (catW + catGap);
			boolean chosen = cat.id.equals(selectedCategory);
			Button button = addRenderableWidget(Button.builder(Component.literal(cat.label), ignored -> selectCategory(cat.id))
				.bounds(x, catY, catW, 18).build());
			button.active = !chosen;
		}

		List<LocalRecipes.Entry> visible = visibleRecipes();
		int pageSize = listPageSize();
		int maxPage = visible.isEmpty() ? 0 : (visible.size() - 1) / pageSize;
		page = Math.max(0, Math.min(page, maxPage));
		LocalRecipes.Entry selected = selectedRecipe(visible);
		int start = page * pageSize;
		int end = Math.min(visible.size(), start + pageSize);
		for (int i = start; i < end; i++) {
			LocalRecipes.Entry recipe = visible.get(i);
			int y = listTop() + (i - start) * 22;
			boolean chosen = selected != null && selected.id().equals(recipe.id());
			ItemIconButton icon = addRenderableWidget(new ItemIconButton(
				left, y, 20, 20, recipe.output(), Component.literal(recipe.name()), () -> selectRecipe(recipe)));
			icon.setChosen(chosen);
			Button row = addRenderableWidget(Button.builder(
				Component.literal(KitUi.fit(this.font, recipe.name(), 168)),
				button -> selectRecipe(recipe)
			).bounds(left + 22, y, 176, 20)
				.tooltip(Tooltip.create(Component.literal(recipe.name() + "\n点一下看右边合成表。格子里的材料再点可以接着查。")))
				.build());
			row.active = !chosen;
		}

		if (selected != null) addCraftingGrid(left + 210, listTop(), selected);

		int footerY = footerButtonY();
		addRenderableWidget(Button.builder(Component.literal("上一页"), button -> changePage(-1)).bounds(left, footerY, 85, 20).build())
			.active = page > 0;
		addRenderableWidget(Button.builder(Component.literal("下一页"), button -> changePage(1)).bounds(left + 92, footerY, 85, 20).build())
			.active = page < maxPage;
		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose()).bounds(left + 185, footerY, 215, 20).build());
		setInitialFocus(search);
	}

	@Override
	/** 画合成预览与列表。 */
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		int left = panelLeft(PANEL_W);
		int center = this.width / 2;
		List<LocalRecipes.Entry> visible = visibleRecipes();
		LocalRecipes.Entry selected = selectedRecipe(visible);
		int gx = left + 210;
		int gy = listTop();
		if (selected != null) drawCraftingBackground(graphics, gx, gy);

		super.extractRenderState(graphics, mouseX, mouseY, delta);

		KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(10), 0xFFFFFF);
		KitUi.centered(graphics, this.font, "选分类或搜名称；右侧看合成表", center, headerY(24), 0xA0A0A0);

		if (visible.isEmpty()) {
			KitUi.centered(graphics, this.font, "这个分类下没有匹配的配方", center, bodyTop(156), 0xA0A0A0);
		} else if (selected != null) {
			drawCraftingItems(graphics, selected, gx, gy);
			KitUi.text(graphics, this.font, needsCraftingTable(selected) ? "需要工作台" : "背包 2×2 就能做", gx, gy + 72, 0xA0A0A0);
		}

		int pageSize = listPageSize();
		int maxPage = visible.isEmpty() ? 0 : (visible.size() - 1) / pageSize;
		String footer = categoryLabel() + "  第 " + (page + 1) + "/" + (maxPage + 1) + " 页  共 " + visible.size() + " 条";
		if (!notice.isEmpty()) footer += "  " + notice;
		KitUi.centered(graphics, this.font, footer, center, footerButtonY() - 22, notice.isEmpty() ? 0xA0A0A0 : 0x55FF55);
	}

	/** 画合成格底图。 */
	private static void drawCraftingBackground(GuiGraphicsExtractor graphics, int gx, int gy) {
		for (int i = 0; i < 9; i++) {
			int x = gx + (i % 3) * 22;
			int y = gy + (i / 3) * 22;
			graphics.fill(x, y, x + 20, y + 20, 0xFF2A2A2A);
			graphics.fill(x + 1, y + 1, x + 19, y + 19, 0xFF1A1A1A);
		}
		graphics.fill(gx + 72, gy + 22, gx + 80, gy + 42, 0xFF555555);
		graphics.fill(gx + 88, gy + 18, gx + 112, gy + 42, 0xFF2A2A2A);
	}

	/** 画合成格物品。 */
	private void drawCraftingItems(GuiGraphicsExtractor graphics, LocalRecipes.Entry recipe, int gx, int gy) {
		ItemStack[] grid = recipe.grid();
		for (int i = 0; i < 9; i++) {
			ItemStack slot = grid[i];
			if (slot == null || slot.isEmpty()) continue;
			int x = gx + (i % 3) * 22;
			int y = gy + (i / 3) * 22;
			graphics.item(slot, x + 2, y + 2);
		}
		ItemStack output = recipe.output();
		graphics.item(output, gx + 92, gy + 22);
		if (output.getCount() > 1) {
			KitUi.text(graphics, this.font, "×" + output.getCount(), gx + 114, gy + 24, 0xFFFFFF);
		}
	}

	/** 布置合成预览区。 */
	private void addCraftingGrid(int gx, int gy, LocalRecipes.Entry recipe) {
		ItemStack[] grid = recipe.grid();
		for (int i = 0; i < 9; i++) {
			ItemStack slot = grid[i];
			if (slot == null || slot.isEmpty()) continue;
			int x = gx + (i % 3) * 22;
			int y = gy + (i / 3) * 22;
			ItemStack ingredient = slot;
			if (LocalRecipes.hasRecipe(ingredient.getItem())) {
				addRenderableWidget(new ItemIconButton(
					x, y, 20, 20, ingredient,
					Component.literal(ingredient.getHoverName().getString() + "\n点击查看怎么做"),
					() -> showRecipesFor(ingredient)));
			}
		}
		ItemStack output = recipe.output();
		addRenderableWidget(new ItemIconButton(
			gx + 90, gy + 20, 20, 20, output,
			Component.literal(output.getHoverName().getString()),
			() -> {
			}));
	}

	/** 当前筛选可见配方。 */
	private List<LocalRecipes.Entry> visibleRecipes() {
		String query = search != null ? search.getValue() : draftQuery;
		List<LocalRecipes.Entry> result = new ArrayList<>();
		for (LocalRecipes.Entry entry : LocalRecipes.entries()) {
			if (!entry.matchesCategory(selectedCategory)) continue;
			if (query != null && !query.trim().isEmpty() && !entry.matches(query)) continue;
			result.add(entry);
		}
		if (query != null && !query.trim().isEmpty()) {
			String needle = query.trim().toLowerCase(Locale.ROOT);
			Item held = heldItem();
			result.sort(Comparator
				.comparingInt((LocalRecipes.Entry entry) -> searchRank(entry, needle, held))
				.thenComparing(LocalRecipes.Entry::name, String.CASE_INSENSITIVE_ORDER));
		}
		return result;
	}

	/** 当前选中配方。 */
	private LocalRecipes.Entry selectedRecipe(List<LocalRecipes.Entry> visible) {
		if (visible.isEmpty()) return null;
		for (LocalRecipes.Entry entry : visible) {
			if (entry.id().equals(selectedId)) return entry;
		}
		return visible.getFirst();
	}

	/** 选中一条配方。 */
	private void selectRecipe(LocalRecipes.Entry recipe) {
		selectedId = recipe.id();
		rebuildWidgets();
	}

	/** 切换分类。 */
	private void selectCategory(String category) {
		if (category.equals(selectedCategory)) return;
		selectedCategory = category;
		page = 0;
		selectedId = "";
		rebuildWidgets();
	}

	/** 当前分类显示名。 */
	private String categoryLabel() {
		for (RecipeCategory cat : CATEGORIES) {
			if (cat.id.equals(selectedCategory)) return cat.label;
		}
		return "全部";
	}

	/** 只显示产出/用到该物品的配方。 */
	private void showRecipesFor(ItemStack stack) {
		if (stack == null || stack.isEmpty()) return;
		if (!LocalRecipes.hasRecipe(stack.getItem())) {
			showNotice(stack.getHoverName().getString() + " 没有合成来源", 0xA0A0A0);
			return;
		}
		saveDraft();
		draftQuery = stack.getHoverName().getString();
		page = 0;
		selectedId = "";
		for (LocalRecipes.Entry entry : LocalRecipes.entries()) {
			if (entry.output().is(stack.getItem())) {
				selectedId = entry.id();
				break;
			}
		}
		rebuildWidgets();
	}

	/** 用手里物品筛选。 */
	private void useHeldItem() {
		if (this.minecraft == null || this.minecraft.player == null) return;
		ItemStack held = this.minecraft.player.getMainHandItem();
		if (held.isEmpty()) {
			showNotice("先拿着要查的物品", 0xFF5555);
			return;
		}
		draftQuery = "";
		selectedId = "";
		page = 0;
		for (LocalRecipes.Entry entry : LocalRecipes.entries()) {
			if (entry.output().is(held.getItem())) {
				selectedId = entry.id();
				break;
			}
		}
		rebuildWidgets();
	}

	/** 当前手里物品。 */
	private Item heldItem() {
		if (this.minecraft == null || this.minecraft.player == null) return null;
		ItemStack held = this.minecraft.player.getMainHandItem();
		return held.isEmpty() ? null : held.getItem();
	}

	/** 列表顶 Y。 */
	private int listTop() {
		return bodyTop(66);
	}

	/** 每页条数。 */
	private int listPageSize() {
		int avail = footerButtonY() - listTop() - 28;
		return Math.max(3, Math.min(7, avail / 22));
	}

	/** 翻页。 */
	private void changePage(int direction) {
		page += direction;
		rebuildWidgets();
	}

	@Override
	/** 关屏。 */
	public void onClose() {
		saveDraft();
		super.onClose();
	}

	@Override
	/** 滚轮翻页。 */
	public boolean mouseScrolled(double mouseX, double mouseY, double scrollX, double scrollY) {
		if (scrollY > 0) changePage(-1);
		else if (scrollY < 0) changePage(1);
		return true;
	}

	/** 保存搜索草稿。 */
	private void saveDraft() {
		if (search != null) draftQuery = search.getValue();
	}

	/** 搜索相关度排序键。 */
	private static int searchRank(LocalRecipes.Entry entry, String needle, Item held) {
		String name = entry.name().toLowerCase(Locale.ROOT);
		if (held != null && entry.output().is(held)) return 0;
		if (name.equals(needle) || entry.output().getHoverName().getString().toLowerCase(Locale.ROOT).equals(needle)) return 1;
		if (name.contains(needle)) return 2;
		return 3;
	}

	/** 是否需要工作台。 */
	private static boolean needsCraftingTable(LocalRecipes.Entry recipe) {
		int used = 0;
		for (int i = 0; i < recipe.grid().length; i++) {
			ItemStack stack = recipe.grid()[i];
			if (stack == null || stack.isEmpty()) continue;
			used++;
			if (i % 3 == 2 || i / 3 == 2) return true;
		}
		return used > 4;
	}

	private enum RecipeCategory {
		ALL("all", "全部"),
		BUILDING("building", "建筑"),
		BLOCKS("blocks", "方块"),
		REDSTONE("redstone", "红石"),
		EQUIPMENT("equipment", "装备"),
		FOOD("food", "食物"),
		MISC("misc", "杂项");

		final String id;
		final String label;

		RecipeCategory(String id, String label) {
			this.id = id;
			this.label = label;
		}
	}
}
