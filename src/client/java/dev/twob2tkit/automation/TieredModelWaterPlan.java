package dev.twob2tkit.automation;
import java.util.*;
import java.util.function.Predicate;
import net.minecraft.core.*;
import net.minecraft.world.level.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.SlabType;
import net.minecraft.world.level.material.*;
/** Opt-in finite wet-volume proof. Unlimited lateral reach conservatively includes source regeneration. */
final class TieredModelWaterPlan {
 static boolean bounds(ProjectedWaterFlowPolicy.Bounds b,BlockPos source){return b!=null&&b.valid()&&b.min().y()==source.getY()-4&&b.max().y()==source.getY()+1&&(long)(b.max().x()-b.min().x()+1)*(b.max().z()-b.min().z()+1)*6<=8192;}
 static String rejection(BlockGetter current,BlockGetter model,ProjectedWaterFlowPolicy.Bounds b,BlockPos source,Predicate<BlockPos> occupied){
  if(!bounds(b,source)||source.getX()<=b.min().x()||source.getX()>=b.max().x()||source.getZ()<=b.min().z()||source.getZ()>=b.max().z())return "Tiered source requires an explicit six-layer envelope";
  var goal=model.getBlockState(source);if(!goal.is(Blocks.WATER)||goal.getValue(LiquidBlock.LEVEL)!=0)return "Original tiered source required";
  Set<BlockPos> wet=new HashSet<>(),barriers=new HashSet<>();ArrayDeque<BlockPos> queue=new ArrayDeque<>();queue.add(source);
  while(!queue.isEmpty()){
   var p=queue.removeFirst();if(wet.contains(p)||barriers.contains(p))continue;
   if(!b.contains(new ProjectedWaterFlowPolicy.Cell(p.getX(),p.getY(),p.getZ())))return "Tiered water could escape declared envelope";
   var actual=current.getBlockState(p);var expected=model.getBlockState(p);
   if(actual.is(Blocks.MAGMA_BLOCK)||actual.is(Blocks.SOUL_SAND))return "Tiered bubbles need their dedicated mode";
   if(!expected.is(Blocks.WATER)){
    if(!ModelWaterPlan.same(actual,expected)||!actual.getFluidState().isEmpty()||ModelWaterPlan.holds(current,p,Fluids.FLOWING_WATER))return "Tiered dry boundary missing or permeable "+p;
    barriers.add(p);continue;
   }
   if(current.getBlockEntity(p)!=null||!(actual.isAir()||actual.is(Blocks.WATER))||occupied.test(p))return "Tiered wet cell protected, changed or occupied "+p;
   wet.add(p);if(wet.size()>8192)return "Tiered volume exceeded";queue.add(p.below());for(var d:Direction.Plane.HORIZONTAL)queue.add(p.relative(d));
  }
  // A model barrier must also survive the conservative possibility of adjacent regenerated sources.
  for(var p:barriers){var s=current.getBlockState(p);if(!(s.getBlock()instanceof LiquidBlockContainer container)||!container.canPlaceLiquid(null,current,p,s,Fluids.WATER))continue;
   int adjacent=0;for(var d:Direction.Plane.HORIZONTAL)if(wet.contains(p.relative(d))||ModelWaterPlan.source(current.getBlockState(p.relative(d))))adjacent++;
   if(adjacent>=2&&(current.getBlockState(p.below()).isSolid()||wet.contains(p.below())||ModelWaterPlan.source(current.getBlockState(p.below()))))return "Tiered regeneration could waterlog a dry boundary "+p;
  }
  return null;
 }
}
