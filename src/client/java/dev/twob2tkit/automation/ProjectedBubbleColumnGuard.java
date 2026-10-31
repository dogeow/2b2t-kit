package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.*;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Half;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.AABB;
import java.util.*;
/** Exact seven-cell upward bubble lift and its six-west/one-north outlet. */
final class ProjectedBubbleColumnGuard {
 private final BlockPos low,high,target,cap;
 private final String placement;
 private final Set<BlockPos> fluidCells=new HashSet<>();
 private final Map<BlockPos,String> pins=new HashMap<>();
 static boolean requested(JsonObject r){
  if(!r.has("projected_bubble_column"))return false;var v=r.get("projected_bubble_column");
  if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Bubble column flag must be boolean");return v.getAsBoolean();
 }
 static boolean upward(BlockState s){return s.is(Blocks.BUBBLE_COLUMN)&&!s.getValue(BubbleColumnBlock.DRAG_DOWN);}
 static int stageState(BlockState s){return s.isAir()?-1:upward(s)?1:s.is(Blocks.WATER)&&s.getValue(LiquidBlock.LEVEL)==0?0:-2;}
 static boolean shape(BlockPos lo,BlockPos hi,BlockPos target){return hi.equals(lo.above(6))&&target.getX()==lo.getX()&&target.getZ()==lo.getZ()&&target.getY()>=lo.getY()&&target.getY()<=hi.getY();}
 ProjectedBubbleColumnGuard(JsonObject r,BlockPos target){
  this.target=target.immutable();var b=r.getAsJsonObject("bubble_bounds");if(b==null)throw new IllegalArgumentException("Exact bubble bounds required");
  low=ProjectedSourceColumnGuard.point(b.get("min"));high=ProjectedSourceColumnGuard.point(b.get("max"));
  if(!shape(low,high,target))throw new IllegalArgumentException("Only a seven-cell one-wide upward column is supported");
  cap=high.above();if(!cap.equals(ProjectedSourceColumnGuard.point(r.get("bubble_service_cap"))))throw new IllegalArgumentException("Exact original service cap required");
  placement=ProjectionLoadPolicy.text(r,"placement_key",8192);if(placement.isBlank())throw new IllegalArgumentException("Locked bubble projection required");
  for(int y=0;y<7;y++)fluidCells.add(low.above(y));for(int i=1;i<=7;i++)fluidCells.add(high.offset(ProjectedBubblePolicy.outletDx(i),0,ProjectedBubblePolicy.outletDz(i)));
  var boundaries=new HashSet<BlockPos>();for(var p:fluidCells)for(var d:Direction.values()){var q=p.relative(d);if(!fluidCells.contains(q))boundaries.add(q);}
  if(!r.has("bubble_boundary_pins")||!r.get("bubble_boundary_pins").isJsonArray())throw new IllegalArgumentException("All bubble boundary pins required");
  for(var raw:r.getAsJsonArray("bubble_boundary_pins")){
   var row=raw.getAsJsonObject();var p=ProjectedSourceColumnGuard.point(row.get("pos"));String expected=ProjectionLoadPolicy.text(row,"expected_state",512);
   if(!boundaries.contains(p)||expected.isBlank()||pins.putIfAbsent(p,expected)!=null)throw new IllegalArgumentException("Foreign or duplicate bubble pin");
  }
  if(!pins.keySet().equals(boundaries))throw new IllegalArgumentException("Bubble pins must cover every boundary");
 }
 private static void loaded(Minecraft c,BlockPos p){
  if(!c.level.getWorldBorder().isWithinBounds(p)||c.level.isOutsideBuildHeight(p)||!LoadedServerChunkEvidence.isServerChunk(c.level,c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false)))throw new IllegalStateException("Current loaded bubble geometry required");
 }
 static boolean barrier(BlockState s,net.minecraft.world.level.BlockGetter world,BlockPos p){
  if(!s.getFluidState().isEmpty())return false;
  if(s.is(Blocks.GLASS)||s.is(Blocks.COBBLESTONE))return s.isCollisionShapeFullBlock(world,p);
  boolean partial=s.is(Blocks.GLASS_PANE)||s.is(Blocks.SPRUCE_TRAPDOOR)&&s.getValue(TrapDoorBlock.HALF)==Half.TOP&&!s.getValue(TrapDoorBlock.OPEN)&&!s.getValue(TrapDoorBlock.POWERED);
  return partial&&s.getBlock() instanceof LiquidBlockContainer liquid&&!liquid.canPlaceLiquid(null,world,p,s,Fluids.FLOWING_WATER);
 }
 void require(Minecraft c,boolean before){
  var selection=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
  if(model==null||!selection.key().equals(placement)||!LitematicaAccess.loadingReason(selection).isEmpty()||c.level.environmentAttributes().getValue(net.minecraft.world.attribute.EnvironmentAttributes.WATER_EVAPORATES,target))throw new IllegalStateException("Bubble projection or environment changed");
  var states=new ArrayList<Integer>();
  for(int i=0;i<7;i++){
   var p=low.above(i);loaded(c,p);if(!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p)||!upward(model.getBlockState(p))||c.level.getBlockEntity(p)!=null)throw new IllegalStateException("All original upward bubble cells must remain visible and empty of containers");states.add(stageState(c.level.getBlockState(p)));
  }
  if(!ProjectedBubblePolicy.stage(states,target.getY()-low.getY(),before))throw new IllegalStateException("Only bottom-up dry target with preserved completed bubbles is allowed");
  for(int i=1;i<=7;i++){
   var p=high.offset(ProjectedBubblePolicy.outletDx(i),0,ProjectedBubblePolicy.outletDz(i));loaded(c,p);var goal=model.getBlockState(p);var actual=c.level.getBlockState(p);
   if(!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p)||c.level.getBlockEntity(p)!=null||!goal.is(Blocks.WATER)||goal.getValue(LiquidBlock.LEVEL)!=i)throw new IllegalStateException("Exact original six-west/one-north outlet required");
   boolean flowing=actual.is(Blocks.WATER)&&actual.getValue(LiquidBlock.LEVEL)>0&&actual.getValue(LiquidBlock.LEVEL)<=7;
   if(!actual.isAir()&&!(target.equals(high)&&!before&&flowing))throw new IllegalStateException("Outlet must stay dry until the top bubble is filled");
  }
  for(var entry:pins.entrySet()){
   var p=entry.getKey();loaded(c,p);var goal=model.getBlockState(p);var actual=c.level.getBlockState(p);
   if(!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p)||c.level.getBlockEntity(p)!=null||!goal.toString().equals(entry.getValue()))throw new IllegalStateException("Original bubble boundary changed");
   if(p.equals(cap)){if(!goal.is(Blocks.GLASS)||!actual.isAir())throw new IllegalStateException("Only the pinned original glass cap may be open");}
   else if(!actual.equals(goal)||(!p.equals(low.below())&&!goal.isAir()&&!barrier(actual,c.level,p)))throw new IllegalStateException("Bubble seal must keep its exact original dry state");
   if(p.equals(low.below())&&!actual.is(Blocks.SOUL_SAND))throw new IllegalStateException("Original soul sand must be installed first");
   if(goal.isAir()&&p.getY()!=high.getY()+1)throw new IllegalStateException("Only the original upward-open outlet roof may be air");
  }
  for(var p:fluidCells)if(!c.level.getEntities(c.player,new AABB(p),e->e instanceof LivingEntity&&e.isAlive()).isEmpty())throw new IllegalStateException("Bubble path contains a living entity");
 }
 boolean expectedPacket(BlockState s){return upward(s);}
 String expectedState(){return "Block{minecraft:bubble_column}[drag=false]";}
}
