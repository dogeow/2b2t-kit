package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.core.Direction;
import net.minecraft.world.item.ItemStack;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import dev.twob2tkit.borer.AreaProjectsScreen;
import dev.twob2tkit.borer.BorerAreaMarks;
import dev.twob2tkit.borer.BorerAreaProjects;
import dev.twob2tkit.borer.TunnelBorer;
import dev.twob2tkit.chopper.AutoChopper;
import dev.twob2tkit.combat.HealingItemsScreen;
import dev.twob2tkit.feeder.AutoFeeder;
import dev.twob2tkit.fisher.AutoFisher;
import dev.twob2tkit.piglin.PiglinBrawler;
import dev.twob2tkit.planter.AutoPlanter;
import dev.twob2tkit.recipe.LocalRecipeBookInjector;
import dev.twob2tkit.surround.AutoSurround;
import dev.twob2tkit.surround.SurroundBlocks;

/** 模块栏里的密排设置。在主界面里打开，不再弹出第二层窗口。 */
final class ClickGuiPages {
	private ClickGuiPages() {
	}

	static void mining(Screen parent, KitConfig c, TunnelBorer.Mode mode) {
		TunnelBorer b = KitClient.borer();
		KitFormScreen p = new KitFormScreen(parent, mode.label, "只配置当前挖法；保存数值不启动。物资与安全设置共用。")
			.bind(c).id("mining-" + mode.name()).active(() -> b != null && b.isActive(), () -> {
				if (b == null) return;
				if (b.isActive()) b.stop(mc(), "界面停止当前挖掘任务");
				else { c.borerLastMode = mode.name(); c.save(); KitClient.prepareForBorer(mc()); b.start(mc(), mode); }
			});
		p.status(() -> b == null ? "运行引擎未就绪" : b.status());
		if (mode == TunnelBorer.Mode.ORE) {
			p.section("目标矿石 · 可多选");
			List<KitFormScreen.IconChip> choices = new ArrayList<>();
			for (TunnelBorer.OreTarget ore : TunnelBorer.OreTarget.values()) choices.add(new KitFormScreen.IconChip(new ItemStack(ore.icon()), ore.label,
				() -> TunnelBorer.OreTarget.contains(c.borerOreTarget, ore), () -> { c.borerOreTarget = TunnelBorer.OreTarget.toggle(c.borerOreTarget, ore); c.save(); }));
			p.icons("选择实际想采集的矿石", choices);
			p.slider("扫描半径（格）", "仅使用已加载世界里的矿石信息。", 8, 32, () -> c.borerOreRadius, v -> { c.borerOreRadius = v; c.save(); });
			p.bool("煤只取经验", "挖煤但不主动拾取煤。", () -> c.borerCoalXpMode, v -> { c.borerCoalXpMode = v; c.save(); });
			p.bool("石英只取经验", "挖石英但不主动拾取石英。", () -> c.borerQuartzXpMode, v -> { c.borerQuartzXpMode = v; c.save(); });
		} else {
			p.section(mode == TunnelBorer.Mode.DOWN ? "竖向截面" : "巷道断面");
			p.chips("常用断面，立即保存", List.of(chipSize(c, "1×2", 1, 2), chipSize(c, "2×2", 2, 2), chipSize(c, "3×3", 3, 3)));
			p.slider("宽度（格）", "当前挖法的左右截面。", 1, 5, () -> c.borerWidth, v -> { c.borerWidth = v; c.save(); });
			p.slider("高度 / 前后截面（格）", "向前挖为高度；向下挖为前后截面。", 1, 5, () -> c.borerHeight, v -> { c.borerHeight = v; c.save(); });
			p.cycle("方向", "准星或固定方向。", new String[]{"准星", "北", "南", "西", "东"}, () -> headingIndex(c.borerHeading), i -> {
				c.borerHeading = new String[]{"LOOK", "NORTH", "SOUTH", "WEST", "EAST"}[i]; c.save();
			});
			p.slider("前探（格）", "检查前方通道。", 1, 5, () -> Math.max(1, c.borerLookAhead), v -> { c.borerLookAhead = v; c.save(); });
		}
		p.section("准备与安全");
		p.bool("轴向瞄准", "仅沿轴向处理眼前通道。", () -> c.borerAxisAim, v -> { c.borerAxisAim = v; c.save(); });
		p.action("挖矿物资清单", "检查工具、食物、封水方块等。", () -> UiFeature.CHECKLIST.open(p));
		p.action("安全与反击", "液体、怪物与卸货选项。", () -> miningSafety(p, c));
		p.action("挖矿路线", "回家、返回地狱门和显示路线。", () -> UiFeature.ROUTE.open(p));
		open(parent, p);
	}

	static void miningSafety(Screen parent, KitConfig c) {
		var b = KitClient.borer();
		var p = new KitFormScreen(parent, "挖矿安全与物资", "相关任务运行时先停止再修改；不会因编辑而改变正在执行的区域。")
			.bind(c).id("mining-safety").lockWhen(() -> b != null && b.isActive());
		p.section("液体与撤离");
		p.bool("尝试封堵液体", "仅在引擎判断可安全封堵时处理；不可封的水或岩浆保留保护。", () -> c.borerSealLiquids, v -> { c.borerSealLiquids = v; c.save(); });
		p.bool("遇岩浆尝试转向", "用于支持转向的掘进模式。", () -> c.borerTurnAroundLava, v -> { c.borerTurnAroundLava = v; c.save(); });
		p.bool("结束后沿路回家", "只在对应模式支持回家且具备路线时使用。工具耗尽保护可能直接离线。", () -> c.borerHomeOnDone, v -> { c.borerHomeOnDone = v; c.save(); });
		p.section("威胁响应");
		p.bool("自动反击", "响应主动威胁；苦力怕优先，其次射手。只是看到且未接近的怪不主动攻击。", () -> c.borerAutoDefend, v -> { c.borerAutoDefend = v; c.save(); });
		p.bool("遇威胁暂停", "保留引擎现有交战条件，不因 UI 改版扩大攻击范围。", () -> c.borerPauseOnMob, v -> { c.borerPauseOnMob = v; c.save(); });
		p.bool("副手举盾", "有盾且满足防御条件时使用。", () -> c.borerShieldOnMob, v -> { c.borerShieldOnMob = v; c.save(); });
		p.bool("苦力怕贴身围护", "开启后仅在危险接近时使用围箱。", () -> c.borerSurroundOnCreeper, v -> { c.borerSurroundOnCreeper = v; c.save(); });
		p.slider("威胁检查半径（格）", "检查范围，不代表攻击其中所有怪物。", 2, 24, () -> c.borerMobRadius, v -> { c.borerMobRadius = v; c.save(); });
		p.section("区域挖 · 背包管理");
		p.bool("快满时丢弃普通石料", "仅石料白名单，到安全的区域外丢弃，保留矿物和备用建材。", () -> c.borerAreaDiscardStone, v -> { c.borerAreaDiscardStone = v; c.save(); });
		p.bool("快满时自动存箱", "优先可达工地箱；不足时尝试放备用箱。不会取走箱内物品。", () -> c.borerAreaStoreDrops, v -> { c.borerAreaStoreDrops = v; c.save(); });
		p.action("检查挖矿物资", "打开行动清单。", () -> UiFeature.CHECKLIST.open(p));
		open(parent, p);
	}

