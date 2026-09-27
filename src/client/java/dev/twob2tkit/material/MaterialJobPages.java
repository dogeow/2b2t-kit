package dev.twob2tkit.material;

import dev.twob2tkit.KitCollectionScreen;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitFormScreen;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

/** Native entry points; all execution belongs to the local deterministic material worker. */
public final class MaterialJobPages {
    private MaterialJobPages() {}
    public static void open(Screen parent, KitConfig config) { form(parent, config, false); }
    public static void projection(Screen parent, KitConfig config) { form(parent, config, true); }
    private static void form(Screen parent, KitConfig config, boolean projection) {
        var page = new KitFormScreen(parent, projection ? "自动补齐材料并建造" : "材料任务",
            projection ? "按当前投影核对缺料，优先取库存，再采集、制作并施工。" : "选择目标物品与数量，优先使用库存，再按可用配方采集和制作。")
            .bind(config).id(projection ? "material-job-projection" : "material-job-item")
            .lockWhen(MaterialJobs::running).status(MaterialJobs::status)
            .footerHint("本地自动执行 · 遇到缺能力或危险时停止并显示原因");
        if (projection) {
            page.liveNote(() -> dev.twob2tkit.builder.LitematicaAccess.describe());
            page.note("请先在 Litematica 中选好并锁定一份投影。使用真实放置核对进度；原有方块不会当作可随意拆除的障碍。");
        } else {
            page.liveLine(() -> "目标：" + displayName(config.materialJobItem));
            page.action("选择物品", "搜索物品中文名称或完整 ID。", () -> {
                if (MaterialJobs.running()) { page.message("请先取消当前任务，再修改目标", 0xFFFF77); return; }
                select(page, config, () -> form(parent, config, false));
            });
            page.number("背包目标数量", "以任务结束时背包实际数量为准；已有物品计入目标。", 1, 2304, true,
                () -> config.materialJobCount, value -> config.materialJobCount = (int)value);
            page.note("例如：选择白色混凝土 800。后台会计算原料和制作步骤；现有能力不支持的物品会明确列出原因。");
        }
        page.section("当前任务");
        page.liveNote(MaterialJobs::status);
        page.action("暂停任务", "先安全收尾，再暂停。不会重新连接服务器。", () -> perform(page, () -> MaterialJobs.pause(mc())));
        page.action("继续已暂停任务", "关闭界面后重新检查世界、背包和安全状态；不会解除低血量锁。", () -> perform(page, () -> MaterialJobs.resume(mc())));
        page.action("取消任务", "取消后保留已取得的材料，不自动重新开始。", () -> perform(page, () -> MaterialJobs.cancel(mc())));
        page.action("复制任务记录路径", "复制当前任务的计划、进度与日志所在路径。", () -> {
            if (MaterialJobs.directory() == null) { page.message("尚无材料任务记录", 0xFFFF77); return; }
            mc().keyboardHandler.setClipboard(MaterialJobs.directory().toString()); page.message("已复制任务记录路径", 0x77DDCC);
        });
        page.submit(projection ? "自动补齐并建造" : "开始获取材料", () -> perform(page, () -> {
            if (projection) MaterialJobs.startProjection(mc(), config);
            else { validateItem(config.materialJobItem); MaterialJobs.startItem(mc(), config, config.materialJobItem, config.materialJobCount); }
        }));
        mc().setScreen(page);
    }
    private record Choice(String id, String name, ItemStack icon) {
        boolean matches(String query) {
            String text = (id + " " + name).toLowerCase(Locale.ROOT);
            return java.util.Arrays.stream(query.strip().toLowerCase(Locale.ROOT).split("\\s+")).allMatch(text::contains);
        }
    }
    private static void select(Screen parent, KitConfig config, Runnable returnToForm) {
        List<Choice> choices = BuiltInRegistries.ITEM.stream().filter(item -> item != Items.AIR && BuiltInRegistries.ITEM.getKey(item).getNamespace().equals("minecraft"))
            .map(item -> new Choice(BuiltInRegistries.ITEM.getKey(item).toString(), new ItemStack(item).getHoverName().getString(), new ItemStack(item)))
            .sorted(Comparator.comparing(Choice::id)).toList();
        var page = new KitCollectionScreen<Choice>(parent, config, "material-job-items", "选择材料", "选择后设置背包目标数量",
            () -> choices, Choice::name, Choice::id, choice -> choice.name() + " " + choice.id())
            .key(Choice::id).icon(Choice::icon).matcher(Choice::matches).searchHint("搜索中文名称或 ID，例如混凝土、gravel…");
        page.onOpen(choice -> { config.materialJobItem = choice.id(); config.save(); returnToForm.run(); });
        mc().setScreen(page);
    }
    private static String displayName(String id) {
        try { return new ItemStack(BuiltInRegistries.ITEM.getValue(Identifier.parse(id))).getHoverName().getString() + " · " + id; }
        catch (RuntimeException e) { return "未选择"; }
    }
    private static void validateItem(String id) {
        try {
            Identifier key = Identifier.parse(id);
            if (!key.getNamespace().equals("minecraft") || !BuiltInRegistries.ITEM.containsKey(key) || BuiltInRegistries.ITEM.getValue(key) == Items.AIR) throw new IllegalArgumentException();
        } catch (RuntimeException e) { throw new IllegalArgumentException("请选择游戏中有效的目标物品"); }
    }
    private static void perform(KitFormScreen page, Runnable action) {
        try { action.run(); }
        catch (RuntimeException error) {
            if (mc().screen == null) mc().setScreen(page);
            page.message(error.getMessage() == null ? "材料任务未能开始" : error.getMessage(), 0xFF7777);
        }
    }
    private static Minecraft mc() { return Minecraft.getInstance(); }
}
