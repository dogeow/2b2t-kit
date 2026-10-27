package dev.twob2tkit.automation;

/** Opt-in dry access above unchanged source water, never a general liquid bypass. */
final class DryRoofMiningPolicy {
    private DryRoofMiningPolicy() {}

    static String rejection(boolean owned, boolean healthyDryFlight, boolean naturalDryTarget,
                            boolean sourceWaterBelow, boolean otherFluid, boolean unstableNeighbour,
                            boolean currentSupport, boolean suitablePickaxe) {
        if (!owned || !healthyDryFlight) return "Dry roof mining requires the current healthy dry Flight material owner";
        if (!naturalDryTarget || !suitablePickaxe) return "Dry roof mining requires ordinary natural rock and a durable plain pickaxe";
        if (!sourceWaterBelow || otherFluid) return "Only unchanged source water directly below the dry roof target is allowed";
        if (unstableNeighbour || currentSupport) return "Falling neighbours, light supports and current footing are protected";
        return null;
    }
}
