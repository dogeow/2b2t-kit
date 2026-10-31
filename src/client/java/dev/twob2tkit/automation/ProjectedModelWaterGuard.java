package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.*;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.ExperienceOrb;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.entity.monster.EnderMan;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;
/** Source repair only inside a loaded original planar network; no arbitrary water placement. */
final class ProjectedModelWaterGuard {
 private static final dev.twob2tkit.runtime.engine.BorerMiningConfirmation PREDICTIONS=new dev.twob2tkit.runtime.engine.BorerMiningConfirmation();
 final ProjectedWaterFlowPolicy.Bounds bounds;private final BlockPos target,support;private final String placement;
 static boolean requested(JsonObject r){
  if(!r.has("projected_model_water_source"))return false;var v=r.get("projected_model_water_source");
  if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Model source flag must be boolean");return v.getAsBoolean();
 }
 ProjectedModelWaterGuard(JsonObject r,BlockPos target){
  var box=r.getAsJsonObject("model_water_bounds");if(box==null)throw new IllegalArgumentException("Original water bounds required");
  var lo=ProjectedSourceColumnGuard.point(box.get("min"));var hi=ProjectedSourceColumnGuard.point(box.get("max"));
  bounds=new ProjectedWaterFlowPolicy.Bounds(new ProjectedWaterFlowPolicy.Cell(lo.getX(),lo.getY(),lo.getZ()),new ProjectedWaterFlowPolicy.Cell(hi.getX(),hi.getY(),hi.getZ()));
  long volume=(long)(hi.getX()-lo.getX()+1)*(hi.getY()-lo.getY()+1)*(hi.getZ()-lo.getZ()+1);
  if(!bounds.valid()||volume>4096||lo.getY()!=target.getY()-1||hi.getY()!=target.getY()+1||!bounds.contains(new ProjectedWaterFlowPolicy.Cell(target.getX(),target.getY(),target.getZ())))throw new IllegalArgumentException("Bounded planar source region required");
  this.target=target.immutable();support=ProjectedSourceColumnGuard.point(r.get("support"));placement=ProjectionLoadPolicy.text(r,"placement_key",8192);
 }
 static boolean loaded(Minecraft c,BlockPos p){return !c.level.isOutsideBuildHeight(p)&&c.level.getWorldBorder().isWithinBounds(p)&&LoadedServerChunkEvidence.isServerChunk(c.level,c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false));}
 void require(Minecraft c,boolean before){
  var selected=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
  if(!selected.key().equals(placement)||!selected.contains(target)||!selected.contains(support)||model==null||!LitematicaAccess.loadingReason(selected).isEmpty()||!LitematicaAccess.inVisibleLayer(target))throw new IllegalStateException("Original source selection changed");
  if(c.level.environmentAttributes().getValue(net.minecraft.world.attribute.EnvironmentAttributes.WATER_EVAPORATES,target))throw new IllegalStateException("Water evaporates here");
  var state=c.level.getBlockState(target);
  if(c.level.getBlockEntity(target)!=null||(before?!(state.isAir()||state.is(Blocks.WATER)&&!ModelWaterPlan.source(state)):!state.is(Blocks.WATER)||!ModelWaterPlan.source(state)))throw new IllegalStateException("Exact missing/flowing original source or confirmed source required");
  var anchor=c.level.getBlockState(support);
  if(!anchor.equals(model.getBlockState(support))||c.level.getBlockEntity(support)!=null||!anchor.getFluidState().isEmpty()||anchor.getBlock()instanceof LiquidBlockContainer||!anchor.isCollisionShapeFullBlock(c.level,support))throw new IllegalStateException("Original dry inert full support required");
  for(int x=bounds.min().x()-1;x<=bounds.max().x()+1;x++)for(int y=bounds.min().y();y<=bounds.max().y();y++)for(int z=bounds.min().z()-1;z<=bounds.max().z()+1;z++){
   var p=new BlockPos(x,y,z);if(!loaded(c,p))throw new IllegalStateException("Whole source region and regeneration halo need loaded server chunks");
   if((before||!p.equals(target))&&PREDICTIONS.pending(c.level,p))throw new IllegalStateException("Unsettled prediction in original water region");
   if(model.getBlockState(p).is(Blocks.WATER)&&(!selected.contains(p)||!LitematicaAccess.inVisibleLayer(p)))throw new IllegalStateException("Original fluid path outside locked visible selection");
  }
  String why=ModelWaterPlan.rejection(c.level,model,bounds,target,p->!c.level.getEntities(c.player,new AABB(p),e->e.isAlive()&&!(e instanceof ItemEntity)&&!(e instanceof ExperienceOrb)).isEmpty());
  if(why!=null)throw new IllegalStateException(why);
 }
 static boolean shieldedWorkspace(Minecraft c,JsonObject r){
  try{
   if(c.player==null||c.level==null||!"bucket_place".equals(ProjectionLoadPolicy.text(r,"op",64))||!requested(r))return false;
   var target=ProjectedSourceColumnGuard.point(r.get("pos"));var guard=new ProjectedModelWaterGuard(r,target);guard.require(c,!ModelWaterPlan.source(c.level.getBlockState(target)));
   long now=System.currentTimeMillis(),hurt=KitClient.config().lastAttackTimeEpochMillis;if(hurt<0||hurt>now||hurt!=0&&now-hurt<5000)return false;
   var p=c.player;var body=p.getBoundingBox();
   if(!c.level.getEntities(p,body.inflate(24),e->e instanceof Projectile a&&e.isAlive()&&a.getOwner()!=p&&e.getDeltaMovement().lengthSqr()>.0001).isEmpty())return false;
   for(var e:c.level.getEntities(p,body.inflate(16),e->e instanceof Enemy&&e.isAlive())){
    String type=BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();boolean current=e.level()==c.level&&c.level.getEntity(e.getId())==e&&loaded(c,e.blockPosition());
    if(!ModelWaterThreatPolicy.permit(type,current,p.hasLineOfSight(e),ProjectedSourceColumnGuard.boxDistanceSquared(body,e.getBoundingBox()),e instanceof EnderMan a&&!a.isCreepy()))return false;
   }return true;
  }catch(RuntimeException unproved){return false;}
 }
}
