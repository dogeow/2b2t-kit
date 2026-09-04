package dev.twob2tkit.runtime.engine;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.minecraft.client.Minecraft;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 把镐+附魔+方块的挖法记到 config/2b2t-kit/mine-timings.json。 */
final class BorerMineTimings {
	private static final Logger LOGGER = LoggerFactory.getLogger("2b2t-kit/Borer");
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
	private static final int MAX_ENTRIES = 512;

	private final Map<String, BorerMineTimingPolicy.Memory> byKey = new LinkedHashMap<>();
	private boolean dirty;

	/** 挖矿节奏记忆文件路径。 */
	static Path file(Minecraft client) {
		return client.gameDirectory.toPath().resolve("config/2b2t-kit/mine-timings.json");
	}

	/** 按键取节奏记忆；没有则 null。 */
	BorerMineTimingPolicy.Memory get(String key) {
		if (key == null || key.isBlank()) return null;
		return byKey.get(key);
	}

	/** 写入一条节奏记忆；成功返回 true。 */
	boolean put(String key, BorerMineTimingPolicy.Memory memory) {
		if (key == null || key.isBlank() || memory == null) return false;
		BorerMineTimingPolicy.Memory combined = BorerMineTimingPolicy.combine(byKey.get(key), memory);
		BorerMineTimingPolicy.Memory previous = byKey.get(key);
		if (combined.equals(previous)) return false;
		byKey.remove(key);
		byKey.put(key, combined);
		while (byKey.size() > MAX_ENTRIES) {
			String first = byKey.keySet().iterator().next();
			byKey.remove(first);
		}
		dirty = true;
		return true;
	}

	/** 从磁盘加载节奏表。 */
	void load(Minecraft client) {
		if (client == null) return;
		byKey.clear();
		dirty = false;
		Path path = file(client);
		if (!Files.isRegularFile(path)) return;
		try {
			String text = Files.readString(path, StandardCharsets.UTF_8);
			FileData data = GSON.fromJson(text, FileData.class);
			if (data == null || data.entries == null) return;
			for (FileEntry entry : data.entries) {
				if (entry == null || entry.key == null || entry.key.isBlank()) continue;
				byKey.put(entry.key, new BorerMineTimingPolicy.Memory(entry.insta, Math.max(0, entry.holdTicks)));
			}
		} catch (Exception exception) {
			LOGGER.warn("Could not read config/2b2t-kit/mine-timings.json", exception);
		}
	}

	/** 把节奏表写回磁盘。 */
	void save(Minecraft client) {
		if (client == null || !dirty) return;
		try {
			Path path = file(client);
			Files.createDirectories(path.getParent());
			FileData data = new FileData();
			for (Map.Entry<String, BorerMineTimingPolicy.Memory> entry : byKey.entrySet()) {
				FileEntry row = new FileEntry();
				row.key = entry.getKey();
				row.insta = entry.getValue().insta();
				row.holdTicks = entry.getValue().holdTicks();
				data.entries.add(row);
			}
			Files.writeString(path, GSON.toJson(data), StandardCharsets.UTF_8);
			dirty = false;
		} catch (IOException exception) {
			LOGGER.warn("Could not write config/2b2t-kit/mine-timings.json", exception);
		}
	}

	/** mine-timings.json 根：条目列表。 */
	private static final class FileData {
		List<FileEntry> entries = new ArrayList<>();
	}

	/** 一条镐+方块挖法记忆。 */
	private static final class FileEntry {
		String key;
		boolean insta;
		int holdTicks;
	}
}
