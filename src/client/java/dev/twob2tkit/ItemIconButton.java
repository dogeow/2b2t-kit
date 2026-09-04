package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.AbstractButton;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.narration.NarrationElementOutput;
import net.minecraft.client.input.InputWithModifiers;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;

/** 用原版物品图标当开关，选中时浅蓝底。 */
public final class ItemIconButton extends AbstractButton {
	private ItemStack stack;
	private final Runnable action;
	private boolean chosen;

	public ItemIconButton(int x, int y, int width, int height, ItemStack stack, Component name, Runnable action) {
		super(x, y, width, height, name);
		this.stack = stack;
		this.action = action;
		setTooltip(Tooltip.create(name));
	}

	/** 是否画选中高亮。 */
	public void setChosen(boolean chosen) {
		this.chosen = chosen;
	}

	/** 换图标与悬停提示。 */
	public void setIcon(ItemStack stack, Component tip) {
		this.stack = stack;
		setTooltip(Tooltip.create(tip));
	}

	/** 执行构造时传入的点击回调。 */
	@Override
	public void onPress(InputWithModifiers input) {
		action.run();
	}

	/** 画默认按钮底、选中浅蓝与居中物品。 */
	@Override
	protected void extractContents(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		extractDefaultSprite(graphics);
		if (chosen) {
			graphics.fill(getX() + 1, getY() + 1, getX() + getWidth() - 1, getY() + getHeight() - 1, 0x8844DDFF);
		}
		int itemX = getX() + (getWidth() - 16) / 2;
		int itemY = getY() + (getHeight() - 16) / 2;
		graphics.item(stack, itemX, itemY);
		Font font = Minecraft.getInstance().font;
		graphics.itemDecorations(font, stack, itemX, itemY);
	}

	/** 用按钮默认旁白。 */
	@Override
	public void updateWidgetNarration(NarrationElementOutput output) {
		defaultButtonNarrationText(output);
	}
}
