package dev.twob2tkit.automation;

/** Explicit title-only actions never disconnect a loaded world or bypass a safety hold. */
final class TitleConnectionPolicy {
    private TitleConnectionPolicy() {}
    static void require(boolean disconnected, boolean titleScreen, boolean idle, boolean safetyHeld,
                        String world, String requestedWorld, long revision, long requestedRevision,
                        long now, long expires, String player, String expectedPlayer) {
        if (!disconnected || !titleScreen || !idle || safetyHeld
                || !world.equals(requestedWorld) || revision != requestedRevision
                || expires < now || expires - now > 15_000
                || expectedPlayer.isBlank() || !player.equals(expectedPlayer))
            throw new IllegalStateException("Title action requires the current idle account, world and revision without a safety hold");
    }
}