	static void guard(Screen parent, KitConfig c) {
		var p = new KitFormScreen(parent, "自动保护", "这里配置保护策略；不主动启动采矿或巡航。").bind(c).id("guard");
        p.action("独立防护："+(dev.twob2tkit.automation.AutomationBridge.guardArmed()?"开":"关"), "空闲也反击主动威胁；按移动键或空格立即关闭并交还控制。", () -> {dev.twob2tkit.automation.AutomationBridge.toggleGuard(mc());guard(parent,c);});
        p.note("紧急停止会关闭独立防护。换维度或离开当前区域 512 格后需要重新开启。");
		p.bool("遇袭协调 Meteor 保护", "沿用当前自动保护逻辑。", () -> c.autoProtectOnHit, v -> { c.autoProtectOnHit = v; c.save(); });
		p.bool("恶魂防护", "独立恶魂防护；具体射程和反弹设置见自动打猪人。", () -> c.ghastGuardEnabled, v -> { c.ghastGuardEnabled = v; c.save(); });
		p.action("挂机离线条件", "血量、玩家警戒等当前设置。", () -> cruiseOptions(p, c));
		p.action("挖矿反击条件", "主动威胁、盾牌和苦力怕保护。", () -> miningSafety(p, c));
		p.action("玩家白名单", "编辑可信玩家。", () -> UiFeature.TRUSTED.open(p));
		open(parent, p);
	}

	static void settings(Screen parent, KitConfig c) {
		var p = new KitFormScreen(parent, "通用设置", "原生与简洁外观共用同一套页面；所有功能入口一致。").bind(c).id("settings");
		p.bool("简洁面板配色", "关闭为默认 Minecraft 风格。保留原有风格选择，不改变功能或快捷键。", () -> c.clickGui, v -> { c.clickGui = v; c.save(); });
		p.bool("打开容器后自动补货", "根据现有清单与补货规则处理。", () -> c.autoRestockFromOpenedContainers, v -> { c.autoRestockFromOpenedContainers = v; c.save(); });
		p.bool("首次材料配方提示", "首次得到关键材料时提示。", () -> c.localRecipeHints, v -> { c.localRecipeHints = v; c.save(); });
		p.bool("背包与工作台配方书增强", "使用本地相关配方。", () -> c.recipeBookEnhancementEnabled, v -> LocalRecipeBookInjector.setEnhancementEnabled(mc(), v));
		p.action("按键绑定", "查看功能键和紧急停止键。", () -> UiFeature.KEYBINDS.open(p));
		p.action("运行与兼容信息", "主包、引擎和依赖信息。", () -> diagnostics(p, c));
		p.action("检查并加载运行引擎", "只热加载运行包；UI 主包变化仍需重启。", () -> { var r = KitClient.reloadBorerRuntime(mc(), false); p.showNotice(r.message(), r.success() ? 0x77DDCC : 0xFF7777); });
		p.danger("恢复内置引擎", "停止相关动作并恢复主包内置引擎，不删除工程。", () -> { var r = KitClient.reloadBorerRuntime(mc(), true); p.showNotice(r.message(), r.success() ? 0x77DDCC : 0xFF7777); });
		p.danger("重置已看配方提示", "仅重置配方提示记录，不清空收藏、工程或物品。", () -> { c.seenRecipeHints.clear(); c.save(); });
		open(parent, p);
	}

	static void diagnostics(Screen parent, KitConfig c) {
		var p = new KitFormScreen(parent, "运行与兼容", "信息为当前客户端状态；已安装不等于模块已经启用。").bind(c).id("diagnostics");
		String version = net.fabricmc.loader.api.FabricLoader.getInstance().getModContainer("twob2tkit").map(m -> m.getMetadata().getVersion().getFriendlyString()).orElse("开发环境");
		p.note("主包版本：" + version);
		p.note("运行引擎：" + (KitClient.borer() == null ? "尚未初始化" : KitClient.borer().runtimeLabel()));
		for (String id : new String[]{"meteor-client", "bobby", "voxy", "litematica", "malilib"})
			p.note(id + "：" + net.fabricmc.loader.api.FabricLoader.getInstance().getModContainer(id).map(m -> "已安装 " + m.getMetadata().getVersion().getFriendlyString()).orElse("未安装"));
		p.note("日志：游戏目录 logs/latest.log；config/twob2tkit 下的功能日志。主包界面需重启，运行引擎可热加载。");
		p.action("复制诊断摘要", "只复制版本信息，不复制账号或聊天记录。", () -> mc().keyboardHandler.setClipboard("twob2tkit " + version + "; engine=" + (KitClient.borer() == null ? "unknown" : KitClient.borer().runtimeLabel())));
		open(parent, p);
	}

	static void routes(Screen parent, KitConfig c) {
		var b = KitClient.borer();
		var p = new KitFormScreen(parent, "挖矿路线", "路线显示与自动返回分开；清空路线需要确认。").bind(c).id("mining-routes");
		p.liveNote(() -> b == null ? "运行引擎未就绪" : "已记录路点 " + b.trailLength() + "；" + b.status());
		p.action("显示 / 隐藏回家箭头", "只显示，不自动移动。", () -> { if (b != null) b.toggleHomeRoute(mc()); });
		p.action("沿路回家", "按现有路点返回，不清除工程进度。", () -> { if (b != null) { KitClient.goBorerHome(mc()); if (b.isGoingHome()) mc().setScreen(null); } });
		p.action("回地狱门", "使用已记录的地狱门路线。", () -> KitClient.goNetherPortal(mc()));
		p.danger("清空回家路点", "清除回家路线，仅保留地狱门记录；不删除区域工程。", () -> {
			if (b == null) return;
			if (b.isActive()) { p.showNotice("请先停止当前任务再清空路线", 0xFF7777); return; }
			b.clearTrailKeepPortal(); p.showNotice("已清空回家路点，地狱门记录保留", 0xFFFF55);
		});
		open(parent, p);
	}

