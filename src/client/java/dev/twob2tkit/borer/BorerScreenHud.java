package dev.twob2tkit.borer;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;

import java.util.ArrayList;
import java.util.List;
import dev.twob2tkit.KitUi;

/** 挖矿状态画在屏幕正中下方，不跟镜头、不跟人物晃。 */
public final class BorerScreenHud {
	private static volatile boolean visible;
	private static volatile String action = "";
	private static volatile String detail = "";
	private static volatile int color = 0xFFFF55;

	private BorerScreenHud() {
	}

	/** 显示主行与可选详情；动作为空则隐藏。 */
	public static void show(String actionText, int rgb, String detailText) {
		action = actionText == null ? "" : actionText;
		detail = detailText == null ? "" : detailText;
		color = rgb;
		visible = !action.isBlank();
	}

	/** 关掉面板。 */
	public static void hide() {
		visible = false;
	}

	/** 在 GUI 层画半透明底 + 居中换行文字。 */
	public static void render(Minecraft client, GuiGraphicsExtractor graphics) {
		if (!visible || client == null || graphics == null || client.player == null) return;
		if (client.options.hideGui) return;
		String actionText = action;
		String detailText = detail;
		int rgb = color;
		if (actionText == null || actionText.isBlank()) return;
		Font font = client.font;
		int maxW = Math.min(280, Math.max(80, graphics.guiWidth() - 24));
		List<String> lines = new ArrayList<>();
		lines.addAll(KitUi.wrap(font, actionText, maxW));
		if (detailText != null && !detailText.isBlank()) {
			lines.addAll(KitUi.wrap(font, detailText, maxW));
		}
		int lineH = 11;
		int pad = 5;
		int width = 48;
		for (String line : lines) width = Math.max(width, font.width(line) + 14);
		width = Math.min(maxW + 14, width);
		int height = pad * 2 + lines.size() * lineH;
		int x = (graphics.guiWidth() - width) / 2;
		int y = graphics.guiHeight() / 2 + 22;
		graphics.nextStratum();
		graphics.fill(x, y, x + width, y + height, 0xC0101018);
		int textY = y + pad;
		int center = graphics.guiWidth() / 2;
		for (int i = 0; i < lines.size(); i++) {
			KitUi.centered(graphics, font, lines.get(i), center, textY, i == 0 ? rgb : 0xC0C0C0);
			textY += lineH;
		}
	}
}
