package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.*;
import net.minecraft.network.chat.Component;
import java.util.*;

/**
 * Toolbox overview: what is running (with its live status and a stop button), favorites and recent pages.
 * It only navigates or stops; it never starts automation.
 */
public class KitWorkspaceScreen extends KitHudScreen {
    private static final int ROW = 24;
    protected final KitConfig config;
    protected final KitController controller;
    private UiPageLayout layout;
    private List<UiFeature> shownRunning = List.of();
    private final List<StatusLine> statusLines = new ArrayList<>();
    private int scroll, contentHeight;
    private final List<Placed> placed = new ArrayList<>();
    private record Placed(AbstractWidget widget, int y) {}
    private record StatusLine(UiFeature feature, StringWidget widget, int width) {}

    public KitWorkspaceScreen(KitConfig config, KitController controller) {
        super(Component.literal("2b2t 工具箱"), null); this.config = config; this.controller = controller;
    }
    /** Kept for old callers that still pass a category; the overview no longer has category tabs. */
    public KitWorkspaceScreen(KitConfig config, KitController controller, UiFeature.Category category) { this(config, controller); }

    @Override protected UiFeature navFeature() { return null; }

    @Override protected void init() {
        layout = UiPageLayout.workspace(width, height);
        placed.clear(); statusLines.clear();
        shownRunning = UiFeature.running();
        int y = layout.top();
        y = heading("运行中", y);
        if (shownRunning.isEmpty()) y = hint("没有正在运行的任务", y);
        for (UiFeature f : shownRunning) {
            int buttons = 48 + 4 + 48, textWidth = layout.width() - buttons - 8;
            String title = KitUi.fit(font, f.title, textWidth);
            place(new StringWidget(layout.left(), y + 1, font.width(title), 10, Component.literal(title).withColor(0x77EE99), font), y);
            var status = new StringWidget(layout.left(), y + 12, 1, 10, Component.empty(), font);
            place(status, y + 12); statusLines.add(new StatusLine(f, status, textWidth));
            int x = layout.left() + layout.width() - buttons;
            place(Button.builder(Component.literal("打开"), b -> f.open(this)).bounds(x, y, 48, 20).build(), y);
            place(Button.builder(Component.literal("停止"), b -> { f.stop(minecraft); showNotice("已停止：" + f.title, 0xFFFF55); rebuildWidgets(); })
                .bounds(x + 52, y, 48, 20).tooltip(Tooltip.create(Component.literal("只停止这一项"))).build(), y);
            y += ROW + 6;
        }
        updateStatus();
        y += 6;
        List<UiFeature> favorites = UiFeature.resolve(config.favoriteUiFeatures);
        y = heading("★ 收藏", y);
        y = favorites.isEmpty() ? hint("在左侧功能名右边点 ☆ 加入收藏", y) : grid(favorites, y);
        List<UiFeature> recent = UiFeature.resolve(config.recentUiFeatures).stream().filter(f -> !favorites.contains(f)).limit(6).toList();
        if (!recent.isEmpty()) { y += 6; y = heading("最近使用", y); y = grid(recent, y); }
        contentHeight = y - layout.top();
        if (!sidebarShown()) {
            // Narrow screens hide the navigation column: offer the full catalog here instead.
            addRenderableWidget(Button.builder(Component.literal("紧急停止全部"), b -> { KitClient.emergencyStop("工具箱停止全部"); showNotice("任务与独立防护已停止", 0xFFFF55); })
                .bounds(layout.footerButtonX(0, 2), layout.footer(), layout.footerButtonWidth(2), 20).build());
            addRenderableWidget(Button.builder(Component.literal("返回游戏"), b -> minecraft.gui.setScreen(null))
                .bounds(layout.footerButtonX(1, 2), layout.footer(), layout.footerButtonWidth(2), 20).build());
            y += 6; y = heading("全部功能", y);
            for (var category : UiFeature.Category.values()) if (category != UiFeature.Category.HOME) {
                y = hint(category.label, y); y = grid(UiFeature.listed(category), y);
            }
            contentHeight = y - layout.top();
        }
        positionEntries();
    }

    private int heading(String text, int y) {
        place(new StringWidget(layout.left(), y, font.width(text), 10, Component.literal(text).withColor(0x8DAEC0), font), y);
        return y + 14;
    }
    private int hint(String text, int y) {
        String shown = KitUi.fit(font, text, layout.width());
        place(new StringWidget(layout.left(), y, font.width(shown), 10, Component.literal(shown).withColor(0xAABBCC), font), y);
        return y + 14;
    }
    /** Feature buttons, two or three per row; a running feature is prefixed with a dot. */
    private int grid(List<UiFeature> features, int y) {
        int columns = layout.width() >= 420 ? 3 : 2, gap = 6, w = (layout.width() - (columns - 1) * gap) / columns;
        for (int i = 0; i < features.size(); i++) {
            UiFeature f = features.get(i);
            int x = layout.left() + (i % columns) * (w + gap), rowY = y + (i / columns) * ROW;
            place(Button.builder(Component.literal(KitUi.fit(font, (f.activeInNav() ? "● " : "") + f.title, w - 8)), b -> f.open(this))
                .bounds(x, rowY, w, 20).tooltip(Tooltip.create(Component.literal(f.description))).build(), rowY);
        }
        return y + ((features.size() + columns - 1) / columns) * ROW;
    }
    private void place(AbstractWidget widget, int y) { placed.add(new Placed(addRenderableWidget(widget), y)); }
    private void positionEntries() {
        scroll = layout.clampScroll(scroll, contentHeight);
        for (Placed p : placed) {
            int y = p.y() - scroll; p.widget().setY(y);
            p.widget().visible = p.widget().active = layout.fullyVisible(y, Math.min(p.widget().getHeight(), 20));
        }
    }
    private void updateStatus() {
        for (StatusLine line : statusLines) {
            String value = line.feature().status(); String shown = KitUi.fit(font, value, line.width());
            line.widget().setMessage(Component.literal(shown).withColor(0xAABBCC)); line.widget().setWidth(Math.max(1, font.width(shown)));
            line.widget().setTooltip(value.isBlank() ? null : Tooltip.create(Component.literal(value)));
        }
    }
    @Override public void tick() {
        super.tick();
        if (!UiFeature.running().equals(shownRunning)) rebuildWidgets(); else updateStatus();
    }
    @Override public boolean mouseScrolled(double x, double y, double sx, double sy) {
        if (!overSidebar(x) && y >= layout.top() && y < layout.bottom()) { scroll -= (int)(sy * ROW); positionEntries(); return true; }
        return super.mouseScrolled(x, y, sx, sy);
    }
    @Override protected boolean onEnterPressed() { return false; }
    @Override public void extractRenderState(GuiGraphicsExtractor g, int x, int y, float delta) {
        super.extractRenderState(g, x, y, delta);
        KitUi.text(g, font, "总览", layout.left(), 14, 0xFFFFFF);
        KitUi.text(g, font, KitUi.fit(font, "左侧选择功能 · 打开页面不会自动开始 · Esc 返回游戏", layout.width()), layout.left(), 32, 0x8DA0B0);
        if (!notice.isEmpty()) KitUi.text(g, font, KitUi.fit(font, notice, layout.width()), layout.left(), layout.footer() + (sidebarShown() ? 6 : -14), noticeColor);
    }
}