	static void concrete(Screen parent, KitConfig c) {
		var maker=KitClient.concrete();
		var p=new KitFormScreen(parent,"混凝土制作","手持粉末，瞄准漏斗顶面或支撑面；旁边准备好水，再开始循环。").bind(c).id("concrete");
		p.active(()->maker!=null && maker.isActive(),()->{KitClient.toggleConcrete(mc());if(maker!=null && !maker.isActive())p.showNotice(maker.status(),0xFFFF77);});
		p.status(()->maker==null?"模块未就绪":maker.status());
		p.runLabels("开始制作","停止制作");
		p.slider("制作数量","0 为持续循环；缺料或异常时停止。",0,100000,()->c.concreteLimit,v->c.concreteLimit=v);
		p.slider("放置间隔","游戏刻；20 刻约为一秒。",2,40,()->c.concreteDelayTicks,v->c.concreteDelayTicks=v);
		p.slider("保留工具耐久 %","低于该百分比换另一把可用镐；没有可用镐就停止。",1,90,()->c.concreteToolReservePercent,v->c.concreteToolReservePercent=v);
		p.note("自动补充背包里的同色粉末并切换镐。只挖锁定位置的同色混凝土，旁边的漏斗、箱子和水保持原样。");
		p.note("打开界面会暂停；关闭后继续。移动离开、缺料、水失效或工具不足会停止。紧急停止键也可结束。");
		open(parent,p);
	}

	static void builder(Screen parent, KitConfig c) {
		var job=KitClient.buildJob();
		var p=new KitFormScreen(parent,"投影建造","选好并锁定一份投影，准备背包材料，再开始。实际放置使用 Litematica Printer。").bind(c).id("builder-v2");
		p.liveLine(()->dev.twob2tkit.builder.LitematicaAccess.describe());
		p.status(()->job==null?"模块未就绪":job.status());
		p.cycle("走位方式","自动走位使用 Meteor Flight 绕过障碍；定点打印由你自己移动角色。",new String[]{"自动走位建造","定点打印（自己走位）"},()->c.projectionAutoMove?0:1,v->{c.projectionAutoMove=v==0;c.save();});
		p.liveLine(()->job==null?"":job.progress());
		p.liveLine(()->job==null?"":"状态："+job.status());
		p.liveLine(()->job==null?"":job.missing());
		p.active(()->job!=null&&job.isActive(),()->{KitClient.toggleProjectionBuild(mc());if(job!=null&&!job.isActive())p.showNotice(job.status(),0xFFFF77);});
		p.runLabels("开始建造","停止建造").footerHint("打开界面暂停 · 关闭后继续 · 可随时紧急停止");
		p.note("自动模式：检查图纸 → 找可走路线 → 停稳打印 → 核对服务器结果。缺料、有旧方块挡住或找不到路线时，会显示原因并停止。");
		p.action("操作说明","如何加载投影、开始和停止。",()->builderHelp(p,c));
		p.action("材料清单与补货","查看需要准备的材料。",()->UiFeature.CHECKLIST.open(p));
		open(parent,p);
	}
	static void builderHelp(Screen parent,KitConfig c){
		var p=new KitFormScreen(parent,"投影建造 · 操作说明", "从准备到停止").bind(c).id("builder-help");
		p.note("1. 用 M 打开 Litematica，加载图纸并启用一份放置；确认位置、朝向和渲染层。锁定放置可避免误移动图纸。");
		p.note("2. 把材料放进背包，走到投影附近。打印器需开启自动朝向，关闭悬空打印及 Meteor Air Place。");
		p.note("3. U → 生产 → 投影建造，选择自动走位或定点打印，再点开始建造。");
		p.note("4. 自动走位会借用 Flight 并沿可通行空间移动。打开界面暂停、关闭后继续；停止按钮或紧急停止键结束。");
		p.note("5. 看已匹配格数和缺料提示判断进度。不会自动拆错块；缺少支撑或没有可走路线时，先处理提示的问题，再开始。");
		open(parent,p);
	}

	static void villagers(Screen parent, KitConfig c) {
		var scanner = KitClient.villagerScanner();
		var p = new KitFormScreen(parent, "村民职业", "扫描已加载范围内的村民，显示职业与缺少的工作方块。").bind(c).id("villagers");
		p.bool("职业扫描", "只显示职业信息，不操作村民。", () -> scanner != null && scanner.isEnabled(), v -> { if (scanner != null && v != scanner.isEnabled()) KitClient.toggleVillagerScan(mc()); });
		p.slider("扫描范围（格）", "16–96 格。", 16, 96, () -> c.villagerScanRange, v -> { c.villagerScanRange = v; c.save(); });
		p.liveNote(() -> scanner == null || !scanner.isEnabled() ? "扫描未开启" : scanner.summary());
		p.liveNote(() -> scanner == null || !scanner.isEnabled() ? "" : "缺少：" + scanner.missingPairsText());
		p.liveNote(() -> scanner == null || !scanner.isEnabled() ? "" : scanner.unemployedHintText());
		open(parent, p);
	}

	static void scenery(Screen parent, KitConfig c) {
		var b = KitClient.borer();
		var p = new KitFormScreen(parent, "风景预加载", "新建使用当前位置；继续上次保留原圆心、半径和进度。").bind(c).id("scenery");
		p.slider("新任务半径（格）", "16–4096；大半径耗时与磁盘占用更大。不会改变巡航目标。", 16, 4096, () -> c.sceneryRadiusBlocks, v -> { c.sceneryRadiusBlocks = v; c.save(); });
		p.active(() -> b != null && b.isSceneryActive(), () -> {
			if (b != null && b.isSceneryActive()) b.stop(mc(), "手动停止风景任务，保留进度");
			else if (!KitClient.startScenery(mc(), c.sceneryRadiusBlocks, true)) p.showNotice(b == null ? "模块未就绪" : b.sceneryStatus(), 0xFF7777);
		}).runLabels("继续上次", "停止并保留").runUsesDraft(false);
		p.liveNote(() -> b == null ? "运行引擎未就绪" : b.sceneryStatus());
		p.note("按实际服务端视距补漏，采用引擎确认的缓存后端；只标记已确认接收并保存的区块。未获知的状态不会显示为完成。");
		p.action("当前位置新建任务", "替换上次风景任务前需要确认；不改挖矿工程或巡航坐标。", () -> {
			if (b != null && b.isActive()) { p.showNotice("请先停止当前任务，再新建风景任务", 0xFF7777); return; }
			if (!p.finishEdits()) return;
			mc().setScreen(new KitConfirmScreen(p, "新建风景任务", "使用当前位置和半径 " + c.sceneryRadiusBlocks + " 格，替换上次风景任务的进度。", () -> {
				if (KitClient.startScenery(mc(), c.sceneryRadiusBlocks, false)) mc().setScreen(null);
				else p.showNotice(b == null ? "模块未就绪" : b.sceneryStatus(), 0xFF7777);
			}));
		});
		p.action("查看依赖与版本", "Bobby、Voxy 和当前引擎版本。", () -> diagnostics(p, c));
		open(parent, p);
	}

