package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.tags.FluidTags;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.chunk.status.ChunkStatus;

final class ProjectedWetTerrainGuard {
    static boolean requested(JsonObject r){
        if(r==null||!r.has("projected_wet_terrain"))return false;
        var flag=r.get("projected_wet_terrain");
        if(!flag.isJsonPrimitive()||!flag.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Projected wet terrain flag must be boolean");
        return flag.getAsBoolean();
    }
    static boolean componentCorrection(JsonObject r){
        if(!r.has("projected_component_correction"))return false;
        var flag=r.get("projected_component_correction");
        if(!flag.isJsonPrimitive()||!flag.getAsJsonPrimitive().isBoolean())
            throw new IllegalArgumentException("Projected component correction flag must be boolean");
        return flag.getAsBoolean();
    }
    private static String text(JsonObject r,String key){
        var v=r.get(key);return v!=null&&v.isJsonPrimitive()&&v.getAsJsonPrimitive().isString()?v.getAsString():"";
    }
    static void require(Minecraft c,JsonObject r,BlockPos target,boolean owned,boolean started){
        var selection=LitematicaAccess.lockedBuildSelection();var schematic=LitematicaAccess.schematicWorld();
        var actual=c.level.getBlockState(target);String initial=text(r,"expected_state");
        int end=initial.indexOf('}');String initialId=initial.startsWith("Block{")&&end>6?initial.substring(6,end):"";
        boolean removed=started&&(actual.isAir()||actual.is(Blocks.WATER));
        boolean projection=schematic!=null&&selection.key().equals(text(r,"placement_key"))&&selection.contains(target)
            &&LitematicaAccess.inVisibleLayer(target)&&LitematicaAccess.loadingReason(selection).isEmpty()
            &&schematic.getBlockState(target).toString().equals(text(r,"expected_goal_state"));
        String goal=schematic==null?"":BuiltInRegistries.BLOCK.getKey(schematic.getBlockState(target).getBlock()).toString();
        boolean correction=componentCorrection(r);
        boolean eligible=correction
            ?ProjectedComponentCorrectionPolicy.observerCorrection(initial,text(r,"expected_goal_state"))
            :ProjectedWetTerrainPolicy.obstruction(initialId,goal);
        boolean natural=eligible
            &&(actual.toString().equals(initial)&&actual.getFluidState().isEmpty()||removed)
            &&c.level.getBlockEntity(target)==null;
        var held=c.player.getMainHandItem();var slot=r.get("expected_tool_slot");
        boolean pinned=false;
        try{pinned=slot!=null&&slot.isJsonPrimitive()&&slot.getAsJsonPrimitive().isNumber()
            &&slot.getAsBigDecimal().intValueExact()==c.player.getInventory().getSelectedSlot();}catch(ArithmeticException ignored){}
        boolean tool=pinned&&held.is(correction||initialId.equals("minecraft:stone")?ItemTags.PICKAXES:ItemTags.SHOVELS)
            &&held.isDamageableItem()&&held.getMaxDamage()-held.getDamageValue()>=(started?1:33);
        boolean healthy=c.player.getHealth()>=19&&c.player.getFoodData().getFoodLevel()>=18
            &&!c.player.hasInfiniteMaterials()&&!c.player.isInWater()&&!c.player.isInLava()&&!c.player.isOnFire()
            &&c.gui.screen()==null&&c.player.containerMenu==c.player.inventoryMenu
            &&c.player.containerMenu.getCarried().isEmpty()&&!c.player.isUsingItem();
        boolean footing=c.player.onGround()&&(c.player.blockPosition().equals(target)||c.player.blockPosition().below().equals(target));
        var targetChunk=c.level.getChunkSource().getChunk(target.getX()>>4,target.getZ()>>4,ChunkStatus.FULL,false);
        boolean neighbors=LoadedServerChunkEvidence.isServerChunk(c.level,targetChunk),container=false;
        var pins=r.has("expected_neighbors")&&r.get("expected_neighbors").isJsonObject()?r.getAsJsonObject("expected_neighbors"):null;
        neighbors&=pins!=null&&pins.size()==6;
        for(var direction:Direction.values()){
            var pos=target.relative(direction);var chunk=c.level.getChunkSource().getChunk(pos.getX()>>4,pos.getZ()>>4,ChunkStatus.FULL,false);
            var state=c.level.getBlockState(pos);var fluid=state.getFluidState();
            String pin=pins==null?null:text(pins,direction.name().toLowerCase(java.util.Locale.ROOT));
            neighbors&=LoadedServerChunkEvidence.isServerChunk(c.level,chunk)&&(fluid.isEmpty()||fluid.is(FluidTags.WATER))
                &&ProjectedWetTerrainPolicy.neighborPreserved(pin,state.toString(),removed);
            container|=c.level.getBlockEntity(pos)!=null;
        }
        var rejection=ProjectedWetTerrainPolicy.rejection(owned,healthy,projection,natural,tool,footing,neighbors,container);
        if(rejection!=null)throw new IllegalStateException(rejection);
    }
}
