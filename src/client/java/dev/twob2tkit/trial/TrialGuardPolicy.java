package dev.twob2tkit.trial;

/** Exact local trial ownership, independent of game inputs or health thresholds. */
public final class TrialGuardPolicy {
    private TrialGuardPolicy() {}

    public record Owner(boolean registeredLocalWorld, boolean activeRun, boolean allowDeathRespawn,
            String trialId, String runId, String worldId, String worldSession, String dimension) {}
    public record Scope(boolean localTrial, boolean pveOnly, String trialId, String runId,
            String worldId, String worldSession, String dimension) {}

    private static boolean same(String actual, String expected) {
        return actual != null && !actual.isBlank() && actual.equals(expected);
    }
    public static boolean exactOwner(Owner owner, Scope scope) {
        return owner != null && scope != null && owner.registeredLocalWorld() && scope.localTrial()
            && SingleplayerTrialPolicy.owner(scope.trialId(), scope.runId(), owner.trialId(), owner.runId())
            && same(scope.worldId(), owner.worldId()) && same(scope.worldSession(), owner.worldSession())
            && same(scope.dimension(), owner.dimension());
    }
    public static boolean healthRecoveryEnabled(boolean guardEnabled, Owner owner, Scope scope) {
        boolean optedIn = exactOwner(owner, scope) && owner.activeRun()
            && owner.allowDeathRespawn() && scope.pveOnly();
        return guardEnabled && !optedIn;
    }
    public static boolean ownedChop(Owner owner, Scope scope, boolean activeChopRequest, boolean chopperActive) {
        return activeChopRequest && chopperActive && exactOwner(owner, scope) && owner.activeRun();
    }
    public static boolean stopOwnedChop(Owner owner, Scope scope, String trialId, String runId,
                                       boolean activeChopRequest, boolean chopperActive) {
        // A crashed/cancelled worker must still release its own live child.
        // Runtime retains these ids until cleanup; another run cannot borrow them.
        return activeChopRequest && chopperActive && exactOwner(owner, scope)
            && SingleplayerTrialPolicy.owner(trialId, runId, owner.trialId(), owner.runId());
    }
    public static boolean disableModule(boolean flightModule, boolean ownedChop) {
        return !flightModule || !ownedChop;
    }
}