	/** 嵌在模块栏内开详情，否则单独开屏。 */
	private static void open(Screen parent, KitFormScreen panel) {
		panel.bind(KitClient.config());
		if (parent instanceof ClickGuiScreen gui) {
			gui.showDetail(panel);
			return;
		}
		mc().setScreen(panel);
	}

	/** 盾构机密排设置页。 */
	static void borer(Screen parent, KitConfig config) {
		if (TunnelBorer.Mode.fromConfig(config.borerLastMode) == TunnelBorer.Mode.AREA) {
			mc().setScreen(new dev.twob2tkit.borer.AreaSetupScreen(parent, config)); return;
		}
		TunnelBorer borer = KitClient.borer();
		KitFormScreen panel = new KitFormScreen(parent, "盾构机", "点图标勾矿。Xray 用 Meteor 的 Z。");
		panel.active(
			() -> borer != null && borer.isActive(),
			() -> {
				if (borer == null) return;
				if (borer.isActive()) borer.stop(mc(), "设置页关闭");
				else {
					KitClient.prepareForBorer(mc());
					borer.start(mc(), TunnelBorer.Mode.fromConfig(config.borerLastMode));
				}
			});
		panel.section("模式");
		panel.cycle("挖法", "向前 / 向下 / 找矿 / 区域",
			new String[]{"向前挖", "向下挖", "自动找矿", "区域挖"},
			() -> TunnelBorer.Mode.fromConfig(config.borerLastMode).ordinal(),
			i -> {
				config.borerLastMode = TunnelBorer.Mode.values()[i].name();
				config.save();
				borer(parent, config);
			});
		List<KitFormScreen.IconChip> ores = new ArrayList<>();
		for (TunnelBorer.OreTarget ore : TunnelBorer.OreTarget.values()) {
			String tip = ore == TunnelBorer.OreTarget.ANY
				? "全选任意矿石"
				: "点击开关：" + ore.label + "。可同时勾选多种";
			ores.add(new KitFormScreen.IconChip(
				new ItemStack(ore.icon()),
				tip,
				() -> TunnelBorer.OreTarget.contains(config.borerOreTarget, ore),
				() -> {
					config.borerOreTarget = TunnelBorer.OreTarget.toggle(config.borerOreTarget, ore);
					config.save();
				}));
		}
		panel.icons("点图标勾矿。可同时勾选多种。全选=任意矿。", ores,
			() -> TunnelBorer.Mode.fromConfig(config.borerLastMode) == TunnelBorer.Mode.ORE);
		panel.cycle("朝向", "准星或东南西北",
			new String[]{"准星", "北", "南", "西", "东"},
			() -> headingIndex(config.borerHeading),
			i -> {
				config.borerHeading = switch (i) {
					case 1 -> Direction.NORTH.name();
					case 2 -> Direction.SOUTH.name();
					case 3 -> Direction.WEST.name();
					case 4 -> Direction.EAST.name();
					default -> "LOOK";
				};
				config.save();
			});
		panel.bool("轴向瞄准", "只沿东西南北上下挖眼前 1×2。关掉可斜着瞄。",
			() -> config.borerAxisAim,
			v -> {
				config.borerAxisAim = v;
				config.save();
			});
		panel.section("巷道");
		panel.chips("常用断面", List.of(
			chipSize(config, "1×2", 1, 2),
			chipSize(config, "2×2", 2, 2),
			chipSize(config, "3×3", 3, 3),
			chipSize(config, "4×4", 4, 4),
			chipSize(config, "3×5", 3, 5)));
		panel.slider("宽度", "向前=左右宽。向下=截面左右格数；4 格时多 1 格在朝向右侧。", 1, 5, () -> config.borerWidth, v -> {
			config.borerWidth = v;
			config.save();
		});
		panel.slider("高度", "向前=巷道高。向下=截面前后格数；4 格时多 1 格在朝向正前方。", 1, 5, () -> config.borerHeight, v -> {
			config.borerHeight = v;
			config.save();
		});
		panel.slider("前探格", "提前看前方几格。", 1, 5, () -> Math.max(1, config.borerLookAhead), v -> {
			config.borerLookAhead = v;
			config.save();
		});
		panel.slider("找矿半径", "扫描勾选矿的范围。", 8, 32, () -> config.borerOreRadius, v -> {
			config.borerOreRadius = v;
			config.save();
		});
		if (TunnelBorer.Mode.fromConfig(config.borerLastMode) == TunnelBorer.Mode.AREA) {
			panel.action("区域与工程", "设置范围、保存或加载工程、开始挖掘。", () -> mc().setScreen(new dev.twob2tkit.borer.AreaSetupScreen(parent, config)));
		} else {
			panel.note("切到「区域挖」后可设两点矩形；同页设置范围、保存工程和启动。");
		}
		panel.section("安全与反击");
		panel.bool("自动反击", "苦力怕优先，其次持弓/弩射手，最后其他敌怪；使用背包弓箭。", () -> config.borerAutoDefend, v -> { config.borerAutoDefend = v; config.save(); });
		panel.bool("煤经验", "仍挖煤拿经验，但不捡煤。", () -> config.borerCoalXpMode, v -> {
			config.borerCoalXpMode = v;
			config.save();
		});
		panel.bool("石英经验", "下界挖石英只拿经验不捡。", () -> config.borerQuartzXpMode, v -> {
			config.borerQuartzXpMode = v;
			config.save();
		});
		panel.bool("挖完回家", "背包满或镐快坏时沿路回家。", () -> config.borerHomeOnDone, v -> {
			config.borerHomeOnDone = v;
			config.save();
		});
		panel.bool("封水岩浆", "挖到液体时封上。", () -> config.borerSealLiquids, v -> {
			config.borerSealLiquids = v;
			config.save();
		});
		panel.bool("遇岩浆拐弯", "关掉则走直线地铁。", () -> config.borerTurnAroundLava, v -> {
			config.borerTurnAroundLava = v;
			config.save();
		});
		panel.bool("遇怪躲开", "附近有敌对生物时暂停。", () -> config.borerPauseOnMob, v -> {
			config.borerPauseOnMob = v;
			config.save();
		});
		panel.bool("副手举盾", "遇怪时举盾。", () -> config.borerShieldOnMob, v -> {
			config.borerShieldOnMob = v;
			config.save();
		});
		panel.bool("苦力怕围箱", "苦力怕贴身才围。默认关。", () -> config.borerSurroundOnCreeper, v -> {
			config.borerSurroundOnCreeper = v;
			config.save();
		});
		panel.slider("怪物距离", "探测怪物的半径。", 2, 24, () -> config.borerMobRadius, v -> {
			config.borerMobRadius = v;
			config.save();
		});
		panel.bool("回家路点", "只显示金色箭头，不自动走。",
			() -> borer != null && borer.isShowingHomeRoute(),
			v -> {
				if (borer != null) borer.toggleHomeRoute(mc());
			});
		panel.action("清空路点", "丢掉旧路点，只留地狱门。", () -> {
			if (borer != null) borer.clearTrailKeepPortal();
		});
		panel.action("沿路回家", "自动沿走过的路往回走。", () -> {
			if (borer != null) {
				mc().setScreen(null);
				borer.goHome(mc());
			}
		});
		panel.action("回地狱门", "沿走过的路飞回记下的门。", () -> KitClient.goNetherPortal(mc()));
		open(parent, panel);
	}

