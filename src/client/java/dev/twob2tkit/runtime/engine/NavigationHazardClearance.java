package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.chunk.status.ChunkStatus;

/** Read-only heat and contact clearance for continuous native supply routes. */
final class NavigationHazardClearance {
    interface Cells {
        boolean loaded(BlockPos pos);
        boolean hazardous(BlockPos pos);
    }
    private NavigationHazardClearance() {}

    static boolean hazardous(String id,boolean lit) {
        return switch(id) {
            case "minecraft:lava","minecraft:fire","minecraft:soul_fire",
                 "minecraft:magma_block","minecraft:cactus",
                 "minecraft:sweet_berry_bush","minecraft:wither_rose" -> true;
            case "minecraft:campfire","minecraft:soul_campfire" -> lit;
            default -> false;
        };
    }
    static boolean safe(BlockPos feet,Cells cells) {
        for(int dx=-1;dx<=1;dx++)for(int dz=-1;dz<=1;dz++)for(int dy=-1;dy<=2;dy++) {
            var p=feet.offset(dx,dy,dz);
            if(!cells.loaded(p)||cells.hazardous(p))return false;
        }
        return true;
    }
    static boolean current(BlockPos feet) {
        var c=Minecraft.getInstance();
        // Pure navigation fixtures provide their own authoritative World and
        // have no Minecraft singleton. A live client without a level is unsafe.
        if(c==null)return true;
        if(c.level==null)return false;
        var level=c.level;
        return safe(feet,new Cells() {
            public boolean loaded(BlockPos p) {
                var chunk=level.getChunkSource().getChunk(Math.floorDiv(p.getX(),16),
                    Math.floorDiv(p.getZ(),16),ChunkStatus.FULL,false);
                return LoadedServerChunkEvidence.isServerChunk(level,chunk);
            }
            public boolean hazardous(BlockPos p) {
                var state=level.getBlockState(p);
                return NavigationHazardClearance.hazardous(
                    BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString(),
                    state.hasProperty(BlockStateProperties.LIT)&&state.getValue(BlockStateProperties.LIT));
            }
        });
    }
}
