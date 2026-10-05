package dev.twob2tkit.compat;

/** World teardown/reconnect invariants shared by host compatibility hooks. */
public final class ClientWorldGuard {
	private ClientWorldGuard() {}
	public static boolean ready(Object player, Object level, Object gameMode) {
		return player != null && level != null && gameMode != null;
	}
	/** Missing players have no abilities to restore; an existing player's actual spectator check is unchanged. */
	public static boolean spectatorOrMissingPlayer(Object player, java.util.function.BooleanSupplier spectator) {
		return player == null || spectator.getAsBoolean();
	}
	public static boolean sameSession(Object expectedLevel, Object currentLevel, Object expectedConnection, Object currentConnection) {
		return expectedLevel != null && expectedConnection != null && expectedLevel == currentLevel && expectedConnection == currentConnection;
	}
}
