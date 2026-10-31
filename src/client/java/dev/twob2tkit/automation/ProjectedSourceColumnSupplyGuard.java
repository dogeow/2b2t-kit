package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;

/** One ordinary fill from a completed middle source, never either outer seed source. */
final class ProjectedSourceColumnSupplyGuard {
    private final ProjectedSourceColumnGuard column;
    private final BlockPos target;
    private final boolean completedOverflow;
    private final int overflowY;
    boolean completedOverflow(){return completedOverflow;}
    static boolean requested(JsonObject request){
        if(!request.has("projected_source_column_supply"))return false;
        var value=request.get("projected_source_column_supply");
        if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Source supply flag must be boolean");
        return value.getAsBoolean();
    }
    static boolean completedOverflowRequested(JsonObject request){
        var flag=request.get("source_supply_completed_overflow");
        if(flag!=null&&(!flag.isJsonPrimitive()||!flag.getAsJsonPrimitive().isBoolean()))throw new IllegalArgumentException("Completed overflow supply flag must be boolean");
        return flag!=null&&flag.getAsBoolean();
    }
    ProjectedSourceColumnSupplyGuard(Minecraft c,JsonObject request,BlockPos target){
        if(!request.has("source_column_bounds")||!request.get("source_column_bounds").isJsonObject())throw new IllegalArgumentException("Pinned source bounds required");
        var min=ProjectedSourceColumnGuard.point(request.getAsJsonObject("source_column_bounds").get("min"));
        completedOverflow=completedOverflowRequested(request);
        overflowY=ProjectedSourceColumnGuard.point(request.getAsJsonObject("source_column_bounds").get("max")).getY()+1;
        this.target=target.immutable();
        column=new ProjectedSourceColumnGuard(c,request,new BlockPos(min.getX(),target.getY(),min.getZ()));
        column.excludeRefillTarget(this.target);
    }
    private static int level(BlockState state){return state.is(Blocks.WATER)?state.getValue(LiquidBlock.LEVEL):-1;}
    private void requireWorkspace(Minecraft c){
        if(!completedOverflow){column.require(c,false);return;}
        column.requireCompletedSupply(c);
        var model=dev.twob2tkit.builder.LitematicaAccess.schematicWorld();
        var goals=new java.util.ArrayList<Integer>();var actual=new java.util.ArrayList<Integer>();
        for(int x=target.getX()-1;x<=target.getX()+1;x++){
            var p=new BlockPos(x,overflowY,target.getZ());goals.add(level(model.getBlockState(p)));actual.add(level(c.level.getBlockState(p)));
        }
        if(!SourceColumnSupplyPolicy.completedTop(goals,actual))throw new IllegalStateException("Completed overflow supply must preserve the original top water row");
    }
    void requireBefore(Minecraft c){
        requireWorkspace(c);var below=c.level.getBlockState(target.below());
        boolean support=level(below)==0||below.getFluidState().isEmpty()&&below.isCollisionShapeFullBlock(c.level,target.below());
        if(!SourceColumnSupplyPolicy.ready(true,level(c.level.getBlockState(target.west())),level(c.level.getBlockState(target)),
                level(c.level.getBlockState(target.east())),support))throw new IllegalStateException("Refill needs a complete three-source row with a supported center");
    }
    boolean current(Minecraft c){try{requireWorkspace(c);return true;}catch(RuntimeException changed){return false;}}
    static boolean shieldedWorkspace(Minecraft c,JsonObject request){
        try{
            if(!"bucket_fill".equals(ProjectionLoadPolicy.text(request,"op",64))||!requested(request)||c.player==null||c.level==null)return false;
            var guard=new ProjectedSourceColumnSupplyGuard(c,request,ProjectedSourceColumnGuard.point(request.get("pos")));
            guard.requireWorkspace(c);return guard.column.shieldedActor(c);
        }catch(RuntimeException unproved){return false;}
    }
}
