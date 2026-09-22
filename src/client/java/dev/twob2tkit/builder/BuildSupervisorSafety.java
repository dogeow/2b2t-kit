package dev.twob2tkit.builder;

/** Native watchdog; no model request is needed to put an unattended player into a safe state. */
public final class BuildSupervisorSafety {
    public enum Action { NONE, REVOKE, PAUSE_LOCAL, LOGOUT, KEEP_PVE_GUARD }
    private BuildSupervisorSafety() {}
    public static Action decide(boolean sameScope,boolean manualInput,boolean localPrivateWorld,
                                boolean heartbeatExpired,boolean complete,boolean disconnectRemote) {
        if(!sameScope || manualInput)return Action.REVOKE;
        if(!heartbeatExpired && !complete)return Action.NONE;
        if(localPrivateWorld)return Action.PAUSE_LOCAL;
        return disconnectRemote?Action.LOGOUT:Action.KEEP_PVE_GUARD;
    }
}
