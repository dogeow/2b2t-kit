package dev.twob2tkit.cruise;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import dev.twob2tkit.KitUi;

/**
 * 巡航进度：屏幕正中下方两行，主行高亮剩余路程与剩余时间。
 */
public final class CruiseScreenHud {
	private static volatile boolean visible;
	private static volatile String primary = "";
	private static volatile String secondary = "";

	private CruiseScreenHud() {
	}

	/** 更新两行文案；主行为空则隐藏。 */
	public static void show(String primaryLine, String secondaryLine) {
		primary = primaryLine == null ? "" : primaryLine;
		secondary = secondaryLine == null ? "" : secondaryLine;
		visible = !primary.isBlank();
	}

	/** 关掉面板。 */
	public static void hide() {
		visible = false;
		primary = "";
		secondary = "";
	}

	/** 在 GUI 层画半透明底 + 居中两行。 */
	public static void render(Minecraft client, GuiGraphicsExtractor graphics) {
		if (!visible || client == null || graphics == null || client.player == null) return;
		if (client.options.hideGui) return;
		String line1 = primary;
		String line2 = secondary;
		if (line1 == null || line1.isBlank()) return;
		Font font = client.font;
		int maxW = Math.min(320, Math.max(100, graphics.guiWidth() - 24));
		int lineH = 12;
		int pad = 5;
		int width = Math.min(maxW + 14, Math.max(font.width(line1), line2.isBlank() ? 0 : font.width(line2)) + 16);
		int height = pad * 2 + lineH + (line2.isBlank() ? 0 : lineH);
		int x = (graphics.guiWidth() - width) / 2;
		int y = graphics.guiHeight() / 2 + 22;
		graphics.nextStratum();
		graphics.fill(x, y, x + width, y + height, 0xC0101018);
		int center = graphics.guiWidth() / 2;
		KitUi.centered(graphics, font, KitUi.fit(font, line1, maxW), center, y + pad, 0x55FF55);
		if (!line2.isBlank()) {
			KitUi.centered(graphics, font, KitUi.fit(font, line2, maxW), center, y + pad + lineH, 0xA0A0A0);
		}
	}
}
