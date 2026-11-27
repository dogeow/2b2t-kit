package dev.twob2tkit;

import java.io.IOException;
import java.io.Writer;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

/**
 * Writes beside the target and then swaps it in, so a crash or a reader (decision-runtime polls the
 * config) never sees a half-written file. A failed write leaves the previous file untouched.
 */
public final class AtomicFiles {
	public interface Body { void write(Writer writer) throws IOException; }

	private AtomicFiles() {}

	public static void write(Path target, Body body) throws IOException {
		Files.createDirectories(target.toAbsolutePath().getParent());
		Path temporary = target.resolveSibling(target.getFileName() + ".tmp");
		try {
			try (Writer writer = Files.newBufferedWriter(temporary)) {
				body.write(writer);
			}
			try {
				Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
			} catch (AtomicMoveNotSupportedException unsupported) {
				Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
			}
		} finally {
			Files.deleteIfExists(temporary);
		}
	}
}
