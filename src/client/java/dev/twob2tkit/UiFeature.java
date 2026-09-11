package dev.twob2tkit;

import java.util.*;
import dev.twob2tkit.borer.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;

/** Single feature inventory used by native navigation, compact appearance, search and legacy routes. */
public enum UiFeature {
    AREA(Category.MINING, "区域挖", "分次标 A/B、保存工程、浅层水平／深层竖井", "工程 采石场 AB 黄框"),
    ORE(Category.MINING, "自动找矿", "选择矿种、开路采集与拾取", "煤 铁 钻石 找矿"),
    FORWARD(Category.MINING, "向前挖", "巷道断面与掘进方向", "隧道 地铁"),
    DOWN(Category.MINING, "向下挖", "竖向截面与方向", "竖井"),
    ROUTE(Category.MINING, "挖矿路线", "回家、回地狱门、路线显示", "路点 返回 门"),
    BORER_SAFETY(Category.MINING, "挖矿安全", "反击、液体、补给和卸货", "封水 弓箭 苦力怕 箱子"),
    CRUISE(Category.TRAVEL, "巡航", "目标 X/Y/Z 与自动飞行", "坐标 飞行 导航"),
    CRUISE_OPTIONS(Category.TRAVEL, "巡航选项", "到达、绕障及挂机保护", "半径 卡住 视角"),
    PLACES(Category.TRAVEL, "地点收藏", "保存、编辑、指引、前往地点", "收藏 地标 位置"),
    SCENERY(Category.TRAVEL, "风景预加载", "按实际服务端视距跑图缓存", "Voxy Bobby 区块 风景"),
    STRUCTURES(Category.TRAVEL, "附近结构", "结构候选、指引、备注", "村庄 要塞 种子 Chunkbase"),
    STRUCTURE_MARKS(Category.TRAVEL, "结构标记", "已记录结构和探索备注", "去过 备注"),
    DEATH(Category.TRAVEL, "死亡点", "查看、复制、返回死亡点上方", "复活 遗物"),
    CHOPPER(Category.PRODUCTION, "自动砍树", "树木范围、砍伐、拾取和补种", "挖树 原木"),
    PLANTER(Category.PRODUCTION, "自动种田", "耕种、成熟收获和拾取", "作物 种子 收成"),
    FEEDER(Category.PRODUCTION, "自动喂养", "动物选择、繁殖和幼体喂食", "动物 饲料"),
    FISHER(Category.PRODUCTION, "自动钓鱼", "钓点、Meteor 配合与满包存箱", "鱼竿"),
    CONCRETE(Category.PRODUCTION, "混凝土制作", "定点放粉末、遇水硬化、挖掘循环", "混凝土 粉末 自动 放置 挖掉 concrete"),
    SKILLS(Category.PRODUCTION, "技能库", "查看已学技能、候选技能与验证记录", "Voyager skill 学习 经验 技能"),
    BUILDER(Category.PRODUCTION, "投影建造", "自动走位、打印、核对与缺料提示", "建筑 投影 打印 printer"),
    VILLAGER(Category.PRODUCTION, "村民职业", "职业统计与缺失工作方块", "村庄 交易"),
    BRAWLER(Category.PRODUCTION, "自动打猪人", "近战、远程和恶魂火球处理", "猪灵 经验 下界"),
    STORAGE(Category.STORAGE, "仓库记录", "搜索箱子、物品、备注和位置", "箱子 容器 物品"),
    CHECKLIST(Category.STORAGE, "行动清单", "物资需求、背包检查和补货", "准备 挖矿 清单 行动指南"),
    RECIPES(Category.STORAGE, "配方指南", "本地配方与所需材料", "合成 工作台"),
    GUARD(Category.SAFETY, "自动保护", "遇袭响应与恶魂防护", "战斗 KillAura"),
    SURROUND(Category.SAFETY, "自动围箱", "围护形状、方块选择和补洞", "防护 保护"),
    SURVIVAL(Category.SAFETY, "生存提醒", "补给、护甲、图腾和鞘翅提醒", "血量 食物 耐久"),
    HEALING(Category.SAFETY, "治疗物资", "选择计入提醒的食物与药水", "回血 补给"),
    TRUSTED(Category.SAFETY, "玩家白名单", "可信玩家与警戒例外", "信任 好友"),
    SETTINGS(Category.SETTINGS, "通用设置", "风格、配方、兼容与运行引擎", "版本 热更新 菜单"),
    KEYBINDS(Category.SETTINGS, "按键绑定", "查看和修改快捷键", "快捷键 热键 紧急停止"),
    DIAGNOSTICS(Category.SETTINGS, "运行与兼容", "当前版本、依赖与诊断信息", "日志 Meteor Fabric" );

