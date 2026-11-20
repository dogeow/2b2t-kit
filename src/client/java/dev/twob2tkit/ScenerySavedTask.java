package dev.twob2tkit;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import net.minecraft.client.Minecraft;

/**
 * 页面只读的风景进度摘要：决定主按钮是「继续上次」还是「开始新任务」。
 * 世界标识与引擎写入时一致（服务器地址|维度）；缓存后端仍由引擎在继续时最终校验。
 */
record ScenerySavedTask(String world, long x, long z, int radius) {
	static final String FILE = "config/twob2tkit/scenery-progress.json";

	/** 读不到或格式不对都视为没有上次任务，不抛错。 */
	static ScenerySavedTask read(Minecraft client) {
		try {
			Path path = client.gameDirectory.toPath().resolve(FILE);
			if (!Files.isRegularFile(path) || Files.size(path) > 2_000_000) return null;
			JsonObject saved = JsonParser.parseString(Files.readString(path)).getAsJsonObject();
			return new ScenerySavedTask(saved.get("world").getAsString(), Math.round(saved.get("x").getAsDouble()),
				Math.round(saved.get("z").getAsDouble()), saved.get("radius").getAsInt());
		} catch (Exception unreadable) {
			return null;
		}
	}

	/** 当前连接与维度的标识；未进入世界时为 null。 */
	static String currentWorld(Minecraft client) {
		if (client.level == null) return null;
		String server = client.getCurrentServer() != null ? client.getCurrentServer().ip : client.getSingleplayerServer() != null
			? client.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toString() : "unknown";
		return server + "|" + client.level.dimension().identifier();
	}

	boolean belongsTo(String current) {
		return world.equals(current);
	}

	/** 例如「154.21.197.138:25565 · 主世界」。 */
	String place() {
		int split = world.lastIndexOf('|');
		String server = split < 0 ? world : world.substring(0, split);
		String dimension = split < 0 ? "" : dev.twob2tkit.storage.StorageLabels.dimensionLabel(world.substring(split + 1));
		return server + (dimension.isEmpty() ? "" : " · " + dimension);
	}
}
