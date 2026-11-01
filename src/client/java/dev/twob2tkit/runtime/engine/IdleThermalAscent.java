package dev.twob2tkit.runtime.engine;
import com.google.gson.*;import java.nio.file.*;import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.damagesource.DamageTypes;import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
/** Native idle-only heat recovery: normal Flight and Jump, no teleport and no health-lock acknowledgement. */
final class IdleThermalAscent {
 private boolean active,latched,jumpOwned;private Double originalSpeed;private Object world,connection;private double startX,startZ,target;
 private long deadline,lastRead,firstIdle;private String idleWorld="",published="";private JsonObject observed;
 boolean active(){return active;}
 private Path root(Minecraft c){return c.gameDirectory.toPath().resolve("config/twob2tkit/automation");}
 private boolean manual(Minecraft c){
  if(!c.isWindowActive())return false;
  for(var key:new net.minecraft.client.KeyMapping[]{c.options.keyUp,c.options.keyDown,c.options.keyLeft,c.options.keyRight,c.options.keyJump,c.options.keyShift,c.options.keyAttack,c.options.keyUse}){
   var k=KeyMappingHelper.getBoundKeyOf(key);
   if(k.getType()==InputConstants.Type.KEYSYM&&InputConstants.isKeyDown(c.getWindow(),k.getValue()))return true;
   if(k.getType()==InputConstants.Type.MOUSE&&org.lwjgl.glfw.GLFW.glfwGetMouseButton(c.getWindow().handle(),k.getValue())==org.lwjgl.glfw.GLFW.GLFW_PRESS)return true;
  }return false;
 }
 private boolean thermal(Minecraft c){
  var p=c.player;var d=p.getLastDamageSource();
  return p.isOnFire()||p.hurtTime>0&&d!=null&&(d.is(DamageTypes.HOT_FLOOR)||d.is(DamageTypes.CAMPFIRE)||d.is(DamageTypes.IN_FIRE)||d.is(DamageTypes.ON_FIRE));
 }
 private boolean idle(Minecraft c,long now){
  if(now-lastRead>=150){
   lastRead=now;observed=null;
   try{
    Path p=root(c).resolve("status.json");if(Files.size(p)>2000000)return false;
    var s=JsonParser.parseString(Files.readString(p)).getAsJsonObject();boolean pending=false;Path req=root(c).resolve("request.json");
    if(Files.isRegularFile(req)&&Files.size(req)<2000000){
     var r=JsonParser.parseString(Files.readString(req)).getAsJsonObject();
     pending=IdleThermalPolicy.pendingMutation(r,s,now);
    }
    String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
    if(IdleThermalPolicy.idle(s,now,server,c.level.dimension().identifier().toString(),pending))observed=s;
   }catch(Exception unavailable){return false;}
  }
  if(observed==null||now-observed.get("time").getAsLong()>1500)return false;
  try{
   Path req=root(c).resolve("request.json");
   if(Files.isRegularFile(req)&&Files.size(req)<2000000){
    var r=JsonParser.parseString(Files.readString(req)).getAsJsonObject();
    if(IdleThermalPolicy.pendingMutation(r,observed,now))return false;
   }
  }catch(Exception unknownPending){return false;}
  return true;
 }
 private boolean clear(Minecraft c,double delta){
  var box=c.player.getBoundingBox().expandTowards(0,delta,0);
  if(!c.level.noCollision(c.player,box))return false;
  for(var p:BlockPos.betweenClosed(BlockPos.containing(box.minX,box.minY,box.minZ),BlockPos.containing(box.maxX-1e-7,box.maxY-1e-7,box.maxZ-1e-7))){
   if(!LoadedServerChunkEvidence.isServerChunk(c.level,c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false)))return false;
   if(c.level.getFluidState(p).is(net.minecraft.tags.FluidTags.LAVA))return false;
  }return true;
 }
 boolean tick(Minecraft c){
  long now=System.currentTimeMillis();
  if(c.player==null||c.level==null||c.getConnection()==null||c.player.isDeadOrDying()||c.player.getHealth()<14||c.player.isInLava()){
   cancel(c,"critical_or_context",true);return false;
  }
  if(c.gui.screen()!=null||manual(c)){cancel(c,"manual_or_interface",false);latched=false;return false;}
  if(!thermal(c))latched=false;
  if(!idle(c,now)){cancel(c,"active_task_or_stale_context",false);firstIdle=0;return false;}
  String session=IdleThermalPolicy.text(observed,"world_session");
  if(!session.equals(idleWorld)){idleWorld=session;firstIdle=now;}
  if(firstIdle==0)firstIdle=now;
  if(active){
   if(world!=c.level||connection!=c.getConnection()||Math.hypot(c.player.getX()-startX,c.player.getZ()-startZ)>1){cancel(c,"context_or_position",false);return false;}
   if(!BorerFlight.isFlying(c.player)){cancel(c,"flight_changed",false);latched=true;return false;}
   if(c.player.getY()>=target-.1){cancel(c,"done",false);latched=true;return false;}
   if(now>=deadline||!clear(c,.35)){cancel(c,"ceiling_or_timeout",false);latched=true;return false;}
   Double speed=BorerFlight.readFlightSpeed();
   if(speed==null||Double.compare(speed,.025)!=0){cancel(c,"flight_setting_changed",false);latched=true;return false;}
   c.options.keyJump.setDown(true);jumpOwned=true;return true;
  }
  if(!thermal(c)){publish(c,"watching_idle");return false;}
  if(latched||now-firstIdle<200)return false;
  target=IdleThermalPolicy.rise(c.player.getY(),d->clear(c,d));
  if(!Double.isFinite(target)){publish(c,"no_clear_ascent");latched=true;return false;}
  if(!BorerFlight.ensureFlying(c.player,true)){publish(c,"flight_unavailable");latched=true;return false;}
  originalSpeed=BorerFlight.readFlightSpeed();
  if(originalSpeed==null||!Double.isFinite(originalSpeed)||!BorerFlight.writeFlightSpeed(.025)){originalSpeed=null;publish(c,"flight_speed_unavailable");latched=true;return false;}
  world=c.level;connection=c.getConnection();startX=c.player.getX();startZ=c.player.getZ();deadline=now+8000;active=true;
  c.options.keyJump.setDown(true);jumpOwned=true;publish(c,"rising");return true;
 }
 void cancel(Minecraft c,String reason,boolean yieldToEmergency){
  if(jumpOwned&&!yieldToEmergency&&c.player!=null&&!physicalJump(c))c.options.keyJump.setDown(false);
  jumpOwned=false;
  if(originalSpeed!=null){
   Double current=BorerFlight.readFlightSpeed();
   if(!yieldToEmergency&&current!=null&&Double.compare(current,.025)==0)BorerFlight.writeFlightSpeed(originalSpeed);
   originalSpeed=null;
  }
  if(active){active=false;publish(c,reason);}
 }
 private boolean physicalJump(Minecraft c){var k=KeyMappingHelper.getBoundKeyOf(c.options.keyJump);return c.isWindowActive()&&k.getType()==InputConstants.Type.KEYSYM&&InputConstants.isKeyDown(c.getWindow(),k.getValue());}
 private void publish(Minecraft c,String phase){
  if(phase.equals(published))return;published=phase;
  try{
   var j=new JsonObject();j.addProperty("protocol",1);j.addProperty("runtime_version",EngineBuildVersion.VALUE);j.addProperty("time",System.currentTimeMillis());j.addProperty("phase",phase);j.addProperty("active",active);j.addProperty("target_y",target);j.addProperty("safety_lock_cleared",false);if(c.player!=null){j.addProperty("y",c.player.getY());j.addProperty("health",c.player.getHealth());}
   Path p=root(c).resolve("idle-thermal-ascent-state.json"),tmp=p.resolveSibling(p.getFileName()+".tmp");Files.writeString(tmp,j.toString());Files.move(tmp,p,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
  }catch(Exception ignored){}
 }
}
