package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.*;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import java.util.*;
import java.util.function.*;

/** Shared native configuration page. Numbers are drafted and validated together; toggles are explicit immediate preferences. */
public final class KitFormScreen extends KitHudScreen {
    private final String description;
    private final List<Row> rows = new ArrayList<>();
    private final List<Placed> widgets = new ArrayList<>();
    private final Set<String> collapsed = new HashSet<>();
    private KitConfig config;
    private String pageId;
    private UiDraft draft = new UiDraft();
    private UiPageLayout layout;
    private int contentHeight, scroll;
    private BooleanSupplier active = () -> false;
    private BooleanSupplier locked = () -> false;
    private Supplier<String> state = () -> "";
    private Runnable toggle;
    private String startText = "开始", stopText = "停止";
    private String footerHint="数值退出自动暂存 · 应用后生效 · 开关即时保存";
    private boolean runUsesDraft = true;
    private String applyText = "应用数值";
    private Runnable afterApply = () -> {};
    private boolean recordDraft;
    private boolean customSubmit;
    private String boundDraftKey;
    private Button runButton, applyButton;
    private record Placed(AbstractWidget widget, int y, boolean setting) {}
    private interface Row { int build(KitFormScreen screen, int y); }
    public record Chip(String label, BooleanSupplier on, Runnable toggle) {}
    public record IconChip(ItemStack stack, String tip, BooleanSupplier on, Runnable toggle) {}

