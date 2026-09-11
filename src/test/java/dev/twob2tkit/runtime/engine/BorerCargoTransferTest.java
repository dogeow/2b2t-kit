package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static dev.twob2tkit.runtime.engine.BorerCargoTransfer.Result.*;

class BorerCargoTransferTest {
	@Test void reopenAuditRejectsPredictionRolledBackByServer() {
		assertFalse(BorerCargoTransfer.audited(0, 74, 64, 10));
		assertFalse(BorerCargoTransfer.audited(0, 74, 0, 10));
		assertFalse(BorerCargoTransfer.audited(0, 74, 64, 74));
		assertTrue(BorerCargoTransfer.audited(0, 74, 0, 74));
	}
	@Test void successfulDepositWaitsForSourceAndDestinationAndSeveralTicks() {
		var t = new BorerCargoTransfer(64, 10);
		for (int i = 0; i < 3; i++) assertEquals(WAIT, t.observe(0, 74));
		assertEquals(CONFIRMED, t.observe(0, 74));
	}
	@Test void delayedServerResponseIsNotRetriedOrDeclaredFullPrematurely() {
		var t = new BorerCargoTransfer(64, 10);
		for (int i = 0; i < 30; i++) assertEquals(WAIT, t.observe(64, 10));
		assertEquals(CONFIRMED, t.observe(32, 42));
	}
	@Test void refusedOrOneSidedChangeNeverCountsAsStored() {
		for (int[] counts : new int[][]{{64, 10}, {0, 10}, {64, 74}}) {
			var t = new BorerCargoTransfer(64, 10);
			for (int i = 0; i < 39; i++) assertEquals(WAIT, t.observe(counts[0], counts[1]));
			assertEquals(REFUSED, t.observe(counts[0], counts[1]));
		}
	}
}
