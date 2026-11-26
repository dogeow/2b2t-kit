package dev.twob2tkit;

import java.util.*;
import dev.twob2tkit.borer.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;

/**
 * Single feature inventory used by the navigation column, overview, search and legacy routes.
 * Entries with a {@code navTarget} are merged into another entry: they are not listed in the navigation,
 * keep their id for favorites/commands, and either open their own sub-page or the merged page.
 */
public enum UiFeature {
    AREA(Category.MINING, null, "区域挖", "分次标 A/B、保存工程；海平面以上站着分层挖，水下竖井", "工程 采石场 AB 黄框 站挖 分层 沙滩"),
    ORE(Category.MINING, null, "自动找矿", "选择矿种、开路采集与拾取", "煤 铁 钻石 找矿"),
    GRAVEL(Category.MINING, ORE, "采集沙砾", "水下专用采集；陆地沿用自动找矿设置", "沙砾 海底 水下 陆地 呼吸"),
    TUNNEL(Category.MINING, null, "隧道掘进", "向前挖巷道或向下挖竖井", "隧道 地铁 竖井 向前挖 向下挖"),
    FORWARD(Category.MINING, TUNNEL, "向前挖", "巷道断面与掘进方向", "隧道 地铁"),
    DOWN(Category.MINING, TUNNEL, "向下挖", "竖向截面与方向", "竖井"),
    MINING_COMMON(Category.MINING, null, "挖矿通用", "路线回家、液体、反击和背包管理", "路线 安全 物资 回家"),
    ROUTE(Category.MINING, MINING_COMMON, "挖矿路线", "回家、回地狱门、路线显示", "路点 返回 门"),
    BORER_SAFETY(Category.MINING, MINING_COMMON, "挖矿安全", "反击、液体、补给和卸货", "封水 弓箭 苦力怕 箱子"),
    CRUISE(Category.TRAVEL, null, "巡航", "目标坐标、自动飞行与挂机保护", "坐标 飞行 导航"),
    CRUISE_OPTIONS(Category.TRAVEL, CRUISE, "巡航选项", "到达、绕障及挂机保护", "半径 卡住 视角"),
    PLACES(Category.TRAVEL, null, "地点", "收藏地点、死亡点、指引和前往", "收藏 地标 位置"),
    DEATH(Category.TRAVEL, PLACES, "死亡点", "查看、复制、返回死亡点上方", "复活 遗物"),
    SCENERY(Category.TRAVEL, null, "风景预加载", "按实际服务端视距跑图缓存", "Voxy Bobby 区块 风景"),
    STRUCTURES(Category.TRAVEL, null, "附近结构", "结构候选、指引和已去过的标记", "村庄 要塞 种子 Chunkbase"),
    STRUCTURE_MARKS(Category.TRAVEL, STRUCTURES, "结构标记", "已记录结构和探索备注", "去过 备注"),
    CHOPPER(Category.PRODUCTION, null, "自动砍树", "树木范围、砍伐、拾取和补种", "挖树 原木"),
    PLANTER(Category.PRODUCTION, null, "自动种田", "耕种、成熟收获和拾取", "作物 种子 收成"),
    FEEDER(Category.PRODUCTION, null, "自动喂养", "动物选择、繁殖和幼体喂食", "动物 饲料"),
    FISHER(Category.PRODUCTION, null, "自动钓鱼", "钓点、Meteor 配合与满包存箱", "鱼竿"),
    CARETAKER(Category.PRODUCTION, null, "农场管家", "已登记土豆田与牛羊的周期收田、繁殖、烹饪存箱", "农场 牧场 土豆 循环 caretaker 周期"),
    CONCRETE(Category.PRODUCTION, null, "混凝土制作", "定点放粉末、遇水硬化、挖掘循环", "混凝土 粉末 自动 放置 挖掉 concrete"),
    MATERIALS(Category.PRODUCTION, null, "材料任务", "指定物品与数量，自动取料、采集和制作", "沙砾 沙子 混凝土 熔炼 合成 自动 材料"),
    SKILLS(Category.PRODUCTION, MATERIALS, "技能库", "查看已学技能、候选技能与验证记录", "Voyager skill 学习 经验 技能"),
    BUILDER(Category.PRODUCTION, null, "投影建造", "自动走位、打印、核对与缺料提示", "建筑 投影 打印 printer"),
    BRAWLER(Category.PRODUCTION, null, "自动打猪人", "近战、远程和恶魂火球处理", "猪灵 经验 下界"),
    STORAGE(Category.STORAGE, null, "仓库记录", "搜索箱子、物品、备注和位置", "箱子 容器 物品"),
    CHECKLIST(Category.STORAGE, null, "行动清单", "物资需求、背包检查和补货", "准备 挖矿 清单 行动指南"),
    RECIPES(Category.STORAGE, null, "配方指南", "本地配方与所需材料", "合成 工作台"),
    VILLAGER(Category.STORAGE, null, "村民职业", "职业统计与缺失工作方块", "村庄 交易"),
    GUARD(Category.SAFETY, null, "自动保护", "遇袭响应、恶魂防护与玩家白名单", "战斗 KillAura"),
    TRUSTED(Category.SAFETY, GUARD, "玩家白名单", "可信玩家与警戒例外", "信任 好友"),
    SURROUND(Category.SAFETY, null, "自动围箱", "围护形状、方块选择和补洞", "防护 保护"),
    SURVIVAL(Category.SAFETY, null, "生存提醒", "补给、护甲、图腾、鞘翅与治疗物资", "血量 食物 耐久"),
    HEALING(Category.SAFETY, SURVIVAL, "治疗物资", "选择计入提醒的食物与药水", "回血 补给"),
    SETTINGS(Category.SETTINGS, null, "通用设置", "界面配色、自动补货与配方提示", "菜单 外观 补货 配方"),
    KEYBINDS(Category.SETTINGS, null, "按键绑定", "查看和修改快捷键", "快捷键 热键 紧急停止"),
    CHAT_TRANSLATION(Category.SETTINGS, null, "聊天翻译 /mct", "启动本地翻译、按需翻译与防刷屏设置", "双语 翻译 translate ignore 屏蔽 聊天 mct 按需"),
    DIAGNOSTICS(Category.SETTINGS, null, "运行与兼容", "版本、依赖、运行引擎热加载与日志", "日志 Meteor Fabric 版本 热更新 引擎");

