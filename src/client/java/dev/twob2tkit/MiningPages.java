package dev.twob2tkit;

import net.minecraft.client.gui.screens.Screen;
import net.minecraft.world.item.ItemStack;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Supplier;
import dev.twob2tkit.borer.TunnelBorer;

import static dev.twob2tkit.FeaturePages.mc;
import static dev.twob2tkit.FeaturePages.open;

/** 挖掘分类：找矿、向前/向下挖、沙砾、路线与挖矿安全。 */
final class MiningPages {
	private MiningPages() {
	}

	static void mining(Screen parent, KitConfig c, TunnelBorer.Mode mode) {
		TunnelBorer b = KitClient.borer();
		boolean tunnel = mode != TunnelBorer.Mode.ORE;
		KitFormScreen p = new KitFormScreen(parent, tunnel ? "隧道掘进" : mode.label, "保存数值不会启动；物资与安全在「挖矿通用」，各挖法共用。")
			.bind(c).id("mining-" + mode.name()).runLabels("开始挖矿", "停止挖矿");
		bindMiningRun(p, b, c, () -> mode);
		p.status(() -> b == null ? "运行引擎未就绪" : b.status());
		if (mode == TunnelBorer.Mode.ORE) {
			p.section("目标矿石 · 可多选");
			List<KitFormScreen.IconChip> choices = new ArrayList<>();
			for (TunnelBorer.OreTarget ore : TunnelBorer.OreTarget.values()) choices.add(new KitFormScreen.IconChip(new ItemStack(ore.icon()), ore.label,
				() -> TunnelBorer.OreTarget.contains(c.borerOreTarget, ore), () -> { c.borerOreTarget = TunnelBorer.OreTarget.toggle(c.borerOreTarget, ore); c.save(); }));
			p.icons("选择实际想采集的矿石", choices);
			p.slider("扫描半径（格）", "仅使用已加载世界里的矿石信息。", 8, 32, () -> c.borerOreRadius, v -> c.borerOreRadius = v);
			p.action("水下采集沙砾", "海底采集与自动返气的专用页；这里选的沙砾按陆地找矿处理，不会改动矿种选择。", () -> UiFeature.GRAVEL.open(p));
			p.advanced();
			p.bool("煤只取经验", "挖煤但不主动拾取煤。", () -> c.borerCoalXpMode, v -> c.borerCoalXpMode = v);
			p.bool("石英只取经验", "挖石英但不主动拾取石英。", () -> c.borerQuartzXpMode, v -> c.borerQuartzXpMode = v);
			p.bool("轴向瞄准", "仅沿轴向处理眼前通道。", () -> c.borerAxisAim, v -> c.borerAxisAim = v);
		} else {
			p.section("挖法");
			p.chips("切换后立即保存；运行中先停止", List.of(
				new KitFormScreen.Chip("向前挖巷道", () -> mode == TunnelBorer.Mode.FORWARD, () -> switchTunnel(parent, c, TunnelBorer.Mode.FORWARD)),
				new KitFormScreen.Chip("向下挖竖井", () -> mode == TunnelBorer.Mode.DOWN, () -> switchTunnel(parent, c, TunnelBorer.Mode.DOWN))));
			p.section(mode == TunnelBorer.Mode.DOWN ? "竖向截面" : "巷道断面");
			p.chips("常用断面，立即保存", List.of(chipSize(c, "1×2", 1, 2), chipSize(c, "2×2", 2, 2), chipSize(c, "3×3", 3, 3)));
			p.slider("宽度（格）", "当前挖法的左右截面。", 1, 5, () -> c.borerWidth, v -> c.borerWidth = v);
			p.slider("高度 / 前后截面（格）", "向前挖为高度；向下挖为前后截面。", 1, 5, () -> c.borerHeight, v -> c.borerHeight = v);
			p.cycle("方向", "准星或固定方向。", new String[]{"准星", "北", "南", "西", "东"}, () -> headingIndex(c.borerHeading), i -> {
				c.borerHeading = new String[]{"LOOK", "NORTH", "SOUTH", "WEST", "EAST"}[i]; c.save();
			});
			p.advanced();
			p.slider("前探（格）", "检查前方通道。", 1, 5, () -> Math.max(1, c.borerLookAhead), v -> c.borerLookAhead = v);
			p.bool("轴向瞄准", "仅沿轴向处理眼前通道。", () -> c.borerAxisAim, v -> c.borerAxisAim = v);
		}
		p.section("准备");
		p.liveLine(()->b==null?"":b.preparationSummary());
		p.action("挖矿通用：路线、液体与反击", "各挖法共用的安全、回家和背包设置。", () -> UiFeature.MINING_COMMON.open(p));
		open(parent, p);
	}

