package dev.twob2tkit.automation;

/** A seed is an exact, single plain-cube placement, never a paving loop. */
final class ProjectionAirSeedPolicy {
    static final int SETTLE_TICKS=8;
    private ProjectionAirSeedPolicy() {}

    static boolean confirmed(boolean serverConfirmed,boolean currentStateMatches,
                             int inventoryBefore,int inventoryNow,long ackTick,long tick) {
        return serverConfirmed&&currentStateMatches&&inventoryBefore>0
            &&inventoryBefore-inventoryNow==1&&ackTick>=0&&tick-ackTick>=SETTLE_TICKS;
    }
}
