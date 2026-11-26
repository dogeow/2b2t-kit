package dev.twob2tkit;

import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.narration.NarratedElementType;
import net.minecraft.client.gui.narration.NarrationElementOutput;
import net.minecraft.client.input.MouseButtonEvent;
import net.minecraft.network.chat.Component;

/**
 * Toolbox navigation column. Clicking a name only opens a page; the ☆ at the right edge of a row
 * toggles the favorite. Running features carry a green dot. Query and scroll last for the session.
 */
final class UiSidebar extends AbstractWidget {
	private static final int STAR_WIDTH = 12;
	private static String query = "";
	private static int scroll;

	private final Font font;
	private final KitConfig config;
	private final UiFeature current;
	private final boolean overview;
	private List<UiNavModel.Row> rows = List.of();
	private int hovered = -1;

	UiSidebar(Font font, KitConfig config, UiFeature current, boolean overview, int x, int y, int width, int height) {
		super(x, y, width, height, Component.literal("导航"));
		this.font = font; this.config = config; this.current = current == null ? null : current.nav(); this.overview = overview;
		refresh();
	}

	static String query() { return query; }

	void search(String value) { query = value == null ? "" : value; scroll = 0; refresh(); }

	private void refresh() {
		if (config.collapsedNavGroups == null) config.collapsedNavGroups = new LinkedHashSet<>();
		rows = UiNavModel.rows(query, config.favoriteUiFeatures, config.collapsedNavGroups);
		scroll = UiNavModel.clampScroll(scroll, UiNavModel.contentHeight(rows), getHeight());
	}

	@Override
	protected void extractWidgetRenderState(GuiGraphicsExtractor g, int mouseX, int mouseY, float delta) {
		int x = getX(), y = getY(), w = getWidth(), h = getHeight();
		g.fill(x, y, x + w, y + h, 0x66101820);
		int index = isMouseOver(mouseX, mouseY) ? UiNavModel.rowAt(rows, mouseY - y + scroll) : -1;
		if (index != hovered) { hovered = index; setTooltip(index < 0 ? null : tooltip(rows.get(index))); }
		for (int i = 0; i < rows.size(); i++) {
			int top = y + i * UiNavModel.ROW_HEIGHT - scroll;
			if (top < y || top + UiNavModel.ROW_HEIGHT > y + h) continue;
			var row = rows.get(i);
			boolean selected = row.kind() == UiNavModel.Kind.OVERVIEW ? overview
				: row.feature() != null && current != null && (row.feature() == current || row.feature().nav() == current && "SEARCH".equals(row.group()));
			if (selected) g.fill(x, top, x + w, top + UiNavModel.ROW_HEIGHT, 0xFF2D4A5E);
			else if (i == hovered) g.fill(x, top, x + w, top + UiNavModel.ROW_HEIGHT, 0x44FFFFFF);
			switch (row.kind()) {
				case OVERVIEW -> {
					int running = UiFeature.running().size();
					KitUi.text(g, font, KitUi.fit(font, "⌂ 总览" + (running > 0 ? " · 运行 " + running : ""), w - 6), x + 3, top + 2, running > 0 ? 0x77EE99 : 0xFFFFFF);
				}
				case HEADER -> KitUi.text(g, font, KitUi.fit(font, row.label(), w - 6), x + 3, top + 2, 0x8DAEC0);
				case FEATURE -> {
					var f = row.feature();
					if (f.activeInNav()) g.fill(x + 4, top + 4, x + 8, top + 8, 0xFF55EE77);
					KitUi.text(g, font, KitUi.fit(font, row.label(), w - 14 - STAR_WIDTH), x + 11, top + 2, selected ? 0xFFFFFF : 0xD8E2EA);
					boolean favorite = f.favorite(config);
					if (favorite || i == hovered) KitUi.text(g, font, favorite ? "★" : "☆", x + w - STAR_WIDTH + 1, top + 2, favorite ? 0xFFDD55 : 0x8DAEC0);
				}
			}
		}
		int content = UiNavModel.contentHeight(rows);
		if (content > h) {
			int thumb = Math.max(10, h * h / content), ty = y + (h - thumb) * scroll / Math.max(1, content - h);
			g.fill(x + w - 2, ty, x + w, ty + thumb, 0xFF8DAEC0);
		}
	}

	private Tooltip tooltip(UiNavModel.Row row) {
		return switch (row.kind()) {
			case OVERVIEW -> Tooltip.create(Component.literal("运行中的任务、收藏和最近使用"));
			case HEADER -> "SEARCH".equals(row.group()) ? null : Tooltip.create(Component.literal("点击折叠 / 展开"));
			case FEATURE -> Tooltip.create(Component.literal(row.feature().description + "\n点击打开 · 点右侧 ☆ 收藏"));
		};
	}

	@Override
	public void onClick(MouseButtonEvent event, boolean doubleClick) {
		int index = UiNavModel.rowAt(rows, (int) event.y() - getY() + scroll);
		if (index < 0) return;
		var row = rows.get(index);
		var mc = Minecraft.getInstance();
		switch (row.kind()) {
			case OVERVIEW -> mc.gui.setScreen(new KitWorkspaceScreen(config, KitClient.controller()));
			case HEADER -> {
				if ("SEARCH".equals(row.group())) return;
				UiNavModel.toggle(config.collapsedNavGroups, row.group()); config.save(); refresh();
			}
			case FEATURE -> {
				if (event.x() >= getX() + getWidth() - STAR_WIDTH - 2) { row.feature().toggleFavorite(config); refresh(); return; }
				row.feature().open(null);
			}
		}
	}

	@Override
	public boolean mouseScrolled(double mouseX, double mouseY, double scrollX, double scrollY) {
		if (!isMouseOver(mouseX, mouseY)) return false;
		scroll = UiNavModel.clampScroll(scroll - (int) (scrollY * UiNavModel.ROW_HEIGHT * 2), UiNavModel.contentHeight(rows), getHeight());
		return true;
	}

	@Override
	protected void updateWidgetNarration(NarrationElementOutput output) {
		output.add(NarratedElementType.TITLE, Component.literal("工具箱导航"));
	}
}
