package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.SlabBlock;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.SimpleWaterloggedBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.SlabType;
import net.minecraft.world.level.material.Fluids;

/** Remove only the waterlogging bit that contradicts the locked schematic. Never break a block. */
final class ProjectedWaterlogDrain {
    private final BlockPos target;
    private final String placement;
    private final BlockState wet,dry;
    static boolean requested(JsonObject r){
        if(!r.has("projected_waterlog_drain"))return false;
        var v=r.get("projected_waterlog_drain");
        if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Projected drain flag must be boolean");
        return v.getAsBoolean();
    }
    static boolean pair(BlockState wet,BlockState dry,boolean blockEntity){
        var property=BlockStateProperties.WATERLOGGED;
        if(blockEntity||!wet.hasProperty(property)||!dry.hasProperty(property)
            ||!wet.getValue(property)||dry.getValue(property)||wet.getBlock()!=dry.getBlock()
            ||!(wet.getBlock() instanceof SimpleWaterloggedBlock)
            ||!(wet.getBlock() instanceof SlabBlock||wet.getBlock() instanceof TrapDoorBlock))return false;
        if(wet.getBlock() instanceof SlabBlock&&wet.getValue(BlockStateProperties.SLAB_TYPE)==SlabType.DOUBLE)return false;
        return wet.setValue(property,false).equals(dry)&&wet.getFluidState().is(Fluids.WATER)
            &&wet.getFluidState().isSource()&&dry.getFluidState().isEmpty();
    }
    ProjectedWaterlogDrain(Minecraft c,JsonObject r,BlockPos target){
        this.target=target.immutable();placement=ProjectionLoadPolicy.text(r,"placement_key",8192);
        var selection=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(!selection.key().equals(placement)||!selection.contains(target)||!LitematicaAccess.inVisibleLayer(target)
            ||model==null||!LitematicaAccess.loadingReason(selection).isEmpty())throw new IllegalStateException("Projected drain needs the current locked loaded visible target");
        wet=c.level.getBlockState(target);dry=model.getBlockState(target);
        if(!ProjectionLoadPolicy.text(r,"expected_dry_state",2048).equals(dry.toString())
            ||!pair(wet,dry,c.level.getBlockEntity(target)!=null))
            throw new IllegalStateException("Projected drain only changes waterlogged=true to the otherwise identical dry slab or trapdoor in the schematic");
    }
    boolean context(Minecraft c){
        var selected=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        return selected.key().equals(placement)&&selected.contains(target)&&LitematicaAccess.inVisibleLayer(target)
            &&model!=null&&LitematicaAccess.loadingReason(selected).isEmpty()&&dry.equals(model.getBlockState(target))
            &&c.level.getBlockEntity(target)==null;
    }
    void requireBefore(Minecraft c){
        if(!context(c)||!wet.equals(c.level.getBlockState(target)))throw new IllegalStateException("Projected drain target or blueprint changed before use");
    }
    boolean current(Minecraft c){return context(c)&&currentState(c.level.getBlockState(target),wet,dry);}
    static boolean currentState(BlockState current,BlockState wet,BlockState dry){return current.equals(wet)||current.equals(dry);}
    boolean expectedPacket(BlockState state){return state.equals(dry);}
    String expectedDry(){return dry.toString();}
}
