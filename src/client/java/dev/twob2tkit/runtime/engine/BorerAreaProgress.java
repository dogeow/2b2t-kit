package dev.twob2tkit.runtime.engine;

import com.google.gson.Gson;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.AtomicMoveNotSupportedException;
import java.io.IOException;

/** One versioned checkpoint, bound to server/dimension and exact area bounds. */
final class BorerAreaProgress {
	private static final Gson JSON = new Gson();
	private record Saved(int schema, String world, BorerAreaPlan.Snapshot plan) {}
	static BorerAreaPlan.Snapshot read(Path path, String world) {
		try {
			if (!Files.isRegularFile(path) || Files.size(path) > 1_000_000) return null;
			Saved saved = JSON.fromJson(Files.readString(path), Saved.class);
			return saved != null && saved.schema == 1 && world.equals(saved.world) ? saved.plan : null;
		} catch (IOException | RuntimeException ignored) { return null; }
	}
	static void write(Path path, String world, BorerAreaPlan.Snapshot plan) throws IOException {
		Files.createDirectories(path.getParent());
		Path temp = path.resolveSibling(path.getFileName() + ".new");
		Files.writeString(temp, JSON.toJson(new Saved(1, world, plan)));
		try { Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE); }
		catch (AtomicMoveNotSupportedException ignored) { Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING); }
	}
	private BorerAreaProgress() {}
}
