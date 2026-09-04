package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

/** 各功能共用 {@code config/2b2t-kit/<module>.log}。 */
public final class ModuleFileLog {
	/** LogReview 会扫的模块名列表。 */
	public static final String[] REVIEW_MODULES = {
		"chopper", "planter", "feeder", "fisher", "cruise", "surround", "brawler",
		"nether-roof", "combat", "builder", "borer"
	};
	private static final Logger LOGGER = LoggerFactory.getLogger("2b2t-kit");
	private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");
	private static final long MAX_BYTES = 256 * 1024;

	private ModuleFileLog() {
	}

	/** 该模块日志文件路径。 */
	public static Path file(Minecraft client, String module) {
		return client.gameDirectory.toPath().resolve("config/2b2t-kit/" + module + ".log");
	}

	/** 写一行到游戏日志与模块文件；超大则先拦腰截断。 */
	public static void append(Minecraft client, String module, String line) {
		if (client == null || module == null || line == null || line.isBlank()) return;
		LOGGER.info("[2b2t-kit/{}] {}", module, line);
		try {
			Path path = file(client, module);
			Files.createDirectories(path.getParent());
			trimIfHuge(path);
			String stamped = TIME.format(LocalDateTime.now()) + " " + line + System.lineSeparator();
			Files.writeString(path, stamped, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
		} catch (IOException exception) {
			LOGGER.warn("Could not write config/2b2t-kit/{}.log", module, exception);
		}
	}

	/** 玩家坐标短串，供日志行拼接。 */
	public static String player(LocalPlayer player) {
		if (player == null) return "-";
		return String.format(Locale.ROOT, "%.1f,%.1f,%.1f", player.getX(), player.getY(), player.getZ());
	}

	/** 超过上限时丢掉前半，从最近换行处起保留。 */
	private static void trimIfHuge(Path path) throws IOException {
		if (!Files.exists(path) || Files.size(path) < MAX_BYTES) return;
		String text = Files.readString(path, StandardCharsets.UTF_8);
		int keepFrom = Math.max(0, text.length() / 2);
		int newline = text.indexOf('\n', keepFrom);
		if (newline >= 0) keepFrom = newline + 1;
		Files.writeString(path, text.substring(keepFrom), StandardCharsets.UTF_8);
	}
}
