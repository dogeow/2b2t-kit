package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;
import java.util.*;
/** Exact eight-cell west-then-south overflow above a completed pinned source chamber. */
final class ProjectedBentChannelGuard {
    private final BlockPos source;
    private final String placement;
    private final boolean seed;
    private final int collectIndex;
    private final BlockPos serviceRoof;
    private final BlockPos middleRoof;
    BlockPos middleRoof(){return middleRoof;}
    int collectIndex(){return collectIndex;}
    BlockPos serviceRoof(){return serviceRoof;}
    boolean seed(){return seed;}
    private final ProjectedSourceColumnGuard chamber;
    static boolean requested(JsonObject r){
        if(!r.has("projected_bent_channel"))return false;
        var v=r.get("projected_bent_channel");
        if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Bent-channel flag must be boolean");
        return v.getAsBoolean();
    }
    static int collectionIndex(JsonObject r){
        var value=r.get("projected_bent_channel_collect_index");if(value==null)return 0;
        if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Collection index must be an explicit integer");
        int index=value.getAsBigDecimal().intValueExact();if(index!=1&&index!=2)throw new IllegalArgumentException("Only temporary sources1/2 may be collected");return index;
    }
    static boolean collectRequested(JsonObject r){return collectionIndex(r)>0;}
    static boolean shieldedWorkspace(Minecraft c,JsonObject r){
        try{
            if(c==null||c.player==null||c.level==null)return false;
            boolean fill="bucket_fill".equals(ProjectionLoadPolicy.text(r,"op",64));
            if(fill?!collectRequested(r):!"bucket_place".equals(ProjectionLoadPolicy.text(r,"op",64))||!requested(r))return false;
            var guard=new ProjectedBentChannelGuard(c,r,ProjectedSourceColumnGuard.point(r.get("pos")));
            if(guard.chamber.rows()!=4&&guard.collectIndex==0)return false;
            guard.require(c,false);return guard.chamber.shieldedActor(c);
        }catch(RuntimeException unproved){return false;}
    }
    ProjectedBentChannelGuard(Minecraft c,JsonObject r,BlockPos source){
        var b=r.getAsJsonObject("source_column_bounds");
        if(b==null)throw new IllegalArgumentException("Completed source chamber bounds required");
        var low=ProjectedSourceColumnGuard.point(b.get("min"));var high=ProjectedSourceColumnGuard.point(b.get("max"));
        var flag=r.get("projected_bent_channel_seed");
        if(flag!=null&&(!flag.isJsonPrimitive()||!flag.getAsJsonPrimitive().isBoolean()))throw new IllegalArgumentException("Bent seed flag must be boolean");
        seed=flag!=null&&flag.getAsBoolean();collectIndex=collectionIndex(r);
        if(seed&&collectIndex>0)throw new IllegalArgumentException("Seed placement and collection are exclusive");
        var origin=new BlockPos(high.getX(),high.getY()+1,low.getZ());
        if(!source.equals(collectIndex>0?origin.west(collectIndex):seed?origin.west(2):origin))throw new IllegalArgumentException("Only the original upper overflow source is supported");
        this.source=origin.immutable();placement=ProjectionLoadPolicy.text(r,"placement_key",8192);
        chamber=new ProjectedSourceColumnGuard(c,r,low);
        serviceRoof=r.has("bent_service_ceiling")?ProjectedSourceColumnGuard.point(r.get("bent_service_ceiling")):null;
        if(serviceRoof!=null&&(chamber.rows()!=4||!serviceRoof.equals(source.above())))throw new IllegalArgumentException("Only this short-profile action's exact original roof may be temporarily open");
        middleRoof=r.has("bent_middle_ceiling")?ProjectedSourceColumnGuard.point(r.get("bent_middle_ceiling")):null;
        if(middleRoof!=null&&!middleServiceAllowed(chamber.rows(),middleRoof,origin,serviceRoof))throw new IllegalArgumentException("Only the distinct original middle roof may remain as a shared service opening");
    }
    private static int level(BlockState s){return s.isAir()?-1:s.is(Blocks.WATER)?s.getValue(LiquidBlock.LEVEL):-2;}
    private static void loaded(Minecraft c,BlockPos p){
        var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
        if(!c.level.getWorldBorder().isWithinBounds(p)||c.level.isOutsideBuildHeight(p)||!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))
            throw new IllegalStateException("Entire overflow must be current server-loaded geometry");
    }
    void require(Minecraft c,boolean before){
        chamber.requireCompleted(c);
        var selection=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(model==null||!selection.key().equals(placement))throw new IllegalStateException("Overflow projection changed");
        var path=new ArrayList<BlockPos>();
        for(int i=0;i<8;i++)path.add(source.offset(ProjectedBentChannelPolicy.dx(i,chamber.rows()),0,ProjectedBentChannelPolicy.dz(i,chamber.rows())));
        var goals=new ArrayList<Integer>();var actual=new ArrayList<Integer>();
        for(int i=0;i<8;i++){
            var p=path.get(i);loaded(c,p);
            if(!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p)||c.level.getBlockEntity(p)!=null)
                throw new IllegalStateException("Overflow cell is hidden, outside projection or occupied by a container");
            goals.add(level(model.getBlockState(p)));actual.add(level(c.level.getBlockState(p)));
            var floor=p.below();loaded(c,floor);var f=c.level.getBlockState(floor);
            if(i<3?!f.is(Blocks.WATER)||level(f)!=0:!f.is(chamber.rows()==4?Blocks.COBBLESTONE:Blocks.GLASS)||!f.equals(model.getBlockState(floor)))
                throw new IllegalStateException("Overflow floor must preserve the source chamber and original glass");
            var roof=p.above();loaded(c,roof);
            var roofGoal=model.getBlockState(roof);var roofNow=c.level.getBlockState(roof);
            if(chamber.rows()==4&&i<3){
                if(!shortRoof(roofGoal,roofNow,roof.equals(serviceRoof)||roof.equals(middleRoof)))throw new IllegalStateException("Short overflow needs all original bottom roofs except its one pinned service opening");
            }else if(!roofNow.isAir()||!roofGoal.isAir())throw new IllegalStateException("Overflow must retain its original open top");
            for(var side:Direction.Plane.HORIZONTAL){
                var q=p.relative(side);if(path.contains(q))continue;loaded(c,q);var s=c.level.getBlockState(q);var goal=model.getBlockState(q);
                boolean end=i==7&&side==Direction.SOUTH;
                String endpoint="Block{minecraft:spruce_trapdoor}[facing=east,half=top,open=false,powered=false,waterlogged=false]";
                if(!selection.contains(q)||!LitematicaAccess.inVisibleLayer(q)||c.level.getBlockEntity(q)!=null
                        ||!s.equals(goal)||(end?!s.toString().equals(endpoint):chamber.rows()==4?!shortSide(s,c.level,q,side.getOpposite()):!s.is(Blocks.GLASS)))
                    throw new IllegalStateException("Overflow side wall or dry terminal changed");
            }
            var box=new AABB(p);
            if(box.intersects(c.player.getBoundingBox())||!c.level.getEntities(c.player,box,e->e.isAlive()
                    &&!(e instanceof net.minecraft.world.entity.item.ItemEntity)&&!(e instanceof net.minecraft.world.entity.ExperienceOrb)).isEmpty())
                throw new IllegalStateException("Overflow has an entity in its water cells");
        }
        if(!(collectIndex>0?ProjectedBentChannelPolicy.collectLevels(goals,actual,collectIndex,before):seed?ProjectedBentChannelPolicy.seedLevels(goals,actual,before):ProjectedBentChannelPolicy.levels(goals,actual,before)))throw new IllegalStateException("Exact dry L-shaped eight-cell overflow required before use");
    }
    static boolean shortSide(BlockState s,net.minecraft.world.level.BlockGetter level,BlockPos pos,Direction inward){
        if(s.getFluidState().isEmpty()&&(s.is(Blocks.GLASS)||s.is(Blocks.COBBLESTONE)))return s.isCollisionShapeFullBlock(level,pos);
        return s.is(Blocks.COBBLESTONE_STAIRS)&&s.getValue(StairBlock.FACING)==inward
            &&s.getValue(StairBlock.HALF)==net.minecraft.world.level.block.state.properties.Half.BOTTOM
            &&s.getValue(StairBlock.SHAPE)==net.minecraft.world.level.block.state.properties.StairsShape.STRAIGHT
            &&!s.getValue(StairBlock.WATERLOGGED)&&Block.isFaceFull(s.getCollisionShape(level,pos),inward);
    }
    static boolean shortRoof(BlockState original,BlockState actual,boolean service){
        return original.is(Blocks.COBBLESTONE_SLAB)&&original.getValue(SlabBlock.TYPE)==net.minecraft.world.level.block.state.properties.SlabType.BOTTOM
            &&!original.getValue(SlabBlock.WATERLOGGED)&&(service?actual.isAir():actual.equals(original));
    }

    static boolean middleServiceAllowed(int rows,BlockPos middle,BlockPos origin,BlockPos active){
        return rows==4&&active!=null&&middle!=null&&middle.equals(origin.west().above())&&!middle.equals(active);
    }

}
