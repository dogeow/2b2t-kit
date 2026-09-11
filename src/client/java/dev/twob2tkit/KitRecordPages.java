package dev.twob2tkit;

import dev.twob2tkit.borer.*;
import dev.twob2tkit.storage.*;
import dev.twob2tkit.structure.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import java.util.*;

/** Record navigation edits local records only; travel/load/delete are separate, named actions. */
public final class KitRecordPages {
    private static Minecraft mc() { return Minecraft.getInstance(); }
    private static final String[] DIMENSIONS = {KitConfig.DIM_OVERWORLD, KitConfig.DIM_NETHER, KitConfig.DIM_END};
    private static boolean sameDimension(String dim) {
        return dim == null || dim.isBlank() || mc().level != null && KitConfig.normalizeDimension(mc().level.dimension().identifier().toString()).equals(KitConfig.normalizeDimension(dim));
    }
    private static <T> void dimensionFilters(KitCollectionScreen<T> list, java.util.function.Function<T, String> dimension) {
        list.filters(new String[]{"全部", "主世界", "下界", "末地"}, (value, index) -> index == 0 || KitConfig.normalizeDimension(dimension.apply(value)).equals(DIMENSIONS[index - 1]));
    }
    private static void confirm(Screen parent, String title, String message, Runnable action) { mc().setScreen(new KitConfirmScreen(parent, title, message, action)); }
    private static void requireName(String name) { if (name == null || name.isBlank()) throw new IllegalArgumentException("名称不能为空"); }

