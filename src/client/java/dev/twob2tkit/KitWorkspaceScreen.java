package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.*;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import java.util.*;

/** Seven native categories, one catalog, explicit navigation. Clicking a name can never start automation. */
public class KitWorkspaceScreen extends KitHudScreen {
    protected final KitConfig config;
    protected final KitController controller;
    private UiFeature.Category category;
    private EditBox search;
    private String query = "";
    private int scroll;
    private final List<Placed> entries = new ArrayList<>();
    private UiPageLayout layout;
    private int bodyTop, bodyHeight, contentHeight;
    private record Placed(AbstractWidget widget, int y) {}
    public KitWorkspaceScreen(KitConfig config, KitController controller) { this(config, controller, UiFeature.Category.parse(config.workspaceCategory)); }
    public KitWorkspaceScreen(KitConfig config, KitController controller, UiFeature.Category category) {
        super(Component.literal("2b2t 工具箱"), null); this.config = config; this.controller = controller; this.category = category;
    }
    @Override protected void init() {
        if (search != null) query = search.getValue();
        layout = UiPageLayout.of(width, height);
        int n = UiFeature.Category.values().length, w = (layout.width() - (n - 1) * 3) / n;
        for (var item : UiFeature.Category.values()) {
            var button = addRenderableWidget(Button.builder(Component.literal(item.label), b -> {
                category = item; config.workspaceCategory = item.name(); config.save(); scroll = 0; query = ""; if (search != null) search.setValue(""); rebuildWidgets();
            }).bounds(layout.left() + item.ordinal() * (w + 3), 8, w, 20).build()); button.active = item != category;
        }
        search = addRenderableWidget(KitUi.field(font, layout.left(), 36, layout.width(), "搜索全部功能", query, 80));
        search.setHint(Component.literal("搜索全部功能，例如：钻石、箱子、飞行、按键…"));
        search.setResponder(value -> { query = value; scroll = 0; rebuildEntries(); });
        bodyTop = 64; bodyHeight = Math.max(28, layout.footer() - 22 - bodyTop);
        rebuildEntries();
        addRenderableWidget(Button.builder(Component.literal("紧急停止全部"), b -> { KitClient.emergencyStop("工具箱停止全部"); showNotice("任务与独立防护已停止", 0xFFFF55); })
            .bounds(layout.footerButtonX(0, 2), layout.footer(), layout.footerButtonWidth(2), 20).build());
        addRenderableWidget(Button.builder(Component.literal("返回游戏"), b -> minecraft.setScreen(null))
            .bounds(layout.footerButtonX(1, 2), layout.footer(), layout.footerButtonWidth(2), 20).build());
    }
    private List<UiFeature> selected() {
        if (!query.isBlank()) return Arrays.stream(UiFeature.values()).filter(f -> f.matches(query)).toList();
        if (category != UiFeature.Category.HOME) return Arrays.stream(UiFeature.values()).filter(f -> f.category == category).toList();
        Set<UiFeature> home = new LinkedHashSet<>();
        for (var feature : UiFeature.values()) if (feature.active()) home.add(feature);
        if (config.favoriteUiFeatures != null) for (String id : config.favoriteUiFeatures) { var f = UiFeature.find(id); if (f != null) home.add(f); }
        if (config.recentUiFeatures != null) for (String id : config.recentUiFeatures) { var f = UiFeature.find(id); if (f != null) home.add(f); }
        home.addAll(List.of(UiFeature.AREA, UiFeature.ORE, UiFeature.CRUISE, UiFeature.PLACES, UiFeature.SCENERY, UiFeature.CHECKLIST));
        return List.copyOf(home);
    }
    private void rebuildEntries() {
        for (Placed p : entries) removeWidget(p.widget()); entries.clear();
        List<UiFeature> features = selected();
        UiFeatureGridLayout grid = UiFeatureGridLayout.of(layout, features.size());
        for (int i = 0; i < features.size(); i++) {
            UiFeature feature = features.get(i);
            int x = grid.x(i), y = grid.y(i, bodyTop);
            String prefix = feature.active() ? "运行中 · " : "";
            Button open = Button.builder(Component.literal(prefix + feature.title + "  ›"), b -> feature.open(this))
                .bounds(x, y, grid.openWidth(), 20).tooltip(Tooltip.create(Component.literal(feature.description))).build();
            entries.add(new Placed(addRenderableWidget(open), y));
            boolean favorite = config.favoriteUiFeatures != null && config.favoriteUiFeatures.contains(feature.name());
            Button pin = Button.builder(Component.literal(favorite ? "★" : "☆"), b -> {
                if (config.favoriteUiFeatures == null) config.favoriteUiFeatures = new LinkedHashSet<>();
                if (!config.favoriteUiFeatures.add(feature.name())) config.favoriteUiFeatures.remove(feature.name()); config.save(); rebuildEntries();
            }).bounds(grid.favoriteX(i), y, UiFeatureGridLayout.FAVORITE_WIDTH, 20).tooltip(Tooltip.create(Component.literal(favorite ? "取消常用" : "添加到首页常用"))).build();
            entries.add(new Placed(addRenderableWidget(pin), y));
            String summary = KitUi.fit(font, feature.description, grid.cardWidth() - 12);
            var info = new StringWidget(x + 6, y + 22, font.width(summary), 10,
                Component.literal(summary).withColor(0xA9B9C9), font);
            entries.add(new Placed(addRenderableWidget(info), y + 22));
        }
        contentHeight = grid.contentHeight(); positionEntries();
    }
    private void positionEntries() {
        scroll = Math.max(0, Math.min(scroll, Math.max(0, contentHeight - bodyHeight)));
        for (Placed p : entries) {
            int y = p.y() - scroll; p.widget().setY(y);
            p.widget().visible = p.widget().active = y >= bodyTop && y + p.widget().getHeight() <= bodyTop + bodyHeight;
        }
    }
    @Override public boolean mouseScrolled(double x, double y, double sx, double sy) {
        if (y >= bodyTop && y < bodyTop + bodyHeight) { scroll -= (int)(sy * UiFeatureGridLayout.ROW_HEIGHT); positionEntries(); return true; }
        return super.mouseScrolled(x, y, sx, sy);
    }
    @Override protected boolean onEnterPressed() { return false; }
    @Override public void extractRenderState(GuiGraphicsExtractor g, int x, int y, float delta) {
        super.extractRenderState(g, x, y, delta);
        if (config.clickGui) g.fill(layout.left(), 30, layout.left() + layout.width(), 32, 0xFF6FA9B6);
        if (entries.isEmpty()) KitUi.centered(g, font, "没有匹配功能，换个关键词试试", width / 2, bodyTop + 8, 0xAABBCC);
        String running = Arrays.stream(UiFeature.values()).filter(UiFeature::active).map(f -> f.title).collect(java.util.stream.Collectors.joining(" · "));
        String status = !notice.isEmpty() ? notice : running.isEmpty() ? "点击功能进入配置 · ☆ 设为常用 · Esc 返回游戏" : "正在运行：" + running;
        KitUi.text(g, font, KitUi.fit(font, status, layout.width()), layout.left(), layout.footer() - 14, notice.isEmpty() ? 0xAABBCC : noticeColor);
    }
    public void showDetail(KitFormScreen screen) { minecraft.setScreen(screen.bind(config)); }
    public void switchToPages() { config.clickGui = false; config.save(); minecraft.setScreen(new KitWorkspaceScreen(config, controller, UiFeature.Category.SETTINGS)); }
}
