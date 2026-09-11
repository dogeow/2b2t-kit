package dev.twob2tkit.compat;

/** World teardown/reconnect invariants shared by host compatibility hooks. */
public final class ClientWorldGuard {
	private ClientWorldGuard() {}
	public static boolean ready(Object player, Object level, Object gameMode) {
		return player != null && level != null && gameMode != null;
	}
	public static boolean sameSession(Object expectedLevel, Object currentLevel, Object expectedConnection, Object currentConnection) {
		return expectedLevel != null && expectedConnection != null && expectedLevel == currentLevel && expectedConnection == currentConnection;
	}
}
