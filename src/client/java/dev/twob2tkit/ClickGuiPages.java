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

	/** 嵌在模块栏内开详情，否则单独开屏。 */
	private static void open(Screen parent, ClickGuiPanelScreen panel) {
		if (parent instanceof ClickGuiScreen gui) {
			gui.showDetail(panel);
			return;
		}
		mc().setScreen(panel);
	}

	/** 盾构机密排设置页。 */
	static void borer(Screen parent, KitConfig config) {
		TunnelBorer borer = KitClient.borer();
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "盾构机", "点图标勾矿。Xray 用 Meteor 的 Z。");
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
			});
		List<ClickGuiPanelScreen.IconChip> ores = new ArrayList<>();
		for (TunnelBorer.OreTarget ore : TunnelBorer.OreTarget.values()) {
			String tip = ore == TunnelBorer.OreTarget.ANY
				? "全选任意矿石"
				: "点击开关：" + ore.label + "。可同时勾选多种";
			ores.add(new ClickGuiPanelScreen.IconChip(
				new ItemStack(ore.icon()),
				tip,
				() -> TunnelBorer.OreTarget.contains(config.borerOreTarget, ore),
				() -> {
					config.borerOreTarget = TunnelBorer.OreTarget.toggle(config.borerOreTarget, ore);
					config.save();
				}));
		}
		panel.icons("点图标勾矿。可同时勾选多种。全选=任意矿。", ores,
			() -> TunnelBorer.Mode.fromConfig(config.borerLastMode) != TunnelBorer.Mode.AREA);
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
			panel.action("区域设置", "标点、断面与工程管理。", () -> open(parent, borerAreaPanel(parent, config)));
		} else {
			panel.note("切到「区域挖」后可设两点矩形；设置页里分标点 / 断面 / 工程。");
		}
		panel.section("安全与回家");
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

	/** 区域挖标点/断面/工程面板。 */
	static ClickGuiPanelScreen borerAreaPanel(Screen parent, KitConfig config) {
		TunnelBorer borer = KitClient.borer();
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "区域挖", BorerAreaMarks.sizeLabel(config));
		panel.section("标点");
		panel.edit("点A", "x y z。可粘贴坐标。",
			() -> BorerAreaMarks.format(config.borerAreaASet, config.borerAreaAx, config.borerAreaAy, config.borerAreaAz),
			s -> BorerAreaMarks.applyA(config, s));
		panel.edit("点B", "另一个角 x y z。",
			() -> BorerAreaMarks.format(config.borerAreaBSet, config.borerAreaBx, config.borerAreaBy, config.borerAreaBz),
			s -> BorerAreaMarks.applyB(config, s));
		panel.action("准星为A", "用当前准星打到的方块（最远 128 格）。", () -> {
			var pos = BorerAreaMarks.lookBlock(mc());
			if (pos == null) {
				BorerAreaMarks.tell(mc(), "准星没有方块");
				return;
			}
			BorerAreaMarks.setA(config, pos);
			BorerAreaMarks.tell(mc(), "点A " + pos.getX() + " " + pos.getY() + " " + pos.getZ());
		});
		panel.action("准星为B", "第二个角。太远先看过去再点。", () -> {
			var pos = BorerAreaMarks.lookBlock(mc());
			if (pos == null) {
				BorerAreaMarks.tell(mc(), "准星没有方块");
				return;
			}
			BorerAreaMarks.setB(config, pos);
			BorerAreaMarks.tell(mc(), "点B " + pos.getX() + " " + pos.getY() + " " + pos.getZ()
				+ "  " + BorerAreaMarks.sizeLabel(config));
		});
		panel.action("下次左键为A", "关掉界面后看向目标，点一下左键。", () -> {
			mc().setScreen(null);
			KitClient.beginPickingArea(mc(), 1);
		});
		panel.action("下次左键为B", "关掉界面后看向目标，点一下左键。", () -> {
			mc().setScreen(null);
			KitClient.beginPickingArea(mc(), 2);
		});
		panel.action("脚下为A", "当前站立这格当点A。", () -> {
			if (mc().player == null) return;
			BorerAreaMarks.setA(config, mc().player.blockPosition());
		});
		panel.action("脚下 40×40", "以脚下为原点，朝向右/前铺开 40×40。", () -> {
			if (mc().player == null) return;
			BorerAreaMarks.sizeFromFeet(config, mc().player.blockPosition(), mc().player.getDirection(), 40);
			config.borerLastMode = TunnelBorer.Mode.AREA.name();
			config.save();
			BorerAreaMarks.tell(mc(), "已标 " + BorerAreaMarks.sizeLabel(config));
		});
		panel.action("清除区域", "忘掉两个角。", () -> BorerAreaMarks.clear(config));
		panel.section("断面");
		panel.note("条带宽×一次挖高。1×2 一条巷道，2×2 两列一起挖。");
		panel.chips("常用", List.of(
			chipAreaSize(config, "1×2", 1, 2),
			chipAreaSize(config, "2×2", 2, 2),
			chipAreaSize(config, "3×3", 3, 3),
			chipAreaSize(config, "4×4", 4, 4)));
		panel.slider("条带宽", "垂直于前进方向一次挖几列。", 1, 5, () -> Math.max(1, config.borerWidth), v -> {
			config.borerWidth = v;
			config.save();
		});
		panel.slider("一次挖高", "沿条带每次挖这么高。", 1, 5, () -> Math.max(1, config.borerAreaSliceHeight), v -> {
			config.borerAreaSliceHeight = v;
			config.save();
		});
		panel.section("工程");
		panel.action("保存当前", "把点 A/B 和断面写入列表；同名覆盖。", () -> {
			if (!config.borerAreaASet || !config.borerAreaBSet) {
				BorerAreaMarks.tell(mc(), "先设点A和点B");
				return;
			}
			String name = BorerAreaProjects.activeName(config);
			if (name.isEmpty()) name = BorerAreaProjects.defaultName(config);
			boolean added = config.upsertAreaProject(name, BorerAreaProjects.currentDimension(mc()));
			BorerAreaMarks.tell(mc(), (added ? "已保存工程：" : "已更新工程：") + name);
		});
		panel.action("工程管理", "查看、加载、删除已保存的区域。", () -> mc().setScreen(new AreaProjectsScreen(panel, config)));
		panel.action("开始挖这块", "按已标区域启动盾构。", () -> {
			if (!config.borerAreaASet || !config.borerAreaBSet) {
				BorerAreaMarks.tell(mc(), "先设点A和点B");
				return;
			}
			config.borerLastMode = TunnelBorer.Mode.AREA.name();
			config.save();
			if (borer == null) return;
			KitClient.prepareForBorer(mc());
			borer.start(mc(), TunnelBorer.Mode.AREA);
			mc().setScreen(null);
		});
		return panel;
	}

	/** 巡航坐标与开始。 */
	static void cruise(Screen parent, KitConfig config, KitController controller) {
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "巡航", "填坐标后点运行中，或用下面的开始。");
		panel.active(controller::isActive, () -> {
			if (controller.isActive()) controller.stop(mc(), "设置页停止");
			else if (config.hasTarget) controller.start(mc(), config.targetX, config.targetZ, config.cruiseY);
		});
		panel.edit("X", "可粘贴 /tp 坐标。",
			() -> KitUi.formatNumber(config.hasTarget ? config.targetX : currentX()),
			s -> setCoord(config, s, 'x'));
		panel.edit("Y", "巡航高度。",
			() -> KitUi.formatNumber(config.cruiseY),
			s -> setCoord(config, s, 'y'));
		panel.edit("Z", "目标 Z。",
			() -> KitUi.formatNumber(config.hasTarget ? config.targetZ : currentZ()),
			s -> setCoord(config, s, 'z'));
		panel.slider("转向速度", "度/tick，越大转得越快。", 1.0, 120.0, 1.0, () -> config.turnSpeed, v -> {
			config.turnSpeed = v;
			config.save();
		});
		panel.action("填入当前位置", "用当前站立的 X / Z。", () -> {
			if (mc().player == null) return;
			config.targetX = mc().player.getX();
			config.targetZ = mc().player.getZ();
			config.hasTarget = true;
			config.save();
		});
		panel.action("填入当前高度", "用当前脚底当巡航 Y。", () -> {
			if (mc().player == null) return;
			config.cruiseY = mc().player.getY();
			config.save();
		});
		panel.action("开始巡航", "保存坐标并起飞。", () -> {
			if (!config.hasTarget) return;
			controller.start(mc(), config.targetX, config.targetZ, config.cruiseY);
			mc().setScreen(null);
		});
		open(parent, panel);
	}

	/** 巡航挂机保护与绕障选项。 */
	static void cruiseOptions(Screen parent, KitConfig config) {
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "巡航选项", "挂机保护。填 0 即关闭对应项。");
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
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "自动喂养", "没对应饲料就按顺序改喂下一种。不要和 Meteor auto-breed 一起开。");
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
		List<ClickGuiPanelScreen.Chip> types = new ArrayList<>();
		for (String id : KitConfig.FEEDER_TYPE_IDS) {
			String label = KitConfig.feederTypeLabel(id);
			types.add(new ClickGuiPanelScreen.Chip(label,
				() -> config.feederTypeEnabled(id),
				() -> {
					config.setFeederTypeEnabled(id, !config.feederTypeEnabled(id));
					config.save();
				}));
		}
		panel.chips("要喂的种类，可多选。", types);
		open(parent, panel);
	}

	/** 自动种田选项。 */
	static void planter(Screen parent, KitConfig config) {
		AutoPlanter planter = KitClient.planter();
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "自动种田", "拿着要种的种子。一片田只种一种。");
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
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "自动挖树", "从树干底部往上砍。连通超过 80 根当建筑跳过。");
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
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "自动钓鱼", "对准水面后开运行中。会锁开始时的坐标和视角。");
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
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "自动围箱", "只摆 10 块：脚下、四面、头边、头顶。数字越小越先用。");
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
		List<ClickGuiPanelScreen.Chip> blocks = new ArrayList<>();
		for (SurroundBlocks.Choice choice : SurroundBlocks.CATALOG) {
			blocks.add(new ClickGuiPanelScreen.Chip(choice.label(),
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
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "自动打猪人", "距离单位是格。开了 Meteor KillAura 就把近战交出去。");
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
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "生存提醒", "提醒显示在屏幕中央和聊天栏。");
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
	static ClickGuiPanelScreen general(ClickGuiScreen gui, KitConfig config) {
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(gui, "设置", "");
		panel.bool("模块栏界面", "关掉就回到原来的分页按钮。再在分页的设置里勾回来。",
			() -> config.clickGui,
			v -> {
				if (!v) gui.switchToPages();
			});
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
		panel.action("检查并加载新版", "热加载 runtime/2b2t-kit-engine.jar。", () -> {
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
		ClickGuiPanelScreen panel = new ClickGuiPanelScreen(parent, "最近死亡点", deathSummary(config));
		panel.action("自动返回死亡点上方", "升到安全高度，到达后不离线。", () -> {
			if (!config.hasDeathPoint) return;
			double safeY = Math.max(config.cruiseY, config.deathY + 32.0);
			controller.startDeathRecovery(mc(), config.deathX, config.deathZ, safeY);
			mc().setScreen(null);
		});
		panel.action("设为巡航目标", "返回后可开始巡航。", () -> {
			if (!config.hasDeathPoint) return;
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
		panel.action("清除死亡点", "", () -> {
			config.hasDeathPoint = false;
			config.save();
		});
		open(parent, panel);
	}

	/** 死亡点摘要文案。 */
	private static String deathSummary(KitConfig config) {
		if (!config.hasDeathPoint) return "还没有记录。被打和死亡会写入 config/2b2t-kit/combat.log。";
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
	private static ClickGuiPanelScreen.Chip chipAreaSize(KitConfig config, String label, int w, int h) {
		return new ClickGuiPanelScreen.Chip(label,
			() -> config.borerWidth == w && config.borerAreaSliceHeight == h,
			() -> {
				config.borerWidth = w;
				config.borerHeight = h;
				config.borerAreaSliceHeight = h;
				config.save();
			});
	}

	/** 巷道断面快捷 chip。 */
	private static ClickGuiPanelScreen.Chip chipSize(KitConfig config, String label, int w, int h) {
		return new ClickGuiPanelScreen.Chip(label,
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
