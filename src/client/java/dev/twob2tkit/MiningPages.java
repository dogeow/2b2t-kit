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
		KitFormScreen p = new KitFormScreen(parent, mode.label, "只配置当前挖法；保存数值不启动。物资与安全设置共用。")
			.bind(c).id("mining-" + mode.name()).runLabels("开始挖矿", "停止挖矿");
		bindMiningRun(p, b, c, () -> mode);
		p.status(() -> b == null ? "运行引擎未就绪" : b.status());
		if (mode == TunnelBorer.Mode.ORE) {
			p.section("目标矿石 · 可多选");
			List<KitFormScreen.IconChip> choices = new ArrayList<>();
			for (TunnelBorer.OreTarget ore : TunnelBorer.OreTarget.values()) choices.add(new KitFormScreen.IconChip(new ItemStack(ore.icon()), ore.label,
				() -> TunnelBorer.OreTarget.contains(c.borerOreTarget, ore), () -> { c.borerOreTarget = TunnelBorer.OreTarget.toggle(c.borerOreTarget, ore); c.save(); }));
			p.icons("选择实际想采集的矿石", choices);
			p.liveLine(() -> TunnelBorer.OreTarget.contains(c.borerOreTarget, TunnelBorer.OreTarget.GRAVEL)
				? "已选沙砾：此页仍按陆地/地下找矿运行，水下请打开专用入口。"
				: "水下沙砾请用专用入口；不会改变这里的多矿选择。");
			p.action("水下采集沙砾", "使用海底采集与自动返气；不会修改当前矿种。", () -> UiFeature.GRAVEL.open(p));
			p.slider("扫描半径（格）", "仅使用已加载世界里的矿石信息。", 8, 32, () -> c.borerOreRadius, v -> c.borerOreRadius = v);
			p.bool("煤只取经验", "挖煤但不主动拾取煤。", () -> c.borerCoalXpMode, v -> c.borerCoalXpMode = v);
			p.bool("石英只取经验", "挖石英但不主动拾取石英。", () -> c.borerQuartzXpMode, v -> c.borerQuartzXpMode = v);
		} else {
			p.section(mode == TunnelBorer.Mode.DOWN ? "竖向截面" : "巷道断面");
			p.chips("常用断面，立即保存", List.of(chipSize(c, "1×2", 1, 2), chipSize(c, "2×2", 2, 2), chipSize(c, "3×3", 3, 3)));
			p.slider("宽度（格）", "当前挖法的左右截面。", 1, 5, () -> c.borerWidth, v -> c.borerWidth = v);
			p.slider("高度 / 前后截面（格）", "向前挖为高度；向下挖为前后截面。", 1, 5, () -> c.borerHeight, v -> c.borerHeight = v);
			p.cycle("方向", "准星或固定方向。", new String[]{"准星", "北", "南", "西", "东"}, () -> headingIndex(c.borerHeading), i -> {
				c.borerHeading = new String[]{"LOOK", "NORTH", "SOUTH", "WEST", "EAST"}[i]; c.save();
			});
			p.slider("前探（格）", "检查前方通道。", 1, 5, () -> Math.max(1, c.borerLookAhead), v -> c.borerLookAhead = v);
		}
		p.section("准备与安全");
		p.note("区域挖：开挖前开启 Meteor“瞬时破坏”即可接管连续点挖；运行中暂停其后台循环，结束后自动恢复，无需再次手动开启。");
		p.liveLine(()->b==null?"":b.preparationSummary());
		p.bool("轴向瞄准", "仅沿轴向处理眼前通道。", () -> c.borerAxisAim, v -> c.borerAxisAim = v);
		p.action("挖矿物资清单", "检查工具、食物、封水方块等。", () -> UiFeature.CHECKLIST.open(p));
		p.action("安全与反击", "液体、怪物与卸货选项。", () -> miningSafety(p, c));
		p.action("挖矿路线", "回家、返回地狱门和显示路线。", () -> UiFeature.ROUTE.open(p));
		open(parent, p);
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

	static void miningSafety(Screen parent, KitConfig c) {
		var b = KitClient.borer();
		var p = new KitFormScreen(parent, "挖矿安全与物资", "相关任务运行时先停止再修改；不会因编辑而改变正在执行的区域。")
			.bind(c).id("mining-safety").lockWhen(() -> b != null && b.isActive());
		p.section("挖矿准备");
		p.liveLine(()->b==null?"":b.preparationSummary());
		p.note("水桶用于主世界应急；下界应准备抗火药水。建议带备用镐，区域井底缺光时会尝试补火把。");
		p.section("液体与撤离");
		p.bool("尝试封堵液体", "仅在引擎判断可安全封堵时处理；不可封的水或岩浆保留保护。", () -> c.borerSealLiquids, v -> c.borerSealLiquids = v);
		p.bool("遇岩浆尝试转向", "用于支持转向的掘进模式。", () -> c.borerTurnAroundLava, v -> c.borerTurnAroundLava = v);
		p.bool("结束后沿路回家", "只在对应模式支持回家且具备路线时使用。工具耗尽保护可能直接离线。", () -> c.borerHomeOnDone, v -> c.borerHomeOnDone = v);
		p.section("威胁响应");
		p.bool("自动反击", "响应主动威胁；苦力怕优先，其次射手。只是看到且未接近的怪不主动攻击。", () -> c.borerAutoDefend, v -> c.borerAutoDefend = v);
		p.bool("遇威胁暂停", "保留引擎现有交战条件，不因 UI 改版扩大攻击范围。", () -> c.borerPauseOnMob, v -> c.borerPauseOnMob = v);
		p.bool("副手举盾", "有盾且满足防御条件时使用。", () -> c.borerShieldOnMob, v -> c.borerShieldOnMob = v);
		p.bool("苦力怕贴身围护", "开启后仅在危险接近时使用围箱。", () -> c.borerSurroundOnCreeper, v -> c.borerSurroundOnCreeper = v);
		p.slider("威胁检查半径（格）", "检查范围，不代表攻击其中所有怪物。", 2, 24, () -> c.borerMobRadius, v -> c.borerMobRadius = v);
		p.section("区域挖 · 背包管理");
		p.bool("快满时丢弃普通石料", "仅石料白名单，到安全的区域外丢弃，保留矿物和备用建材。", () -> c.borerAreaDiscardStone, v -> c.borerAreaDiscardStone = v);
		p.bool("快满时自动存箱", "优先可达工地箱；不足时尝试放备用箱。不会取走箱内物品。", () -> c.borerAreaStoreDrops, v -> c.borerAreaStoreDrops = v);
		p.note("自动存箱可使用可达的工地箱；需要新放箱子时请带普通箱子，建议至少两个。");
		p.note("默认存入普通采集物；食物、火把、装备和应急物品保留。原木、工作台、封堵方块按“出门挖矿”清单数量留够，余量存箱。");
		p.action("检查挖矿物资", "打开行动清单。", () -> UiFeature.CHECKLIST.open(p));
		open(parent, p);
	}

	static void routes(Screen parent, KitConfig c) {
		var b = KitClient.borer();
		var p = new KitFormScreen(parent, "挖矿路线", "暂停、继续和重启保留同一行程；沿路回家返回该行程的起点。").bind(c).id("mining-routes");
		p.liveNote(() -> b == null ? "运行引擎未就绪" : b.trailOriginLabel() + " · " + b.trailLength() + " 个路点；" + b.status());
		p.action("显示 / 隐藏回家箭头", "只显示，不自动移动。", () -> { if (b != null) b.toggleHomeRoute(mc()); });
		p.action("沿路回家", "按现有路点返回，不清除工程进度。", () -> { if (b != null) { KitClient.goBorerHome(mc()); if (b.isGoingHome()) mc().gui.setScreen(null); } });
		p.action("回地狱门", "使用已记录的地狱门路线。", () -> KitClient.goNetherPortal(mc()));
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
