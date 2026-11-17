package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class BorerOreCenteringFlightTest {
	@TempDir Path temp;
	private final AtomicReference<Double> speed = new AtomicReference<>(0.06);
	private final BorerOreCenteringFlight flight = new BorerOreCenteringFlight(speed::get, value -> {
		speed.set(value);
		return true;
	});

	private Path receipt() {
		return temp.resolve("ore-centering-flight-speed.bak");
	}

	@Test void reportedOscillationEntersCorridorAfterOneLimitedMove() {
		double right = 760963.875736;
		double center = 760963.5;
		double left = right - 0.98 * 10 * speed.get();
		assertTrue(BorerCenterPolicy.overlapsSideWall(center - right));
		assertTrue(BorerCenterPolicy.overlapsSideWall(center - left));

		assertTrue(flight.limit(receipt()));
		for (int meteorMultiplier : new int[]{10, 15}) {
			double step = 0.98 * meteorMultiplier * speed.get();
			assertFalse(BorerCenterPolicy.overlapsSideWall(center - (right - step)));
			assertFalse(BorerCenterPolicy.overlapsSideWall(center - (left + step)));
		}
		flight.release();
		assertEquals(0.06, speed.get());
	}

	@Test void manualSpeedChangeSurvivesReleaseAndRecovery() throws Exception {
		assertTrue(flight.limit(receipt()));
		speed.set(0.12);
		flight.release();
		flight.recover(receipt());
		assertEquals(0.12, speed.get());
		assertNull(new BorerFlightSpeedBackup(receipt()).read());
	}

	@Test void aTemporarySpeedSavedBeforeInterruptionCanBeRestored() throws Exception {
		assertTrue(flight.limit(receipt()));
		var reloaded = new BorerOreCenteringFlight(speed::get, value -> {
			speed.set(value);
			return true;
		});
		reloaded.recover(receipt());
		assertEquals(0.06, speed.get());
		assertNull(new BorerFlightSpeedBackup(receipt()).read());
	}

	@Test void aSpeedOwnedByAnotherFeatureIsLeftAlone() throws Exception {
		new BorerFlightSpeedBackup(temp.resolve("guard-hover-flight.bak")).beforeWrite(0.1, 0.0, 0.06);
		assertFalse(flight.limit(receipt()));
		flight.release();
		assertEquals(0.06, speed.get());
		assertNull(new BorerFlightSpeedBackup(receipt()).read());
	}

	@Test void alreadySlowFlightNeedsNoTemporarySetting() throws Exception {
		speed.set(0.015);
		assertTrue(flight.limit(receipt()));
		flight.release();
		assertEquals(0.015, speed.get());
		assertNull(new BorerFlightSpeedBackup(receipt()).read());
	}
}