    public static void places(Screen parent, KitConfig c) {
        var list = new KitCollectionScreen<KitConfig.SavedPlace>(parent, c, "places", "地点收藏", "点名称查看详情；编辑不会改变当前目标",
            () -> c.savedPlaces, p -> p.name + "  " + KitConfig.dimensionLabel(p.dimension), KitRecordPages::placeSummary,
            p -> p.name + " " + placeSummary(p)).key(p -> p.name);
        dimensionFilters(list, p -> p.dimension);
        list.onOpen(p -> placeDetails(list, c, p));
        list.add("新增地点", () -> placeEditor(list, c, null));
        list.action("编辑", "只编辑收藏，不起飞。", p -> placeEditor(list, c, p), p -> true);
        list.action("前往", "按收藏巡航高度起飞；维度必须一致。", p -> {
            if (!sameDimension(p.dimension)) { list.message("当前维度不同，请先换维度"); return; }
            var guide = KitClient.structureGuide(); if (guide != null) guide.stop();
            c.targetX = p.x; c.targetZ = p.z; c.cruiseY = p.cruiseY; c.hasTarget = true; c.save();
            KitClient.controller().start(mc(), p.x, p.z, p.cruiseY);
            if (KitClient.controller().isActive()) mc().setScreen(null);
        }, p -> sameDimension(p.dimension));
        list.action("删除", "删除收藏前确认。", p -> confirm(list, "删除地点「" + p.name + "」", "只删除这条收藏，不改变当前巡航任务。", () -> { c.removePlace(p.name); list.refresh(); }), p -> true);
        list.footer("停止指引", () -> { if (KitClient.structureGuide() != null) KitClient.structureGuide().stop(); list.message("已停止指引"); });
        mc().setScreen(list);
    }
    private static String placeSummary(KitConfig.SavedPlace p) { return "X " + KitUi.formatNumber(p.x) + "  Y " + KitUi.formatNumber(p.cruiseY) + "  Z " + KitUi.formatNumber(p.z) + "\n" + KitConfig.dimensionLabel(p.dimension); }
    private static void placeDetails(Screen parent, KitConfig c, KitConfig.SavedPlace place) {
        var p = new KitFormScreen(parent, place.name, "地点详情；只查看不会更换目标。").bind(c).recordDraft().id("place-detail:" + place.name);
        p.note(placeSummary(place));
        p.action("编辑收藏", "修改后保存，不自动起飞。", () -> placeEditor(parent, c, place));
        p.action("显示方向指引", "仅显示箭头与距离，不移动。", () -> {
            if (!sameDimension(place.dimension)) { p.showNotice("当前维度不同", 0xFF7777); return; }
            if (KitClient.structureGuide() != null) { KitClient.structureGuide().start(place.name, (int)Math.round(place.x), (int)Math.round(place.z)); mc().setScreen(null); }
        });
        p.action("设为巡航目标", "明确替换巡航目标，但不启动巡航。", () -> {
            if (!sameDimension(place.dimension)) { p.showNotice("当前维度不同", 0xFF7777); return; }
            c.targetX = place.x; c.targetZ = place.z; c.cruiseY = place.cruiseY; c.hasTarget = true; c.save(); p.showNotice("已设置目标，尚未起飞", 0x77DDCC);
        });
        p.action("复制坐标", "复制 X Y Z。", () -> mc().keyboardHandler.setClipboard(KitUi.formatNumber(place.x) + " " + KitUi.formatNumber(place.cruiseY) + " " + KitUi.formatNumber(place.z)));
        mc().setScreen(p);
    }
    private static void placeEditor(Screen parent, KitConfig c, KitConfig.SavedPlace original) {
        String[] name = {original == null ? "" : original.name};
        double[] xyz = {original == null ? c.targetX : original.x, original == null ? c.cruiseY : original.cruiseY, original == null ? c.targetZ : original.z};
        String[] dim = {original == null ? BorerAreaProjects.currentDimension(mc()) : KitConfig.normalizeDimension(original.dimension)};
        if (!Arrays.asList(DIMENSIONS).contains(dim[0])) dim[0] = KitConfig.DIM_OVERWORLD;
        var p = new KitFormScreen(parent, original == null ? "新增地点" : "编辑地点", "输入自动暂存；保存收藏不改变巡航目标。").bind(c).recordDraft().id("place-edit:" + (original == null ? "new" : original.name));
        p.edit("名称", "同名地点保存时会询问是否覆盖。", () -> name[0], KitRecordPages::requireName, v -> name[0] = v.trim());
        p.number("X", "世界 X 坐标。", -30_000_000, 30_000_000, false, () -> xyz[0], v -> xyz[0] = v);
        p.number("巡航 Y", "前往时使用的飞行高度。", -64, 2048, false, () -> xyz[1], v -> xyz[1] = v);
        p.number("Z", "世界 Z 坐标。", -30_000_000, 30_000_000, false, () -> xyz[2], v -> xyz[2] = v);
        p.choiceInput("维度", "地点所属维度。", DIMENSIONS, () -> dim[0], v -> dim[0] = v);
        p.action("填入当前位置", "填写 X/Y/Z 与维度，不自动保存收藏。", () -> {
            if (mc().player == null) return;
            p.draftValue("X", KitUi.formatNumber(mc().player.getX())); p.draftValue("巡航 Y", KitUi.formatNumber(mc().player.getY()));
            p.draftValue("Z", KitUi.formatNumber(mc().player.getZ())); p.draftValue("维度", BorerAreaProjects.currentDimension(mc()));
        });
        p.submit("保存地点", () -> {
            Runnable save = () -> { c.upsertPlace(name[0], xyz[0], xyz[2], xyz[1], dim[0]); p.clearDraft(); mc().setScreen(parent); };
            boolean conflict = c.savedPlaces.stream().anyMatch(value -> value != original && value.name.equalsIgnoreCase(name[0]));
            if (conflict) confirm(p, "覆盖地点「" + name[0] + "」", "同名收藏已经存在，将用此次坐标替换它。", save); else save.run();
        });
        mc().setScreen(p);
    }