	/** 隧道页内切换向前 / 向下；记住选择，下次从导航打开仍是这一种。 */
	private static void switchTunnel(Screen parent, KitConfig c, TunnelBorer.Mode mode) {
		if (!mode.name().equals(c.borerLastMode)) { c.borerLastMode = mode.name(); c.save(); }
		UiFeature.valueOf(mode.name()).open(parent);
	}

	static void gravel(Screen parent, KitConfig c) {
		boolean water = c.gravelWaterMode;
		var p = new KitFormScreen(parent, "采集沙砾", water
			? "水下采集：先站在海面上方，再开始；陆地找矿有独立设置。"
			: "陆地采集沿用自动找矿，原有多矿选择保持不变。")
			.bind(c).id("gravel");
		if (water) {
			p.active(dev.twob2tkit.automation.GravelCollector::isActive, () -> {
				if (dev.twob2tkit.automation.GravelCollector.isActive())
					dev.twob2tkit.automation.GravelCollector.stop(mc(), "界面停止");
				else if (c.gravelWaterMode) dev.twob2tkit.automation.GravelCollector.start(mc());
			}).status(dev.twob2tkit.automation.GravelCollector::status)
				.runLabels("开始水下采集", "停止并上浮");
			p.slider("采集数量（0=背包满）", "只按实际捡进背包的沙砾计数。", 0, 2304,
				() -> c.gravelLimit, v -> c.gravelLimit = v);
			p.slider("扫描半径（格）", "从近到远查找已加载的水下沙砾；找到可采目标后立即开始。", 4, 64,
				() -> c.gravelRadius, v -> c.gravelRadius = v);
			p.slider("最大深度（格）", "从水面向下搜索的最大深度；仍需满足返气与安全通道。", 6, 32,
				() -> c.gravelDepth, v -> c.gravelDepth = v);
			p.section("下水前准备");
			p.note("需要精准采集铲子（耐久至少 100）、食物、水下速掘／水下呼吸 III 头盔、深海探索者 III 靴子。");
			p.note("无需水肺药水。氧气接近返程余量时先上浮补气，再继续采集；只计实际入包数量。");
			p.note("适用于本地生存世界和已确认允许此功能的 Simpcraft 服务器。");
		} else {
			p.section("陆地找矿");
			p.note("陆地沙砾由自动找矿处理，可与原有矿种一起选择；不适合水下采集。切换到这里不会清除已选矿石。");
			p.action("打开陆地找矿设置", "在原自动找矿页选沙砾；保留其他已选矿种。", () -> UiFeature.ORE.open(p));
		}
		p.action(water ? "切换到陆地找矿" : "切换到水下采集",
			"切换页面与说明，不改动自动找矿的矿种选择。", () -> {
				if (dev.twob2tkit.automation.GravelCollector.isActive()) {
					p.message("请先停止水下采集，再切换方式", 0xFF7777);return;
				}
				c.gravelWaterMode = !c.gravelWaterMode;c.save();gravel(parent,c);
			});
		open(parent, p);
	}

