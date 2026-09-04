package dev.twob2tkit.planter;

import net.minecraft.client.Minecraft;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/** 种田诊断写到 config/twob2tkit/planter.log。 */
public final class PlanterFileLog {
	private static final Logger LOGGER = LoggerFactory.getLogger("twob2tkit/Planter");
	private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");
	private static final long MAX_BYTES = 256 * 1024;

	private PlanterFileLog() {
	}

	/** 写一行种田诊断到 planter.log，同时打 SLF4J。 */
	public static void append(Minecraft client, String version, String line) {
		if (client == null || line == null || line.isBlank()) return;
		LOGGER.info("[twob2tkit/Planter {}] {}", version, line);
		try {
			Path path = client.gameDirectory.toPath().resolve("config/twob2tkit/planter.log");
			Files.createDirectories(path.getParent());
			trimIfHuge(path);
			String stamped = TIME.format(LocalDateTime.now()) + " " + version + " " + line + System.lineSeparator();
			Files.writeString(path, stamped, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
		} catch (IOException exception) {
			LOGGER.warn("Could not write config/twob2tkit/planter.log", exception);
		}
	}

	/** 超过上限时丢掉前半，从最近换行处截断。 */
	private static void trimIfHuge(Path path) throws IOException {
		if (!Files.exists(path) || Files.size(path) < MAX_BYTES) return;
		String text = Files.readString(path, StandardCharsets.UTF_8);
		int keepFrom = Math.max(0, text.length() / 2);
		int newline = text.indexOf('\n', keepFrom);
		if (newline >= 0) keepFrom = newline + 1;
		Files.writeString(path, text.substring(keepFrom), StandardCharsets.UTF_8);
	}
}
