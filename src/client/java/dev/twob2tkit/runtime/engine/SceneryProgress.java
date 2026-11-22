package dev.twob2tkit.runtime.engine;

import com.google.gson.Gson;
import java.nio.file.*;
import java.io.IOException;

/** Only completed cache batches are checkpointed; interrupted pending work is retried. */
final class SceneryProgress {
	private static final Gson JSON = new Gson();
	private record Saved(int schema, String world, String cache, double x, double z, int radius, long[] covered, String bitmap) {}
	static void write(Path path, String world, String cache, SceneryCoverage coverage) throws IOException {
		Files.createDirectories(path.getParent());
		Path temp = Files.createTempFile(path.getParent(), "scenery-", ".tmp");
		try {
			boolean big=coverage.radius>SceneryCoverage.LEGACY_RADIUS;
			long[] covered=coverage.checkpoint();
			String bitmap=big ? java.util.Base64.getEncoder().encodeToString(java.util.BitSet.valueOf(covered).toByteArray()) : null;
			Files.writeString(temp, JSON.toJson(new Saved(big ? 2 : 1,world,cache,coverage.centreX,coverage.centreZ,
				coverage.radius,big ? null : covered,bitmap)));
			try { Files.move(temp, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
			catch (AtomicMoveNotSupportedException fallback) { Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING); }
		} finally { Files.deleteIfExists(temp); }
	}
    static SceneryCoverage readForMap(Path path, String world) throws IOException {
        return read(path, world, null);
    }

	static SceneryCoverage read(Path path, String world, String cache) throws IOException {
		if (!Files.isRegularFile(path)) throw new IOException("没有可继续的风景预加载任务，请先设置半径并开始");
		if (Files.size(path) > 3_000_000) throw new IOException("风景进度文件过大，未覆盖");
		try {
			Saved saved = JSON.fromJson(Files.readString(path), Saved.class);
			if (saved == null || saved.schema != (saved.radius>SceneryCoverage.LEGACY_RADIUS ? 2 : 1) || !world.equals(saved.world) || cache != null && !cache.equals(saved.cache))
				throw new IOException("上次风景任务属于其它服务器、维度或缓存后端，不能混用；请从当前位置新建");
			SceneryCoverage coverage = new SceneryCoverage(saved.x, saved.z, saved.radius); coverage.restore(saved.schema==2
				? java.util.BitSet.valueOf(java.util.Base64.getDecoder().decode(saved.bitmap)).toLongArray()
				: saved.covered);
			return coverage;
		} catch (RuntimeException bad) { throw new IOException("风景进度无法读取，未覆盖", bad); }
	}
}
