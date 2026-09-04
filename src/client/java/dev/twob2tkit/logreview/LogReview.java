package dev.twob2tkit.logreview;

import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.ModuleFileLog;
import dev.twob2tkit.aihud.AiHud;

/** 运行时扫各功能 config/2b2t-kit/<module>.log，卡住就问 Grok。盾构另有「想想」，这里不重复问。 */
public final class LogReview {
	private final KitConfig config;
	private int ticks;
	private int ticksSinceAsk = LogReviewPolicy.URGENT_COOLDOWN_TICKS;
	private final Map<String, Long> marks = new HashMap<>();
	private boolean toldMissingGrok;

	/** 按配置构造日志复审。 */
	public LogReview(KitConfig config) {
		this.config = config;
	}

	/** 定时扫模块日志；紧急则问 Grok。 */
	public void tick(Minecraft client) {
		if (!config.logReviewEnabled || client == null || client.player == null) return;
		ticks++;
		if (ticksSinceAsk < 20_000) ticksSinceAsk++;
		if (!LogReviewPolicy.scanThisTick(ticks)) return;
		if (LogReviewAsk.busy()) return;
		for (String module : ModuleFileLog.REVIEW_MODULES) {
			if (!LogReviewPolicy.reviewable(module)) continue;
			Slice slice = peek(client, module);
			if (!slice.present) continue;
			if (slice.firstSeen) {
				commit(module, slice.size);
				continue;
			}
			if (slice.text.isBlank() || !LogReviewPolicy.urgent(slice.text)) {
				commit(module, slice.size);
				continue;
			}
			if (!LogReviewAsk.canAsk(client)) {
				if (!toldMissingGrok) {
					toldMissingGrok = true;
					client.player.sendSystemMessage(Component.literal(
						"[2b2t-kit] 日志有卡住迹象，但本机没登录 Grok、也没有 xai.key"));
				}
				return;
			}
			if (!LogReviewPolicy.shouldAsk(true, true, false, ticksSinceAsk, true)) return;
			ticksSinceAsk = 0;
			commit(module, slice.size);
			String label = LogReviewPolicy.label(module);
			AiHud.begin("Grok · " + label);
			AiHud.step("正在看" + label + "日志");
			LogReviewAsk.ask(client, module, slice.text, advice -> {
				String lesson = advice.lesson == null || advice.lesson.isBlank() ? "看过了，没有明确建议" : advice.lesson;
				int color = advice.needFix ? 0xFFAA55 : 0x55FF55;
				if (client.player != null) {
					client.player.sendSystemMessage(Component.literal("[2b2t-kit/Grok] " + lesson).withColor(color));
				}
				ModuleFileLog.append(client, module,
					"review needFix=" + advice.needFix + " cause=" + advice.cause + " lesson=" + lesson);
				AiHud.done(lesson, false);
			}, () -> {
				if (client.player != null) {
					client.player.sendSystemMessage(Component.literal("[2b2t-kit] Grok 看日志失败").withColor(0xFF5555));
				}
				ModuleFileLog.append(client, module, "review-fail");
				AiHud.fail("问 Grok 失败");
			});
			return;
		}
	}

	/** 读模块日志自水印起的新尾部。 */
	private Slice peek(Minecraft client, String module) {
		Path path = ModuleFileLog.file(client, module);
		if (!Files.isRegularFile(path)) return Slice.missing();
		try {
			long size = Files.size(path);
			long mark = marks.getOrDefault(module, -1L);
			if (mark < 0) return Slice.first(size);
			if (size < mark) mark = 0;
			if (size == mark) return new Slice("", false, size, true);
			byte[] all = Files.readAllBytes(path);
			int from = (int) Math.min(Math.max(0L, mark), all.length);
			int len = all.length - from;
			if (len <= 0) return new Slice("", false, size, true);
			if (len > LogReviewPolicy.TAIL_BYTES) {
				from = all.length - LogReviewPolicy.TAIL_BYTES;
				len = LogReviewPolicy.TAIL_BYTES;
			}
			return new Slice(new String(all, from, len, StandardCharsets.UTF_8), false, size, true);
		} catch (Exception ignored) {
			return Slice.missing();
		}
	}

	/** 把水印推到当前文件大小。 */
	private void commit(String module, long size) {
		marks.put(module, size);
	}

	/** 一次日志切片：文本、是否首见、大小。 */
	private record Slice(String text, boolean firstSeen, long size, boolean present) {
		/** 表示文件不存在。 */
		public static Slice missing() {
			return new Slice("", false, 0, false);
		}

		/** 首次见到文件，只记大小不问。 */
		public static Slice first(long size) {
			return new Slice("", true, size, true);
		}
	}
}
