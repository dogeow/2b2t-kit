package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import java.util.EnumMap;

final class BelowFlowMiningGuard {
    static boolean requested(JsonObject request){
        if(request==null||!request.has("flowing_water_below"))return false;
        var value=request.get("flowing_water_below");
        if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isBoolean())
            throw new IllegalArgumentException("Flowing-water-below flag must be boolean");
        return value.getAsBoolean();
    }
    private static String text(JsonObject r,String key){return r.has(key)?r.get(key).getAsString():"";}
    static void require(Minecraft c,JsonObject r,BlockPos target,boolean owned,boolean silk,boolean started){
        if(c.player==null||c.level==null)throw new IllegalStateException("Live construction world required");
        var selection=LitematicaAccess.lockedBuildSelection();
        var schematic=LitematicaAccess.schematicWorld();
        var actual=c.level.getBlockState(target);
        boolean projected=selection.key().equals(text(r,"placement_key"))&&selection.contains(target)
            &&LitematicaAccess.inVisibleLayer(target)&&LitematicaAccess.loadingReason(selection).isEmpty()
            &&schematic!=null&&schematic.getBlockState(target).is(Blocks.GLASS)
            &&text(r,"expected_state").equals(Blocks.GLASS.defaultBlockState().toString())
            &&(actual.is(Blocks.GLASS)||started&&actual.isAir())&&c.level.getBlockEntity(target)==null;
        var held=c.player.getMainHandItem();
        boolean tool=silk&&held.is(ItemTags.PICKAXES)&&held.isDamageableItem()
            &&held.getMaxDamage()-held.getDamageValue()>=(started?1:33)
            &&r.has("expected_tool_slot")&&r.get("expected_tool_slot").getAsInt()==c.player.getInventory().getSelectedSlot();
        boolean healthy=c.player.getHealth()>=19&&c.player.getFoodData().getFoodLevel()>=8
            &&!c.player.hasInfiniteMaterials()&&!c.player.isInWater()&&!c.player.isInLava()&&!c.player.isOnFire()
            &&c.gui.screen()==null&&c.player.containerMenu==c.player.inventoryMenu
            &&c.player.containerMenu.getCarried().isEmpty()&&!c.player.isUsingItem();
        var neighbors=new EnumMap<BelowFlowMiningPolicy.Side,BelowFlowMiningPolicy.Fluid>(BelowFlowMiningPolicy.Side.class);
        for(var direction:Direction.values()){
            var pos=target.relative(direction);var chunk=c.level.getChunkSource().getChunk(pos.getX()>>4,pos.getZ()>>4,ChunkStatus.FULL,false);
            var fluid=BelowFlowMiningPolicy.Fluid.UNKNOWN;
            if(LoadedServerChunkEvidence.isServerChunk(c.level,chunk)){
                var state=c.level.getBlockState(pos);var liquid=state.getFluidState();
                fluid=liquid.isEmpty()?BelowFlowMiningPolicy.Fluid.DRY:
                    state.is(Blocks.WATER)&&liquid.isSource()?BelowFlowMiningPolicy.Fluid.WATER_SOURCE:
                    state.is(Blocks.WATER)?BelowFlowMiningPolicy.Fluid.FLOWING_WATER:BelowFlowMiningPolicy.Fluid.OTHER;
            }
            neighbors.put(BelowFlowMiningPolicy.Side.valueOf(direction.name()),fluid);
        }
        boolean footing=c.player.onGround()&&(c.player.blockPosition().equals(target)||c.player.blockPosition().below().equals(target));
        var rejection=BelowFlowMiningPolicy.rejection(owned,healthy,projected,tool,footing,
            c.level.getBlockState(target.below()).toString().equals(text(r,"expected_below_state")),neighbors);
        if(rejection!=null)throw new IllegalStateException(rejection);
    }
}
