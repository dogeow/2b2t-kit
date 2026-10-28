package dev.twob2tkit.automation;

import java.util.Set;

/** Excavates natural obstructions, never sources or finished projected blocks. */
final class ProjectedWetTerrainPolicy {
    private static final Set<String> NATURAL=Set.of("minecraft:dirt","minecraft:grass_block","minecraft:stone","minecraft:clay");
    private static final Set<String> GOALS=Set.of("minecraft:air","minecraft:cobblestone","minecraft:cobblestone_slab",
        "minecraft:cobblestone_stairs","minecraft:packed_ice","minecraft:magma_block","minecraft:water",
        "minecraft:hopper","minecraft:spruce_trapdoor","minecraft:spruce_fence_gate","minecraft:glass");
    static boolean obstruction(String actual,String goal){
        return NATURAL.contains(actual)&&GOALS.contains(goal)&&!actual.equals(goal);
    }
    static boolean neighborPreserved(String expected,String actual,boolean started){
        if(expected==null||actual==null)return false;
        if(expected.equals(actual))return true;
        // Only updates caused by the one removal may propagate into air or flowing water.
        // Original sources and waterlogged blocks remain exact throughout the operation.
        return started&&(expected.equals("Block{minecraft:air}")||flow(expected))&&water(actual);
    }
    private static boolean flow(String state){return water(state)&&!state.equals("Block{minecraft:water}[level=0]");}
    private static boolean water(String state){
        for(int level=0;level<=15;level++)if(state.equals("Block{minecraft:water}[level="+level+"]"))return true;
        return false;
    }
    static String rejection(boolean owned,boolean healthyDry,boolean projection,boolean naturalObstruction,
            boolean tool,boolean footing,boolean neighbors,boolean containerNearby){
        if(!owned||!healthyDry)return "Healthy dry guarded material owner required for projected terrain";
        if(!projection||!naturalObstruction)return "Exact natural obstruction of the locked projection required";
        if(!tool)return "Pinned appropriate tool with durability reserve required";
        if(footing)return "Current footing is protected";
        if(!neighbors)return "Six loaded pinned neighbors with only water fluids required";
        if(containerNearby)return "Neighboring containers remain protected";
        return null;
    }
}