	/** 巡航坐标与开始。 */
	static void cruise(Screen parent, KitConfig config, KitController controller) {
		KitFormScreen panel = new KitFormScreen(parent, "巡航", "填写目标 X / Y / Z；Y 是巡航高度。返回保留草稿，不自动起飞。").bind(config).id("cruise");
		panel.status(() -> controller.statusLine(mc()));
		panel.active(controller::isActive, () -> {
			if (controller.isActive()) controller.stop(mc(), "设置页停止巡航");
			else if (config.hasTarget) controller.start(mc(), config.targetX, config.targetZ, config.cruiseY);
			else panel.showNotice("请填写目标 X/Z 或填入当前位置", 0xFF7777);
		});
		panel.section("目的地");
		panel.edit("目标 X", "世界坐标；没有目标时必须填写。", () -> config.hasTarget ? KitUi.formatNumber(config.targetX) : "",
			v -> UiDraft.number(v, "目标 X", -30_000_000, 30_000_000, false), v -> { config.targetX = Double.parseDouble(v.trim()); config.hasTarget = true; config.save(); });
		panel.number("巡航 Y", "飞行高度，不是落地高度。", -64, 2048, false, () -> config.cruiseY, v -> { config.cruiseY = v; config.save(); });
		panel.edit("目标 Z", "世界坐标；没有目标时必须填写。", () -> config.hasTarget ? KitUi.formatNumber(config.targetZ) : "",
			v -> UiDraft.number(v, "目标 Z", -30_000_000, 30_000_000, false), v -> { config.targetZ = Double.parseDouble(v.trim()); config.hasTarget = true; config.save(); });
		panel.action("填入当前位置 X/Z", "只填入草稿，保留巡航高度。", () -> {
			if (mc().player == null || controller.isActive()) return;
			panel.draftValue("目标 X", KitUi.formatNumber(mc().player.getX())); panel.draftValue("目标 Z", KitUi.formatNumber(mc().player.getZ()));
		});
		panel.action("填入当前高度", "使用当前脚底 Y。", () -> {
			if (mc().player != null && !controller.isActive()) panel.draftValue("巡航 Y", KitUi.formatNumber(mc().player.getY()));
		});
		panel.action("从剪贴板填入坐标", "支持 X Y Z、/tp 或 Chunkbase 坐标；只填写，不起飞。", () -> {
			if (controller.isActive()) return;
			var coords = KitUi.parseTeleport(mc().keyboardHandler.getClipboard());
			if (coords == null) { panel.showNotice("剪贴板未找到有效坐标", 0xFF7777); return; }
			panel.draftValue("目标 X", KitUi.formatNumber(coords.x())); panel.draftValue("目标 Z", KitUi.formatNumber(coords.z()));
			if (coords.y() != null) panel.draftValue("巡航 Y", KitUi.formatNumber(coords.y()));
		});
		panel.section("收藏与出行");
		panel.action("地点收藏", "编辑收藏不会改变当前目标；按前往才起飞。", () -> UiFeature.PLACES.open(panel));
		panel.action("继续上次巡航", "使用控制器保存的目标，不把本页草稿当成新目标。", () -> { if (!controller.isActive() && controller.resume(mc())) mc().setScreen(null); });
		panel.action("巡航选项", "绕障、到达和挂机保护。", () -> cruiseOptions(panel, config));
		panel.action("附近结构", "查看候选位置与指引。", () -> UiFeature.STRUCTURES.open(panel));
		panel.action("风景预加载", "独立跑图任务。", () -> UiFeature.SCENERY.open(panel));
		panel.action("回地狱门", "按已记录的路线返航。", () -> KitClient.goNetherPortal(mc()));
		open(parent, panel);
	}
	/** 巡航挂机保护与绕障选项。 */
	static void cruiseOptions(Screen parent, KitConfig config) {
		KitFormScreen panel = new KitFormScreen(parent, "巡航选项", "挂机保护。填 0 即关闭对应项。");
		panel.slider("到达半径", "靠近目标多少格算到。", 1.0, 128.0, 1.0, () -> config.arrivalRadius, v -> {
			config.arrivalRadius = v;
			config.save();
		});
		panel.slider("玩家警戒", "挂机（钓鱼/巡航/挖树等）时附近有陌生玩家就下线。0=关。", 0.0, 256.0, 1.0, () -> config.playerRadius, v -> {
			config.playerRadius = v;
			config.save();
		});
		panel.slider("最低心数", "挂机时血量掉到这就下线。4=半血。0=关。", 0.0, 10.0, 0.5, () -> config.minHealth / 2.0, v -> {
			config.minHealth = v * 2.0;
			config.save();
		});
		panel.slider("挂机怪物半径", "走近的骷髅不下线。只在钓鱼时被打中一次才下。此项不再按距离踢人。", 0.0, 32.0, 1.0, () -> config.afkHostileRadius, v -> {
			config.afkHostileRadius = v;
			config.save();
		});
		panel.slider("卡住秒数", "一直不动就停。0=关。", 0, 600, () -> config.stuckSeconds, v -> {
			config.stuckSeconds = v;
			config.save();
		});
		panel.slider("转向速度", "度/tick，越大转得越快。", 1.0, 120.0, 1.0, () -> config.turnSpeed, v -> {
			config.turnSpeed = v;
			config.save();
		});
		panel.slider("障碍探测", "前方多少格内开始绕障。", 8.0, 128.0, 1.0, () -> config.obstacleLookAhead, v -> {
			config.obstacleLookAhead = v;
			config.save();
		});
		panel.slider("绕障环距", "贴身绕开后再平移多少格。", 4.0, 64.0, 1.0, () -> config.obstacleBypassDistance, v -> {
			config.obstacleBypassDistance = v;
			config.save();
		});
		panel.bool("到达后自动离线", "飞到点就断开服务器。", () -> config.disconnectOnArrival, v -> {
			config.disconnectOnArrival = v;
			config.save();
		});
		panel.bool("前方障碍自动绕行", "贴身先升高，远处再水平绕。", () -> config.obstacleAvoidance, v -> {
			config.obstacleAvoidance = v;
			config.save();
		});
		panel.bool("升空时挖掉头上", "基岩、箱子不挖。", () -> config.clearCeiling, v -> {
			config.clearCeiling = v;
			config.save();
		});
		open(parent, panel);
	}