	/** 挖矿通用：路线回家、液体、威胁响应与区域挖背包管理，各挖法共用。 */
	static void common(Screen parent, KitConfig c) {
		var b = KitClient.borer();
		var p = new KitFormScreen(parent, "挖矿通用", "开关在挖掘运行时锁定；暂停、继续和重启保留同一行程，沿路回家返回行程起点。")
			.bind(c).id("mining-common").lockWhen(() -> b != null && b.isActive());
		p.status(() -> b == null ? "运行引擎未就绪" : b.trailOriginLabel() + " · " + b.trailLength() + " 个路点");
		p.section("路线");
		p.action("沿路回家", "按现有路点返回，不清除工程进度。", () -> { if (b != null) { KitClient.goBorerHome(mc()); if (b.isGoingHome()) mc().gui.setScreen(null); } });
		p.action("回地狱门", "使用已记录的地狱门路线。", () -> KitClient.goNetherPortal(mc()));
		p.action("显示 / 隐藏回家箭头", "只显示，不自动移动。", () -> { if (b != null) b.toggleHomeRoute(mc()); });
		p.bool("结束后沿路回家", "只在对应模式支持回家且具备路线时使用。工具耗尽保护可能直接离线。", () -> c.borerHomeOnDone, v -> c.borerHomeOnDone = v);
		p.section("液体");
		p.bool("尝试封堵液体", "向前挖、向下挖时在引擎判断可安全封堵时处理；区域挖从不往水里放方块，临水方块直接保留。", () -> c.borerSealLiquids, v -> c.borerSealLiquids = v);
		p.bool("遇岩浆尝试转向", "用于支持转向的掘进模式。", () -> c.borerTurnAroundLava, v -> c.borerTurnAroundLava = v);
		p.section("威胁响应");
		p.bool("自动反击", "响应主动威胁；苦力怕优先，其次射手。只是看到且未接近的怪不主动攻击。", () -> c.borerAutoDefend, v -> c.borerAutoDefend = v);
		p.bool("遇威胁暂停", "保留引擎现有交战条件。", () -> c.borerPauseOnMob, v -> c.borerPauseOnMob = v);
		p.bool("副手举盾", "有盾且满足防御条件时使用。", () -> c.borerShieldOnMob, v -> c.borerShieldOnMob = v);
		p.bool("苦力怕贴身围护", "开启后仅在危险接近时使用围箱。", () -> c.borerSurroundOnCreeper, v -> c.borerSurroundOnCreeper = v);
		p.slider("威胁检查半径（格）", "检查范围，不代表攻击其中所有怪物。", 2, 24, () -> c.borerMobRadius, v -> c.borerMobRadius = v);
		p.section("区域挖 · 背包");
		p.bool("快满时丢弃普通石料", "仅石料白名单，到安全的区域外丢弃，保留矿物和备用建材。", () -> c.borerAreaDiscardStone, v -> c.borerAreaDiscardStone = v);
		p.bool("快满时自动存箱", "优先可达工地箱，不足时放备用箱（建议带两个普通箱子）。存普通采集物；食物、火把、装备和应急物品保留，原木、工作台、封堵方块按清单留够。不会取走箱内物品。",
			() -> c.borerAreaStoreDrops, v -> c.borerAreaStoreDrops = v);
		p.section("物资");
		p.liveLine(()->b==null?"":b.preparationSummary());
		p.action("挖矿物资清单", "检查工具、食物、封水方块；主世界带水桶，下界带抗火药水，建议备用镐。", () -> UiFeature.CHECKLIST.open(p));
		p.advanced("路线维护");
		p.danger("开始新的挖矿行程", "先备份完整旧路线，再把当前位置设为新起点；不会立即开始挖矿。", () -> {
			if (b == null) return;
			if (b.isActive()) { p.showNotice("请先停止当前任务再开始新行程", 0xFF7777); return; }
			b.clearTrailKeepPortal(); p.showNotice(b.status(), 0xFFFF55);
		});
		open(parent, p);
	}

	private static void bindMiningRun(KitFormScreen page, TunnelBorer borer, KitConfig config, Supplier<TunnelBorer.Mode> mode) {
		page.active(() -> borer != null && borer.isActive(), () -> {
			if (borer == null) {
				page.showNotice("运行引擎未就绪", 0xFF7777);
				return;
			}
			if (borer.isActive()) {
				borer.stop(mc(), "界面停止当前挖掘任务");
				return;
			}
			TunnelBorer.Mode selected = mode.get();
			if (!selected.name().equals(config.borerLastMode)) {
				config.borerLastMode = selected.name();
				config.save();
			}
			borer.start(mc(), selected);
			if (!borer.isActive()) {
				String reason = TunnelBorer.manualStartBlock(mc());
				page.showNotice(reason.isEmpty() ? "未启动，请查看游戏提示" : reason, 0xFF7777);
			}
		});
	}

	/** 巷道断面快捷 chip。 */
	private static KitFormScreen.Chip chipSize(KitConfig config, String label, int w, int h) {
		return new KitFormScreen.Chip(label,
			() -> config.borerWidth == w && config.borerHeight == h,
			() -> {
				config.borerWidth = w;
				config.borerHeight = h;
				config.save();
			});
	}

	/** 朝向配置 → 循环索引。 */
	private static int headingIndex(String heading) {
		if (heading == null) return 0;
		return switch (heading.toUpperCase(Locale.ROOT)) {
			case "NORTH" -> 1;
			case "SOUTH" -> 2;
			case "WEST" -> 3;
			case "EAST" -> 4;
			default -> 0;
		};
	}
}
