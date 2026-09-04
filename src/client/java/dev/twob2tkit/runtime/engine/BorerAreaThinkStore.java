package dev.twob2tkit.runtime.engine;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.minecraft.client.Minecraft;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HashMap;
import java.util.Map;

/** 区域挖思考记忆：哪类卡住用哪招解开过。坏文件当空白，不崩游戏。 */
final class BorerAreaThinkStore {
	private static final Logger LOGGER = LoggerFactory.getLogger("twob2tkit/Borer");
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

	/** 某场景某招的胜/负计数。 */
	public static final class Counts {
		int w;
		int l;
	}

	/** 磁盘上的想想记忆：场景 → 招数 → 胜负。 */
	public static final class File {
		Map<String, Map<String, Counts>> scenes = new HashMap<>();
	}

	private BorerAreaThinkStore() {
	}

	/** 对应配置/日志文件路径。 */
	static Path file(Minecraft client) {
		return client.gameDirectory.toPath().resolve("config/twob2tkit/area-think.json");
	}

	/** 从磁盘加载。 */
	static File load(Minecraft client) {
		if (client == null) return new File();
		Path path = file(client);
		if (!Files.isRegularFile(path)) return new File();
		try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
			File parsed = GSON.fromJson(reader, File.class);
			if (parsed == null || parsed.scenes == null) return new File();
			return parsed;
		} catch (RuntimeException | IOException exception) {
			LOGGER.warn("Could not read config/twob2tkit/area-think.json", exception);
			return new File();
		}
	}

	/** 写回磁盘。 */
	static void save(Minecraft client, File data) {
		if (client == null || data == null) return;
		try {
			Path path = file(client);
			Files.createDirectories(path.getParent());
			try (Writer writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
				GSON.toJson(data, writer);
			}
		} catch (IOException exception) {
			LOGGER.warn("Could not write config/twob2tkit/area-think.json", exception);
		}
	}

	/** 该场景招数胜场。 */
	static int wins(File data, String scene, BorerAreaThinkPolicy.Move move) {
		Counts counts = counts(data, scene, move);
		return counts == null ? 0 : counts.w;
	}

	/** 该场景招数负场。 */
	static int losses(File data, String scene, BorerAreaThinkPolicy.Move move) {
		Counts counts = counts(data, scene, move);
		return counts == null ? 0 : counts.l;
	}

	/** 追加一条课到本地。 */
	static void appendLesson(Minecraft client, String lesson) {
		if (client == null || lesson == null || lesson.isBlank()) return;
		try {
			Path path = client.gameDirectory.toPath().resolve("config/twob2tkit/area-think-lessons.md");
			Files.createDirectories(path.getParent());
			String stamped = "- " + java.time.LocalDateTime.now().toString() + "  " + lesson.trim()
				+ System.lineSeparator();
			Files.writeString(path, stamped, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
		} catch (IOException exception) {
			LOGGER.warn("Could not write config/twob2tkit/area-think-lessons.md", exception);
		}
	}

	/** 记一次胜负。 */
	static void record(File data, String scene, BorerAreaThinkPolicy.Move move, boolean win) {
		if (data.scenes == null) data.scenes = new HashMap<>();
		Map<String, Counts> row = data.scenes.computeIfAbsent(scene, key -> new HashMap<>());
		Counts counts = row.computeIfAbsent(move.name(), key -> new Counts());
		if (win) counts.w++;
		else counts.l++;
	}

	/** 取胜负计数。 */
	private static Counts counts(File data, String scene, BorerAreaThinkPolicy.Move move) {
		if (data == null || data.scenes == null || scene == null || move == null) return null;
		Map<String, Counts> row = data.scenes.get(scene);
		if (row == null) return null;
		return row.get(move.name());
	}
}