    public KitFormScreen(Screen parent, String heading, String description) {
        super(Component.literal(heading), parent); this.description = description == null ? "" : description;
        pageId = heading;
    }
    public KitFormScreen bind(KitConfig config) { this.config = config; return this; }
    public KitFormScreen id(String id) { pageId = id; return this; }
    public KitFormScreen active(BooleanSupplier active, Runnable toggle) { this.active = active; this.toggle = toggle; return this; }
    public KitFormScreen status(Supplier<String> status) { state = status; return this; }
    public KitFormScreen lockWhen(BooleanSupplier locked) { this.locked = locked; return this; }
    public KitFormScreen footerHint(String text){footerHint=text;return this;}
    public KitFormScreen runLabels(String start, String stop) { startText = start; stopText = stop; return this; }
    public KitFormScreen runUsesDraft(boolean value) { runUsesDraft = value; return this; }
    public KitFormScreen submit(String label, Runnable action) { applyText = label; afterApply = action; customSubmit = true; return this; }
    public void message(String text, int color) { showNotice(text, color); }
    /** Temporary record models are not the persisted source until an explicit save succeeds. */
    public KitFormScreen recordDraft() { recordDraft = true; return this; }
    public void clearDraft() { if (config != null && config.uiDrafts != null) config.uiDrafts.remove(boundDraftKey == null ? draftKey() : boundDraftKey); }
    public void draftValue(String label, String value) {
        for (Row row : rows) if (row instanceof Input input && input.label.equals(label)) {
            draft.remember(label, value, input.source()); input.error = "";
            if (input.box != null) { input.box.setValue(value); input.box.setTextColor(0xFFE0E0E0); }
            showNotice("已填入草稿，尚未保存", 0x77DDCC); return;
        }
    }
    private boolean settingsLocked() { return active.getAsBoolean() || locked.getAsBoolean(); }
    public KitFormScreen section(String title) { rows.add(new Section(title)); return this; }
    public KitFormScreen note(String text) {
        rows.add((s, y) -> { int start = y; for (String line : KitUi.wrap(font, text, layout.width())) { text(line, y, 0xA4B4C4); y += 12; } return y - start + 8; }); return this;
    }
    public KitFormScreen liveNote(Supplier<String> text) { rows.add(new LiveNote(text)); return this; }
    public KitFormScreen liveLine(Supplier<String> text) { rows.add(new LiveNote(text,1)); return this; }
    public KitFormScreen order(String tip, Supplier<List<String>> ids, Function<String, String> label, BiConsumer<String, Integer> move) {
        rows.add((s, y) -> {
            int start = y; List<String> order = List.copyOf(ids.get());
            for (int i = 0; i < order.size(); i++) {
                String id = order.get(i); text((i + 1) + ". " + label.apply(id), y + 6, 0xDDDDDD, layout.width() - 100);
                int x = layout.left() + layout.width() - 94;
                place(Button.builder(Component.literal("上移"), b -> { if (!settingsLocked()) { move.accept(id, -1); rebuildWidgets(); } }).bounds(x, y, 44, 20).tooltip(Tooltip.create(Component.literal(tip))).build(), y, true);
                place(Button.builder(Component.literal("下移"), b -> { if (!settingsLocked()) { move.accept(id, 1); rebuildWidgets(); } }).bounds(x + 50, y, 44, 20).build(), y, true); y += 28;
            }
            return y - start;
        }); return this;
    }
    public KitFormScreen bool(String label, String tip, BooleanSupplier get, Consumer<Boolean> set) {
        rows.add((s, y) -> {
            text(label, y + 6, 0xEEEEEE, layout.labelWidth());
            Button b = Button.builder(Component.literal(get.getAsBoolean() ? "开启" : "关闭"), ignored -> {
                if (settingsLocked()) return;
                set.accept(!get.getAsBoolean()); showNotice("已保存：" + label, 0x77DDCC); rebuildWidgets();
            }).bounds(layout.fieldX(), y, layout.fieldWidth(), 20).tooltip(Tooltip.create(Component.literal(tip + "\n此开关即时保存；运行时请先停止再修改。"))).build();
            place(b, y, true); return 28;
        }); return this;
    }
    public KitFormScreen cycle(String label, String tip, String[] options, IntSupplier get, IntConsumer set) {
        rows.add((s, y) -> {
            text(label, y + 6, 0xEEEEEE, layout.labelWidth());
            int current = Math.floorMod(get.getAsInt(), options.length);
            place(Button.builder(Component.literal(options[current] + " ›"), b -> { if (!settingsLocked()) { set.accept((current + 1) % options.length); rebuildWidgets(); } })
                .bounds(layout.fieldX(), y, layout.fieldWidth(), 20).tooltip(Tooltip.create(Component.literal(tip + "\n点击切换并立即保存。"))).build(), y, true);
            return 28;
        }); return this;
    }
    public KitFormScreen slider(String label, String tip, int min, int max, IntSupplier get, IntConsumer set) {
        return number(label, tip, min, max, true, () -> get.getAsInt(), v -> set.accept((int)v));
    }
    public KitFormScreen slider(String label, String tip, double min, double max, double step, DoubleSupplier get, DoubleConsumer set) {
        return number(label, tip, min, max, false, get, set);
    }
    public KitFormScreen number(String label, String tip, double min, double max, boolean integer, DoubleSupplier get, DoubleConsumer set) {
        rows.add(new Input(label, tip, () -> KitUi.formatNumber(get.getAsDouble()),
            value -> UiDraft.number(value, label, min, max, integer), value -> set.accept(Double.parseDouble(value.trim())))); return this;
    }
    public KitFormScreen edit(String label, String tip, Supplier<String> get, Consumer<String> set) {
        rows.add(new Input(label, tip, get, value -> {}, set)); return this;
    }
    public KitFormScreen edit(String label, String tip, Supplier<String> get, Consumer<String> validate, Consumer<String> set) {
        rows.add(new Input(label, tip, get, validate, set)); return this;
    }
    public KitFormScreen choiceInput(String label, String tip, String[] options, Supplier<String> get, Consumer<String> set) {
        Input input = new Input(label, tip, get, value -> { if (!Arrays.asList(options).contains(value)) throw new IllegalArgumentException(label + "：请选择有效选项"); }, set);
        input.options = options.clone(); rows.add(input); return this;
    }
    public KitFormScreen action(String label, String tip, Runnable run) {
        rows.add((s, y) -> {
            place(Button.builder(Component.literal(label + " ›"), b -> {
                capture(); run.run(); if (minecraft.screen == this) rebuildWidgets();
            }).bounds(layout.left(), y, layout.width(), 20).tooltip(Tooltip.create(Component.literal(tip))).build(), y, false);
            return 28;
        }); return this;
    }
    public KitFormScreen danger(String label, String tip, Runnable run) {
        return action(label, tip, () -> minecraft.setScreen(new KitConfirmScreen(this, label, tip, run)));
    }
    public KitFormScreen chips(String tip, List<Chip> chips) {
        rows.add((s, y) -> {
            int x = layout.left(), start = y;
            for (Chip chip : chips) {
                int w = Math.min(layout.width(), Math.max(64, font.width(chip.label()) + 28));
                if (x + w > layout.left() + layout.width()) { x = layout.left(); y += 24; }
                place(Button.builder(Component.literal((chip.on().getAsBoolean() ? "✓ " : "") + chip.label()), b -> {
                    if (!settingsLocked()) { chip.toggle().run(); rebuildWidgets(); }
                }).bounds(x, y, w, 20).tooltip(Tooltip.create(Component.literal(tip))).build(), y, true);
                x += w + 4;
            }
            return y - start + 28;
        }); return this;
    }
    public KitFormScreen icons(String tip, List<IconChip> icons) { return icons(tip, icons, () -> true); }
    public KitFormScreen icons(String tip, List<IconChip> icons, BooleanSupplier visible) {
        rows.add((s, y) -> {
            if (!visible.getAsBoolean()) return 0;
            List<Chip> chips = icons.stream().map(c -> new Chip(c.tip().isBlank() ? c.stack().getHoverName().getString() : c.tip(), c.on(), c.toggle())).toList();
            int x = layout.left(), start = y;
            for (int i = 0; i < chips.size(); i++) {
                var chip = chips.get(i); var icon = icons.get(i);
                int w = Math.min(layout.width(), Math.max(96, font.width(chip.label()) + 44));
                if (x + w > layout.left() + layout.width()) { x = layout.left(); y += 24; }
                var itemButton = new ItemIconButton(x, y, 22, 20, icon.stack(), Component.literal(icon.tip()), () -> {
                    if (!settingsLocked()) { chip.toggle().run(); rebuildWidgets(); }
                });
                itemButton.setChosen(chip.on().getAsBoolean()); place(itemButton, y, true);
                place(Button.builder(Component.literal((chip.on().getAsBoolean() ? "✓ " : "") + chip.label()), b -> {
                    if (!settingsLocked()) { chip.toggle().run(); rebuildWidgets(); }
                }).bounds(x + 24, y, w - 24, 20).tooltip(Tooltip.create(Component.literal(icon.tip()))).build(), y, true);
                x += w + 4;
            }
            return y - start + 28;
        }); return this;
    }
    private String draftKey() { return "form:" + pageId + "|" + dev.twob2tkit.borer.AreaDrafts.context(minecraft); }
    @Override protected void init() {
        capture();
        for (Row row : rows) if (row instanceof Input input) input.box = null;
        if (config == null) config = KitClient.config();
        if (config != null) {
            if (config.uiDrafts == null) config.uiDrafts = new LinkedHashMap<>();
            if (boundDraftKey == null) boundDraftKey = draftKey();
            draft = config.uiDrafts.computeIfAbsent(boundDraftKey, key -> new UiDraft());
        }
        scroll = draft.scroll; layout = UiPageLayout.of(width, height); widgets.clear();
        addRenderableWidget(Button.builder(Component.literal("‹ 返回"), b -> onClose()).bounds(layout.left(), 8, 58, 20).build());
        addRenderableWidget(Button.builder(Component.literal("紧急停止"), b -> KitClient.emergencyStop("界面紧急停止"))
            .bounds(layout.left() + layout.width() - 76, 8, 76, 20).build());
        int y = layout.top(); boolean skip = false;
        for (Row row : rows) {
            if (row instanceof Section section) { y += row.build(this, y); skip = collapsed.contains(section.title); }
            else if (!skip) y += row.build(this, y);
        }
        contentHeight = y - layout.top();
        boolean inputs = rows.stream().anyMatch(r -> r instanceof Input);
        int count = 1 + (inputs ? 1 : 0) + (toggle != null ? 1 : 0), index = 0;
        if (inputs) applyButton = addRenderableWidget(Button.builder(Component.literal(applyText), b -> finishEdits())
            .bounds(layout.footerButtonX(index++, count), layout.footer(), layout.footerButtonWidth(count), 20).build());
        if (toggle != null) runButton = addRenderableWidget(Button.builder(Component.literal(active.getAsBoolean() ? stopText : startText), b -> {
            if (active.getAsBoolean()) { toggle.run(); showNotice("已停止；输入草稿保留", 0xFFFF55); }
            else if (!runUsesDraft || finishEdits()) { toggle.run(); if (active.getAsBoolean()) minecraft.setScreen(null); else if (notice.isEmpty()) showNotice("未启动，请查看状态或游戏提示", 0xFF7777); }
        }).bounds(layout.footerButtonX(index++, count), layout.footer(), layout.footerButtonWidth(count), 20).build());
        addRenderableWidget(Button.builder(Component.literal(inputs ? "返回 · 保留草稿" : "返回"), b -> onClose())
            .bounds(layout.footerButtonX(index, count), layout.footer(), layout.footerButtonWidth(count), 20).build());
        layoutWidgets();
    }
    private void capture() {
        for (Row row : rows) if (row instanceof Input input && input.box != null)
            draft.remember(input.label, input.box.getValue(), input.source());
        draft.scroll = scroll;
    }
    public boolean finishEdits() {
        if (settingsLocked()) { showNotice("请先停止相关功能再应用数值", 0xFF7777); return false; }
        capture();
        Map<Input, String> values = new LinkedHashMap<>();
        for (Row row : rows) if (row instanceof Input input) {
            String value = draft.read(input.label, input.source());
            try { input.validate.accept(value); input.error = ""; values.put(input, value); }
            catch (IllegalArgumentException error) {
                input.error = error.getMessage(); showNotice(input.error, 0xFF7777);
                reveal(input);
                return false;
            }
        }
        // No configuration setter is invoked until every field has passed validation.
        values.forEach((input, value) -> { if (!value.trim().equals(input.get.get().trim())) input.set.accept(value); });
        if (!recordDraft) values.keySet().forEach(input -> { draft.committed(input.label, input.get.get()); if (input.box != null) input.box.setValue(input.get.get()); });
        if (config != null) config.save();
        afterApply.run();
        if (!customSubmit) showNotice("数值已应用；开关即时保存", 0x77DDCC);
        if (minecraft.screen == this) rebuildWidgets(); return true;
    }
    @Override public void removed() { capture(); if (config != null) config.save(); super.removed(); }
    private void reveal(Input input) {
        collapsed.clear(); rebuildWidgets();
        if (input.box == null) return;
        for (Placed p : widgets) if (p.widget() == input.box) { scroll = p.y() - layout.top(); break; }
        layoutWidgets(); input.box.setTextColor(0xFFFF7777); input.box.setTooltip(Tooltip.create(Component.literal(input.error))); setFocused(input.box);
    }
    @Override protected boolean onEnterPressed() { return false; }
    @Override public boolean mouseScrolled(double x, double y, double sx, double sy) {
        if (y >= layout.top() && y < layout.bottom()) { scroll -= (int)(sy * 28); layoutWidgets(); return true; }
        return super.mouseScrolled(x, y, sx, sy);
    }
    private void layoutWidgets() {
        scroll = layout.clampScroll(scroll, contentHeight);
        for (Placed p : widgets) {
            int y = p.y() - scroll; p.widget().setY(y);
            p.widget().visible = layout.fullyVisible(y, p.widget().getHeight());
            p.widget().active = p.widget().visible && (!p.setting() || !settingsLocked());
        }
        draft.scroll = scroll;
    }
    @Override public void tick() {
        if (runButton != null) runButton.setMessage(Component.literal(active.getAsBoolean() ? stopText : startText));
        if (applyButton != null) applyButton.active = !settingsLocked();
        if (layout != null) layoutWidgets();
        for (Row row : rows) if (row instanceof LiveNote live) live.update();
    }
    @Override public void extractRenderState(GuiGraphicsExtractor g, int x, int y, float delta) {
        super.extractRenderState(g, x, y, delta);
        KitUi.text(g, font, KitUi.fit(font, title.getString(), layout.width() - 146), layout.left() + 66, 14, 0xFFFFFF);
        KitUi.text(g, font, KitUi.fit(font, description, layout.width()), layout.left(), 36, 0xA8B8C8);
        String message = !notice.isEmpty() ? notice : active.getAsBoolean() ? "运行中 · " + state.get() : footerHint;
        KitUi.text(g, font, KitUi.fit(font, message, layout.width()), layout.left(), layout.footer() - 14, notice.isEmpty() ? 0xA8B8C8 : noticeColor);
        if (contentHeight > layout.height()) {
            int h = Math.max(10, layout.height() * layout.height() / contentHeight);
            int sy = layout.top() + (layout.height() - h) * scroll / Math.max(1, contentHeight - layout.height());
            g.fill(layout.left() + layout.width() + 4, sy, layout.left() + layout.width() + 7, sy + h, 0xFF93A8BC);
        }
    }
    private void place(AbstractWidget widget, int y, boolean setting) { widgets.add(new Placed(addRenderableWidget(widget), y, setting)); }
    private void text(String value, int y, int color) { text(value, y, color, layout.width()); }
    private void text(String value, int y, int color, int w) {
        String shown = KitUi.fit(font, value, w);
        place(new StringWidget(layout.left(), y, font.width(shown), 10, Component.literal(shown).withColor(color), font), y, false);
    }
    private final class Section implements Row {
        private final String title;
        private Section(String title) { this.title = title; }
        @Override public int build(KitFormScreen screen, int y) {
            place(Button.builder(Component.literal((collapsed.contains(title) ? "▸ " : "▾ ") + title), b -> {
                if (!collapsed.add(title)) collapsed.remove(title); rebuildWidgets();
            }).bounds(layout.left(), y, layout.width(), 20).build(), y, false); return 28;
        }
    }
    private final class LiveNote implements Row {
        private final Supplier<String> supplier; private final int lineCount; private final List<StringWidget> lines = new ArrayList<>();
        private LiveNote(Supplier<String> supplier) { this(supplier,3); }
        private LiveNote(Supplier<String> supplier,int count) { this.supplier=supplier;lineCount=count; }
        @Override public int build(KitFormScreen screen, int y) {
            lines.clear();
            for (int i = 0; i < lineCount; i++) {
                var line = new StringWidget(layout.left(), y + i * 12, 1, 10, Component.empty(), font);
                lines.add(line); place(line, y + i * 12, false);
            }
            update(); return lineCount==1?14:44;
        }
        private void update() {
            if (lines.isEmpty() || layout == null) return;
            String value=supplier.get();
            var text = lineCount==1?java.util.List.of(KitUi.fit(font,value,layout.width())):KitUi.wrap(font,value,layout.width());
            for (int i = 0; i < lines.size(); i++) {
                String line = i < text.size() ? text.get(i) : "";
                lines.get(i).setTooltip(Tooltip.create(Component.literal(value)));
                lines.get(i).setMessage(Component.literal(line).withColor(0xA9C9D9)); lines.get(i).setWidth(Math.max(1, font.width(line)));
            }
        }
    }
    private final class Input implements Row {
        private final String label, tip; private final Supplier<String> get; private final Consumer<String> validate, set;
        private final String origin;
        private EditBox box; private String error = "";
        private String[] options;
        private Input(String label, String tip, Supplier<String> get, Consumer<String> validate, Consumer<String> set) {
            this.label = label; this.tip = tip; this.get = get; this.validate = validate; this.set = set;
            this.origin = Objects.toString(get.get(), "");
        }
        private String source() { return recordDraft ? origin : Objects.toString(get.get(), ""); }
        @Override public int build(KitFormScreen screen, int y) {
            text(label, y + 6, 0xEEEEEE, layout.labelWidth());
            if (options != null) {
                String value = draft.read(label, source());
                place(Button.builder(Component.literal(value + " ›"), b -> {
                    int index = Arrays.asList(options).indexOf(draft.read(label, source()));
                    draft.remember(label, options[Math.floorMod(index + 1, options.length)], source()); rebuildWidgets();
                }).bounds(layout.fieldX(), y, layout.fieldWidth(), 20).tooltip(Tooltip.create(Component.literal(tip + "\n选择保留为草稿，保存后生效。"))).build(), y, true);
                return 28;
            }
            String initial = draft.read(label, source());
            box = KitUi.field(font, layout.fieldX(), y, layout.fieldWidth(), label, initial, Math.max(256, initial.length()));
            box.setTooltip(Tooltip.create(Component.literal(error.isEmpty() ? tip + "\n退出保留草稿，应用数值后生效。" : error)));
            if (!error.isEmpty()) box.setTextColor(0xFFFF7777);
            place(box, y, true); return 28;
        }
    }
}
