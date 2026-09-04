package dev.twob2tkit;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.builder.MachineBuilder;

/** 助手子页：按 Litematica 投影自动摆放。 */
public final class TechHomeScreen extends KitHudScreen {
	private final MachineBuilder builder;

	TechHomeScreen(Screen parent, MachineBuilder builder) {
		super(Component.literal("投影建造"), parent);
		this.builder = builder;
	}

	/** 布置开始/停止投影建造与返回。 */
	@Override
	protected void init() {
		int left = panelLeft(340);
		int y = bodyTop(28);

		boolean printing = builder.isPlacing();
		addRenderableWidget(Button.builder(
				Component.literal(printing ? "停止投影建造" : "开始按投影建造"),
				button -> {
					if (builder.isPlacing()) {
						builder.cancel(this.minecraft, "在界面停止");
					} else if (!builder.start(this.minecraft)) {
						showNotice(builder.status(), 0xFF5555);
					}
					rebuildWidgets();
				})
			.bounds(left, y, 340, 20)
			.tooltip(Tooltip.create(Component.literal(
				"先用 Litematica（默认 M）加载并放置投影。全息仍由 Litematica 画；这里只按投影自动摆背包里有的方块，不拆已有方块。")))
			.build());

		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(left, footerButtonY(), 340, 20).build());
	}

	/** 画 Litematica 状态与操作步骤说明。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, "看图用 Litematica，自动摆用 2b2t-kit", center, bodyTop(56), 0x55FFFF);
		int y = bodyTop(76);
		KitUi.centered(graphics, this.font, LitematicaAccess.describe(), center, y, 0xFFFFFF);
		y += 18;
		if (builder.isPlacing()) {
			KitUi.centered(graphics, this.font, builder.status(), center, y, 0x55FF55);
			y += 16;
		}
		KitUi.centered(graphics, this.font, "1. 用 Litematica 加载 .litematic 并 Create Placement", center, y, 0xA0A0A0);
		y += 12;
		KitUi.centered(graphics, this.font, "2. 把全息对到要建的位置，需要时打开材料列表", center, y, 0xA0A0A0);
		y += 12;
		KitUi.centered(graphics, this.font, "3. 点「开始按投影建造」。缺材料会停，补货后继续。End 停止", center, y, 0xA0A0A0);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, this.height - 48, noticeColor);
	}
}
