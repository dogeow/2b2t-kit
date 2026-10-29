package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.ExperienceOrb;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.StairBlock;
import net.minecraft.world.level.block.TrapDoorBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Half;
import net.minecraft.world.level.block.state.properties.StairsShape;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;
import java.util.ArrayList;

/** Exact original one-wide channel, using the ordinary bucket and receipt path. */
final class ProjectedChannelWaterGuard {
    private final BlockPos source;
    private final String placement;
    static boolean requested(JsonObject r){
        if(!r.has("projected_water_channel"))return false;
        var value=r.get("projected_water_channel");
        if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isBoolean())
            throw new IllegalArgumentException("Projected channel flag must be boolean");
        return value.getAsBoolean();
    }
    ProjectedChannelWaterGuard(JsonObject r,BlockPos source){
        placement=ProjectionLoadPolicy.text(r,"placement_key",8192);
        if(placement.isBlank()||!ProjectionLoadPolicy.text(r,"channel_direction",16).equals("west")
                ||!r.has("channel_length")||!r.get("channel_length").isJsonPrimitive()
                ||!r.get("channel_length").getAsJsonPrimitive().isNumber()
                ||r.get("channel_length").getAsBigDecimal().intValueExact()!=8)
            throw new IllegalArgumentException("An explicit locked eight-cell west-flowing channel required");
        this.source=source.immutable();
    }
    private static boolean loaded(Minecraft c,BlockPos p){
        var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
        return c.level.getWorldBorder().isWithinBounds(p)&&!c.level.isOutsideBuildHeight(p)
            &&LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    private static boolean northStair(BlockState s){
        return s.is(Blocks.COBBLESTONE_STAIRS)&&s.getValue(StairBlock.FACING)==Direction.SOUTH
            &&s.getValue(StairBlock.HALF)==Half.BOTTOM&&s.getValue(StairBlock.SHAPE)==StairsShape.STRAIGHT
            &&!s.getValue(StairBlock.WATERLOGGED);
    }
    private static boolean stop(BlockState s){
        return s.is(Blocks.SPRUCE_TRAPDOOR)&&s.getValue(TrapDoorBlock.HALF)==Half.TOP
            &&!s.getValue(TrapDoorBlock.OPEN)&&!s.getValue(TrapDoorBlock.POWERED)
            &&!s.getValue(TrapDoorBlock.WATERLOGGED);
    }
    private static int level(BlockState s){
        return s.isAir()?-1:s.is(Blocks.WATER)?s.getValue(net.minecraft.world.level.block.LiquidBlock.LEVEL):-2;
    }
    void require(Minecraft c,boolean before){
        var selection=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(!selection.key().equals(placement)||model==null||!LitematicaAccess.loadingReason(selection).isEmpty()
                ||c.level.environmentAttributes().getValue(net.minecraft.world.attribute.EnvironmentAttributes.WATER_EVAPORATES,source))
            throw new IllegalStateException("Projected channel context changed");
        for(var p:BlockPos.betweenClosed(source.offset(-8,-1,-1),source.offset(1,1,1))){
            if(!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p)||!loaded(c,p)||c.level.getBlockEntity(p)!=null)
                throw new IllegalStateException("Entire projected channel must be visible, server-loaded and container-free");
        }
        var cells=new ArrayList<ProjectedChannelWaterPolicy.Cell>();
        for(int i=0;i<8;i++){
            var p=source.west(i);var floor=p.below();var north=p.north();var south=p.south();var ceiling=p.above();
            var goal=model.getBlockState(p);
            boolean bottom=model.getBlockState(floor).is(Blocks.COBBLESTONE)
                &&model.getBlockState(floor).equals(c.level.getBlockState(floor));
            boolean n=northStair(model.getBlockState(north))&&model.getBlockState(north).equals(c.level.getBlockState(north))
                &&Block.isFaceFull(c.level.getBlockState(north).getCollisionShape(c.level,north),Direction.SOUTH);
            boolean s=model.getBlockState(south).is(Blocks.GLASS)&&model.getBlockState(south).equals(c.level.getBlockState(south));
            var actualRoof=c.level.getBlockState(ceiling);
            // Only the source's one original cobblestone ceiling cell may
            // be a temporary AIR service opening. Water cannot rise into it.
            boolean roof=model.getBlockState(ceiling).is(Blocks.COBBLESTONE)
                &&(actualRoof.equals(model.getBlockState(ceiling))||i==0&&actualRoof.isAir());
            cells.add(new ProjectedChannelWaterPolicy.Cell(level(goal),level(c.level.getBlockState(p)),bottom,n,s,roof));
        }
        boolean ends=true;
        for(var p:new BlockPos[]{source.east(),source.west(8)}){
            ends&=stop(model.getBlockState(p))&&model.getBlockState(p).equals(c.level.getBlockState(p))
                &&model.getBlockState(p.below()).is(Blocks.PACKED_ICE)
                &&model.getBlockState(p.below()).equals(c.level.getBlockState(p.below()));
        }
        boolean clear=true;
        for(int i=0;i<8;i++){
            var box=new AABB(source.west(i));
            if(box.intersects(c.player.getBoundingBox())||!c.level.getEntities(c.player,box,
                    e->e.isAlive()&&!(e instanceof ItemEntity)&&!(e instanceof ExperienceOrb)).isEmpty())clear=false;
        }
        String reason=ProjectedChannelWaterPolicy.rejection(cells,before,ends,clear);
        if(reason!=null)throw new IllegalStateException(reason);
    }
}
