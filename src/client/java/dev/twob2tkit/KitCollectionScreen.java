package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.*;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.client.gui.narration.NarratableEntry;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import java.util.*;
import java.util.function.*;

/** Shared searchable list: native clipped entries, full-text tooltips, stable scroll/query, explicit row actions. */
public final class KitCollectionScreen<T> extends KitHudScreen {
    private final KitConfig config; private final String id, description;
    private final Supplier<List<T>> source; private final Function<T, String> titleText, detailText, searchText;
    private final List<Action<T>> actions = new ArrayList<>();
    private final List<Runnable> footerActions = new ArrayList<>(); private final List<String> footerLabels = new ArrayList<>();
    private Consumer<T> open = value -> {};
    private Function<T, net.minecraft.world.item.ItemStack> icon;
    private BiPredicate<T, String> matcher;
    private Function<T, String> key;
    private String selectedKey = "";
    private String addLabel; private Runnable add;
    private String[] filterLabels; private BiPredicate<T, Integer> filter;
    private int filterIndex; private UiDraft draft; private EditBox search; private Items list; private UiPageLayout layout;
    private String query = ""; private double savedScroll;
    private LongSupplier sourceRevision; private Supplier<String> liveDescription;
    private long lastRevision=Long.MIN_VALUE; private int refreshTicks;
    private String searchHint="搜索名称、备注或坐标…";
    public KitCollectionScreen<T> refreshWhen(LongSupplier revision){this.sourceRevision=revision;return this;}
    public KitCollectionScreen<T> liveDescription(Supplier<String> description){this.liveDescription=description;return this;}
    public KitCollectionScreen<T> searchHint(String hint){this.searchHint=hint;return this;}
    @Override public void tick(){
        super.tick();
        if(sourceRevision!=null && ++refreshTicks%20==0){
            long next=sourceRevision.getAsLong();
            if(next!=lastRevision){lastRevision=next;refresh();}
        }
    }
    private record Action<T>(String label, String tip, Consumer<T> run, Predicate<T> enabled) {}
    public KitCollectionScreen(Screen parent, KitConfig config, String id, String title, String description, Supplier<List<T>> source,
                               Function<T, String> titleText, Function<T, String> detailText, Function<T, String> searchText) {
        super(Component.literal(title), parent); this.config = config; this.id = id; this.description = description;
        this.source = source; this.titleText = titleText; this.detailText = detailText; this.searchText = searchText;
    }
    public KitCollectionScreen<T> onOpen(Consumer<T> open) { this.open = open; return this; }
    public KitCollectionScreen<T> icon(Function<T, net.minecraft.world.item.ItemStack> icon) { this.icon = icon; return this; }
    public KitCollectionScreen<T> matcher(BiPredicate<T, String> matcher) { this.matcher = matcher; return this; }
    public KitCollectionScreen<T> key(Function<T, String> key) { this.key = key; return this; }
    public KitCollectionScreen<T> add(String label, Runnable action) { addLabel = label; add = action; return this; }
    public KitCollectionScreen<T> action(String label, String tip, Consumer<T> run, Predicate<T> enabled) { actions.add(new Action<>(label, tip, run, enabled)); return this; }
    public KitCollectionScreen<T> filters(String[] labels, BiPredicate<T, Integer> filter) { this.filterLabels = labels; this.filter = filter; return this; }
    public KitCollectionScreen<T> footer(String label, Runnable action) { footerLabels.add(label); footerActions.add(action); return this; }
    public void message(String text) { showNotice(text, 0x77DDCC); }
    public void refresh() { if (list != null) list.populate(); }
    public void query(String value) { query = value; if (search != null) search.setValue(value); }
    private String stateKey() { return "list:" + id + "|" + dev.twob2tkit.borer.AreaDrafts.context(minecraft); }
    @Override protected void init() {
        if (search != null) query = search.getValue(); if (list != null) savedScroll = list.scrollAmount();
        if (config.uiDrafts == null) config.uiDrafts = new LinkedHashMap<>();
        if (draft == null) {
            draft = config.uiDrafts.computeIfAbsent(stateKey(), key -> new UiDraft());
            query = draft.query == null ? "" : draft.query; savedScroll = draft.scroll;
            selectedKey = draft.read("selected", "");
            try { filterIndex = Integer.parseInt(draft.read("filter", "0")); } catch (RuntimeException e) { filterIndex = 0; }
        }
        layout = UiPageLayout.of(width, height);
        addRenderableWidget(Button.builder(Component.literal("‹ 返回"), b -> onClose()).bounds(layout.left(), 8, 58, 20).build());
        addRenderableWidget(Button.builder(Component.literal("紧急停止"), b -> KitClient.emergencyStop("列表页紧急停止"))
            .bounds(layout.left() + layout.width() - 76, 8, 76, 20).build());
        int searchWidth = layout.width() - (add == null ? 0 : 100);
        search = addRenderableWidget(KitUi.field(font, layout.left(), 36, searchWidth, "搜索", query, 80));
        search.setHint(Component.literal(searchHint));
        search.setResponder(value -> { query = value; savedScroll = 0; if (list != null) { list.populate(); list.setScrollAmount(0); } });
        if (add != null) addRenderableWidget(Button.builder(Component.literal(addLabel), b -> add.run()).bounds(layout.left() + layout.width() - 94, 36, 94, 20).build());
        int top = 64;
        if (filter != null) {
            filterIndex = Math.floorMod(filterIndex, filterLabels.length);
            for (int i = 0; i < filterLabels.length; i++) {
                int index = i;
                var button = addRenderableWidget(Button.builder(Component.literal(filterLabels[i]), b -> {
                    filterIndex = index; draft.remember("filter", Integer.toString(index), "0"); savedScroll = 0; if (list != null) list.setScrollAmount(0); rebuildWidgets();
                }).bounds(layout.buttonX(i, filterLabels.length), top, layout.buttonWidth(filterLabels.length), 20).build());
                button.active = i != filterIndex;
            }
            top += 26;
        }
        list = addRenderableWidget(new Items(minecraft, layout.width(), Math.max(24,layout.collectionHeight(filter != null)-(liveDescription==null?0:14)), layout.collectionTop(filter != null)));
        list.setX(layout.left()); list.populate(); list.setScrollAmount(savedScroll);
        int count = footerActions.size() + 1;
        for (int i = 0; i < footerActions.size(); i++) {
            Runnable action = footerActions.get(i);
            addRenderableWidget(Button.builder(Component.literal(footerLabels.get(i)), b -> action.run())
                .bounds(layout.footerButtonX(i, count), layout.footer(), layout.footerButtonWidth(count), 20).build());
        }
        addRenderableWidget(Button.builder(Component.literal("返回"), b -> onClose())
            .bounds(layout.footerButtonX(count - 1, count), layout.footer(), layout.footerButtonWidth(count), 20).build());
        setInitialFocus(search);
    }
    @Override public void removed() {
        if (draft != null) { draft.query = search == null ? query : search.getValue(); draft.scroll = list == null ? (int)savedScroll : (int)list.scrollAmount(); draft.remember("selected", selectedKey, ""); config.save(); }
        super.removed();
    }
    @Override protected boolean onEnterPressed() { return false; }
    @Override public void extractRenderState(GuiGraphicsExtractor g, int mx, int my, float delta) {
        super.extractRenderState(g, mx, my, delta);
        String heading = notice.isEmpty() ? title.getString() + " · " + list.children().size() + " 条" : notice;
        KitUi.text(g, font, KitUi.fit(font, heading, layout.width() - 146), layout.left() + 66, 14, notice.isEmpty() ? 0xFFFFFF : noticeColor);
        if(liveDescription!=null && list.getY()+list.getHeight()+3<=layout.footer()-10)
            KitUi.text(g,font,KitUi.fit(font,liveDescription.get(),layout.width()),layout.left(),layout.footer()-12,0xAABBCC);
        if (list.children().isEmpty()) KitUi.centered(g, font, "暂无匹配记录，可调整筛选或新增", width / 2, list.getY() + 8, 0xAABBCC);
    }
    private final class Items extends ContainerObjectSelectionList<Items.Entry> {
        Items(Minecraft client, int w, int h, int y) { super(client, w, h, y, 24); centerListVertically = false; }
        @Override public int getRowWidth() { return width - 16; }
        void populate() {
            double oldScroll = scrollAmount(); clearEntries();
            String[] terms = query.toLowerCase(Locale.ROOT).trim().split("\\s+");
            for (T item : List.copyOf(source.get())) {
                if (filter != null && !filter.test(item, filterIndex)) continue;
                String text = searchText.apply(item).toLowerCase(Locale.ROOT);
                if (matcher == null ? Arrays.stream(terms).allMatch(text::contains) : matcher.test(item, query)) {
                    Entry entry = new Entry(item); addEntry(entry);
                    if ((key == null ? searchText : key).apply(item).equals(selectedKey)) setSelected(entry);
                }
            }
            setScrollAmount(oldScroll);
        }
        final class Entry extends ContainerObjectSelectionList.Entry<Entry> {
            final T item; final List<Button> buttons = new ArrayList<>();
            Entry(T item) {
                this.item = item;
                buttons.add(Button.builder(Component.literal(titleText.apply(item)), b -> { selectEntry(); open.accept(item); })
                    .bounds(0, 0, 100, 20).tooltip(Tooltip.create(Component.literal(titleText.apply(item) + "\n" + detailText.apply(item)))).build());
                for (Action<T> action : actions) {
                    var button = Button.builder(Component.literal(action.label()), b -> { if (action.enabled().test(item)) { selectEntry(); action.run().accept(item); } })
                        .bounds(0, 0, 44, 20).tooltip(Tooltip.create(Component.literal(action.tip()))).build();
                    button.active = action.enabled().test(item); buttons.add(button);
                }
            }
            @Override public void extractContent(GuiGraphicsExtractor g, int mx, int my, boolean hover, float delta) {
                int contentWidth = getContentRight() - getContentX(), mainWidth = Math.max(40, contentWidth - actions.size() * 48);
                int y = getContentYMiddle() - 10;
                int offset = icon == null ? 0 : 22;
                Button main = buttons.getFirst(); main.setPosition(getContentX() + offset, y); main.setWidth(mainWidth - offset - 4);
                main.setMessage(Component.literal(KitUi.fit(font, titleText.apply(item), mainWidth - offset - 12)));
                if (icon != null) { var stack = icon.apply(item); if (stack != null && !stack.isEmpty()) g.item(stack, getContentX() + 2, y + 2); }
                for (int i = 1; i < buttons.size(); i++) { buttons.get(i).setPosition(getContentX() + mainWidth + (i - 1) * 48, y); buttons.get(i).active = actions.get(i - 1).enabled().test(item); }
                for (Button button : buttons) button.extractRenderState(g, mx, my, delta);
            }
            @Override public List<? extends GuiEventListener> children() { return buttons; }
            @Override public List<? extends NarratableEntry> narratables() { return buttons; }
            private void selectEntry() { setSelected(this); selectedKey = (key == null ? searchText : key).apply(item); }
        }
    }
}