	/** 自动喂养选项。 */
	static void feeder(Screen parent, KitConfig config) {
		AutoFeeder feeder = KitClient.feeder();
		KitFormScreen panel = new KitFormScreen(parent, "自动喂养", "没对应饲料就按顺序改喂下一种。不要和 Meteor auto-breed 一起开。");
		panel.status(() -> feeder == null ? "模块未就绪" : feeder.status());
		panel.active(
			() -> feeder != null && feeder.isActive(),
			() -> KitClient.toggleFeeder(mc()));
		panel.bool("繁殖成体", "喂可以繁殖的成年动物。", () -> config.feederBreedAdults, v -> {
			config.feederBreedAdults = v;
			config.save();
		});
		panel.bool("催熟幼体", "喂幼体加速长大。", () -> config.feederGrowBabies, v -> {
			config.feederGrowBabies = v;
			config.save();
		});
		panel.bool("走近再喂", "范围内的动物走过去喂。", () -> config.feederWalk, v -> {
			config.feederWalk = v;
			config.save();
		});
		panel.bool("喂完收起饲料", "避免 Meteor 自动攻击把动物打死。", () -> config.feederHideFood, v -> {
			config.feederHideFood = v;
			config.save();
		});
		panel.slider("搜寻范围", "格。", 3.0, 24.0, 1.0, () -> config.feederRange, v -> {
			config.feederRange = v;
			config.save();
		});
		List<KitFormScreen.Chip> types = new ArrayList<>();
		for (String id : KitConfig.FEEDER_TYPE_IDS) {
			String label = KitConfig.feederTypeLabel(id);
			types.add(new KitFormScreen.Chip(label,
				() -> config.feederTypeEnabled(id),
				() -> {
					config.setFeederTypeEnabled(id, !config.feederTypeEnabled(id));
					config.save();
				}));
		}
		panel.chips("要喂的种类，可多选。", types);
		panel.section("饲喂优先顺序");
		panel.order("按顺序先喂有饲料的种类。", config::feederTypeOrder, KitConfig::feederTypeLabel,
			(id, delta) -> { config.moveFeederType(id, delta); config.save(); });
		open(parent, panel);
	}

	/** 自动种田选项。 */
	static void planter(Screen parent, KitConfig config) {
		AutoPlanter planter = KitClient.planter();
		KitFormScreen panel = new KitFormScreen(parent, "自动种田", "拿着要种的种子。一片田只种一种。");
		panel.status(() -> planter == null ? "模块未就绪" : planter.status());
		panel.active(
			() -> planter != null && planter.isActive(),
			() -> KitClient.togglePlanter(mc()));
		panel.bool("走近再种", "范围内的空位走过去种。", () -> config.planterWalk, v -> {
			config.planterWalk = v;
			config.save();
		});
		panel.bool("没有耕地时先锄", "只锄水源 4 格内能浇到的地。", () -> config.planterTill, v -> {
			config.planterTill = v;
			config.save();
		});
		panel.bool("甘蔗仙人掌往上叠", "默认只补地面空位。", () -> config.planterStack, v -> {
			config.planterStack = v;
			config.save();
		});
		panel.bool("自动收成", "收成熟作物再种。没拿种子时也会先收田里已熟的。开了 Meteor Nuker 就关掉。", () -> config.planterHarvest, v -> {
			config.planterHarvest = v;
			config.save();
		});
		panel.bool("捡掉落物", "收完或种完一圈后，把附近的小麦、种子等捡进背包。", () -> config.planterPickup, v -> {
			config.planterPickup = v;
			config.save();
		});
		panel.slider("搜寻范围", "格。", 3.0, 24.0, 1.0, () -> config.planterRange, v -> {
			config.planterRange = v;
			config.save();
		});
		open(parent, panel);
	}

	/** 自动挖树选项。 */
	static void chopper(Screen parent, KitConfig config) {
		AutoChopper chopper = KitClient.chopper();
		KitFormScreen panel = new KitFormScreen(parent, "自动挖树", "从树干底部往上砍。连通超过 80 根当建筑跳过。");
		panel.status(() -> chopper == null ? "模块未就绪" : chopper.status());
		panel.active(
			() -> chopper != null && chopper.isActive(),
			() -> KitClient.toggleChopper(mc()));
		panel.bool("走近再砍", "够得着就落地砍，够不着才飞。", () -> config.chopperWalk, v -> {
			config.chopperWalk = v;
			config.save();
		});
		panel.bool("连树叶一起挖", "默认只砍原木。勾了会换剪刀。", () -> config.chopperLeaves, v -> {
			config.chopperLeaves = v;
			config.save();
		});
		panel.bool("砍完补种树苗", "在原位置补对应树苗。", () -> config.chopperReplant, v -> {
			config.chopperReplant = v;
			config.save();
		});
		panel.bool("必须连着树叶", "木头房子不会动。", () -> config.chopperRequireLeaves, v -> {
			config.chopperRequireLeaves = v;
			config.save();
		});
		panel.bool("砍完去捡木头", "落到掉落物上再补种。", () -> config.chopperPickup, v -> {
			config.chopperPickup = v;
			config.save();
		});
		panel.slider("搜寻范围", "格。", 4.0, 32.0, 1.0, () -> config.chopperRange, v -> {
			config.chopperRange = v;
			config.save();
		});
		open(parent, panel);
	}

	/** 自动钓鱼选项。 */
	static void fisher(Screen parent, KitConfig config) {
		AutoFisher fisher = KitClient.fisher();
		KitFormScreen panel = new KitFormScreen(parent, "自动钓鱼", "对准水面后开运行中。会锁开始时的坐标和视角。");
		panel.status(() -> fisher == null ? "模块未就绪" : fisher.status());
		panel.active(
			() -> fisher != null && fisher.isActive(),
			() -> KitClient.toggleFisher(mc()));
		panel.bool("钩子交给 Meteor", "这边只锁视角和存箱。抛收用 auto-fish。", () -> config.fisherLeaveHookToMeteor, v -> {
			config.fisherLeaveHookToMeteor = v;
			config.save();
		});
		panel.slider("箱子半径", "开始时在这个范围找箱子。2–8。", 2, 8, () -> Math.max(2, config.fisherChestRange), v -> {
			config.fisherChestRange = v;
			config.save();
		});
		panel.slider("挂机怪物半径", "骷髅只是站旁边不下线。钓鱼时被打中一次才下。此项不再按距离踢人。", 0.0, 32.0, 1.0, () -> config.afkHostileRadius, v -> {
			config.afkHostileRadius = v;
			config.save();
		});
		open(parent, panel);
	}

