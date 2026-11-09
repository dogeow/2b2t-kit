package dev.twob2tkit.runtime.engine;
import com.google.gson.*;
import java.nio.file.*;
import java.util.concurrent.CompletableFuture;
import net.minecraft.client.multiplayer.ClientLevel;import net.minecraft.client.Minecraft;import net.minecraft.world.entity.monster.zombie.ZombifiedPiglin;import net.minecraft.world.entity.player.Player;import net.minecraft.world.entity.projectile.Projectile;import net.minecraft.world.item.Items;import net.minecraft.world.level.GameType;
/** Explicit, bounded stationary-farm intent. All attacks remain Meteor actions. */
final class MeteorFarmAssist {
 private final FarmBowModules bow=new FarmBowModules();private final BorerCargoModules criticals=new BorerCargoModules();private dev.twob2tkit.runtime.api.BorerHost leasedHost;private String owner="",blocked="";private boolean armed,drawing;private int previous=-1,peak,spent;private long nextWrite,nextShot,drawStarted;private String reason="idle";
 private record Frame(JsonObject intent, JsonObject status, long observedAt) {}
 private ClientLevel observedLevel;
 private CompletableFuture<Frame> reading;
 private Frame frame;
 private long nextRead;

 private Frame readFrame(Path root) {
  long observedAt = System.currentTimeMillis();
  Path file = root.resolve("meteor-farm-intent.json");
  try {
   if (!Files.isRegularFile(file) || Files.size(file) > 12000) return null;
   var intent = JsonParser.parseString(Files.readString(file)).getAsJsonObject();
   if (number(intent,"expires_at") < observedAt) return null;
   Path status = root.resolve("status.json");
   if (Files.size(status) > 2_000_000) return null;
   return new Frame(intent,JsonParser.parseString(Files.readString(status)).getAsJsonObject(),observedAt);
  } catch (NoSuchFileException absent) {
   return null;
  } catch (Exception failure) {
   throw new IllegalStateException("Invalid farm intent or state",failure);
  }
 }

