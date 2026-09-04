package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/** 把盾构诊断写到 config/2b2t-kit/borer.log，不用导出游戏日志包。 */
final class BorerFileLog {
	private static final Logger LOGGER = LoggerFactory.getLogger("2b2t-kit/Borer");
	private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");
	private static final long MAX_BYTES = 256 * 1024;

	private BorerFileLog() {
	}

	/** borer.log 路径。 */
	static Path file(Minecraft client) {
		return client.gameDirectory.toPath().resolve("config/2b2t-kit/borer.log");
	}

	/** 读日志末尾若干行。 */
	static String tail(Minecraft client, int lines) {
		if (client == null || lines <= 0) return "";
		Path path = file(client);
		if (!Files.isRegularFile(path)) return "";
		try {
			List<String> all = Files.readAllLines(path, StandardCharsets.UTF_8);
			int from = Math.max(0, all.size() - lines);
			StringBuilder out = new StringBuilder();
			for (int i = from; i < all.size(); i++) {
				if (out.length() > 0) out.append('\n');
				out.append(all.get(i));
			}
			return out.toString();
		} catch (IOException exception) {
			return "";
		}
	}

	/** 追加一行诊断日志。 */
	static void append(Minecraft client, String line) {
		if (client == null || line == null || line.isBlank()) return;
		try {
			Path path = file(client);
			Files.createDirectories(path.getParent());
			trimIfHuge(path);
			String stamped = TIME.format(LocalDateTime.now()) + " " + line + System.lineSeparator();
			Files.writeString(path, stamped, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
		} catch (IOException exception) {
			LOGGER.warn("Could not write config/2b2t-kit/borer.log", exception);
		}
	}

	/** 超过体积上限时拦腰截断。 */
	private static void trimIfHuge(Path path) throws IOException {
		if (!Files.exists(path) || Files.size(path) < MAX_BYTES) return;
		String text = Files.readString(path, StandardCharsets.UTF_8);
		int keepFrom = Math.max(0, text.length() / 2);
		int newline = text.indexOf('\n', keepFrom);
		if (newline >= 0) keepFrom = newline + 1;
		Files.writeString(path, text.substring(keepFrom), StandardCharsets.UTF_8);
	}
}
