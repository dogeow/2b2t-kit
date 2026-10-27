package dev.twob2tkit.automation;

import net.minecraft.world.level.block.HopperBlock;
import net.minecraft.world.level.block.state.BlockState;
import java.util.Objects;

/** Guide-only equivalence. Redstone recomputes ENABLED after placement. */
public final class PrinterHopperPrediction {
    private PrinterHopperPrediction() {}
    public static boolean matches(BlockState predicted,BlockState schematic) {
        if(predicted==null||schematic==null||!(schematic.getBlock() instanceof HopperBlock)
                ||predicted.getBlock()!=schematic.getBlock())return false;
        for(var property:schematic.getProperties())
            if(property!=HopperBlock.ENABLED&&!Objects.equals(schematic.getValue(property),predicted.getValue(property)))return false;
        return true;
    }
}