	/** 自动围箱选项。 */
	static void surround(Screen parent, KitConfig config) {
		AutoSurround surround = KitClient.surround();
		KitFormScreen panel = new KitFormScreen(parent, "自动围箱", "只摆 10 块：脚下、四面、头边、头顶。数字越小越先用。");
		panel.status(() -> surround == null ? "模块未就绪" : surround.status());
		panel.active(
			() -> surround != null && surround.isActive(),
			() -> KitClient.toggleSurround(mc()));
		panel.cycle("形状", "锁定钉在按下位置；跟随会跟着走。",
			new String[]{"十格锁定", "十格跟随"},
			() -> AutoSurround.Mode.fromConfig(config.surroundMode) == AutoSurround.Mode.FULL ? 0 : 1,
			i -> {
				config.surroundMode = (i == 0 ? AutoSurround.Mode.FULL : AutoSurround.Mode.PLUS).name();
				config.save();
			});
		List<KitFormScreen.Chip> blocks = new ArrayList<>();
		for (SurroundBlocks.Choice choice : SurroundBlocks.CATALOG) {
			blocks.add(new KitFormScreen.Chip(choice.label(),
				() -> config.surroundBlockIds.contains(choice.id()),
				() -> toggleSurroundBlock(config, choice.id())));
		}
		panel.chips("多选围箱方块。至少留一种。", blocks);
		panel.slider("每拍块数", "每 tick 最多放几块。", 1, 4, () -> config.surroundPlacesPerTick, v -> {
			config.surroundPlacesPerTick = v;
			config.save();
		});
		panel.bool("围好后继续补洞", "默认关。", () -> config.surroundKeepRepair, v -> {
			config.surroundKeepRepair = v;
			config.save();
		});
		open(parent, panel);
	}

	/** 打猪人选项。 */
	static void brawler(Screen parent, KitConfig config) {
		PiglinBrawler brawler = KitClient.brawler();
		KitFormScreen panel = new KitFormScreen(parent, "自动打猪人", "距离单位是格。开了 Meteor KillAura 就把近战交出去。");
		panel.status(() -> brawler == null ? "模块未就绪" : brawler.status());
		panel.bool("独立恶魂防护", "未开启打猪人时也使用恶魂防护设置。", () -> config.ghastGuardEnabled, v -> { config.ghastGuardEnabled = v; config.save(); });
		panel.active(
			() -> brawler != null && brawler.isActive(),
			() -> {
				if (brawler != null) brawler.toggle(mc());
			});
		panel.bool("近战自己砍", "关掉则完全交给 Meteor KillAura。", () -> config.brawlerMeleeEnabled, v -> {
			config.brawlerMeleeEnabled = v;
			config.save();
		});
		panel.bool("反弹恶魂火球", "关掉则交给 Meteor Arrow Dodge 躲。两边只能开一个。", () -> config.brawlerDeflectFireball, v -> {
			config.brawlerDeflectFireball = v;
			config.save();
		});
		panel.bool("飞行拉扯自己躲", "开了 Meteor Arrow Dodge 就关掉。", () -> config.brawlerStrafeDodge, v -> {
			config.brawlerStrafeDodge = v;
			config.save();
		});
		panel.slider("近战距离", "原版 3。", 1.0, 6.0, 0.1, () -> config.brawlerMeleeReach, v -> {
			config.brawlerMeleeReach = v;
			config.save();
		});
		panel.slider("火球反弹距离", "要进到这么近才打得回去。", 1.0, 6.0, 0.1, () -> config.brawlerFireballReach, v -> {
			config.brawlerFireballReach = v;
			config.save();
		});
		panel.slider("恶魂弓射程", "拉弓射恶魂。", 8.0, 96.0, 1.0, () -> config.brawlerGhastRange, v -> {
			config.brawlerGhastRange = v;
			config.save();
		});
		panel.slider("弩猪弓射程", "射拿弩的猪人。", 8.0, 96.0, 1.0, () -> config.brawlerCrossbowRange, v -> {
			config.brawlerCrossbowRange = v;
			config.save();
		});
		panel.slider("拉弓 tick", "满弓 20。", 5, 60, () -> config.brawlerBowChargeTicks, v -> {
			config.brawlerBowChargeTicks = v;
			config.save();
		});
		panel.slider("最低血量", "掉到这就停手。0=不停。", 0.0, 20.0, 0.5, () -> config.brawlerMinHealth, v -> {
			config.brawlerMinHealth = v;
			config.save();
		});
		panel.slider("悬停高度", "飞行时至少高出猪人这么多。0=不管。", 0.0, 16.0, 0.5, () -> config.brawlerHoverHeight, v -> {
			config.brawlerHoverHeight = v;
			config.save();
		});
		panel.slider("跟踪角速度", "每 tick 最多转几度。越小越稳，默认 7。", 2.0, 30.0, 0.5, () -> config.brawlerLookDegreesPerTick, v -> {
			config.brawlerLookDegreesPerTick = v;
			config.save();
		});
		open(parent, panel);
	}

	/** 生存提醒选项。 */
	static void survival(Screen parent, KitConfig config) {
		KitFormScreen panel = new KitFormScreen(parent, "生存提醒", "提醒显示在屏幕中央和聊天栏。");
		panel.bool("回血物资不足", "低于最低数量就提醒。", () -> config.healingItemAlert, v -> {
			config.healingItemAlert = v;
			config.save();
		});
		panel.slider("回血最低数量", "背包合计。", 0, 64, () -> config.minimumHealingItems, v -> {
			config.minimumHealingItems = v;
			config.save();
		});
		panel.action("多选回血物品", "打开原来的多选页。", () -> mc().setScreen(new HealingItemsScreen(panel, config)));
		panel.bool("下界未穿金质护甲", "猪人会攻击。", () -> config.netherGoldArmorAlert, v -> {
			config.netherGoldArmorAlert = v;
			config.save();
		});
		panel.bool("不死图腾不足", "", () -> config.totemAlert, v -> {
			config.totemAlert = v;
			config.save();
		});
		panel.slider("图腾最低数量", "", 0, 16, () -> config.minimumTotems, v -> {
			config.minimumTotems = v;
			config.save();
		});
		panel.bool("鞘翅耐久过低", "", () -> config.elytraDurabilityAlert, v -> {
			config.elytraDurabilityAlert = v;
			config.save();
		});
		panel.slider("鞘翅最低耐久", "", 1, 431, () -> config.minimumElytraDurability, v -> {
			config.minimumElytraDurability = v;
			config.save();
		});
		panel.slider("重复提醒间隔", "秒。", 5, 600, () -> config.survivalAlertCooldownSeconds, v -> {
			config.survivalAlertCooldownSeconds = v;
			config.save();
		});
		open(parent, panel);
	}