    public enum Category {
        HOME("首页"), MINING("挖掘"), TRAVEL("出行"), PRODUCTION("生产"), STORAGE("仓储"), SAFETY("保护"), SETTINGS("设置");
        public final String label; Category(String label) { this.label = label; }
        public static Category parse(String raw) { try { return valueOf(raw); } catch (RuntimeException ignored) { return HOME; } }
    }
    public final Category category; public final String title, description, keywords;
    UiFeature(Category category, String title, String description, String keywords) { this.category = category; this.title = title; this.description = description; this.keywords = keywords; }
    public boolean matches(String query) {
        String text = (title + " " + description + " " + keywords + " " + name()
            + (category == Category.MINING ? " 盾构 盾构机 borer" : "")).toLowerCase(Locale.ROOT);
        return Arrays.stream(query.toLowerCase(Locale.ROOT).trim().split("\\s+")).allMatch(text::contains);
    }
    public static UiFeature find(String id) { try { return valueOf(id); } catch (RuntimeException ignored) { return null; } }
    public boolean active() {
        var b = KitClient.borer();
        return switch (this) {
            case AREA, ORE, FORWARD, DOWN -> b != null && b.isActive() && !b.isSceneryActive() && b.mode().name().equals(name());
            case SCENERY -> b != null && b.isSceneryActive();
            case CRUISE -> KitClient.controller() != null && KitClient.controller().isActive();
            case CHOPPER -> KitClient.chopper() != null && KitClient.chopper().isActive();
            case PLANTER -> KitClient.planter() != null && KitClient.planter().isActive();
            case FEEDER -> KitClient.feeder() != null && KitClient.feeder().isActive();
            case FISHER -> KitClient.fisher() != null && KitClient.fisher().isActive();
            case SURROUND -> KitClient.surround() != null && KitClient.surround().isActive();
            case BRAWLER -> KitClient.brawler() != null && KitClient.brawler().isActive();
            case CONCRETE -> KitClient.concrete() != null && KitClient.concrete().isActive();
            case BUILDER -> KitClient.buildJob() != null && KitClient.buildJob().isActive();
            default -> false;
        };
    }
    public static void open(String id, Screen parent) {
        UiFeature feature = find(id); if (feature != null) feature.open(parent);
    }
    /** Old constructors remain binary/source-compatible while all visible controls come from the new pages. */
    public static boolean redirect(String id, Screen parent) { open(id, parent); return true; }
    public static boolean redirectCategory(Category category) {
        var c = KitClient.config();
        if (c != null) Minecraft.getInstance().setScreen(new KitWorkspaceScreen(c, KitClient.controller(), category));
        return true;
    }
    public void open(Screen parent) {
        var c = KitClient.config(); var mc = Minecraft.getInstance(); var controller = KitClient.controller();
        if (c == null || controller == null) return;
        if (parent == null) parent = new KitWorkspaceScreen(c, controller, category);
        if (c.recentUiFeatures == null) c.recentUiFeatures = new ArrayList<>();
        c.recentUiFeatures.remove(name()); c.recentUiFeatures.addFirst(name());
        while (c.recentUiFeatures.size() > 10) c.recentUiFeatures.removeLast(); c.save();
        switch (this) {
            case AREA -> mc.setScreen(new AreaSetupScreen(parent, c));
            case ORE, FORWARD, DOWN -> ClickGuiPages.mining(parent, c, TunnelBorer.Mode.valueOf(name()));
            case ROUTE -> ClickGuiPages.routes(parent, c);
            case BORER_SAFETY -> ClickGuiPages.miningSafety(parent, c);
            case CRUISE -> ClickGuiPages.cruise(parent, c, controller);
            case CRUISE_OPTIONS -> ClickGuiPages.cruiseOptions(parent, c);
            case PLACES -> KitRecordPages.places(parent, c);
            case SCENERY -> ClickGuiPages.scenery(parent, c);
            case STRUCTURES -> mc.setScreen(new dev.twob2tkit.structure.NearbyStructuresScreen(parent, c, controller, KitClient.seedScout()));
            case STRUCTURE_MARKS -> KitRecordPages.marks(parent, c);
            case DEATH -> ClickGuiPages.death(parent, c, controller);
            case CHOPPER -> ClickGuiPages.chopper(parent, c);
            case PLANTER -> ClickGuiPages.planter(parent, c);
            case FEEDER -> ClickGuiPages.feeder(parent, c);
            case FISHER -> ClickGuiPages.fisher(parent, c);
            case SURROUND -> ClickGuiPages.surround(parent, c);
            case BRAWLER -> ClickGuiPages.brawler(parent, c);
            case CONCRETE -> ClickGuiPages.concrete(parent, c);
            case SKILLS -> KitSkillPages.open(parent, c);
            case BUILDER -> ClickGuiPages.builder(parent, c);
            case VILLAGER -> ClickGuiPages.villagers(parent, c);
            case STORAGE -> KitRecordPages.storage(parent, c);
            case CHECKLIST -> KitPreparationPages.checklists(parent, c);
            case RECIPES -> KitRecipePages.open(parent, c, "");
            case GUARD -> ClickGuiPages.guard(parent, c);
            case SURVIVAL -> ClickGuiPages.survival(parent, c);
            case HEALING -> KitPreparationPages.healing(parent, c);
            case TRUSTED -> KitRecordPages.trusted(parent, c);
            case KEYBINDS -> mc.setScreen(new KitKeyBindsScreen(parent));
            case SETTINGS -> ClickGuiPages.settings(parent, c);
            case DIAGNOSTICS -> ClickGuiPages.diagnostics(parent, c);
        }
    }
}
