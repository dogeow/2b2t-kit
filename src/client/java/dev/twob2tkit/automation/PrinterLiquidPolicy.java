package dev.twob2tkit.automation;

import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;

/** Ordinary automatic printing cannot validate the resulting flow or escape route. */
public final class PrinterLiquidPolicy {
    private PrinterLiquidPolicy(){}
    public static boolean allowed(boolean kitOwned,BlockState target){
        return !kitOwned||target!=null&&!(target.getBlock() instanceof LiquidBlock);
    }
}
