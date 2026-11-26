package dev.twob2tkit;

import net.minecraft.client.gui.screens.Screen;
import java.util.ArrayList;
import java.util.List;
import dev.twob2tkit.surround.AutoSurround;
import dev.twob2tkit.surround.SurroundBlocks;

import static dev.twob2tkit.FeaturePages.mc;
import static dev.twob2tkit.FeaturePages.open;

/** 保护分类：自动保护、围箱与生存提醒。 */
final class SafetyPages {
	private SafetyPages() {
	}

	static void guard(Screen parent, KitConfig c) {
		var p = new KitFormScreen(parent, "自动保护", "这里配置保护策略；不主动启动采矿或巡航。").bind(c).id("guard");
        p.action("独立防护："+(dev.twob2tkit.automation.AutomationBridge.guardArmed()?"开":"关"), "空闲也反击主动威胁；按移动键或空格立即关闭并交还控制。\n托管会提前进食，受伤后等生命恢复到 9.5 心再继续。\n紧急停止会关闭它；换维度或离开当前区域 512 格后需重新开启。", () -> {dev.twob2tkit.automation.AutomationBridge.toggleGuard(mc());guard(parent,c);});
        if(dev.twob2tkit.combat.EmergencyExit.held(mc()))p.action("我已回来，解除安全离线锁", "生命恢复到 9 颗心后手动确认；不会自动启动任务。", () -> {dev.twob2tkit.combat.EmergencyExit.acknowledge(mc());guard(parent,c);});
		p.bool("遇袭协调 Meteor 保护", "沿用当前自动保护逻辑。", () -> c.autoProtectOnHit, v -> c.autoProtectOnHit = v);
		p.bool("恶魂防护", "独立恶魂防护；具体射程和反弹设置见自动打猪人。", () -> c.ghastGuardEnabled, v -> c.ghastGuardEnabled = v);
		p.action("玩家白名单", "可信玩家不触发警戒与反击。", () -> UiFeature.TRUSTED.open(p));
		p.action("挂机离线条件", "在巡航页「挂机保护」：血量、玩家警戒等。", () -> UiFeature.CRUISE.open(p));
		p.action("挖矿反击条件", "主动威胁、盾牌和苦力怕保护。", () -> UiFeature.MINING_COMMON.open(p));
		open(parent, p);
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
		panel.advanced();
		panel.slider("每拍块数", "每 tick 最多放几块。", 1, 4, () -> config.surroundPlacesPerTick, v -> config.surroundPlacesPerTick = v);
		panel.bool("围好后继续补洞", "默认关。", () -> config.surroundKeepRepair, v -> config.surroundKeepRepair = v);
		open(parent, panel);
	}

	/** 生存提醒选项。 */
	static void survival(Screen parent, KitConfig config) {
		KitFormScreen panel = new KitFormScreen(parent, "生存提醒", "提醒显示在屏幕中央和聊天栏。");
		panel.bool("回血物资不足", "低于最低数量就提醒。", () -> config.healingItemAlert, v -> config.healingItemAlert = v);
		panel.slider("回血最低数量", "背包合计。", 0, 64, () -> config.minimumHealingItems, v -> config.minimumHealingItems = v);
		panel.action("多选回血物品", "选择计入提醒的食物与药水。", () -> UiFeature.HEALING.open(panel));
		panel.bool("下界未穿金质护甲", "猪人会攻击。", () -> config.netherGoldArmorAlert, v -> config.netherGoldArmorAlert = v);
		panel.bool("不死图腾不足", "", () -> config.totemAlert, v -> config.totemAlert = v);
		panel.slider("图腾最低数量", "", 0, 16, () -> config.minimumTotems, v -> config.minimumTotems = v);
		panel.bool("鞘翅耐久过低", "", () -> config.elytraDurabilityAlert, v -> config.elytraDurabilityAlert = v);
		panel.slider("鞘翅最低耐久", "", 1, 431, () -> config.minimumElytraDurability, v -> config.minimumElytraDurability = v);
		panel.slider("重复提醒间隔", "秒。", 5, 600, () -> config.survivalAlertCooldownSeconds, v -> config.survivalAlertCooldownSeconds = v);
		open(parent, panel);
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
}