 boolean active(){return armed;}
 String status(){return "定点农场 · "+(drawing?"Meteor引怪":"Meteor击杀")+" · 已用箭 "+spent+"/4";}
 void close(Minecraft c,boolean restoreSlot){bow.close();criticals.close();if(leasedHost!=null){leasedHost.releaseMeleeTarget();leasedHost=null;}if(restoreSlot&&previous>=0&&c.player!=null&&c.player.getMainHandItem().is(Items.BOW))c.player.getInventory().setSelectedSlot(previous);previous=-1;drawing=false;peak=0;armed=false;}
 private void save(Path p,JsonObject j)throws Exception{Path t=p.resolveSibling(p.getFileName()+".tmp");Files.writeString(t,j.toString());Files.move(t,p,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}
 private long number(JsonObject j,String k){return j.get(k).getAsLong();}
 void tick(Minecraft c,dev.twob2tkit.runtime.api.BorerHost host,Runnable pauseDefense){
  if(c.player==null||c.level==null||c.getCurrentServer()==null||!"simpcraft.com".equals(c.getCurrentServer().ip)){
   close(c,false);observedLevel=null;reading=null;frame=null;nextRead=0;return;
  }
  if(observedLevel!=c.level){
   close(c,false);observedLevel=c.level;reading=null;frame=null;nextRead=0;
  }
  Path root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");
  long now=System.currentTimeMillis();
  String id=owner;
  try{
   if(reading!=null&&reading.isDone()){
    var done=reading;reading=null;frame=null;frame=done.join();
   }
   if(reading==null&&now>=nextRead){
    nextRead=now+100;reading=CompletableFuture.supplyAsync(()->readFrame(root));
   }
   if(frame==null||now-frame.observedAt()>250){
    if(armed||drawing){reason="farm_intent_unavailable";close(c,false);publish(root,now,id,true);}
    return;
   }
   JsonObject r=frame.intent(),s=frame.status();
   if(!r.has("schema")||r.get("schema").getAsInt()!=1||!r.has("mode")||!r.get("mode").getAsString().equals("stationary_meteor_xp"))throw new IllegalArgumentException("Explicit farm intent required");
   id=r.get("id").getAsString();
   if(!id.matches("[a-zA-Z0-9_-]{1,80}")||id.equals(blocked)){close(c,false);return;}
   boolean sameRevision=number(s,"control_revision")==number(r,"expected_revision");
   boolean physicalMovement=BorerAreaRunner.physicalMovementHeld(c,c.options.keyUp,c.options.keyDown,
    c.options.keyLeft,c.options.keyRight,c.options.keyJump,c.options.keyShift);
   boolean sameInput=!physicalMovement&&number(s.getAsJsonObject("game_interaction"),"interaction_serial")==number(r,"input_serial");boolean ready=FarmStationPolicy.scope(c.getCurrentServer().ip,r.get("server").getAsString(),c.level.dimension().identifier().toString().equals("minecraft:the_nether"),c.gameMode.getPlayerMode()==GameType.SURVIVAL,now,number(r,"expires_at"),now-number(s,"time"),s.get("world_session").equals(r.get("world_session")),sameInput,sameRevision,c.player.getHealth(),c.player.getFoodData().getFoodLevel(),s.get("manual_movement").getAsBoolean(),c.gui.screen()!=null,s.getAsJsonObject("safety_hold").get("active").getAsBoolean(),s.get("auto_log").getAsBoolean());
   if(!sameInput||s.get("manual_movement").getAsBoolean())blocked=id;
   if(!ready){
    if(drawing){blocked=id;nextShot=now+30000;}
    reason="farm_scope_or_station_not_ready";close(c,sameInput);publish(root,now,id);return;
   }
   var a=r.getAsJsonArray("station");double sx=a.get(0).getAsDouble(),sy=a.get(1).getAsDouble(),sz=a.get(2).getAsDouble();var eye=c.player.getEyePosition();
   boolean incoming=!c.level.getEntitiesOfClass(Projectile.class,c.player.getBoundingBox().inflate(12),projectile->{
    var velocity=projectile.getDeltaMovement();
    return projectile.isAlive()&&FarmStationPolicy.incoming(projectile.getOwner()==c.player,
     velocity.x,velocity.y,velocity.z,eye.x-projectile.getX(),eye.y-projectile.getY(),eye.z-projectile.getZ());
   }).isEmpty();
   ready&=!incoming&&c.player.position().distanceToSqr(new net.minecraft.world.phys.Vec3(sx,sy,sz))<64*64&&!c.player.isOnFire()&&!c.player.isUnderWater();boolean stationed=FarmStationPolicy.station(c.player.getX(),c.player.getY(),c.player.getZ(),sx,sy,sz,c.player.onGround(),s.get("flight").getAsBoolean());boolean maintenance=r.has("maintenance_until")&&number(r,"maintenance_until")>=now&&number(r,"maintenance_until")-now<=60000;ready&=stationed||maintenance;
   if(!ready){if(drawing){blocked=id;nextShot=now+30000;}reason=incoming?"incoming_projectile_normal_defense_retained":"farm_scope_or_station_not_ready";close(c,sameInput);publish(root,now,id);return;}
   if(!id.equals(owner)){
    close(c,true);
    Path proof=root.resolve("meteor-farm-receipts");
    Files.createDirectories(proof);
    Path ledger=proof.resolve(id+".json");
    spent=Files.exists(ledger)?JsonParser.parseString(Files.readString(ledger)).getAsJsonObject().get("shots_started").getAsInt():0;
    owner=id;nextShot=now+3000;
   }
   if(!armed){
    pauseDefense.run();
    var piglin=net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getValue(
     net.minecraft.resources.Identifier.parse("minecraft:zombified_piglin"));
    if(!host.prepareMeleeTarget(piglin))
     throw new IllegalStateException("Farm target lease refused");
    leasedHost=host;armed=true;
   }
   if(stationed){criticals.pause(FarmBowModules.module("Criticals"));if(!maintenance&&!drawing&&!c.player.isUsingItem()&&!c.player.getMainHandItem().is(net.minecraft.tags.ItemTags.SWORDS)){for(int i=0;i<9;i++)if(c.player.getInventory().getItem(i).is(Items.NETHERITE_SWORD)){c.player.getInventory().setSelectedSlot(i);break;}}}
   if(drawing){
    if(!stationed||!bow.ready()||!c.player.getMainHandItem().is(Items.BOW)){reason="bow_scope_changed_preserve_unknown_shot";close(c,sameInput);nextShot=now+30000;publish(root,now,id);return;}
    if(c.player.isUsingItem())peak=Math.max(peak,c.player.getTicksUsingItem());if(FarmStationPolicy.released(peak,c.player.isUsingItem(),c.player.getTicksUsingItem())){reason="one_meteor_bow_release_observed";bow.close();if(previous>=0&&c.player.getMainHandItem().is(Items.BOW))c.player.getInventory().setSelectedSlot(previous);previous=-1;drawing=false;peak=0;nextShot=now+25000;}
    else if(now-drawStarted>6000){reason="bow_release_unconfirmed_no_replay";close(c,true);blocked=id;}
   }else if(stationed&&!maintenance&&now>=nextShot){
    nextShot=now+3000;ZombifiedPiglin target=null;double best=49;boolean nearby=false;for(var p:c.level.getEntitiesOfClass(ZombifiedPiglin.class,c.player.getBoundingBox().inflate(48),e->e.isAlive()&&!e.hasCustomName())){double d=p.distanceTo(c.player);if(d<5)nearby=true;if(d>=8&&d<best&&c.player.hasLineOfSight(p)){target=p;best=d;}}
    int arrows=0,bowSlot=-1;for(int i=0;i<36;i++){var st=c.player.getInventory().getItem(i);if(st.is(Items.ARROW))arrows+=st.getCount();if(i<9&&st.is(Items.BOW)&&st.getMaxDamage()-st.getDamageValue()>20)bowSlot=i;}boolean other=c.level.players().stream().anyMatch(p->p!=c.player&&p.distanceTo(c.player)<64);
    if(FarmStationPolicy.lure(stationed,nearby,other,target!=null,best,arrows,spent,r.get("arrow_budget").getAsInt())&&bowSlot>=0&&!c.player.isUsingItem()){
     var j=new JsonObject();j.addProperty("id",id);j.addProperty("shots_started",spent+1);j.addProperty("intent_time",now);j.addProperty("target_uuid",target.getUUID().toString());save(root.resolve("meteor-farm-receipts").resolve(id+".json"),j);spent++;previous=c.player.getInventory().getSelectedSlot();bow.begin(target.getType());c.player.getInventory().setSelectedSlot(bowSlot);drawing=true;peak=0;drawStarted=now;reason="Meteor_BowAimbot_and_BowSpam_single_lure";
    }else reason=nearby?"Meteor_KillAura_station":"waiting_for_safe_visible_lure_target";
   }else reason=maintenance&&!stationed?"owned_station_maintenance":"Meteor_KillAura_station";
   publish(root,now,id);
  }catch(Exception failure){reason="farm_helper_refused_"+failure.getClass().getSimpleName();close(c,true);try{publish(root,now,id,true);}catch(Exception ignored){}}
 }
 private void publish(Path root,long now,String id)throws Exception{publish(root,now,id,false);}
 private void publish(Path root,long now,String id,boolean force)throws Exception{if(!force&&now<nextWrite)return;nextWrite=now+500;var j=new JsonObject();j.addProperty("time",now);j.addProperty("id",id);j.addProperty("active",armed);j.addProperty("reason",reason);j.addProperty("bow_cycle",drawing);j.addProperty("draw_peak_ticks",peak);j.addProperty("shots_started",spent);j.addProperty("melee_executor","Meteor KillAura");j.addProperty("ranged_executor","Meteor BowAimbot + BowSpam");j.addProperty("autolog_unchanged",true);save(root.resolve("meteor-farm-state.json"),j);}
}
