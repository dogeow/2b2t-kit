package dev.twob2tkit.runtime.engine;

import com.google.gson.Gson;
import net.minecraft.core.BlockPos;
import java.nio.file.*;
import java.io.IOException;
import java.util.*;

/** Same server/dimension and XZ worksite share depots across successive depth slices. */
final class BorerCargoDepots {
	record Site(int x, int y, int z, boolean full, List<String> accepts) {
		BlockPos pos() { return new BlockPos(x, y, z); }
		boolean acceptsAny(Set<String> cargo) { return !full && (accepts == null || accepts.stream().anyMatch(cargo::contains)); }
	}
	private static final Gson JSON = new Gson();
	private static final class Saved { Map<String, List<Site>> areas = new HashMap<>(); }
	private final Path path;
	private final String key;
	private final Saved saved;
	private Set<String> legacyKeys = Set.of();
	BorerCargoDepots(Path path, String world, BlockPos min, BlockPos max) throws IOException {
		this(path, world + "|worksite-xz:" + min.getX() + "," + min.getZ() + ":" + max.getX() + "," + max.getZ());
		var legacy = java.util.regex.Pattern.compile(java.util.regex.Pattern.quote(world)
			+ "\\|BlockPos\\{x=" + min.getX() + ", y=-?\\d+, z=" + min.getZ() + "\\}"
			+ "\\|BlockPos\\{x=" + max.getX() + ", y=-?\\d+, z=" + max.getZ() + "\\}");
		legacyKeys = saved.areas.keySet().stream().filter(k -> legacy.matcher(k).matches()).collect(java.util.stream.Collectors.toSet());
	}
	BorerCargoDepots(Path path, String key) throws IOException {
		this.path = path; this.key = key;
		try {
			if (Files.exists(path) && Files.size(path) > 1_000_000) throw new IOException("卸货箱记录过大");
			saved = Files.exists(path) ? JSON.fromJson(Files.readString(path), Saved.class) : new Saved();
			if (saved == null || saved.areas == null) throw new IOException("卸货箱记录损坏，未覆盖");
		} catch (RuntimeException e) { throw new IOException("卸货箱记录损坏，未覆盖", e); }
	}
	List<Site> sites() {
		Map<BlockPos, Site> merged = new LinkedHashMap<>();
		for (String legacy : legacyKeys) for (Site site : saved.areas.getOrDefault(legacy, List.of()))
			merged.merge(site.pos(), site, (a, b) -> a.full ? a : b); // Conservative until a real menu observation.
		for (Site site : saved.areas.getOrDefault(key, List.of())) merged.put(site.pos(), site);
		return List.copyOf(merged.values());
	}
	void remember(BlockPos pos, boolean full) throws IOException {
		remember(pos, full, null);
	}
	void remember(BlockPos pos, boolean full, List<String> accepts) throws IOException {
		Site next = new Site(pos.getX(), pos.getY(), pos.getZ(), full, accepts == null ? null : List.copyOf(accepts));
		List<Site> sites = saved.areas.computeIfAbsent(key, k -> new ArrayList<>());
		if (sites.contains(next)) return;
		if (sites.size() >= 128 && sites.stream().noneMatch(s -> s.pos().equals(pos))) throw new IOException("本工程已记录 128 个箱子，请先整理箱子");
		sites.removeIf(s -> s.pos().equals(pos));
		sites.add(next);
		Files.createDirectories(path.getParent());
		Path tmp = Files.createTempFile(path.getParent(), "area-depots-", ".tmp");
		try {
			Files.writeString(tmp, JSON.toJson(saved));
			try { Files.move(tmp, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
			catch (AtomicMoveNotSupportedException ignored) { Files.move(tmp, path, StandardCopyOption.REPLACE_EXISTING); }
		} finally { Files.deleteIfExists(tmp); }
	}
}