	/** 模块栏「设置」页：勾选开关，不是再开一层设置。 */
	static KitFormScreen general(ClickGuiScreen gui, KitConfig config) {
		KitFormScreen panel = new KitFormScreen(gui, "设置", "");
		panel.action("切换为 Minecraft 风格菜单", "使用原版按钮与分页；保存后，下次打开仍使用这个风格。", gui::switchToPages);
		panel.note("统一操作：名称打开配置；右侧开始或停止；编辑后回车应用，Esc 返回。");
		panel.bool("打开容器后自动补货", "开箱时按仓库记录补背包。",
			() -> config.autoRestockFromOpenedContainers,
			v -> {
				config.autoRestockFromOpenedContainers = v;
				config.save();
			});
		panel.bool("配方书增强", "背包/工作台显示本地相关配方。",
			() -> config.recipeBookEnhancementEnabled,
			v -> LocalRecipeBookInjector.setEnhancementEnabled(mc(), v));
		panel.action("按键绑定", "巡航、盾构、紧急停止等热键。",
			() -> mc().setScreen(new KitKeyBindsScreen(gui)));
		panel.action("检查并加载新版", "热加载 runtime/twob2tkit-engine.jar。", () -> {
			TunnelBorer.ReloadResult result = KitClient.reloadBorerRuntime(mc(), false);
			gui.showNotice(result.message(), result.success() ? 0x55FF55 : 0xFF5555);
		});
		panel.action("恢复内置版本", "丢掉热加载包，回到当前 mods 里那份引擎。", () -> {
			TunnelBorer.ReloadResult result = KitClient.reloadBorerRuntime(mc(), true);
			gui.showNotice(result.message(), result.success() ? 0x55FF55 : 0xFF5555);
		});
		TunnelBorer borer = KitClient.borer();
		panel.note(borer == null ? "运行引擎尚未初始化" : "当前运行引擎：" + borer.runtimeLabel());
		return panel;
	}

	/** 最近死亡点操作。 */
	static void death(Screen parent, KitConfig config, KitController controller) {
		KitFormScreen panel = new KitFormScreen(parent, "最近死亡点", deathSummary(config));
		panel.action("自动返回死亡点上方", "升到安全高度，到达后不离线。", () -> {
			if (!config.hasDeathPoint) return;
			if (mc().level == null || !mc().level.dimension().identifier().toString().equals(config.deathDimension)) { panel.showNotice("死亡点在另一维度，请先切换维度", 0xFF7777); return; }
			double safeY = Math.max(config.cruiseY, config.deathY + 32.0);
			controller.startDeathRecovery(mc(), config.deathX, config.deathZ, safeY);
			mc().setScreen(null);
		});
		panel.action("设为巡航目标", "返回后可开始巡航。", () -> {
			if (!config.hasDeathPoint) return;
			if (mc().level == null || !mc().level.dimension().identifier().toString().equals(config.deathDimension)) { panel.showNotice("死亡点在另一维度，请先切换维度", 0xFF7777); return; }
			config.targetX = config.deathX;
			config.targetZ = config.deathZ;
			config.cruiseY = Math.max(config.cruiseY, config.deathY + 32.0);
			config.hasTarget = true;
			config.save();
		});
		panel.action("复制坐标", "", () -> {
			if (!config.hasDeathPoint || mc().keyboardHandler == null) return;
			mc().keyboardHandler.setClipboard(String.format(Locale.ROOT, "%.1f %.1f %.1f", config.deathX, config.deathY, config.deathZ));
		});
		panel.danger("清除死亡点", "清除当前死亡点记录，不能通过返回撤销。", () -> {
			config.clearDeathPoint();
		});
		open(parent, panel);
	}

	/** 死亡点摘要文案。 */
	private static String deathSummary(KitConfig config) {
		if (!config.hasDeathPoint) return "还没有记录。被打和死亡会写入 config/twob2tkit/combat.log。";
		String time = java.time.format.DateTimeFormatter.ofPattern("MM-dd HH:mm:ss")
			.withZone(java.time.ZoneId.systemDefault())
			.format(java.time.Instant.ofEpochMilli(config.deathTimeEpochMillis));
		String hit = config.lastAttackTimeEpochMillis <= 0 ? ""
			: " 上次被打 " + java.time.format.DateTimeFormatter.ofPattern("HH:mm:ss")
			.withZone(java.time.ZoneId.systemDefault())
			.format(java.time.Instant.ofEpochMilli(config.lastAttackTimeEpochMillis))
			+ " " + config.lastAttacker;
		return String.format(Locale.ROOT, "%s  %s  凶手:%s  %s%s",
			time,
			config.deathActivity.isBlank() ? "空闲" : config.deathActivity,
			config.deathKiller.isBlank() ? "未知" : config.deathKiller,
			config.deathMessage.isBlank() ? String.format(Locale.ROOT, "X %.0f Y %.0f Z %.0f", config.deathX, config.deathY, config.deathZ) : config.deathMessage,
			hit);
	}

	/** 区域断面快捷 chip。 */
	private static KitFormScreen.Chip chipAreaSize(KitConfig config, String label, int w, int h) {
		return new KitFormScreen.Chip(label,
			() -> config.borerWidth == w && config.borerAreaSliceHeight == h,
			() -> {
				config.borerWidth = w;
				config.borerHeight = h;
				config.borerAreaSliceHeight = h;
				config.save();
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

	/** 勾选/取消围箱方块，至少留一种。 */
	private static void toggleSurroundBlock(KitConfig config, String id) {
		List<String> ids = new ArrayList<>(config.surroundBlockIds);
		if (ids.contains(id)) {
			if (ids.size() == 1) return;
			ids.remove(id);
		} else {
			ids.add(id);
		}
		config.surroundBlockIds = SurroundBlocks.normalize(ids);
		config.surroundBlockId = config.surroundBlockIds.getFirst();
		config.save();
	}

	/** 写巡航坐标；支持粘贴传送文本。 */
	private static void setCoord(KitConfig config, String raw, char axis) {
		KitUi.TeleportCoords parsed = KitUi.parseTeleport(raw);
		if (parsed != null) {
			config.targetX = parsed.x();
			config.targetZ = parsed.z();
			if (parsed.y() != null) config.cruiseY = parsed.y();
			config.hasTarget = true;
			config.save();
			return;
		}
		try {
			double value = Double.parseDouble(raw.trim());
			if (!Double.isFinite(value)) return;
			if (axis == 'x') {
				config.targetX = value;
				config.hasTarget = true;
			} else if (axis == 'z') {
				config.targetZ = value;
				config.hasTarget = true;
			} else {
				config.cruiseY = value;
			}
			config.save();
		} catch (NumberFormatException ignored) {
		}
	}

	/** 玩家当前 X。 */
	private static double currentX() {
		return mc().player == null ? 0 : mc().player.getX();
	}

	/** 玩家当前 Z。 */
	private static double currentZ() {
		return mc().player == null ? 0 : mc().player.getZ();
	}

	/** 当前客户端实例。 */
	private static Minecraft mc() {
		return Minecraft.getInstance();
	}
}
