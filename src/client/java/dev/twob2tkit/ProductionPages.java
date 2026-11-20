package dev.twob2tkit;

import net.minecraft.client.gui.screens.Screen;
import java.util.ArrayList;
import java.util.List;
import dev.twob2tkit.chopper.AutoChopper;
import dev.twob2tkit.feeder.AutoFeeder;
import dev.twob2tkit.fisher.AutoFisher;
import dev.twob2tkit.piglin.PiglinBrawler;
import dev.twob2tkit.planter.AutoPlanter;

import static dev.twob2tkit.FeaturePages.mc;
import static dev.twob2tkit.FeaturePages.open;

/** 生产分类：混凝土、投影建造、村民、喂养、种田、砍树、钓鱼与打猪人。 */
final class ProductionPages {
	private ProductionPages() {
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
		p.action("自动补齐材料并建造", "按当前投影缺料自动取料、采集、制作，再继续施工。", () -> dev.twob2tkit.material.MaterialJobPages.projection(p, c));
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
		p.slider("扫描范围（格）", "16–96 格。", 16, 96, () -> c.villagerScanRange, v -> c.villagerScanRange = v);
		p.liveNote(() -> scanner == null || !scanner.isEnabled() ? "扫描未开启" : scanner.summary());
		p.liveNote(() -> scanner == null || !scanner.isEnabled() ? "" : "缺少：" + scanner.missingPairsText());
		p.liveNote(() -> scanner == null || !scanner.isEnabled() ? "" : scanner.unemployedHintText());
		open(parent, p);
	}

	/** 自动喂养选项。 */
	static void feeder(Screen parent, KitConfig config) {
		AutoFeeder feeder = KitClient.feeder();
		KitFormScreen panel = new KitFormScreen(parent, "自动喂养", "没对应饲料就按顺序改喂下一种。不要和 Meteor auto-breed 一起开。");
		panel.status(() -> feeder == null ? "模块未就绪" : feeder.status());
		panel.active(
			() -> feeder != null && feeder.isActive(),
			() -> KitClient.toggleFeeder(mc()));
		panel.bool("繁殖成体", "喂可以繁殖的成年动物。", () -> config.feederBreedAdults, v -> config.feederBreedAdults = v);
		panel.bool("催熟幼体", "喂幼体加速长大。", () -> config.feederGrowBabies, v -> config.feederGrowBabies = v);
		panel.bool("走近再喂", "范围内的动物走过去喂。", () -> config.feederWalk, v -> config.feederWalk = v);
		panel.bool("喂完收起饲料", "避免 Meteor 自动攻击把动物打死。", () -> config.feederHideFood, v -> config.feederHideFood = v);
		panel.slider("搜寻范围", "格。", 3.0, 24.0, 1.0, () -> config.feederRange, v -> config.feederRange = v);
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
		KitFormScreen panel = new KitFormScreen(parent, "自动种田", "仅维护已有耕地，不向田外扩种。拿着要种的种子，一片田只种一种。");
		panel.status(() -> planter == null ? "模块未就绪" : planter.status());
		panel.active(
			() -> planter != null && planter.isActive(),
			() -> KitClient.togglePlanter(mc()));
		panel.bool("走近再种", "只走到本次维护名单中的既有耕地，不向周围普通地块扩种。", () -> config.planterWalk, v -> config.planterWalk = v);
		panel.note("日常种田不翻耕草地或泥土；新开田必须通过独立入口明确确认范围。");
		panel.note("甘蔗、竹子等普通地面种植不属于日常耕地维护，需独立确认种植范围。");
		panel.bool("自动收成", "收成熟作物再种。没拿种子时也会先收田里已熟的。开了 Meteor Nuker 就关掉。", () -> config.planterHarvest, v -> config.planterHarvest = v);
		panel.bool("捡掉落物", "收完或种完一圈后，把附近的小麦、种子等捡进背包。", () -> config.planterPickup, v -> config.planterPickup = v);
		panel.slider("搜寻范围", "格。", 3.0, 24.0, 1.0, () -> config.planterRange, v -> config.planterRange = v);
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
		panel.bool("走近再砍", "够得着就落地砍，够不着才飞。", () -> config.chopperWalk, v -> config.chopperWalk = v);
		panel.bool("连树叶一起挖", "默认只砍原木。勾了会换剪刀。", () -> config.chopperLeaves, v -> config.chopperLeaves = v);
		panel.bool("砍完补种树苗", "在原位置补对应树苗。", () -> config.chopperReplant, v -> config.chopperReplant = v);
		panel.bool("必须连着树叶", "木头房子不会动。", () -> config.chopperRequireLeaves, v -> config.chopperRequireLeaves = v);
		panel.bool("砍完去捡木头", "落到掉落物上再补种。", () -> config.chopperPickup, v -> config.chopperPickup = v);
		panel.slider("搜寻范围", "格。", 4.0, 32.0, 1.0, () -> config.chopperRange, v -> config.chopperRange = v);
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
		panel.bool("钩子交给 Meteor", "这边只锁视角和存箱。抛收用 auto-fish。", () -> config.fisherLeaveHookToMeteor, v -> config.fisherLeaveHookToMeteor = v);
		panel.slider("箱子半径", "开始时在这个范围找箱子。2–8。", 2, 8, () -> Math.max(2, config.fisherChestRange), v -> config.fisherChestRange = v);
		panel.slider("挂机怪物半径", "骷髅只是站旁边不下线。钓鱼时被打中一次才下。此项不再按距离踢人。", 0.0, 32.0, 1.0, () -> config.afkHostileRadius, v -> config.afkHostileRadius = v);
		open(parent, panel);
	}

