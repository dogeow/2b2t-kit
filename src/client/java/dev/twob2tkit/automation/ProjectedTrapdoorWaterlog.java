package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.Half;
import net.minecraft.world.level.block.state.properties.SlabType;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.material.Fluids;
import java.util.*;
/** Fill only a contained original closed29-trapdoor row, with its control wire off. */
final class ProjectedTrapdoorWaterlog {
    private final BlockPos target;private final String placement;private final ProjectedTrapdoorRowPolicy.Bounds bounds;
    private final BlockState wet,dry;private final Set<BlockPos> priorWet=new HashSet<>();
    static boolean requested(JsonObject r){
        if(!r.has("projected_trapdoor_waterlog"))return false;var v=r.get("projected_trapdoor_waterlog");
        if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Trapdoor waterlog flag must be boolean");return v.getAsBoolean();
    }
    static boolean closedBottom(BlockState state){return state.is(Blocks.SPRUCE_TRAPDOOR)
        &&state.getValue(TrapDoorBlock.HALF)==Half.BOTTOM&&!state.getValue(TrapDoorBlock.OPEN)&&!state.getValue(TrapDoorBlock.POWERED)
        &&(state.getValue(TrapDoorBlock.FACING)==Direction.NORTH||state.getValue(TrapDoorBlock.FACING)==Direction.SOUTH);}
    static boolean pair(BlockState wet,BlockState dry){return closedBottom(wet)&&closedBottom(dry)&&ProjectedWaterlogDrain.pair(wet,dry,false);}
    ProjectedTrapdoorWaterlog(Minecraft c,JsonObject r,BlockPos target){this(c,r,target,false);}
    ProjectedTrapdoorWaterlog(Minecraft c,JsonObject r,BlockPos target,boolean observeCompleted){
        this.target=target.immutable();placement=ProjectionLoadPolicy.text(r,"placement_key",8192);
        if(!r.has("trapdoor_row_bounds")||!r.get("trapdoor_row_bounds").isJsonObject())throw new IllegalArgumentException("Exact original trapdoor row bounds required");
        var box=r.getAsJsonObject("trapdoor_row_bounds");var lo=ProjectedSourceColumnGuard.point(box.get("min"));var hi=ProjectedSourceColumnGuard.point(box.get("max"));bounds=new ProjectedTrapdoorRowPolicy.Bounds(lo.getX(),lo.getY(),lo.getZ(),hi.getX());
        if(!bounds.valid()||lo.getY()!=hi.getY()||lo.getZ()!=hi.getZ()||target.getY()!=lo.getY()||target.getZ()!=lo.getZ()||target.getX()<lo.getX()||target.getX()>hi.getX())throw new IllegalArgumentException("Only a target inside the original29-cell row is supported");
        var model=LitematicaAccess.schematicWorld();if(model==null)throw new IllegalStateException("Loaded original model required");wet=model.getBlockState(target);var actual=c.level.getBlockState(target);
        dry=observeCompleted&&actual.hasProperty(TrapDoorBlock.WATERLOGGED)?actual.setValue(TrapDoorBlock.WATERLOGGED,false):actual;
        if(!pair(wet,dry)||!wet.toString().equals(ProjectionLoadPolicy.text(r,"expected_wet_state",2048)))throw new IllegalStateException("Only the original waterlogged bit may change");
        for(int x=bounds.minX();x<=bounds.maxX();x++){var p=new BlockPos(x,bounds.y(),bounds.z());if(c.level.getBlockState(p).hasProperty(TrapDoorBlock.WATERLOGGED)&&c.level.getBlockState(p).getValue(TrapDoorBlock.WATERLOGGED))priorWet.add(p);}
    }
    private static void loaded(Minecraft c,BlockPos p){
        var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
        if(c.level.isOutsideBuildHeight(p)||!c.level.getWorldBorder().isWithinBounds(p)||!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))throw new IllegalStateException("Every row boundary must be current server-loaded");
    }
    private static boolean fullDry(Minecraft c,BlockPos p){loaded(c,p);var s=c.level.getBlockState(p);return c.level.getBlockEntity(p)==null&&s.getFluidState().isEmpty()&&s.isCollisionShapeFullBlock(c.level,p)&&!(s.getBlock() instanceof LiquidBlockContainer);}
    void require(Minecraft c,boolean before){
        var selection=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(model==null||!selection.key().equals(placement)||!LitematicaAccess.loadingReason(selection).isEmpty()||!wet.equals(model.getBlockState(target))
            ||c.level.environmentAttributes().getValue(net.minecraft.world.attribute.EnvironmentAttributes.WATER_EVAPORATES,target))throw new IllegalStateException("Original waterlog row context changed");
        var facing=wet.getValue(TrapDoorBlock.FACING);var cells=new ArrayList<ProjectedTrapdoorRowPolicy.Cell>();
        for(int x=bounds.minX();x<=bounds.maxX();x++){
            var p=new BlockPos(x,bounds.y(),bounds.z());loaded(c,p);
            if(!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p)||c.level.getBlockEntity(p)!=null)throw new IllegalStateException("Whole original trapdoor row must remain visible and container-free");
            var goal=model.getBlockState(p);var actual=c.level.getBlockState(p);
            boolean original=closedBottom(goal)&&goal.getValue(TrapDoorBlock.WATERLOGGED)&&goal.getValue(TrapDoorBlock.FACING)==facing;
            boolean same=actual.equals(goal)||actual.equals(goal.hasProperty(TrapDoorBlock.WATERLOGGED)?goal.setValue(TrapDoorBlock.WATERLOGGED,false):goal);
            boolean bottom=closedBottom(actual)&&Block.isFaceFull(actual.getCollisionShape(c.level,p),Direction.DOWN);
            var back=p.relative(facing.getOpposite());boolean sealedBack=fullDry(c,back)&&model.getBlockState(back).equals(c.level.getBlockState(back));
            var inner=p.relative(facing);loaded(c,inner);var inward=c.level.getBlockState(inner);var wanted=model.getBlockState(inner);
            boolean sealedInner=inward.equals(wanted)&&inward.is(Blocks.COBBLESTONE_SLAB)&&inward.getValue(SlabBlock.TYPE)==SlabType.TOP&&!inward.getValue(SlabBlock.WATERLOGGED)
                &&inward.getBlock() instanceof LiquidBlockContainer liquid&&!liquid.canPlaceLiquid(c.player,c.level,inner,inward,Fluids.FLOWING_WATER);
            // Each inward slab has at most the one row source next to it. No second
            // neighboring source may synthesize a source capable of waterlogging it.
            for(var side:Direction.Plane.HORIZONTAL){var q=inner.relative(side);if(q.equals(p))continue;loaded(c,q);sealedInner&=c.level.getFluidState(q).isEmpty();}
            var wire=back.above();loaded(c,wire);var control=c.level.getBlockState(wire);boolean quiet=control.is(Blocks.REDSTONE_WIRE)&&control.getValue(RedStoneWireBlock.POWER)==0;
            cells.add(new ProjectedTrapdoorRowPolicy.Cell(original,same,bottom,sealedBack,sealedInner,!priorWet.contains(p)||actual.hasProperty(TrapDoorBlock.WATERLOGGED)&&actual.getValue(TrapDoorBlock.WATERLOGGED),quiet));
        }
        boolean ends=true;
        for(var p:new BlockPos[]{new BlockPos(bounds.minX()-1,bounds.y(),bounds.z()),new BlockPos(bounds.maxX()+1,bounds.y(),bounds.z())}){
            ends&=fullDry(c,p)&&c.level.getBlockState(p).equals(model.getBlockState(p));
        }
        var now=c.level.getBlockState(target);String error=ProjectedTrapdoorRowPolicy.rejection(bounds,cells,target.getX()-bounds.minX(),before,now.equals(dry),now.equals(dry)||now.equals(wet),ends);
        if(error!=null)throw new IllegalStateException(error);
    }
    boolean expectedPacket(BlockState state){return state.equals(wet);}
    String expectedWet(){return wet.toString();}
}
