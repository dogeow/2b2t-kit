package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.core.*;
import net.minecraft.world.level.block.*;
import java.util.ArrayList;
/** Return water to an unchanged original completed source chamber; no new source is created. */
final class ProjectedSourceReturnGuard {
 private final ProjectedSourceColumnGuard column;
 private final BlockPos low,high,target,support;
 private final Direction face;
 static boolean requested(JsonObject r){
  if(!r.has("projected_source_return"))return false;var v=r.get("projected_source_return");
  if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Source return flag must be boolean");return v.getAsBoolean();
 }
 static boolean centre(BlockPos lo,BlockPos hi,BlockPos p,int rows){
  var b=new ProjectedSourceColumnPolicy.Bounds(lo.getX(),lo.getY(),lo.getZ(),hi.getX(),hi.getY(),hi.getZ());
  return b.validRows(rows)&&p.getX()==lo.getX()+1&&p.getZ()==lo.getZ()&&p.getY()>=lo.getY()&&p.getY()<=hi.getY();
 }
 ProjectedSourceReturnGuard(Minecraft c,JsonObject r,BlockPos p){
  var b=r.getAsJsonObject("source_column_bounds");if(b==null)throw new IllegalArgumentException("Completed source bounds required");
  low=ProjectedSourceColumnGuard.point(b.get("min"));high=ProjectedSourceColumnGuard.point(b.get("max"));target=p.immutable();
  if(!centre(low,high,target,ProjectedSourceColumnGuard.profileRows(r)))throw new IllegalArgumentException("Only a completed original middle source can receive water");
  support=ProjectedSourceColumnGuard.point(r.get("support"));face=Direction.valueOf(ProjectionLoadPolicy.text(r,"face",16).toUpperCase(java.util.Locale.ROOT));
  if(!support.relative(face).equals(target))throw new IllegalArgumentException("Exact original adjacent inert support required");
  column=new ProjectedSourceColumnGuard(c,r,target);
 }
 void require(Minecraft c){
  column.requireCompleted(c);var model=LitematicaAccess.schematicWorld();var top=new ArrayList<Integer>();var wanted=new ArrayList<Integer>();
  for(int x=low.getX();x<=high.getX();x++){
   var p=new BlockPos(x,high.getY()+1,low.getZ());top.add(level(c.level.getBlockState(p)));wanted.add(level(model.getBlockState(p)));
  }
  if(!SourceColumnSupplyPolicy.completedTop(wanted,top))throw new IllegalStateException("Original completed overflow must remain exact");
  var anchor=c.level.getBlockState(support);
  if(!(anchor.is(Blocks.GLASS)||anchor.is(Blocks.COBBLESTONE))||!anchor.equals(model.getBlockState(support))||!anchor.getFluidState().isEmpty()||c.level.getBlockEntity(support)!=null||!anchor.isCollisionShapeFullBlock(c.level,support))throw new IllegalStateException("Return probe support must be original dry inert glass or cobblestone");
 }
 void probe(Minecraft c,net.minecraft.world.phys.BlockHitResult hit){
  require(c);
  if(!c.player.getMainHandItem().is(net.minecraft.world.item.Items.BUCKET)||c.player.getMainHandItem().getCount()!=1
      ||!BlockFaceTarget.matches(hit,support,face)||c.player.getEyePosition().distanceTo(hit.getLocation())>c.player.blockInteractionRange())
      throw new IllegalStateException("Return probe needs the transformed empty bucket and original inert face");
  var fresh=c.level.clip(new net.minecraft.world.level.ClipContext(c.player.getEyePosition(),BlockFaceTarget.inside(hit),net.minecraft.world.level.ClipContext.Block.OUTLINE,net.minecraft.world.level.ClipContext.Fluid.NONE,c.player));
  if(!BlockFaceTarget.matches(fresh,support,face))throw new IllegalStateException("Return probe face became occluded");
  if(c.gameMode.useItemOn(c.player,net.minecraft.world.InteractionHand.MAIN_HAND,fresh).consumesAction())throw new IllegalStateException("Inert source-return support unexpectedly consumed an interaction; inspect original result");
 }
 private static int level(net.minecraft.world.level.block.state.BlockState s){return s.is(Blocks.WATER)?s.getValue(LiquidBlock.LEVEL):-1;}
 static boolean shieldedWorkspace(Minecraft c,JsonObject r){
  try{
   if(c==null||c.player==null||c.level==null||!"bucket_place".equals(ProjectionLoadPolicy.text(r,"op",64))||!requested(r))return false;
   var g=new ProjectedSourceReturnGuard(c,r,ProjectedSourceColumnGuard.point(r.get("pos")));g.require(c);return g.column.shieldedActor(c);
  }catch(RuntimeException unproved){return false;}
 }
}
