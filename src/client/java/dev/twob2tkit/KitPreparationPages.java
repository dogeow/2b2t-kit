package dev.twob2tkit;

import dev.twob2tkit.adventure.ActivityRequirements;
import dev.twob2tkit.combat.HealingItems;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.world.item.ItemStack;
import java.util.*;

/** Checklist selection, requirement editing and inventory picking use the same list/form workflow. */
public final class KitPreparationPages {
    private static Minecraft mc() { return Minecraft.getInstance(); }
    private static void confirm(Screen parent, String title, String detail, Runnable run) { mc().setScreen(new KitConfirmScreen(parent, title, detail, run)); }
    public static void checklists(Screen parent, KitConfig c) {
        ActivityRequirements.ensureLists(c);
        var list = new KitCollectionScreen<KitConfig.ActivityList>(parent, c, "checklists", "行动清单", "打开仅查看；按启用才更换补货清单",
            () -> ActivityRequirements.lists(c), a -> (a.id.equals(c.activityProfile) ? "使用中 · " : "") + a.label,
            a -> a.needs.size() + " 项物资", a -> a.label + " " + a.needs.stream().map(n -> n.label).collect(java.util.stream.Collectors.joining(" "))).key(a -> a.id);
        list.onOpen(a -> needs(list, c, a));
        list.action("启用", "作为开箱补货等功能使用的清单。", a -> { c.activityProfile = a.id; c.save(); list.message("已启用：" + a.label); list.refresh(); }, a -> true);
        list.action("删除", "只能删除自建清单。", a -> confirm(list, "删除清单「" + a.label + "」", "删除此清单和物资条目，不影响背包里的物品。", () -> {
            c.activityLists.remove(a); if (a.id.equals(c.activityProfile)) c.activityProfile = "NONE"; c.save(); list.refresh();
        }), a -> !ActivityRequirements.isBuiltin(a));
        list.add("新建清单", () -> {
            String[] name = {""}; var p = new KitFormScreen(list, "新建行动清单", "名称和输入自动暂存；保存后创建空白清单。").bind(c).recordDraft().id("checklist-new");
            p.edit("名称", "1–16 字。", () -> name[0], v -> { if (v.isBlank() || v.trim().length() > 16) throw new IllegalArgumentException("清单名称须为 1–16 字"); }, v -> name[0] = v.trim());
            p.submit("创建清单", () -> {
                var a = new KitConfig.ActivityList(); a.id = ActivityRequirements.newListId(); a.label = name[0]; a.needs = new ArrayList<>();
                c.activityLists.add(a); c.save(); p.clearDraft(); needs(list, c, a);
            }); mc().setScreen(p);
        });
        list.footer("停用清单", () -> { c.activityProfile = "NONE"; c.save(); list.message("已停用清单，内容保留"); list.refresh(); });
        mc().setScreen(list);
    }
    private static int count(KitConfig.ActivityNeed need) {
        var requirement = ActivityRequirements.requirement(need);
        return mc().player == null || requirement == null ? 0 : ActivityRequirements.count(mc().player, requirement);
    }
    private static void needs(Screen parent, KitConfig c, KitConfig.ActivityList activity) {
        var list = new KitCollectionScreen<KitConfig.ActivityNeed>(parent, c, "needs:" + activity.id, activity.label, "点击条目编辑数量；已持有 / 需要",
            () -> activity.needs, n -> (count(n) >= n.target ? "✓ " : "缺 · ") + n.label + "  " + count(n) + " / " + n.target,
            n -> n.match, n -> n.label + " " + n.match).key(n -> n.match);
        list.onOpen(n -> {
            int[] target = {n.target}; var p = new KitFormScreen(list, n.label, "保存数量不会操作背包，只更新此清单需求。").bind(c).recordDraft().id("need:" + activity.id + ":" + n.match);
            p.slider("需要数量", "1–9999。", 1, 9999, () -> target[0], v -> target[0] = v);
            p.liveNote(() -> "目前持有：" + count(n));
            p.submit("保存数量", () -> { n.target = target[0]; c.save(); p.clearDraft(); mc().setScreen(list); }); mc().setScreen(p);
        });
        list.action("移除", "移除此物资需求，不丢弃物品。", n -> confirm(list, "移除「" + n.label + "」", "只移除清单中的需求。", () -> { activity.needs.remove(n); c.save(); list.refresh(); }), n -> true);
        list.add("添加物品", () -> inventory(list, c, activity));
        list.footer("清单设置", () -> {
            var p = new KitFormScreen(list, activity.label + " · 设置", "查看清单不会自动更换正在使用的补货清单。").bind(c).recordDraft().id("checklist-options:" + activity.id);
            p.bool("开箱后按清单自动补货", "这是所有行动共用的补货开关。", () -> c.autoRestockFromOpenedContainers, v -> { c.autoRestockFromOpenedContainers = v; c.save(); });
            p.action("使用这份清单", "设为当前活动清单。", () -> { c.activityProfile = activity.id; c.save(); p.showNotice("已启用：" + activity.label, 0x77DDCC); });
            p.danger(ActivityRequirements.isBuiltin(activity) ? "恢复默认条目" : "清空条目", "将替换这份清单的物资需求，不改变背包。", () -> {
                activity.needs = ActivityRequirements.isBuiltin(activity) ? new ArrayList<>(ActivityRequirements.defaultNeedsForId(activity.id)) : new ArrayList<>(); c.save();
            }); mc().setScreen(p);
        });
        list.footer("检查背包", () -> {
            var missing = activity.needs.stream().filter(n -> count(n) < n.target).map(n -> n.label + " " + count(n) + "/" + n.target).toList();
            var p = new KitFormScreen(list, "背包检查结果", activity.label).bind(c).recordDraft().id("checklist-result:" + activity.id);
            p.note(mc().player == null ? "当前未进入世界，无法检查" : missing.isEmpty() ? "物资已齐全" : "尚缺：" + String.join("、", missing)); mc().setScreen(p);
        });
        mc().setScreen(list);
    }
    private record InventoryItem(int slot, ItemStack stack) {}
    private static void inventory(Screen parent, KitConfig c, KitConfig.ActivityList activity) {
        var list = new KitCollectionScreen<InventoryItem>(parent, c, "inventory-picker:" + activity.id, "选择背包物品", "选择物品后填写所需数量，不移动或丢弃物品",
            () -> {
                List<InventoryItem> items = new ArrayList<>(); if (mc().player == null) return items;
                for (int i = 0; i < 36; i++) { var stack = mc().player.getInventory().getItem(i); if (!stack.isEmpty()) items.add(new InventoryItem(i, stack.copy())); }
                if (!mc().player.getOffhandItem().isEmpty()) items.add(new InventoryItem(40, mc().player.getOffhandItem().copy())); return items;
            }, i -> i.stack.getHoverName().getString() + " ×" + i.stack.getCount(), i -> "背包槽位 " + i.slot,
            i -> i.stack.getHoverName().getString()).icon(InventoryItem::stack);
        list.onOpen(i -> {
            int[] target = {1}; String label = i.stack.getHoverName().getString();
            var p = new KitFormScreen(list, "加入「" + label + "」", "目标清单：" + activity.label + "；已存在时更新所需数量。").bind(c).recordDraft().id("need-add:" + activity.id + ":" + label);
            p.slider("需要数量", "1–9999。", 1, 9999, () -> target[0], v -> target[0] = v);
            p.submit("加入清单", () -> {
                var added = ActivityRequirements.fromHeld(i.stack, target[0]);
                if (added == null) return;
                var existing = activity.needs.stream().filter(n -> n.match.equals(added.match)).findFirst();
                if (existing.isPresent()) existing.get().target = target[0]; else activity.needs.add(added);
                c.save(); p.clearDraft(); mc().setScreen(parent);
            }); mc().setScreen(p);
        }); mc().setScreen(list);
    }
    public static void healing(Screen parent, KitConfig c) {
        c.healingItemIds = HealingItems.normalize(c.healingItemIds);
        var list = new KitCollectionScreen<HealingItems.Choice>(parent, c, "healing-items", "治疗物资", "选择计入生存提醒的物资，不会食用或丢弃",
            () -> HealingItems.CATALOG, choice -> (c.healingItemIds.contains(choice.id()) ? "✓ " : "") + choice.label()
                + " · 背包 " + (mc().player == null ? "未知" : HealingItems.countChoice(mc().player, choice)),
            choice -> choice.id(), choice -> choice.label() + " " + choice.id()).icon(choice -> new ItemStack(choice.icon()));
        java.util.function.Consumer<HealingItems.Choice> toggle = choice -> {
            if (!c.healingItemIds.add(choice.id())) { if (c.healingItemIds.size() > 1) c.healingItemIds.remove(choice.id()); }
            c.save(); list.refresh();
        };
        list.onOpen(choice -> {
            var p = new KitFormScreen(list, choice.label(), "治疗物资统计项目").bind(c).recordDraft().id("healing-choice:" + choice.id());
            p.note(choice.id()); p.action("选择 / 取消", "至少保留一种统计物资。", () -> { toggle.accept(choice); mc().setScreen(list); }); mc().setScreen(p);
        });
        list.action("选择", "选择 / 取消此物资，至少保留一种。", toggle, choice -> true);
        list.footer("常用食物", () -> { c.healingItemIds = new LinkedHashSet<>(HealingItems.defaultIds()); c.save(); list.refresh(); });
        list.footer("任意食物", () -> { c.healingItemIds = new LinkedHashSet<>(Set.of(HealingItems.ANY_FOOD, HealingItems.HEALING_POTION)); c.save(); list.refresh(); });
        mc().setScreen(list);
    }
    private KitPreparationPages() {}
}
