package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.SlabBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.SlabType;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import java.util.Collection;

/** Adapt only a double slab's first normal side use; final world state stays exact. */
public final class PrinterSlabPlacement {
    private PrinterSlabPlacement(){}
    public static boolean incompleteDouble(BlockState goal,BlockState actual){
        return goal.getBlock() instanceof SlabBlock&&goal.getBlock()==actual.getBlock()
            &&goal.getValue(SlabBlock.TYPE)==SlabType.DOUBLE&&actual.getValue(SlabBlock.TYPE)!=SlabType.DOUBLE
            &&!actual.getValue(SlabBlock.WATERLOGGED)&&!goal.getValue(SlabBlock.WATERLOGGED);
    }
    public static BlockHitResult sideHit(BlockState goal,BlockState current,BlockState anchorState,
                                         BlockPos target,BlockPos anchor,Direction face){
        if(!(goal.getBlock() instanceof SlabBlock)||goal.getValue(SlabBlock.TYPE)!=SlabType.DOUBLE
                ||goal.getValue(SlabBlock.WATERLOGGED)||!current.isAir()
                ||anchorState.getBlock()!=goal.getBlock()||anchorState.getValue(SlabBlock.TYPE)==SlabType.DOUBLE
                ||anchorState.getValue(SlabBlock.WATERLOGGED)||!face.getAxis().isHorizontal()
                ||!anchor.relative(face).equals(target))throw new IllegalArgumentException("No dry adjacent double-slab side correction");
        double y=anchor.getY()+(anchorState.getValue(SlabBlock.TYPE)==SlabType.BOTTOM?.25:.75);
        var center=Vec3.atCenterOf(anchor).relative(face,.5);
        return new BlockHitResult(new Vec3(center.x,y,center.z),face,anchor,false);
    }
    /** Each queued action must share the same replacement, including the look action. */
    static int replaceContexts(Collection<?> actions,Object original,Object replacement)throws ReflectiveOperationException{
        int count=0;
        for(Object action:actions){
            java.lang.reflect.Field field;
            try{field=action.getClass().getField("context");}catch(NoSuchFieldException noContext){continue;}
            if(field.get(action)!=original)continue;
            if(!field.trySetAccessible())throw new IllegalAccessException("Printer action context cannot be adapted");
            field.set(action,replacement);
            if(field.get(action)!=replacement)throw new IllegalStateException("Printer action context was not replaced");
            count++;
        }
        if(count!=2)throw new IllegalStateException("Expected one prepare and one interaction action; refusing unknown queue");
        return count;
    }
    public static BlockPlaceContext correct(Object raw,Collection<?> actions,Player player,
                                            BlockState goal,BlockState actual,BlockState anchorState,
                                            BlockPos target)throws ReflectiveOperationException{
        var context=(BlockPlaceContext)raw;
        if(!(goal.getBlock() instanceof SlabBlock)||goal.getValue(SlabBlock.TYPE)!=SlabType.DOUBLE
                ||context.getClickedPos().equals(target))return context;
        var oldHit=(BlockHitResult)raw.getClass().getField("hitResult").get(raw);
        var hit=sideHit(goal,actual,anchorState,target,oldHit.getBlockPos(),oldHit.getDirection());
        Object replacement=raw.getClass().getConstructor(Player.class,BlockHitResult.class,ItemStack.class,int.class,Direction.class,boolean.class)
            .newInstance(player,hit,context.getItemInHand().copy(),raw.getClass().getField("requiredItemSlot").getInt(raw),
                raw.getClass().getField("lookDirection").get(raw),raw.getClass().getField("shouldSneak").getBoolean(raw));
        var corrected=(BlockPlaceContext)replacement;
        if(!corrected.getClickedPos().equals(target))throw new IllegalStateException("Corrected slab context still resolves outside the target");
        replaceContexts(actions,raw,replacement);
        return corrected;
    }
}
