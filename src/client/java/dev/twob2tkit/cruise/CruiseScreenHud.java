package dev.twob2tkit.cruise;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import dev.twob2tkit.KitUi;

/** Task and cruise status occupy independent rows at the top center. */
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
		if (client.gui.hud.isHidden() || client.gui.screen() != null) return;
		long now = System.nanoTime();
		var job = dev.twob2tkit.hud.WorkHud.current();
		String air=dev.twob2tkit.hud.WorkHud.navigation();
		var rows = CruiseHudRows.select(job,air.isBlank()?state.line(now):air,air.isBlank()&&state.showingNotice(now));
		if (rows.isEmpty()) return;
		Font font = client.font;
		int maxW = Math.max(48, Math.min(300, graphics.guiWidth() - 32));
		var fitted = rows.stream().map(row -> KitUi.fit(font,row.line(),maxW)).toList();
		int width = Math.min(graphics.guiWidth() - 12, fitted.stream().mapToInt(font::width).max().orElse(0) + 20);
		int x = (graphics.guiWidth() - width) / 2;
		int height = rows.size()*22-2;
		int y = dev.twob2tkit.hud.TargetTooltipSpace.top(x, width, height, graphics.guiHeight());
		if (y < 0) return;
		graphics.nextStratum();
		for(int i=0;i<rows.size();i++) {
			var row=rows.get(i);int rowY=y+i*22;
			graphics.fill(x,rowY,x+width,rowY+20,0xC8101720);
			graphics.fill(x,rowY,x+2,rowY+20,row.attention()?0xFFFFC46B:row.notice()?0xFF6FE7B5:0xFF61AEEB);
			KitUi.centered(graphics,font,fitted.get(i),graphics.guiWidth()/2,rowY+6,row.notice()?0xE5FFF0:0xECF5FF);
		}
	}
}
