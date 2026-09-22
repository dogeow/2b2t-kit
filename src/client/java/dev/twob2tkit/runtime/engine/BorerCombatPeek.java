package dev.twob2tkit.runtime.engine;
import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.*;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.*;
import dev.twob2tkit.runtime.api.RotationAim;

/** Bounded normal flight to see an already-engaged, occluded enemy from outside blast range. */
final class BorerCombatPeek {
 private final DefaultTunnelBorerEngine engine;
 private final BorerAreaFlightSession flight=new BorerAreaFlightSession();
 private List<BlockPos> route=List.of();private LivingEntity target;private int index,started,lastMove,nextPlan;
 private Vec3 previous,origin;private boolean active;private RotationAim.Look look;
 BorerCombatPeek(DefaultTunnelBorerEngine engine){this.engine=engine;}
 LivingEntity target(){return target;}
 boolean active(){return active;}
 boolean tick(Minecraft c,LivingEntity enemy){
  var p=c.player;int tick=p.tickCount;
  if(c.screen!=null||p.getHealth()<18||c.level.getEntity(enemy.getId())!=enemy||!enemy.isAlive()){close(c);return false;}
  if(active&&(enemy!=target||tick-started>400||tick-lastMove>40)){close(c);nextPlan=tick+200;return false;}
  if(!active){
   if(tick<nextPlan)return false;nextPlan=tick+200;target=enemy;origin=p.position();
   var base=p.blockPosition();BlockPos start=null;double distance=Double.POSITIVE_INFINITY;
   for(var q:BlockPos.betweenClosed(base.offset(-1,0,-1),base.offset(1,1,1))){
    var center=feet(q);double d=center.distanceToSqr(origin);
    if(d<distance&&clear(c,q)&&c.level.noCollision(p,p.getBoundingBox().expandTowards(center.subtract(origin)))){start=q.immutable();distance=d;}
   }
   if(start==null)return false;
   var cache=new HashMap<BlockPos,Boolean>();
   route=CombatPeekPath.find(new CombatPeekPath.World(){
    public boolean clear(BlockPos q){return cache.computeIfAbsent(q,k->BorerCombatPeek.this.clear(c,k));}
    public boolean edge(BlockPos a,BlockPos b){return c.level.noCollision(p,body(feet(a)).expandTowards(feet(b).subtract(feet(a))));}
    public boolean visible(BlockPos q){var eye=feet(q).add(0,p.getEyeHeight(),0);return c.level.clip(new ClipContext(eye,enemy.getEyePosition(),ClipContext.Block.COLLIDER,ClipContext.Fluid.NONE,p)).getType()==HitResult.Type.MISS;}
   },start,12,3000);
   if(route.isEmpty())return false;
   try{flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/combat-peek-flight.bak"));if(flight.acquire(p)!=null)return false;}
   catch(IllegalStateException unavailable){return false;}
   active=true;index=0;started=lastMove=tick;previous=p.position();
   engine.fileLog(c,"guard-peek-start uuid="+enemy.getUUID()+" nodes="+route.size());
  }
  if(p.position().distanceToSqr(previous)>.01){lastMove=tick;previous=p.position();}
  if(index>=route.size()){close(c);return false;}
  if(p.position().distanceToSqr(feet(route.get(index)))<.025){index++;if(index>=route.size()){close(c);return false;}}
  var destination=feet(route.get(index));var input=BorerFlyPath.input(p.position(),destination,p.getYRot());
  if(!clear(c,route.get(index))||!c.level.noCollision(p,p.getBoundingBox().expandTowards(input.delta()))){close(c);nextPlan=tick+200;return false;}
  engine.pauseGuardMovement(c);flight.speed(input.speed());look=new RotationAim.Look(input.yaw(),0);RotationAim.apply(p,look);
  p.stopUsingItem();c.options.keyUse.setDown(false);c.options.keyUp.setDown(input.forward());c.options.keyJump.setDown(input.up());c.options.keyShift.setDown(input.down());
  engine.status="绕开遮挡，重新确认敌对生物位置";return true;
 }
 boolean acquired(Minecraft c,LivingEntity enemy){return active&&target==enemy&&c.player.position().distanceToSqr(origin)>=1&&c.player.hasLineOfSight(enemy)&&safeDistance(c,c.player.position());}
 void reapply(Minecraft c){if(active&&look!=null&&c.screen==null)RotationAim.apply(c.player,look);}
 void close(Minecraft c){if(!active)return;engine.pauseGuardMovement(c);flight.closeKeepingFlight();active=false;look=null;route=List.of();}
 private boolean clear(Minecraft c,BlockPos p){
  for(int i=0;i<2;i++){var q=p.above(i);if(!c.level.hasChunkAt(q))return false;var s=c.level.getBlockState(q);if(!s.getFluidState().isEmpty()||s.is(Blocks.FIRE)||s.is(Blocks.SOUL_FIRE)||s.is(Blocks.COBWEB)||s.is(Blocks.POWDER_SNOW))return false;}
  return safeDistance(c,feet(p))&&c.level.noCollision(c.player,body(feet(p)));
 }
 private boolean safeDistance(Minecraft c,Vec3 feet){
  for(var e:c.level.getEntities(c.player,body(feet).inflate(14))){
   if(!(e instanceof Enemy)||!e.isAlive())continue;
   double radius=e instanceof Creeper creeper?creeper.isPowered()?13:7:4;
   if(feet.distanceToSqr(e.position())<radius*radius)return false;
  }return true;
 }
 private static Vec3 feet(BlockPos p){return BorerFlyPath.waypoint(p);}
 private static AABB body(Vec3 p){return new AABB(p.x-.31,p.y+.01,p.z-.31,p.x+.31,p.y+1.8,p.z+.31);}
}