    public enum Category {
        HOME("总览"), MINING("挖掘"), TRAVEL("出行"), PRODUCTION("生产"), STORAGE("仓储"), SAFETY("保护"), SETTINGS("设置");
        public final String label; Category(String label) { this.label = label; }
        public static Category parse(String raw) { try { return valueOf(raw); } catch (RuntimeException ignored) { return HOME; } }
    }
    public final Category category; public final String title, description, keywords;
    private final UiFeature navTarget;
    /** Set while a feature builds its page so the new screen knows which navigation entry it belongs to. */
    private static UiFeature opening;

    UiFeature(Category category, UiFeature navTarget, String title, String description, String keywords) {
        this.category = category; this.navTarget = navTarget; this.title = title; this.description = description; this.keywords = keywords;
    }
    /** The navigation entry this feature is shown under (itself for top-level entries). */
    public UiFeature nav() { return navTarget == null ? this : navTarget; }
    public boolean listed() { return navTarget == null; }
    public boolean matches(String query) {
        String text = (title + " " + description + " " + keywords + " " + name()
            + (category == Category.MINING && this != GRAVEL ? " 盾构 盾构机 borer" : "")).toLowerCase(Locale.ROOT);
        return Arrays.stream(query.toLowerCase(Locale.ROOT).trim().split("\\s+")).allMatch(text::contains);
    }
    public static UiFeature find(String id) { try { return valueOf(id); } catch (RuntimeException ignored) { return null; } }
    /** Navigation entries of one category, in catalog order. */
    public static List<UiFeature> listed(Category category) {
        return Arrays.stream(values()).filter(f -> f.category == category && f.listed()).toList();
    }
    /**
     * HOME without a query lists favorites (old merged ids shown as their navigation entry, duplicates dropped,
     * the saved list itself untouched). A query searches every feature, sub-pages included, so old names still work.
     */
    public static List<UiFeature> visible(Category category, String query, Collection<String> favorites) {
        if (category != Category.HOME) return listed(category);
        if (query != null && !query.isBlank()) return Arrays.stream(values()).filter(f -> f.matches(query)).toList();
        return resolve(favorites);
    }
    /** Saved ids → navigation entries, in saved order, unknown ids skipped. */
    public static List<UiFeature> resolve(Collection<String> ids) {
        Set<UiFeature> selected = new LinkedHashSet<>();
        if (ids != null) for (String id : ids) { var feature = find(id); if (feature != null) selected.add(feature.nav()); }
        return List.copyOf(selected);
    }
    public boolean favorite(KitConfig c) {
        return c.favoriteUiFeatures != null && c.favoriteUiFeatures.stream().map(UiFeature::find).anyMatch(f -> f != null && f.nav() == nav());
    }
    public void toggleFavorite(KitConfig c) {
        if (c.favoriteUiFeatures == null) c.favoriteUiFeatures = new LinkedHashSet<>();
        if (favorite(c)) c.favoriteUiFeatures.removeIf(id -> { var f = find(id); return f != null && f.nav() == nav(); });
        else c.favoriteUiFeatures.add(nav().name());
        c.save();
    }
    public boolean active() {
        var b = KitClient.borer();
        return switch (this) {
            case AREA, ORE, FORWARD, DOWN -> b != null && b.isActive() && !b.isSceneryActive() && b.mode().name().equals(name());
            case TUNNEL -> FORWARD.active() || DOWN.active();
            case GRAVEL -> dev.twob2tkit.automation.GravelCollector.isActive();
            case SCENERY -> b != null && b.isSceneryActive();
            case CRUISE -> KitClient.controller() != null && KitClient.controller().isActive();
            case CHOPPER -> KitClient.chopper() != null && KitClient.chopper().isActive();
            case PLANTER -> KitClient.planter() != null && KitClient.planter().isActive();
            case FEEDER -> KitClient.feeder() != null && KitClient.feeder().isActive();
            case FISHER -> KitClient.fisher() != null && KitClient.fisher().isActive();
            case SURROUND -> KitClient.surround() != null && KitClient.surround().isActive();
            case BRAWLER -> KitClient.brawler() != null && KitClient.brawler().isActive();
            case CONCRETE -> KitClient.concrete() != null && KitClient.concrete().isActive();
            case CARETAKER -> dev.twob2tkit.material.CaretakerJobs.running();
            case MATERIALS -> dev.twob2tkit.material.MaterialJobs.running();
            case BUILDER -> KitClient.buildJob() != null && KitClient.buildJob().isActive();
            default -> false;
        };
    }
    /** Navigation entry is running, directly or through one of its sub-pages. */
    public boolean activeInNav() {
        if (active()) return true;
        for (UiFeature f : values()) if (f != this && f.navTarget == this && f.active()) return true;
        return false;
    }
    /** Running features worth showing; sub-modes are reported once under their own name. */
    public static List<UiFeature> running() {
        return Arrays.stream(values()).filter(f -> f != TUNNEL && f.active()).toList();
    }
    /** Short live status, the same text the feature page shows. */
    public String status() {
        var b = KitClient.borer(); var mc = Minecraft.getInstance();
        return switch (this) {
            case AREA, ORE, FORWARD, DOWN, TUNNEL -> b == null ? "运行引擎未就绪" : b.status();
            case SCENERY -> b == null ? "运行引擎未就绪" : b.sceneryStatus();
            case GRAVEL -> dev.twob2tkit.automation.GravelCollector.status();
            case CRUISE -> KitClient.controller() == null ? "" : KitClient.controller().statusLine(mc);
            case CHOPPER -> KitClient.chopper() == null ? "" : KitClient.chopper().status();
            case PLANTER -> KitClient.planter() == null ? "" : KitClient.planter().status();
            case FEEDER -> KitClient.feeder() == null ? "" : KitClient.feeder().status();
            case FISHER -> KitClient.fisher() == null ? "" : KitClient.fisher().status();
            case SURROUND -> KitClient.surround() == null ? "" : KitClient.surround().status();
            case BRAWLER -> KitClient.brawler() == null ? "" : KitClient.brawler().status();
            case CONCRETE -> KitClient.concrete() == null ? "" : KitClient.concrete().status();
            case CARETAKER -> dev.twob2tkit.material.CaretakerJobs.status();
            case MATERIALS -> dev.twob2tkit.material.MaterialJobs.status();
            case BUILDER -> KitClient.buildJob() == null ? "" : KitClient.buildJob().status();
            default -> "";
        };
    }
    /** Stops this feature only when it is running; never starts anything. */
    public void stop(Minecraft mc) {
        if (!active()) return;
        String reason = "总览停止";
        switch (this) {
            case AREA, ORE, FORWARD, DOWN, TUNNEL, SCENERY -> { if (KitClient.borer() != null) KitClient.borer().stop(mc, reason); }
            case GRAVEL -> dev.twob2tkit.automation.GravelCollector.stop(mc, reason);
            case CRUISE -> KitClient.controller().stop(mc, reason);
            case CHOPPER -> KitClient.chopper().stop(mc, reason);
            case PLANTER -> KitClient.planter().stop(mc, reason);
            case FEEDER -> KitClient.feeder().stop(mc, reason);
            case FISHER -> KitClient.fisher().stop(mc, reason);
            case SURROUND -> KitClient.surround().stop(mc, reason);
            case BRAWLER -> KitClient.brawler().stop(mc, reason);
            case CONCRETE -> KitClient.concrete().stop(mc, reason);
            case CARETAKER -> dev.twob2tkit.material.CaretakerJobs.stopImmediately(reason);
            case MATERIALS -> dev.twob2tkit.material.MaterialJobs.stop(reason);
            case BUILDER -> KitClient.buildJob().stop(mc, reason);
            default -> {}
        }
    }
    /** Feature whose page is currently being built, consumed by the screen constructor. */
    static UiFeature opening() { return opening; }
    public static void open(String id, Screen parent) {
        UiFeature feature = find(id); if (feature != null) feature.open(parent);
    }
    /** Old constructors remain binary/source-compatible while all visible controls come from the new pages. */
    public static boolean redirect(String id, Screen parent) { open(id, parent); return true; }
    public static boolean redirectCategory(Category category) {
        var c = KitClient.config();
        if (c != null) Minecraft.getInstance().gui.setScreen(new KitWorkspaceScreen(c, KitClient.controller()));
        return true;
    }
    /** Pages opened from the navigation return to the overview; sub-pages opened from a page return to it. */
    public void open(Screen parent) {
        var c = KitClient.config(); var mc = Minecraft.getInstance(); var controller = KitClient.controller();
        if (c == null || controller == null) return;
        if (parent == null) parent = new KitWorkspaceScreen(c, controller);
        if (c.recentUiFeatures == null) c.recentUiFeatures = new ArrayList<>();
        c.recentUiFeatures.remove(nav().name()); c.recentUiFeatures.addFirst(nav().name());
        while (c.recentUiFeatures.size() > 10) c.recentUiFeatures.removeLast(); c.save();
        UiFeature previous = opening; opening = this;
        try {
            switch (this) {
                case AREA -> mc.gui.setScreen(new AreaSetupScreen(parent, c));
                case ORE, FORWARD, DOWN -> MiningPages.mining(parent, c, TunnelBorer.Mode.valueOf(name()));
                case TUNNEL -> MiningPages.mining(parent, c, "DOWN".equals(c.borerLastMode) ? TunnelBorer.Mode.DOWN : TunnelBorer.Mode.FORWARD);
                case GRAVEL -> MiningPages.gravel(parent, c);
                case CARETAKER -> dev.twob2tkit.material.CaretakerPages.open(parent, c);
                case MATERIALS -> dev.twob2tkit.material.MaterialJobPages.open(parent, c);
                case MINING_COMMON, ROUTE, BORER_SAFETY -> MiningPages.common(parent, c);
                case CRUISE, CRUISE_OPTIONS -> TravelPages.cruise(parent, c, controller);
                case PLACES -> KitRecordPages.places(parent, c);
                case SCENERY -> TravelPages.scenery(parent, c);
                case STRUCTURES -> mc.gui.setScreen(new dev.twob2tkit.structure.NearbyStructuresScreen(parent, c, controller, KitClient.seedScout()));
                case STRUCTURE_MARKS -> KitRecordPages.marks(parent, c);
                case DEATH -> TravelPages.death(parent, c, controller);
                case CHOPPER -> ProductionPages.chopper(parent, c);
                case PLANTER -> ProductionPages.planter(parent, c);
                case FEEDER -> ProductionPages.feeder(parent, c);
                case FISHER -> ProductionPages.fisher(parent, c);
                case SURROUND -> SafetyPages.surround(parent, c);
                case BRAWLER -> ProductionPages.brawler(parent, c);
                case CONCRETE -> ProductionPages.concrete(parent, c);
                case SKILLS -> KitSkillPages.open(parent, c);
                case BUILDER -> ProductionPages.builder(parent, c);
                case VILLAGER -> ProductionPages.villagers(parent, c);
                case STORAGE -> KitRecordPages.storage(parent, c);
                case CHECKLIST -> KitPreparationPages.checklists(parent, c);
                case RECIPES -> KitRecipePages.open(parent, c, "");
                case GUARD -> SafetyPages.guard(parent, c);
                case SURVIVAL -> SafetyPages.survival(parent, c);
                case HEALING -> KitPreparationPages.healing(parent, c);
                case TRUSTED -> KitRecordPages.trusted(parent, c);
                case KEYBINDS -> mc.gui.setScreen(new KitKeyBindsScreen(parent));
                case CHAT_TRANSLATION -> ChatTranslationPage.open(parent);
                case SETTINGS -> SettingsPages.settings(parent, c);
                case DIAGNOSTICS -> SettingsPages.diagnostics(parent, c);
            }
        } finally {
            opening = previous;
        }
    }
}
