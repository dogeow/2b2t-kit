package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.LiquidBlockContainer;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;

/** Opt-in long falling column, still using the ordinary bucket action and its two server receipts. */
final class ProjectedWaterFlowGuard {
    private final ProjectedWaterFlowPolicy.Bounds bounds;
    private final String placement;
    private final BlockPos target;
    static boolean requested(JsonObject r){
        if(!r.has("projected_water_column"))return false;
        var v=r.get("projected_water_column");
        if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Projected column flag must be boolean");
        return v.getAsBoolean();
    }
    private static ProjectedWaterFlowPolicy.Cell cell(JsonArray a){
        if(a==null||a.size()!=3)throw new IllegalArgumentException("Water bounds need integer XYZ");
        int[] n=new int[3];
        for(int i=0;i<3;i++){
            if(!a.get(i).isJsonPrimitive()||!a.get(i).getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Water bounds need integer XYZ");
            n[i]=a.get(i).getAsBigDecimal().intValueExact();
            if(Math.abs((long)n[i])>30000000)throw new IllegalArgumentException("Water bounds outside world");
        }
        return new ProjectedWaterFlowPolicy.Cell(n[0],n[1],n[2]);
    }
    ProjectedWaterFlowGuard(JsonObject r,BlockPos target){
        if(!r.has("water_column_bounds")||!r.get("water_column_bounds").isJsonObject()
            ||!r.has("placement_key"))throw new IllegalArgumentException("Projected column needs locked placement and downstream bounds");
        var box=r.getAsJsonObject("water_column_bounds");
        bounds=new ProjectedWaterFlowPolicy.Bounds(cell(box.getAsJsonArray("min")),cell(box.getAsJsonArray("max")));
        if(!bounds.valid())throw new IllegalArgumentException("Projected column bounds exceed limits");
        placement=r.get("placement_key").getAsString();this.target=target.immutable();
    }
    private static boolean loaded(Minecraft c,BlockPos p){
        var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
        return LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    static boolean fullBarrier(Minecraft c,BlockPos p){
        var s=c.level.getBlockState(p);
        return loaded(c,p)&&s.getFluidState().isEmpty()&&c.level.getBlockEntity(p)==null
            &&!(s.getBlock() instanceof LiquidBlockContainer)&&s.isCollisionShapeFullBlock(c.level,p);
    }
    void require(Minecraft c,boolean before){
        var selected=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(!selected.key().equals(placement)||!selected.contains(target)||model==null
            ||!LitematicaAccess.loadingReason(selected).isEmpty()||!LitematicaAccess.inVisibleLayer(target))
            throw new IllegalStateException("Projected water selection changed");
        var source=model.getBlockState(target);
        if(!source.is(Blocks.WATER)||source.getValue(LiquidBlock.LEVEL)!=0||target.getY()<=selected.min().getY())
            throw new IllegalStateException("Projected column needs its exact source and falling cells");
        for(int y=target.getY()-1;y>=selected.min().getY();y--){
            var s=model.getBlockState(new BlockPos(target.getX(),y,target.getZ()));
            if(!s.is(Blocks.WATER)||s.getValue(LiquidBlock.LEVEL)!=8)throw new IllegalStateException("Projected column is not continuous falling water");
        }
        if(c.level.environmentAttributes().getValue(net.minecraft.world.attribute.EnvironmentAttributes.WATER_EVAPORATES,target)
            ||bounds.min().y()<c.level.getMinY()||bounds.max().y()>=c.level.getMaxY()
            ||bounds.min().y()>=selected.min().getY()||bounds.max().y()<target.getY())
            throw new IllegalStateException("Projected column lacks downstream coverage");
        var actual=c.level.getBlockState(target);
        if(before?!actual.isAir():!actual.is(Blocks.WATER)||actual.getValue(LiquidBlock.LEVEL)!=0)
            throw new IllegalStateException("Projected source state changed");
        for(Direction side:Direction.Plane.HORIZONTAL)if(!fullBarrier(c,target.relative(side)))
            throw new IllegalStateException("Projected source needs four dry full side walls");
        var low=bounds.min();var high=bounds.max();
        var living=c.level.getEntities(c.player,new AABB(low.x(),low.y(),low.z(),high.x()+1,high.y()+1,high.z()+1),e->e instanceof LivingEntity&&e.isAlive());
        var world=new ProjectedWaterFlowPolicy.World(){
            private BlockPos pos(ProjectedWaterFlowPolicy.Cell p){return new BlockPos(p.x(),p.y(),p.z());}
            public ProjectedWaterFlowPolicy.Kind kind(ProjectedWaterFlowPolicy.Cell p){
                var q=pos(p);
                if(!c.level.getWorldBorder().isWithinBounds(q)||!loaded(c,q))return ProjectedWaterFlowPolicy.Kind.UNLOADED;
                var state=c.level.getBlockState(q);
                if(c.level.getBlockEntity(q)!=null)return ProjectedWaterFlowPolicy.Kind.UNSAFE;
                if(state.isAir())return ProjectedWaterFlowPolicy.Kind.AIR;
                if(state.is(Blocks.WATER))return state.getValue(LiquidBlock.LEVEL)==0?ProjectedWaterFlowPolicy.Kind.SOURCE:ProjectedWaterFlowPolicy.Kind.FLOWING;
                return fullBarrier(c,q)?ProjectedWaterFlowPolicy.Kind.BARRIER:ProjectedWaterFlowPolicy.Kind.UNSAFE;
            }
            public boolean living(ProjectedWaterFlowPolicy.Cell p){var box=new AABB(pos(p));return box.intersects(c.player.getBoundingBox())||living.stream().anyMatch(e->e.getBoundingBox().intersects(box));}
        };
        var reason=ProjectedWaterFlowPolicy.rejection(world,bounds,new ProjectedWaterFlowPolicy.Cell(target.getX(),target.getY(),target.getZ()));
        if(reason!=null)throw new IllegalStateException(reason);
    }
}