	/** 打猪人选项。 */
	static void brawler(Screen parent, KitConfig config) {
		PiglinBrawler brawler = KitClient.brawler();
		KitFormScreen panel = new KitFormScreen(parent, "自动打猪人", "距离单位是格。开了 Meteor KillAura 就把近战交出去。");
		panel.status(() -> brawler == null ? "模块未就绪" : brawler.status());
		panel.bool("独立恶魂防护", "未开启打猪人时也使用恶魂防护设置。", () -> config.ghastGuardEnabled, v -> config.ghastGuardEnabled = v);
		panel.active(
			() -> brawler != null && brawler.isActive(),
			() -> {
				if (brawler != null) brawler.toggle(mc());
			});
		panel.bool("近战自己砍", "关掉则完全交给 Meteor KillAura。", () -> config.brawlerMeleeEnabled, v -> config.brawlerMeleeEnabled = v);
		panel.bool("反弹恶魂火球", "关掉则交给 Meteor Arrow Dodge 躲。两边只能开一个。", () -> config.brawlerDeflectFireball, v -> config.brawlerDeflectFireball = v);
		panel.bool("飞行拉扯自己躲", "开了 Meteor Arrow Dodge 就关掉。", () -> config.brawlerStrafeDodge, v -> config.brawlerStrafeDodge = v);
		panel.slider("近战距离", "原版 3。", 1.0, 6.0, 0.1, () -> config.brawlerMeleeReach, v -> config.brawlerMeleeReach = v);
		panel.slider("火球反弹距离", "要进到这么近才打得回去。", 1.0, 6.0, 0.1, () -> config.brawlerFireballReach, v -> config.brawlerFireballReach = v);
		panel.slider("恶魂弓射程", "拉弓射恶魂。", 8.0, 96.0, 1.0, () -> config.brawlerGhastRange, v -> config.brawlerGhastRange = v);
		panel.slider("弩猪弓射程", "射拿弩的猪人。", 8.0, 96.0, 1.0, () -> config.brawlerCrossbowRange, v -> config.brawlerCrossbowRange = v);
		panel.slider("拉弓 tick", "满弓 20。", 5, 60, () -> config.brawlerBowChargeTicks, v -> config.brawlerBowChargeTicks = v);
		panel.slider("最低血量", "掉到这就停手。0=不停。", 0.0, 20.0, 0.5, () -> config.brawlerMinHealth, v -> config.brawlerMinHealth = v);
		panel.slider("悬停高度", "飞行时至少高出猪人这么多。0=不管。", 0.0, 16.0, 0.5, () -> config.brawlerHoverHeight, v -> config.brawlerHoverHeight = v);
		panel.slider("跟踪角速度", "每 tick 最多转几度。越小越稳，默认 7。", 2.0, 30.0, 0.5, () -> config.brawlerLookDegreesPerTick, v -> config.brawlerLookDegreesPerTick = v);
		open(parent, panel);
	}
}
