package dev.twob2tkit.aihud;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;

import java.util.List;
import dev.twob2tkit.KitUi;

/** 屏幕左上角固定画 AI 过程，不跟镜头、不走准星 billboard。 */
public final class AiHud {
	private static final Object LOCK = new Object();
	private static String title = "";
	private static String step = "";
	private static List<String> lines = List.of();
	private static boolean running;
	private static boolean failed;
	private static long startedAt;
	private static long hideAt;

	private AiHud() {
	}

	/** 开始一项 AI 任务，重置标题与过程行。 */
	public static void begin(String job) {
		synchronized (LOCK) {
			title = job == null || job.isBlank() ? "Grok" : job;
			step = "开始";
			lines = List.of("开始");
			running = true;
			failed = false;
			startedAt = System.currentTimeMillis();
			hideAt = 0L;
		}
	}

	/** 追加一步过程文案。 */
	public static void step(String text) {
		if (text == null || text.isBlank()) return;
		synchronized (LOCK) {
			step = text;
			lines = AiHudPolicy.append(lines, text);
			running = true;
			failed = false;
			hideAt = 0L;
			if (startedAt == 0L) startedAt = System.currentTimeMillis();
		}
	}

	/** 结束任务；error 为真时用失败配色，并延迟再隐藏面板。 */
	public static void done(String result, boolean error) {
		synchronized (LOCK) {
			failed = error;
			running = false;
			if (result != null && !result.isBlank()) {
				step = result;
				lines = AiHudPolicy.append(lines, result);
			}
			hideAt = System.currentTimeMillis() + AiHudPolicy.HOLD_MS;
		}
	}

	/** 以失败结束。 */
	public static void fail(String reason) {
		done(reason == null || reason.isBlank() ? "失败" : reason, true);
	}

	/** 在屏幕左上角画出当前 AI 面板（隐藏 GUI 时不画）。 */
	public static void render(Minecraft client, GuiGraphicsExtractor graphics) {
		if (client == null || graphics == null || client.player == null) return;
		if (client.options.hideGui) return;
		View view;
		synchronized (LOCK) {
			long now = System.currentTimeMillis();
			if (!AiHudPolicy.visible(running, now, hideAt)) return;
			view = new View(title, step, lines, running, failed, startedAt, now);
		}
		Font font = client.font;
		int maxText = 220;
		List<String> body = new java.util.ArrayList<>();
		body.add(view.title);
		if (view.running) body.add(AiHudPolicy.elapsed(view.startedAt, view.now));
		for (String line : view.lines) {
			body.addAll(KitUi.wrap(font, line, maxText));
		}
		int lineH = 11;
		int pad = 6;
		int width = 120;
		for (String line : body) width = Math.max(width, font.width(line) + 16);
		width = Math.min(260, width);
		int height = pad * 2 + body.size() * lineH;
		int x = 8;
		int y = 8;
		int accent = view.failed ? 0xFFAA3333 : view.running ? 0xFF2A6A88 : 0xFF2A8844;
		int titleRgb = view.failed ? 0xFF5555 : view.running ? 0x55FFFF : 0x55FF55;
		graphics.nextStratum();
		graphics.fill(x, y, x + width, y + height, 0xC0101018);
		graphics.fill(x, y, x + 3, y + height, accent);
		int textY = y + pad;
		for (int i = 0; i < body.size(); i++) {
			int rgb = i == 0 ? titleRgb : i == 1 && view.running ? 0xAAAAAA : 0xE0E0E0;
			KitUi.text(graphics, font, body.get(i), x + 8, textY, rgb);
			textY += lineH;
		}
	}

	/** 一帧渲染用的 HUD 快照。 */
	private record View(
		String title,
		String step,
		List<String> lines,
		boolean running,
		boolean failed,
		long startedAt,
		long now
	) {
	}
}