    public static void projects(Screen parent, KitConfig c) {
        var list = new KitCollectionScreen<KitConfig.AreaProject>(parent, c, "area-projects", "区域工程", "草稿保存在区域页；这里显示完整工程",
            () -> c.areaProjects, p -> p.name + "  " + BorerAreaProjects.summary(p), BorerAreaProjects::formatCoords,
            p -> p.name + " " + BorerAreaProjects.summary(p) + " " + BorerAreaProjects.formatCoords(p)).key(p -> p.id);
        dimensionFilters(list, p -> p.dimension);
        list.onOpen(project -> {
            var p = new KitFormScreen(list, project.name, "工程详情；查看不会加载范围或开始挖掘。").bind(c).recordDraft().id("project-detail:" + project.id);
            p.note(BorerAreaProjects.summary(project)); p.note(BorerAreaProjects.formatCoords(project));
            p.action("加载并编辑范围", "将该工程加载到区域设置页。", () -> loadProject(list, c, project)); mc().setScreen(p);
        });
        list.action("加载", "加载工程后打开范围页面，不自动开挖。", p -> loadProject(list, c, p), p -> true);
        list.action("删除", "仅删除工程记录，不删除世界方块。", p -> confirm(list, "删除工程「" + p.name + "」", "删除这条保存的工程；不会破坏世界或删除其它工程。", () -> { c.removeAreaProject(p.id); list.refresh(); }), p -> true);
        list.add("新建工程", () -> {
            Runnable create = () -> {
                if (KitClient.borer() != null && KitClient.borer().isActive()) { list.message("请先停止当前任务"); return; }
                var current = AreaDrafts.open(c, AreaDrafts.context(mc()));
                AreaDrafts.store(c, current, current.edit(BorerAreaProjects.defaultName(c), "", "", "30", "30", "30")); c.save();
                mc().setScreen(new AreaSetupScreen(list, c));
            };
            if (AreaDrafts.hasUnappliedCorners(c)) confirm(list, "新建区域草稿", "当前还有未应用的标点草稿，新建将替换该草稿；已保存工程保留。", create); else create.run();
        });
        list.footer("继续标点草稿", () -> mc().setScreen(new AreaSetupScreen(list, c)));
        mc().setScreen(list);
    }
    private static void loadProject(Screen parent, KitConfig c, KitConfig.AreaProject project) {
        Runnable load = () -> {
            if (KitClient.borer() != null && KitClient.borer().isActive()) return;
            c.loadAreaProject(project.id); mc().setScreen(new AreaSetupScreen(parent, c));
        };
        if (KitClient.borer() != null && KitClient.borer().isActive()) { confirm(parent, "任务运行中", "请先停止当前任务，再加载其它区域；此操作不会替你停止。", () -> {}); return; }
        if (AreaDrafts.hasUnappliedCorners(c)) confirm(parent, "加载工程「" + project.name + "」", "替换当前标点草稿；已保存工程和世界不变。", load); else load.run();
    }

    public static void storage(Screen parent, KitConfig c) {
        var list = new KitCollectionScreen<KitConfig.StorageSnapshot>(parent, c, "storage", "仓库记录", "本地快照，不代表箱子当前仍有相同物品",
            () -> c.storageSnapshots, s -> StorageLabels.headline(s) + "  " + s.x + " " + s.y + " " + s.z,
            s -> "X " + s.x + " Y " + s.y + " Z " + s.z + " · " + KitConfig.dimensionLabel(s.dimension) + "\n"
                + s.items.size() + " 类物品，共 " + s.items.stream().mapToInt(i -> i.count).sum() + " 件；点击查看全部内容",
            KitRecordPages::storageSearch).key(KitConfig.StorageSnapshot::key);
        dimensionFilters(list, s -> s.dimension);
        list.onOpen(s -> mc().setScreen(new StorageDetailScreen(list, s)));
        list.action("备注", "只修改本地记录。", s -> {
            String[] note = {s.note == null ? "" : s.note};
            var p = new KitFormScreen(list, "箱子备注", s.x + " " + s.y + " " + s.z).bind(c).recordDraft().id("storage-note:" + s.key());
            p.edit("备注", "用于本地搜索。", () -> note[0], v -> note[0] = v);
            p.submit("保存备注", () -> { s.note = note[0]; c.save(); p.clearDraft(); mc().setScreen(list); }); mc().setScreen(p);
        }, s -> true);
        list.action("指引", "只显示位置，不移动或打开箱子。", s -> {
            if (sameDimension(s.dimension) && KitClient.structureGuide() != null) { KitClient.structureGuide().start(StorageLabels.headline(s), s.x, s.y, s.z); mc().setScreen(null); }
        }, s -> sameDimension(s.dimension));
        list.action("删除", "只删除本地记录，不清空箱子。", s -> confirm(list, "删除仓库记录", StorageLabels.headline(s) + "\n仅删除本地记录，不影响世界中的箱子和物品。", () -> { c.storageSnapshots.removeIf(v -> v.key().equals(s.key())); c.save(); list.refresh(); }), s -> true);
        list.footer("停止指引", () -> { if (KitClient.structureGuide() != null) KitClient.structureGuide().stop(); list.message("已停止指引"); });
        mc().setScreen(list);
    }
    private static String storageSearch(KitConfig.StorageSnapshot s) {
        return StorageLabels.headline(s) + " " + s.note + " " + StorageLabels.colorLabel(s.colorId) + " " + KitConfig.dimensionLabel(s.dimension) + " " + s.x + " " + s.y + " " + s.z + " "
            + s.items.stream().map(i -> i.name + " " + i.id + " ×" + i.count).collect(java.util.stream.Collectors.joining("、"));
    }

