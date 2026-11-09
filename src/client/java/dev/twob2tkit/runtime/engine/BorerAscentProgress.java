package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import java.util.Objects;

/** Track actual vertical gains across short interruptions in the ascent planner. */
final class BorerAscentProgress {
    private BlockPos goal;
    private int lastTick = -1;
    private int lastGain;
    private double highWater;

    void reset() {
        lastTick = -1;
    }

    boolean stalled(BlockPos target, int tick, double y, boolean reliableHeight) {
        if (lastTick < 0 || tick < lastTick || tick - lastTick > 20 || !Objects.equals(goal, target)) {
            goal = target;
            lastGain = tick;
            highWater = y;
        } else if (reliableHeight && y >= highWater + .25) {
            highWater = y;
            lastGain = tick;
        }
        lastTick = tick;
        return tick - lastGain >= 50;
    }
}
