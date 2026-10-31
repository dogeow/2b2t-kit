package dev.twob2tkit.automation;
import java.util.*;
import java.util.function.Predicate;
import net.minecraft.core.*;
import net.minecraft.tags.*;
import net.minecraft.world.level.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.*;
import net.minecraft.world.phys.shapes.Shapes;

/** Read-only potential flow proof for an original planar source, including source regeneration. */
final class ModelWaterPlan {
 static boolean source(BlockState s){return Fluids.WATER.isSame(s.getFluidState().getType())&&s.getFluidState().isSource();}
 static boolean same(BlockState a,BlockState b){
  if(a.is(Blocks.HOPPER)&&b.is(Blocks.HOPPER))return a.setValue(HopperBlock.ENABLED,true).equals(b.setValue(HopperBlock.ENABLED,true));
  if(a.is(Blocks.DROPPER)&&b.is(Blocks.DROPPER))return a.setValue(DropperBlock.TRIGGERED,false).equals(b.setValue(DropperBlock.TRIGGERED,false));
  return a.equals(b);
 }
 static boolean holds(BlockGetter level,BlockPos p,Fluid fluid){
  var s=level.getBlockState(p);var block=s.getBlock();
  if(!s.getFluidState().isEmpty()&&!Fluids.WATER.isSame(s.getFluidState().getType()))return false;
  if(block instanceof LiquidBlockContainer c)return c.canPlaceLiquid(null,level,p,s,fluid);
  if(s.blocksMotion())return false;
  return !(block instanceof DoorBlock)&&!s.is(BlockTags.SIGNS)&&!s.is(Blocks.LADDER)&&!s.is(Blocks.SUGAR_CANE)
    &&!s.is(Blocks.BUBBLE_COLUMN)&&!s.is(Blocks.NETHER_PORTAL)&&!s.is(Blocks.END_GATEWAY)&&!s.is(Blocks.STRUCTURE_VOID);
 }
 static BlockPos pos(ProjectedWaterFlowPolicy.Cell p){return new BlockPos(p.x(),p.y(),p.z());}
 static String rejection(BlockGetter current,BlockGetter model,ProjectedWaterFlowPolicy.Bounds b,BlockPos source,Predicate<BlockPos> occupied){
  if(!b.valid()||b.max().y()!=source.getY()+1||b.min().y()!=source.getY()-1||source.getX()<=b.min().x()||source.getX()>=b.max().x()||source.getZ()<=b.min().z()||source.getZ()>=b.max().z())return "Planar source needs three bounded layers";
  if(!model.getBlockState(source).is(Blocks.WATER)||model.getBlockState(source).getValue(LiquidBlock.LEVEL)!=0)return "Original source required";
  if(current.getBlockState(source.below()).is(Blocks.MAGMA_BLOCK)||current.getBlockState(source.below()).is(Blocks.SOUL_SAND))return "Bubble sources need their dedicated mode";
  var proposed=new ProjectedWaterFlowPolicy.Cell(source.getX(),source.getY(),source.getZ());
  var world=new ProjectedWaterFlowPolicy.World(){
   public ProjectedWaterFlowPolicy.Kind kind(ProjectedWaterFlowPolicy.Cell q){
    var p=pos(q);var s=current.getBlockState(p);var goal=model.getBlockState(p);
    if(!s.getFluidState().isEmpty()&&!Fluids.WATER.isSame(s.getFluidState().getType()))return ProjectedWaterFlowPolicy.Kind.UNSAFE;
    if(source(s))return goal.is(Blocks.WATER)||source(goal)?ProjectedWaterFlowPolicy.Kind.SOURCE:ProjectedWaterFlowPolicy.Kind.UNSAFE;
    if(goal.is(Blocks.WATER)&&(s.isAir()||s.is(Blocks.WATER)))return s.isAir()?ProjectedWaterFlowPolicy.Kind.AIR:ProjectedWaterFlowPolicy.Kind.FLOWING;
    if(same(s,goal)&&!holds(current,p,Fluids.FLOWING_WATER))return ProjectedWaterFlowPolicy.Kind.BARRIER;
    return ProjectedWaterFlowPolicy.Kind.UNSAFE;
   }
   public boolean living(ProjectedWaterFlowPolicy.Cell p){return occupied.test(pos(p));}
  };
  // This interface deliberately forbids new falling paths: use the existing column mode for those.
  for(int x=b.min().x();x<=b.max().x();x++)for(int z=b.min().z();z<=b.max().z();z++){
   var p=new BlockPos(x,source.getY(),z);
   if(model.getBlockState(p).is(Blocks.WATER)&&!source(current.getBlockState(p.below()))
      &&(!same(current.getBlockState(p.below()),model.getBlockState(p.below()))||holds(current,p.below(),Fluids.FLOWING_WATER)))
    return "Original channel floor missing or open below "+p;
  }
  String reason=ProjectedWaterFlowPolicy.rejection(world,b,proposed);if(reason!=null)return reason;
  var sources=new HashSet<BlockPos>();
  for(int x=b.min().x()-1;x<=b.max().x()+1;x++)for(int z=b.min().z()-1;z<=b.max().z()+1;z++){
   var p=new BlockPos(x,source.getY(),z);if(source(current.getBlockState(p)))sources.add(p);
  }sources.add(source);
  boolean changed;
  do{
   changed=false;
   for(int x=b.min().x();x<=b.max().x();x++)for(int z=b.min().z();z<=b.max().z();z++){
    var p=new BlockPos(x,source.getY(),z);if(sources.contains(p)||!holds(current,p,Fluids.WATER))continue;
    int neighbors=0;var state=current.getBlockState(p);
    for(var d:Direction.Plane.HORIZONTAL){var n=p.relative(d);if(sources.contains(n)&&!Shapes.mergedFaceOccludes(state.getCollisionShape(current,p),current.getBlockState(n).getCollisionShape(current,n),d))neighbors++;}
    if(neighbors>=2&&(current.getBlockState(p.below()).isSolid()||source(current.getBlockState(p.below())))){
     if(x==b.min().x()||x==b.max().x()||z==b.min().z()||z==b.max().z())return "Source regeneration may escape the declared boundary "+p;
     var goal=model.getBlockState(p);
     if(!goal.is(Blocks.WATER)||goal.getValue(LiquidBlock.LEVEL)!=0)return "Source regeneration would contradict original cell "+p;
     sources.add(p);changed=true;
    }
   }
  }while(changed);
  return null;
 }
}
