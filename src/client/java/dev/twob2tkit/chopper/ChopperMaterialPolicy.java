package dev.twob2tkit.chopper;

final class ChopperMaterialPolicy {
    static boolean replant(boolean configured,boolean retainSaplings){return configured&&!retainSaplings;}
    static boolean harvestLeaves(boolean configured,boolean retainSaplings){return configured&&!retainSaplings;}
}
