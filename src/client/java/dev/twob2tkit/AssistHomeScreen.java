package dev.twob2tkit;

import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.recipe.RecipeGuideScreen;
import dev.twob2tkit.villager.VillagerScanScreen;

/** 「更多」标签：配方指南、村庄扫描、投影建造入口。 */
public class AssistHomeScreen extends KitHudScreen {
	private final KitConfig config;
	private final KitController controller;

	public AssistHomeScreen(KitConfig config, KitController controller) {
		super(Component.literal("更多"), null);
		this.config = config;
		this.controller = controller;
	}

	/** 固定为「更多」标签。 */
	@Override
	protected KitTab currentTab() {
		return KitTab.MORE;
	}

	/** 布置配方、村庄、投影建造与关闭按钮。 */
	@Override
	protected void init() {
        if (dev.twob2tkit.UiFeature.redirectCategory(dev.twob2tkit.UiFeature.Category.PRODUCTION)) return;
		addTabBar(KitTab.MORE);
		int left = panelLeft(320);
		int y = contentTop();
		addRenderableWidget(Button.builder(Component.literal("配方指南"), button ->
			this.minecraft.setScreen(new RecipeGuideScreen(this, config)))
			.bounds(left, y, 155, 20).build());
		addRenderableWidget(Button.builder(Component.literal("村庄"), button ->
			this.minecraft.setScreen(new VillagerScanScreen(this, config)))
			.bounds(left + 165, y, 155, 20)
			.tooltip(Tooltip.create(Component.literal("扫描村民职业，标出还缺的工作方块")))
			.build());
		y += 24;
		addRenderableWidget(Button.builder(Component.literal("投影建造"), button -> {
			if (KitClient.machines() != null) {
				this.minecraft.setScreen(new TechHomeScreen(this, KitClient.machines()));
			}
		}).bounds(left, y, 155, 20)
			.tooltip(Tooltip.create(Component.literal("用 Litematica 看全息，这里按投影自动摆背包里有的方块")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("关闭"), button -> this.minecraft.setScreen(null))
			.bounds(left + 165, y, 155, 20).build());
	}
}
