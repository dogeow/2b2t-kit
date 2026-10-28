package dev.twob2tkit.automation;

import java.util.Map;

/** Narrow admission for temporary projected-glass removal above flowing water. */
final class BelowFlowMiningPolicy {
    enum Side { DOWN, UP, NORTH, SOUTH, EAST, WEST }
    enum Fluid { DRY, FLOWING_WATER, WATER_SOURCE, OTHER, UNKNOWN }

    static String rejection(boolean owned,boolean healthyDry,boolean exactProjectedGlass,
            boolean silkPickReady,boolean protectsFooting,boolean exactBelowState,
            Map<Side,Fluid> neighbors) {
        if(!owned||!healthyDry)return "Healthy dry guarded material owner required";
        if(!exactProjectedGlass)return "Exact current projected glass required";
        if(!silkPickReady)return "Silk Touch pickaxe with reserve required";
        if(protectsFooting)return "Current footing is protected";
        if(!exactBelowState)return "Observed flowing water below changed";
        if(neighbors==null||neighbors.size()!=Side.values().length)
            return "All six neighbor fluids must be observed";
        for(var side:Side.values()) {
            var fluid=neighbors.get(side);
            if(fluid==null||fluid==Fluid.UNKNOWN)return "Neighbor fluid is unknown";
            if(side==Side.DOWN) {
                if(fluid!=Fluid.FLOWING_WATER)return "Only nonsource water below is admitted";
            } else if(fluid!=Fluid.DRY)return "Other neighboring fluids remain protected";
        }
        return null;
    }
}
