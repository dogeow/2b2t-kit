package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.builder.LitematicaAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.monster.EnderMan;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.projectile.Projectile;
/** Water removal only: an explicit extra source or the exact original waterlogging bit. */
final class ProjectedFlowCorrectionGuard {
 private final BlockPos target;private final String placement;
 static boolean requested(JsonObject r){
  if(!r.has("projected_flow_source_drain"))return false;var v=r.get("projected_flow_source_drain");
  if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Flow source drain flag must be boolean");return v.getAsBoolean();
 }
 static boolean originalFlow(BlockState goal){return goal.is(Blocks.WATER)&&goal.getValue(LiquidBlock.LEVEL)>0&&goal.getValue(LiquidBlock.LEVEL)<=7;}
 static boolean currentFlowOrAir(BlockState actual){return actual.isAir()||actual.is(Blocks.WATER);}
 ProjectedFlowCorrectionGuard(JsonObject r,BlockPos target){this.target=target.immutable();placement=ProjectionLoadPolicy.text(r,"placement_key",8192);}
 void require(Minecraft c,boolean before){
  var selected=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
  if(model==null||!selected.key().equals(placement)||!selected.contains(target)||!LitematicaAccess.inVisibleLayer(target)||!LitematicaAccess.loadingReason(selected).isEmpty()||!originalFlow(model.getBlockState(target)))throw new IllegalStateException("Extra source drain needs an original ordinary flowing-water cell");
  var s=c.level.getBlockState(target);if(c.level.getBlockEntity(target)!=null||!currentFlowOrAir(s)||before&&(!s.is(Blocks.WATER)||!ModelWaterPlan.source(s)))throw new IllegalStateException("Extra source drain must remove one plain source without replacing a block");
  for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++)if(!ProjectedModelWaterGuard.loaded(c,target.offset(x,y,z)))throw new IllegalStateException("Water correction needs current server chunks");
 }
 boolean current(Minecraft c){try{require(c,false);return true;}catch(RuntimeException changed){return false;}}
 static boolean remoteCalmCreeper(boolean current,boolean ordinary,boolean visible,boolean igniting,boolean below,double playerDistanceSquared,double targetDistanceSquared){
  return current&&ordinary&&!visible&&!igniting&&below&&Double.isFinite(playerDistanceSquared)&&Double.isFinite(targetDistanceSquared)&&playerDistanceSquared>64&&targetDistanceSquared>49;
 }
 static boolean separatedThreat(String type,boolean current,boolean visible,double distanceSquared,double verticalGap){
  return current&&Double.isFinite(distanceSquared)&&Double.isFinite(verticalGap)&&(!visible&&verticalGap>=4&&java.util.Set.of("minecraft:skeleton","minecraft:stray","minecraft:bogged").contains(type)||java.util.Set.of("minecraft:zombie","minecraft:zombie_villager","minecraft:slime","minecraft:spider","minecraft:cave_spider").contains(type)&&Double.isFinite(distanceSquared)&&Double.isFinite(verticalGap)
   &&(visible?distanceSquared>=144:verticalGap>=4));
 }
 static boolean shieldedWorkspace(Minecraft c,JsonObject r){
  try{
   if(c.player==null||c.level==null||!"bucket_fill".equals(ProjectionLoadPolicy.text(r,"op",64)))return false;
   var target=ProjectedSourceColumnGuard.point(r.get("pos"));
   if(requested(r))new ProjectedFlowCorrectionGuard(r,target).require(c,false);
   else if(ProjectedWaterlogDrain.requested(r)){if(!new ProjectedWaterlogDrain(c,r,target,true).current(c))return false;}
   else return false;
   if(!ProjectedModelWaterGuard.loaded(c,target))return false;
   long now=System.currentTimeMillis(),hurt=KitClient.config().lastAttackTimeEpochMillis;
   if(hurt<0||hurt>now||hurt!=0&&now-hurt<5000)return false;
   var p=c.player;var body=p.getBoundingBox();
   if(!c.level.getEntities(p,body.inflate(24),e->e instanceof Projectile a&&e.isAlive()&&a.getOwner()!=p&&e.getDeltaMovement().lengthSqr()>.0001).isEmpty())return false;
   for(var e:c.level.getEntities(p,body.inflate(16),e->e instanceof Enemy&&e.isAlive())){
    if(e instanceof Creeper a&&remoteCalmCreeper(e.level()==c.level&&c.level.getEntity(e.getId())==e&&ProjectedModelWaterGuard.loaded(c,e.blockPosition()),!a.isPowered(),p.hasLineOfSight(e),a.isIgnited()||a.getSwellDir()>0||a.getSwelling(1)>0,e.getBoundingBox().maxY<=target.getY()-1,ProjectedSourceColumnGuard.boxDistanceSquared(body,e.getBoundingBox()),ProjectedSourceColumnGuard.boxDistanceSquared(new net.minecraft.world.phys.AABB(target),e.getBoundingBox())))continue;
    if(separatedThreat(BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString(),e.level()==c.level&&c.level.getEntity(e.getId())==e&&ProjectedModelWaterGuard.loaded(c,e.blockPosition()),p.hasLineOfSight(e),ProjectedSourceColumnGuard.boxDistanceSquared(body,e.getBoundingBox()),body.minY-e.getBoundingBox().maxY))continue;
    if(!ModelWaterThreatPolicy.permit(BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString(),e.level()==c.level&&c.level.getEntity(e.getId())==e&&ProjectedModelWaterGuard.loaded(c,e.blockPosition()),p.hasLineOfSight(e),ProjectedSourceColumnGuard.boxDistanceSquared(body,e.getBoundingBox()),e instanceof EnderMan a&&!a.isCreepy()))return false;
   }return true;
  }catch(RuntimeException unproved){return false;}
 }
}
