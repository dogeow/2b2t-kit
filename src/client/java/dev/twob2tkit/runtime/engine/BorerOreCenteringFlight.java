package dev.twob2tkit.runtime.engine;

import java.io.IOException;
import java.nio.file.Path;
import java.util.function.DoublePredicate;
import java.util.function.Supplier;

/** Temporarily limit Meteor Flight while lining up with a narrow mining corridor. */
final class BorerOreCenteringFlight {
	// Meteor Velocity can multiply this setting by 15 while sprinting. A 0.30-block
	// move fits within the corridor's roughly 0.40-block window around the center.
	static final double MAX_CENTERING_SPEED = 0.02;
	private final Supplier<Double> read;
	private final DoublePredicate write;
	private BorerFlightSpeedBackup backup;
	private Double original;

	BorerOreCenteringFlight(Supplier<Double> read, DoublePredicate write) {
		this.read = read;
		this.write = write;
	}

	boolean limit(Path receipt) {
		Double current = read.get();
		if (current == null || !Double.isFinite(current) || current <= 0) return false;
		if (original != null) return current == MAX_CENTERING_SPEED;
		if (current <= MAX_CENTERING_SPEED) return true;
		try {
			if (BorerFlightSpeedBackup.otherReceiptClaims(receipt, current)) return false;
			var candidate = new BorerFlightSpeedBackup(receipt);
			var entry = new BorerFlightSpeedBackup.Entry(current, current, MAX_CENTERING_SPEED);
			if (!entry.equals(candidate.read())) candidate.beforeWrite(current, current, MAX_CENTERING_SPEED);
			backup = candidate;
			original = current;
			return write.test(MAX_CENTERING_SPEED) && Double.valueOf(MAX_CENTERING_SPEED).equals(read.get());
		} catch (IOException e) {
			return false;
		}
	}

	void release() {
		if (original == null) return;
		Double current = read.get();
		if (Double.valueOf(MAX_CENTERING_SPEED).equals(current)) {
			write.test(original);
		} else if (current != null && !original.equals(current)) {
			try { backup.clear(); } catch (IOException ignored) {}
		}
		// Keep the receipt if Meteor may already have saved the temporary value.
		original = null;
		backup = null;
	}

	void recover(Path receipt) throws IOException {
		var saved = new BorerFlightSpeedBackup(receipt);
		var entry = saved.read();
		if (entry == null || original != null) return;
		Double current = read.get();
		if (current == null || BorerFlightSpeedBackup.otherReceiptClaims(receipt, current)) return;
		double restored = entry.restore(current);
		if (restored == current || write.test(restored) && Double.valueOf(restored).equals(read.get())) saved.clear();
	}
}
