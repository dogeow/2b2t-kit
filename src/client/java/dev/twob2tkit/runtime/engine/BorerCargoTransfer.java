package dev.twob2tkit.runtime.engine;

/** Settle the predicted move first; Cargo then reopens the chest to audit a fresh server snapshot. */
final class BorerCargoTransfer {
	enum Result { WAIT, CONFIRMED, REFUSED }
	private final int source, destination;
	private int ticks;
	BorerCargoTransfer(int source, int destination) { this.source = source; this.destination = destination; }
	Result observe(int currentSource, int currentDestination) {
		if (++ticks < 4) return Result.WAIT;
		if (currentSource < source && currentDestination > destination) return Result.CONFIRMED;
		return ticks >= 40 ? Result.REFUSED : Result.WAIT;
	}
	static boolean audited(int expectedBag, int expectedChest, int freshBag, int freshChest) {
		return freshBag <= expectedBag && freshChest >= expectedChest;
	}
}
