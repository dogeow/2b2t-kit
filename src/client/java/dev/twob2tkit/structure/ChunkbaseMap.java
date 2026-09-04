package dev.twob2tkit.structure;

import net.minecraft.client.Minecraft;
import net.minecraft.util.Util;
import net.minecraft.world.level.Level;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

/** 拼 Chunkbase 种子地图链接，并尽量在浏览器打开（失败则复制到剪贴板）。 */
public final class ChunkbaseMap {
	private static final String SEED_MAP = "https://www.chunkbase.com/apps/seed-map";

	private ChunkbaseMap() {
	}

	/** 用 Seedcracker/默认世界生成版本拼链接。 */
	public static String url(long seed, String dimension, double x, double z, int zoom) {
		return url(seed, dimension, x, z, zoom, worldgenVersion());
	}

	/** 拼完整 Seed Map URL（含 platform / version / 坐标）。 */
	public static String url(long seed, String dimension, double x, double z, int zoom, String version) {
		String encodedSeed = URLEncoder.encode(Long.toString(seed), StandardCharsets.UTF_8);
		String platform = platformToken(version);
		String encodedVersion = URLEncoder.encode(version, StandardCharsets.UTF_8);
		return SEED_MAP
			+ "#seed=" + encodedSeed
			+ "&platform=" + platform
			+ "&version=" + encodedVersion
			+ "&dimension=" + dimension
			+ "&x=" + Math.round(x)
			+ "&z=" + Math.round(z)
			+ "&zoom=" + zoom;
	}

	/** Chunkbase 用 java_1_21_3 这种 platform，缺了会落到最新版（现在是 26.x）。 */
	public static String worldgenVersion() {
		String fromSeedcracker = SeedcrackerBridge.worldgenVersion();
		if (fromSeedcracker != null && !fromSeedcracker.isBlank()) return fromSeedcracker.trim();
		return "1.21.3";
	}

	/** 把 {@code 1.21.3} 转成 Chunkbase 的 {@code java_1_21_3}。 */
	public static String platformToken(String version) {
		String cleaned = version.trim().toLowerCase(java.util.Locale.ROOT);
		if (cleaned.startsWith("java")) return cleaned.replace(' ', '_').replace('.', '_');
		return "java_" + cleaned.replace('.', '_');
	}

	/** 当前客户端维度对应 Chunkbase 维度名。 */
	public static String dimensionOf(Minecraft client) {
		if (client.level == null) return "overworld";
		String path = client.level.dimension().identifier().getPath();
		if (path.contains("nether")) return "nether";
		if (path.contains("end")) return "end";
		return "overworld";
	}

	/**
	 * 以玩家坐标打开 Chunkbase；打不开浏览器则复制链接。
	 *
	 * @return 给界面看的中文结果说明
	 */
	public static String open(Minecraft client, long seed) {
		double x = client.player == null ? 0.0 : client.player.getX();
		double z = client.player == null ? 0.0 : client.player.getZ();
		String version = worldgenVersion();
		String link = url(seed, dimensionOf(client), x, z, 1, version);
		try {
			Util.getPlatform().openUri(URI.create(link));
			return "已在浏览器打开 Chunkbase，" + version + "，种子 " + seed;
		} catch (RuntimeException exception) {
			if (client.keyboardHandler != null) client.keyboardHandler.setClipboard(link);
			return "打不开浏览器，已复制链接";
		}
	}

	/** 是否主世界维度。 */
	public static boolean isOverworld(Level level) {
		return level != null && "overworld".equals(level.dimension().identifier().getPath());
	}
}
