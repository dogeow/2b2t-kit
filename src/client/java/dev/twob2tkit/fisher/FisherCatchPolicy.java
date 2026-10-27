package dev.twob2tkit.fisher;

import java.util.UUID;

/** One accepted retrieval per hook, even while the server still exposes the old hook. */
public final class FisherCatchPolicy {
    private UUID retrievedHook;
    private int catches;

    public void reset() {
        retrievedHook = null;
        catches = 0;
    }

    public int catches() {
        return catches;
    }

    public boolean mayUse(UUID hook, int cooldown) {
        return cooldown <= 0 && (hook == null || !hook.equals(retrievedHook));
    }

    /** A cooldown no-op, rejected use or hooked entity is never a fish catch. */
    public boolean recordUse(UUID hook, int cooldown, boolean accepted, boolean bite, boolean hookedEntity) {
        if (!accepted || !mayUse(hook, cooldown)) return false;
        if (hook != null) {
            retrievedHook = hook;
            if (bite && !hookedEntity) catches++;
        }
        return true;
    }
}
