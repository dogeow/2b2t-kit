package dev.twob2tkit.borer;

import dev.twob2tkit.*;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.AbstractWidget;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import java.util.ArrayList;
import java.util.List;

/** A single scrollable task page with save/load/run always visible. */
public final class AreaSetupScreen extends KitHudScreen {
    private final KitConfig config;
    private EditBox a, b, name, length, widthField, heightField;
    private final List<Positioned> content = new ArrayList<>();
    private int scroll, contentHeight, top, bottom;
    private AreaDrafts.Draft draft;
    private boolean overwriteConfirmed;
    private record Positioned(AbstractWidget widget, int y) {}
    public AreaSetupScreen(Screen parent, KitConfig config) {
        super(Component.literal("区域挖"), parent); this.config = config;
    }
    @Override protected void init() {
        rememberDraft(false);
        draft = AreaDrafts.open(config, AreaDrafts.context(this.minecraft));
        content.clear();
        int left = panelLeft(panelWidth());
        button(left, 8, 58, "‹ 返回", this::onClose);
        button(left + panelWidth() - 76, 8, 76, "紧急停止", () -> KitClient.emergencyStop("区域页紧急停止"));
        int third = (panelWidth() - 12) / 3;
        addRenderableWidget(Button.builder(Component.literal("范围与工程"), b -> {}).bounds(left, 36, third, 20).build()).active = false;
        button(left + third + 6, 36, third, "物资与安全", () -> UiFeature.BORER_SAFETY.open(this));
        button(left + 2 * (third + 6), 36, third, "运行情况", this::showRunState);
        top = 64; bottom = footerButtonY() - 42;
        int y = top;
        name = field(left, y, "工程名称", draft.name()); y += 28;
        a = pointField(left, y, true, draft.a()); y += panelWidth() >= 480 ? 28 : 52;
        b = pointField(left, y, false, draft.b()); y += panelWidth() >= 480 ? 30 : 54;
        for (String line : KitUi.wrap(font, "可以先标 A，关闭菜单去标 B；输入自动暂存。完整范围校验后才可开挖。", panelWidth())) {
            track(label(left, y, panelWidth(), line, 0x99BBCC), y); y += 12;
        }
        y += 6;
        rowButton(left, y, "显示已应用黄框", () -> setOutline(true));
        rowButton(left + half() + 6, y, "隐藏黄框", () -> setOutline(false)); y += 28;
        track(label(left, y, panelWidth(), "按尺寸生成：长 X × 宽 Z × 向下高度 Y", 0x99BBCC), y); y += 16;
        length = small(left, y, "长 X", draft.length());
        widthField = small(left + (panelWidth() + 4) / 3, y, "宽 Z", draft.width());
        heightField = small(left + 2 * ((panelWidth() + 4) / 3), y, "高 Y", draft.height()); y += 28;
        rowButton(left, y, "从脚下生成区域", this::generate);
        rowButton(left + half() + 6, y, "应用并预览范围", () -> {
            if (apply()) { this.minecraft.setScreen(null); KitClient.borer().previewArea(this.minecraft); }
        }); y += 28;
        for (String line : KitUi.wrap(font, "自动：实际 1–6 层水平清挖，更深区域用竖井；两角都包含，同 Y 表示挖到世界底部。保存草稿不改变执行中的区域。", panelWidth())) {
            track(label(left, y, panelWidth(), line, 0xCCCC99), y); y += 12;
        }
        y += 8;
        rowButton(left, y, "新建空白草稿", () -> minecraft.setScreen(new KitConfirmScreen(this, "新建区域草稿",
            "清空当前未保存输入；已保存工程和挖掘进度保留。", () -> {
                name.setValue(BorerAreaProjects.defaultName(config)); a.setValue(""); b.setValue("");
                rememberDraft(true); showNotice("已建立空白草稿，原工程保留", 0x77DDCC);
            })));
        rowButton(left + half() + 6, y, "挖矿物资清单", () -> UiFeature.CHECKLIST.open(this)); y += 28;
        contentHeight = y - top;
        int footer = footerButtonY();
        var footerLayout = UiPageLayout.of(this.width, this.height);
        int actionLeft = footerLayout.footerButtonX(0, 2), actionRight = footerLayout.footerButtonX(1, 2), actionWidth = footerLayout.footerButtonWidth(2);
        button(actionLeft, footer - 26, actionWidth, "保存草稿 / 工程", this::saveProject);
        button(actionRight, footer - 26, actionWidth, "加载 / 管理工程", () -> KitRecordPages.projects(this, config));
        button(actionLeft, footer, actionWidth, KitClient.borer() != null && KitClient.borer().isActive() ? "停止当前任务" : "开始 / 继续挖", () -> {
            if (KitClient.borer() == null) { showNotice("运行引擎未就绪", 0xFF7777); return; }
            if (KitClient.borer().isActive()) { KitClient.borer().stop(this.minecraft, "界面停止"); rebuildWidgets(); return; }
            if (apply()) { KitClient.borer().start(this.minecraft, TunnelBorer.Mode.AREA); this.minecraft.setScreen(null); }
        });
        button(actionRight, footer, actionWidth, "返回 · 保留草稿", this::onClose);
        layoutContent();
    }
    private EditBox pointField(int left, int y, boolean first, String value) {
        String label = first ? "A" : "B";
        int pointWidth = panelWidth() >= 480 ? panelWidth() - 236 : panelWidth() - 84;
        track(label(left, y + 5, 82, "点 " + label + " · XYZ", 0xCCCCCC), y + 5);
        EditBox input = addRenderableWidget(KitUi.field(font, left + 84, y, pointWidth, "点 " + label, value, 80));
        track(input, y);
        int buttonsX = panelWidth() >= 480 ? left + panelWidth() - 144 : left;
        int buttonsY = panelWidth() >= 480 ? y : y + 24;
        int buttonWidth = panelWidth() >= 480 ? 69 : half();
        var feet = addRenderableWidget(Button.builder(Component.literal("取脚下 " + label), ignored -> setPoint(first, minecraft.player == null ? null : minecraft.player.blockPosition()))
            .bounds(buttonsX, buttonsY, buttonWidth, 20).build());
        var look = addRenderableWidget(Button.builder(Component.literal("取准星 " + label), ignored -> setPoint(first, BorerAreaMarks.lookBlock(minecraft)))
            .bounds(buttonsX + buttonWidth + 6, buttonsY, buttonWidth, 20).build());
        track(feet, buttonsY); track(look, buttonsY); return input;
    }
    private void showRunState() {
        var borer = KitClient.borer();
        var page = new KitFormScreen(this, "区域挖运行情况", "这里只读取执行状态；输入草稿和当前执行范围分开。").bind(config).id("area-status");
        page.liveNote(() -> borer == null ? "运行引擎未就绪" : (borer.isActive() ? "执行中：" : "未运行：") + borer.status());
        page.liveNote(() -> "已应用范围：" + BorerAreaMarks.sizeLabel(config));
        page.note("配置与工程进度保留；等待、封水、进食、存箱等阶段以实际引擎状态为准。");
        page.action("停止当前任务", "立即停止，不校验草稿，不删除工程。", () -> { if (borer != null && borer.isActive()) borer.stop(minecraft, "运行页停止"); });
        page.action("显示 / 隐藏范围", "返回范围页使用黄框开关。", () -> minecraft.setScreen(this));
        minecraft.setScreen(page);
    }
    private AreaDrafts.Draft snapshot() {
        return draft.edit(name.getValue(), a.getValue(), b.getValue(), length.getValue(), widthField.getValue(), heightField.getValue());
    }
    private void rememberDraft(boolean persist) {
        if (draft == null || a == null || b == null || name == null || heightField == null) return;
        var next = snapshot();
        if (!AreaDrafts.store(config, draft, next)) return;
        draft = next;
        if (persist) config.save();
    }
    /** Only explicit validated apply/save may advance the draft's committed-area baseline. */
    private void rebaseDraft() {
        draft = snapshot().rebase(config);
        config.borerAreaDraft = draft;
    }
    @Override public void removed() {
        rememberDraft(true); // Covers Esc, 返回, close-menu hotkeys and navigation to another page.
        super.removed();
    }
    private int panelWidth() { return UiPageLayout.of(this.width, this.height).width(); }
    private int half() { return (panelWidth() - 6) / 2; }
    private EditBox field(int left, int y, String title, String value) {
        track(label(left, y + 5, 82, title, 0xCCCCCC), y + 5);
        EditBox box = addRenderableWidget(KitUi.field(this.font, left + 84, y, panelWidth() - 84, title, value, 80));
        track(box, y); return box;
    }
    private EditBox small(int left, int y, String title, String value) {
        track(label(left, y + 5, 36, title, 0xCCCCCC), y + 5);
        EditBox box = addRenderableWidget(KitUi.field(this.font, left + 38, y, (panelWidth() - 8) / 3 - 38, title, value, 3));
        track(box, y); return box;
    }
    private void button(int x, int y, int w, String title, Runnable action) {
        addRenderableWidget(Button.builder(Component.literal(title), b -> action.run()).bounds(x, y, w, 20).build());
    }
    private void rowButton(int x, int y, String title, Runnable action) {
        AbstractWidget w = addRenderableWidget(Button.builder(Component.literal(title), b -> action.run()).bounds(x, y, half(), 20).build());
        track(w, y);
    }
    private void track(AbstractWidget w, int y) { content.add(new Positioned(w, y)); }
    private void layoutContent() {
        scroll = Math.max(0, Math.min(scroll, Math.max(0, contentHeight - (bottom - top))));
        for (Positioned p : content) {
            p.widget.setY(p.y - scroll);
            p.widget.visible = p.widget.getY() >= top && p.widget.getY() + p.widget.getHeight() <= bottom;
            p.widget.active = p.widget.visible;
        }
    }
    @Override public boolean mouseScrolled(double x, double y, double sx, double sy) {
        if (y >= top && y < bottom) { scroll -= (int)(sy * 24); layoutContent(); return true; }
        return super.mouseScrolled(x, y, sx, sy);
    }
    @Override public boolean keyPressed(net.minecraft.client.input.KeyEvent event) {
        return super.keyPressed(event);
    }
    private void setPoint(boolean first, BlockPos point) {
        if (point == null) { showNotice("准星没有方块，请先对准目标", 0xFF7777); return; }
        (first ? a : b).setValue(point.getX() + " " + point.getY() + " " + point.getZ());
        rememberDraft(true);
        showNotice("已暂存点 " + (first ? "A" : "B") + "；可关闭菜单去标另一点", 0x77DDCC);
    }
    private void setOutline(boolean visible) {
        TunnelBorer borer = KitClient.borer();
        if (borer == null) return;
        if (!visible) {
            borer.dismissAreaPreview();
            showNotice("已隐藏黄框；坐标、工程和进度均保留", 0x77DDCC);
            return;
        }
        if (!config.borerAreaASet || !config.borerAreaBSet) { showNotice("请先设置并应用两个角点", 0xFF7777); return; }
        if (borer.isActive() && (borer.isSceneryActive() || borer.mode() != TunnelBorer.Mode.AREA)) {
            showNotice("其它自动功能运行中，请先停止再显示区域", 0xFF7777); return;
        }
        borer.previewArea(this.minecraft);
        showNotice("已显示当前范围；返回游戏即可查看", 0x77DDCC);
    }
    private void generate() {
        if (this.minecraft.player == null || this.minecraft.level == null) { showNotice("请先进入世界再生成区域", 0xFF7777); return; }
        try {
            var bounds = AreaForm.fromSize(this.minecraft.player.blockPosition(), Integer.parseInt(length.getValue()), Integer.parseInt(widthField.getValue()), Integer.parseInt(heightField.getValue()));
            setPoint(true, bounds.a()); setPoint(false, bounds.b()); apply();
        } catch (IllegalArgumentException ex) { showNotice("尺寸无效：长宽 1–64，高度 2–384", 0xFF7777); }
    }
    private boolean apply() {
        if (this.minecraft.level == null) { showNotice("请先进入世界再应用区域", 0xFF7777); return false; }
        if (KitClient.borer() != null && KitClient.borer().isActive()) { rememberDraft(true); showNotice("已暂存输入，请先停止当前任务再应用新范围", 0xFF7777); return false; }
        try {
            var bounds = AreaForm.parse(a.getValue(), b.getValue(), this.minecraft.level.getMinY(), this.minecraft.level.getMaxY());
            config.borerAreaAx = bounds.a().getX(); config.borerAreaAy = bounds.a().getY(); config.borerAreaAz = bounds.a().getZ();
            config.borerAreaBx = bounds.b().getX(); config.borerAreaBy = bounds.b().getY(); config.borerAreaBz = bounds.b().getZ();
            config.borerAreaASet = config.borerAreaBSet = true;
            config.borerLastMode = "AREA"; rebaseDraft(); config.save();
            showNotice(BorerAreaMarks.sizeLabel(config), 0x77DDCC); return true;
        } catch (IllegalArgumentException error) { showNotice(error.getMessage(), 0xFF7777); return false; }
    }
    private void saveProject() {
        if (name.getValue().isBlank()) { showNotice("请填写工程名称", 0xFF7777); return; }
        if (this.minecraft.level == null) { rememberDraft(true); showNotice("已暂存输入；进入世界后校验并保存工程", 0x77DDCC); return; }
        if (KitClient.borer() != null && KitClient.borer().isActive()) { rememberDraft(true); showNotice("运行中仅保存草稿；停止后再保存新范围", 0x77DDCC); return; }
        try {
            var bounds = AreaForm.parseDraft(a.getValue(), b.getValue(), this.minecraft.level.getMinY(), this.minecraft.level.getMaxY());
            if (bounds.a() == null || bounds.b() == null) {
                rememberDraft(true);
                showNotice("已保存草稿；可关闭菜单，稍后补点 " + (bounds.a() == null ? "A" : "B"), 0x77DDCC);
                return;
            }
        } catch (IllegalArgumentException error) { rememberDraft(true); showNotice(error.getMessage(), 0xFF7777); return; }
        var existing = config.areaProjectByName(name.getValue().trim());
        if (!overwriteConfirmed && existing != null) {
            var proposed = AreaForm.parse(a.getValue(), b.getValue(), minecraft.level.getMinY(), minecraft.level.getMaxY());
            boolean changed = !proposed.a().equals(new BlockPos(existing.ax, existing.ay, existing.az)) || !proposed.b().equals(new BlockPos(existing.bx, existing.by, existing.bz));
            if (changed) {
                minecraft.setScreen(new KitConfirmScreen(this, "覆盖工程「" + existing.name + "」", "将用当前 A/B 替换该工程的保存范围；不会立即挖掘。", () -> {
                    overwriteConfirmed = true; try { saveProject(); } finally { overwriteConfirmed = false; }
                }));
                return;
            }
        }
        if (!apply()) return;
        config.upsertAreaProject(name.getValue().trim(), BorerAreaProjects.currentDimension(this.minecraft));
        rebaseDraft(); config.save();
        showNotice("已保存工程：" + name.getValue().trim(), 0x77DDCC);
    }
    @Override public void extractRenderState(GuiGraphicsExtractor g, int x, int y, float delta) {
        super.extractRenderState(g, x, y, delta);
        KitUi.centered(g, this.font, "区域挖 · 工程", this.width / 2, 14, 0xFFFFFF);
        String status = a.getValue().equals(BorerAreaMarks.format(config.borerAreaASet, config.borerAreaAx, config.borerAreaAy, config.borerAreaAz))
            && b.getValue().equals(BorerAreaMarks.format(config.borerAreaBSet, config.borerAreaBx, config.borerAreaBy, config.borerAreaBz))
            && config.borerAreaASet && config.borerAreaBSet ? BorerAreaMarks.sizeLabel(config) : AreaDrafts.status(a.getValue(), b.getValue());
        KitUi.centered(g, this.font, KitUi.fit(this.font, notice.isEmpty() ? status : notice, panelWidth()), this.width / 2, bottom + 3, notice.isEmpty() ? 0xBBBBBB : noticeColor);
    }
}
