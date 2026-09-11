package dev.twob2tkit.runtime.engine;

import com.google.gson.Gson;
import java.nio.file.*;
import java.io.IOException;

/** Only completed cache batches are checkpointed; interrupted pending work is retried. */
final class SceneryProgress {
	private static final Gson JSON = new Gson();
	private record Saved(int schema, String world, String cache, double x, double z, int radius, long[] covered) {}
	static void write(Path path, String world, String cache, SceneryCoverage coverage) throws IOException {
		Files.createDirectories(path.getParent());
		Path temp = Files.createTempFile(path.getParent(), "scenery-", ".tmp");
		try {
			Files.writeString(temp, JSON.toJson(new Saved(1, world, cache, coverage.centreX, coverage.centreZ, coverage.radius, coverage.checkpoint())));
			try { Files.move(temp, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
			catch (AtomicMoveNotSupportedException fallback) { Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING); }
		} finally { Files.deleteIfExists(temp); }
	}
	static SceneryCoverage read(Path path, String world, String cache) throws IOException {
		if (!Files.isRegularFile(path)) throw new IOException("没有可继续的风景预加载任务，请先设置半径并开始");
		if (Files.size(path) > 2_000_000) throw new IOException("风景进度文件过大，未覆盖");
		try {
			Saved saved = JSON.fromJson(Files.readString(path), Saved.class);
			if (saved == null || saved.schema != 1 || !world.equals(saved.world) || !cache.equals(saved.cache))
				throw new IOException("上次风景任务属于其它服务器、维度或缓存后端，不能混用；请从当前位置新建");
			SceneryCoverage coverage = new SceneryCoverage(saved.x, saved.z, saved.radius); coverage.restore(saved.covered); return coverage;
		} catch (RuntimeException bad) { throw new IOException("风景进度无法读取，未覆盖", bad); }
	}
}