    public static void marks(Screen parent, KitConfig c) {
        var list = new KitCollectionScreen<KitConfig.StructureMark>(parent, c, "structure-marks", "结构标记", "查看、编辑或删除本地结构标记",
            () -> c.structureMarks, m -> (m.visited ? "已去 · " : "") + StructureLocator.labelForId(m.kind) + " " + m.x + " " + m.z,
            m -> m.note == null ? "" : m.note, m -> StructureLocator.labelForId(m.kind) + " " + m.x + " " + m.z + " " + m.note);
        list.onOpen(m -> {
            String[] note = {m.note == null ? "" : m.note}, visited = {m.visited ? "已去" : "未去"};
            var p = new KitFormScreen(list, StructureLocator.labelForId(m.kind), m.x + " / " + m.z).bind(c).recordDraft().id("structure-note:" + m.kind + ":" + m.x + ":" + m.z);
            p.edit("备注", "本地备注。", () -> note[0], v -> note[0] = v);
            p.choiceInput("状态", "保存后更新标记。", new String[]{"未去", "已去"}, () -> visited[0], v -> visited[0] = v);
            p.submit("保存标记", () -> { m.note = note[0]; m.visited = visited[0].equals("已去"); c.saveStructureMarks(); p.clearDraft(); mc().setScreen(list); }); mc().setScreen(p);
        });
        list.filters(new String[]{"全部", "未去", "已去"}, (m, i) -> i == 0 || m.visited == (i == 2));
        list.action("复制", "复制 X ~ Z，不执行命令。", m -> mc().keyboardHandler.setClipboard(m.x + " ~ " + m.z), m -> true);
        list.action("删除", "删除此标记及备注。", m -> confirm(list, "删除结构标记", StructureLocator.labelForId(m.kind) + " " + m.x + " " + m.z, () -> { c.removeStructureMark(m); list.refresh(); }), m -> true);
        list.footer("清空全部标记", () -> confirm(list, "清空结构标记", "删除全部结构的已去状态和备注，无法撤销。不会影响世界。", () -> { c.clearStructureMarks(); list.refresh(); }));
        mc().setScreen(list);
    }

    public static void trusted(Screen parent, KitConfig c) {
        var list = new KitCollectionScreen<String>(parent, c, "trusted", "玩家白名单", "名单内玩家不触发附近玩家警戒",
            () -> List.copyOf(c.trustedPlayers), n -> n, n -> "可信玩家：" + n, n -> n);
        list.onOpen(n -> { mc().keyboardHandler.setClipboard(n); list.message("已复制玩家名：" + n); });
        list.add("添加玩家", () -> {
            String[] name = {""}; var p = new KitFormScreen(list, "添加可信玩家", "只添加明确可信的人；不会自动信任附近玩家。").bind(c).recordDraft().id("trusted-add");
            p.edit("玩家名", "1–16 位 Minecraft 玩家名。", () -> name[0], v -> { if (!v.trim().matches("[A-Za-z0-9_]{1,16}")) throw new IllegalArgumentException("请输入有效的 Minecraft 玩家名"); }, v -> name[0] = v.trim());
            p.submit("添加白名单", () -> { c.addTrusted(name[0]); p.clearDraft(); mc().setScreen(list); }); mc().setScreen(p);
        });
        list.action("移除", "移除该玩家的警戒例外。", n -> confirm(list, "移除可信玩家「" + n + "」", "此玩家以后可能触发附近玩家警戒。", () -> { c.removeTrusted(n); list.refresh(); }), n -> true);
        mc().setScreen(list);
    }
    private KitRecordPages() {}
}
