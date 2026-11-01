package dev.twob2tkit.automation;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.FenceGateBlock;
import net.minecraft.world.level.block.state.BlockState;
/** One normal click must itself reach the locked original gate state. */
final class VanillaGateInputPolicy {
    static boolean ready(boolean destroying,boolean handsBusy,boolean usingItem,boolean menu){return !destroying&&!handsBusy&&!usingItem&&!menu;}
    static boolean reachesGoal(BlockState actual,BlockState goal,Direction player){
        if(!(actual.getBlock()instanceof FenceGateBlock)||actual.getBlock()!=goal.getBlock()
           ||actual.getValue(FenceGateBlock.OPEN)||!goal.getValue(FenceGateBlock.OPEN))return false;
        var after=actual;
        if(actual.getValue(FenceGateBlock.FACING)==player.getOpposite())after=after.setValue(FenceGateBlock.FACING,player);
        return after.setValue(FenceGateBlock.OPEN,true).equals(goal);
    }
}
