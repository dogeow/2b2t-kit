package dev.twob2tkit.runtime.engine;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

/** Write-ahead speed backup: a saved Meteor config must not turn temporary hover into manual speed 0. */
final class BorerFlightSpeedBackup {
	private final Path path;
	BorerFlightSpeedBackup(Path path) { this.path = path; }
	record Entry(double original, double previous, double requested) {
		Entry {
			if (!Double.isFinite(original) || original <= 0 || !Double.isFinite(previous) || previous < 0
				|| !Double.isFinite(requested) || requested < 0) throw new IllegalArgumentException("Invalid flight backup");
		}
		double restore(double current) { return current == previous || current == requested ? original : current; }
	}
	Entry read() throws IOException {
		if (!Files.exists(path)) return null;
		try {
			String[] values = Files.readString(path).trim().split("\\s+");
			if (values.length != 3) throw new IllegalArgumentException("Invalid flight backup");
			return new Entry(Double.parseDouble(values[0]), Double.parseDouble(values[1]), Double.parseDouble(values[2]));
		} catch (IllegalArgumentException e) { throw new IOException("Invalid flight backup", e); }
	}
	void beforeWrite(double original, double previous, double requested) throws IOException {
		new Entry(original, previous, requested);
		Files.createDirectories(path.getParent());
		Path temp = Files.createTempFile(path.getParent(), "flight-speed-", ".tmp");
		try {
			Files.writeString(temp, original + " " + previous + " " + requested);
			Files.move(temp, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
		} finally { Files.deleteIfExists(temp); }
	}
	void clear() throws IOException { Files.deleteIfExists(path); }
}
