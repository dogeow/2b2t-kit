package dev.twob2tkit;

import dev.twob2tkit.recipe.LocalRecipes;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;

/** Full-size recipe results and a dedicated crafting preview; the recipe catalog remains unchanged. */
public final class KitRecipePages {
    private static final String[] IDS = {"all", "building", "blocks", "redstone", "equipment", "food", "misc"};
    private static final String[] LABELS = {"全部", "建筑", "方块", "红石", "装备", "食物", "杂项"};
    public static void open(Screen parent, KitConfig config, String query) {
        var list = new KitCollectionScreen<LocalRecipes.Entry>(parent, config, "recipes", "配方指南", "点配方查看合成格，点材料继续查来源",
            LocalRecipes::entries, e -> e.name() + " ×" + e.output().getCount(), LocalRecipes.Entry::description, LocalRecipes.Entry::name)
            .icon(LocalRecipes.Entry::output).matcher((e, q) -> q.isBlank() || e.matches(q)).key(LocalRecipes.Entry::id);
        list.filters(LABELS, (e, index) -> e.matchesCategory(IDS[index]));
        list.onOpen(e -> Minecraft.getInstance().setScreen(new Detail(list, config, e)));
        list.add("手中物品", () -> {
            var player = Minecraft.getInstance().player;
            if (player == null || player.getMainHandItem().isEmpty()) { list.message("请先拿着要查询的物品"); return; }
            list.query(player.getMainHandItem().getHoverName().getString());
        });
        Minecraft.getInstance().setScreen(list);
        if (!query.isBlank()) list.query(query);
    }
    private static final class Detail extends KitHudScreen {
        private final KitConfig config; private final LocalRecipes.Entry recipe; private int gx, gy;
        Detail(Screen parent, KitConfig config, LocalRecipes.Entry recipe) { super(Component.literal(recipe.name()), parent); this.config = config; this.recipe = recipe; }
        @Override protected void init() {
            var layout = UiPageLayout.of(width, height); gx = width / 2 - 68; gy = 54;
            for (int i = 0; i < 9; i++) {
                ItemStack stack = recipe.grid()[i]; if (stack == null || stack.isEmpty()) continue;
                addRenderableWidget(new ItemIconButton(gx + i % 3 * 22, gy + i / 3 * 22, 20, 20, stack,
                    Component.literal(stack.getHoverName().getString() + "\n点击查看相关配方"), () -> KitRecipePages.open(this, config, stack.getHoverName().getString())));
            }
            addRenderableWidget(new ItemIconButton(gx + 92, gy + 22, 24, 24, recipe.output(), Component.literal(recipe.name() + " ×" + recipe.output().getCount()), () -> {}));
            addRenderableWidget(Button.builder(Component.literal("‹ 返回配方列表"), b -> onClose()).bounds(layout.footerButtonX(0, 1), layout.footer(), layout.footerButtonWidth(1), 20).build());
        }
        @Override public void extractRenderState(GuiGraphicsExtractor g, int x, int y, float delta) {
            super.extractRenderState(g, x, y, delta);
            var layout = UiPageLayout.of(width, height);
            KitUi.centered(g, font, KitUi.fit(font, recipe.name(), layout.width()), width / 2, 12, 0xFFFFFF);
            KitUi.centered(g, font, "本地合成配方 · 点击材料继续查看 · 不操作物品", width / 2, 32, 0xAABBCC);
            KitUi.text(g, font, "→", gx + 72, gy + 28, 0xFFFFFF);
            for (int i = 0; i < 9; i++) if (recipe.grid()[i] == null || recipe.grid()[i].isEmpty()) {
                int sx = gx + i % 3 * 22, sy = gy + i / 3 * 22; g.fill(sx, sy, sx + 20, sy + 20, 0xFF263442);
            }
            int at = gy + 74;
            boolean table = false;
            for (int i = 0; i < 9; i++) if (recipe.grid()[i] != null && !recipe.grid()[i].isEmpty() && (i % 3 == 2 || i / 3 == 2)) table = true;
            for (String line : KitUi.wrap(font, (table ? "需要工作台。" : "背包 2×2 可合成。") + recipe.description() + "；产出 ×" + recipe.output().getCount(), layout.width())) {
                if (at + 10 >= layout.footer() - 6) break;
                KitUi.text(g, font, line, layout.left(), at, 0xB9C9D9); at += 12;
            }
        }
        @Override protected boolean onEnterPressed() { return false; }
    }
    private KitRecipePages() {}
}
