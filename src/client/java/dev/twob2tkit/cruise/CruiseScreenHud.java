package dev.twob2tkit.cruise;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import dev.twob2tkit.KitUi;

/** Compact one-line cruise status at the top center of the game view. */
public final class CruiseScreenHud {
	private static final long NOTICE_NANOS = 2_000_000_000L;
	private static final CruiseHudState state = new CruiseHudState();

	private CruiseScreenHud() {
	}

	/** New short route leg clears the previous leg's arrival notice. */
	public static void begin(String line) {
		state.begin(line);
	}

	/** Keep the active status visible while travelling. */
	public static void show(String line) {
		state.status(line);
	}

	/** Show a phase change for about two seconds without covering progress permanently. */
	public static void flash(String line) {
		state.notice(line, System.nanoTime(), NOTICE_NANOS);
	}

	/** Brief arrival/stop notice; it disappears without another navigation tick. */
	public static void finish(String line) {
		state.finish(line, System.nanoTime(), NOTICE_NANOS);
	}

	/** Clear on world exit or task replacement. */
	public static void hide() {
		state.clear();
	}

	/** Only draw in unobstructed gameplay, respecting F1 and open screens. */
	public static void render(Minecraft client, GuiGraphicsExtractor graphics) {
		if (client == null || graphics == null) return;
		if (client.level == null || client.player == null) {
			hide();
			dev.twob2tkit.hud.WorkHud.clear();
			return;
		}
		if (client.options.hideGui || client.screen != null) return;
		long now = System.nanoTime();
		var job = dev.twob2tkit.hud.WorkHud.current();
		String line = job == null ? state.line(now) : job.line();
		if (line.isBlank()) return;
		Font font = client.font;
		int maxW = Math.max(48, Math.min(300, graphics.guiWidth() - 32));
		String fitted = KitUi.fit(font, line, maxW);
		int width = Math.min(graphics.guiWidth() - 12, font.width(fitted) + 20);
		int x = (graphics.guiWidth() - width) / 2;
		int height = 20;
		int y = dev.twob2tkit.hud.TargetTooltipSpace.top(x, width, height, graphics.guiHeight());
		if (y < 0) return;
		graphics.nextStratum();
		graphics.fill(x, y, x + width, y + height, 0xC8101720);
		graphics.fill(x, y, x + 2, y + height, job != null && job.attention() ? 0xFFFFC46B : state.showingNotice(now) ? 0xFF6FE7B5 : 0xFF61AEEB);
		KitUi.centered(graphics, font, fitted, graphics.guiWidth() / 2, y + 6,
			state.showingNotice(now) ? 0xE5FFF0 : 0xECF5FF);
	}
}
