package dev.twob2tkit.automation;

/** Explicitly water-aware excavations may refill with water after solid removal. */
final class SingleBlockRemovalPolicy {
    private SingleBlockRemovalPolicy() {}
    static boolean removed(boolean air, boolean waterBlock, boolean underwaterGravel) {
        return removed(air,waterBlock,underwaterGravel,false);
    }
    static boolean removed(boolean air,boolean waterBlock,boolean underwaterGravel,boolean controlledWaterRelease){
        return removed(air,waterBlock,underwaterGravel,controlledWaterRelease,false);
    }
    static boolean removed(boolean air,boolean waterBlock,boolean underwaterGravel,boolean controlledWaterRelease,boolean projectedWetTerrain){
        return air||(underwaterGravel||controlledWaterRelease||projectedWetTerrain)&&waterBlock;
    }
}
