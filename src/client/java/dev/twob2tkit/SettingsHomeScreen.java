package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Checkbox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.borer.TunnelBorer;
import dev.twob2tkit.recipe.LocalRecipeBookInjector;

/** 「设置」标签：模块栏开关、补货、配方、按键与引擎热加载。 */
public final class SettingsHomeScreen extends KitHudScreen {
	private final KitConfig config;
	/** 热加载说明与按键摘要的起始 y，由 init 按按钮底边算出，避免压住关闭。 */
	private int infoY;

	SettingsHomeScreen(KitConfig config) {
		super(Component.literal("设置"), null);
		this.config = config;
	}

	/** 固定为「设置」标签。 */
	@Override
	protected KitTab currentTab() {
		return KitTab.SETTINGS;
	}

	/** 布置界面开关、配方选项、按键与热加载按钮。 */
	@Override
	protected void init() {
		addTabBar(KitTab.SETTINGS);
		int left = panelLeft(320);
		int y = contentTop();
		addRenderableWidget(Checkbox.builder(Component.literal("模块栏界面（一屏列出，像 Meteor）"), this.font)
			.pos(left, y)
			.selected(config.clickGui)
			.onValueChange((box, value) -> {
				config.clickGui = value;
				config.save();
				if (value) {
					KitController controller = KitClient.controller();
					if (controller != null) this.minecraft.setScreen(new ClickGuiScreen(config, controller));
				}
			})
			.build())
			.setTooltip(Tooltip.create(Component.literal(
				"一屏列出功能。关掉就回到这种分页。")));
		y += 24;
		addRenderableWidget(Checkbox.builder(Component.literal("打开容器后自动补货"), this.font)
			.pos(left, y)
			.selected(config.autoRestockFromOpenedContainers)
			.onValueChange((box, value) -> {
				config.autoRestockFromOpenedContainers = value;
				config.save();
			})
			.build());
		y += 24;
		addRenderableWidget(Checkbox.builder(Component.literal("首次获得关键材料时弹出配方提示"), this.font)
			.pos(left, y)
			.selected(config.localRecipeHints)
			.onValueChange((box, value) -> {
				config.localRecipeHints = value;
				config.save();
			})
			.build())
			.setTooltip(Tooltip.create(Component.literal("第一次拿到关键材料时在聊天里提示相关配方")));
		addRenderableWidget(Button.builder(Component.literal("重置已看提示"), button -> {
			config.seenRecipeHints.clear();
			config.save();
		}).bounds(left + 220, y, 100, 20).build());
		y += 24;
		addRenderableWidget(Checkbox.builder(Component.literal("启用背包与工作台配方书增强"), this.font)
			.pos(left, y)
			.selected(config.recipeBookEnhancementEnabled)
			.onValueChange((box, value) -> {
				LocalRecipeBookInjector.setEnhancementEnabled(this.minecraft, value);
			})
			.build());
		y += 32;
		addRenderableWidget(Button.builder(Component.literal("按键绑定"), button ->
			this.minecraft.setScreen(new KitKeyBindsScreen(this)))
			.bounds(left, y, 320, 22).build());
		y += 26;
		addRenderableWidget(Button.builder(Component.literal("检查并加载新版"), button -> {
			TunnelBorer.ReloadResult result = KitClient.reloadBorerRuntime(this.minecraft, false);
			if (this.minecraft.player != null) {
				this.minecraft.player.sendSystemMessage(Component.literal("[2b2t-kit] " + result.message())
					.withColor(result.success() ? 0x55FF55 : 0xFF5555));
			}
			button.setMessage(Component.literal(result.success() ? "新版已加载" : "未加载，查看聊天"));
		}).bounds(left, y, 157, 22).build());
		addRenderableWidget(Button.builder(Component.literal("恢复内置版本"), button -> {
			TunnelBorer.ReloadResult result = KitClient.reloadBorerRuntime(this.minecraft, true);
			if (this.minecraft.player != null) {
				this.minecraft.player.sendSystemMessage(Component.literal("[2b2t-kit] " + result.message())
					.withColor(result.success() ? 0x55FF55 : 0xFF5555));
			}
			button.setMessage(Component.literal(result.success() ? "内置版本已恢复" : "恢复失败，查看聊天"));
		}).bounds(left + 163, y, 157, 22).build());
		y += 26;
		infoY = y;
		addRenderableWidget(Button.builder(Component.literal("关闭"), button -> this.minecraft.setScreen(null))
			.bounds(left, footerButtonY(), 320, 20).build());
	}

	/** 画当前引擎版本与热加载注意点。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		int footerTop = footerButtonY() - 4;
		int y = infoY;
		if (y + 12 >= footerTop) return;
		TunnelBorer borer = KitClient.borer();
		String runtime = borer == null ? "运行引擎尚未初始化" : "当前运行引擎：" + borer.runtimeLabel();
		KitUi.centered(graphics, this.font, runtime, center, y, 0x55FFFF);
		y += 14;
		for (String line : KitUi.wrap(this.font, KitKeys.hintLine(), 320)) {
			if (y + 12 >= footerTop) return;
			KitUi.centered(graphics, this.font, line, center, y, 0xA0A0A0);
			y += 12;
		}
		y += 4;
		if (y + 12 >= footerTop) return;
		KitUi.centered(graphics, this.font, "只替换 runtime/2b2t-kit-engine.jar，不要把整包模组放进这个目录", center, y, 0xA0A0A0);
		y += 12;
		if (y + 12 >= footerTop) return;
		KitUi.centered(graphics, this.font, "Mixin、按键和核心界面更新仍需重启", center, y, 0xA0A0A0);
	}
}
