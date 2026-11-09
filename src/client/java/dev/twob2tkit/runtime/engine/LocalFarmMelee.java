package dev.twob2tkit.runtime.engine;
import com.google.gson.*;import dev.twob2tkit.runtime.api.BorerHost;import net.minecraft.client.Minecraft;import net.minecraft.world.entity.LivingEntity;import net.minecraft.world.entity.monster.zombie.ZombifiedPiglin;import net.minecraft.tags.ItemTags;import net.minecraft.world.level.GameType;import java.nio.file.*;
/** Local-only captured-piglin trial. Uses ordinary client attacks, never server damage or spawned XP. */
final class LocalFarmMelee {
 private final LocalMeteorFarmLease meteorFarm=new LocalMeteorFarmLease();private boolean hostLease;private final BorerCargoModules conflicts=new BorerCargoModules();private Object criticals;private boolean armed,conflictsScoped,criticalsWasActive;private long swings,lastAttackMs,next;private int lastAttackTick;private String blockedRequest="";
 boolean active(){return armed&&conflictsScoped;}
 void close(BorerHost host){armed=false;meteorFarm.close();if(hostLease){host.releaseMeleeTarget();hostLease=false;}conflicts.close();conflictsScoped=false;criticals=null;}
 private Object module(String name)throws ReflectiveOperationException{var m=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");return m.getMethod("get",Class.class).invoke(m.getMethod("get").invoke(null),Class.forName("meteordevelopment.meteorclient.systems.modules."+name));}
 private boolean enabled(Object m)throws ReflectiveOperationException{return m!=null&&(Boolean)m.getClass().getMethod("isActive").invoke(m);}
 void tick(Minecraft c,BorerHost host,Runnable stopOtherCombat){
  long now=System.currentTimeMillis();if(now<next)return;next=now+100;String server=c.getCurrentServer()==null?"":c.getCurrentServer().ip;
  if(!"127.0.0.1:25579".equals(server)||c.player==null||c.level==null){close(host);return;}
  Path root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation"),request=root.resolve("local-farm-melee-request.json");
  try{
   if(!Files.isRegularFile(request)||Files.size(request)>8192){close(host);return;}
   var r=JsonParser.parseString(Files.readString(request)).getAsJsonObject();var s=JsonParser.parseString(Files.readString(root.resolve("status.json"))).getAsJsonObject();var lease=s.has("supervision_lease")?s.getAsJsonObject("supervision_lease"):null;long expiry=r.get("expires_at").getAsLong();
   boolean scoped=r.has("schema")&&r.get("schema").getAsInt()==1&&r.has("mode")&&r.get("mode").getAsString().equals("meteor_zombified_piglins")&&now-s.get("time").getAsLong()<2000&&expiry>=now&&expiry-now<=5000&&lease!=null&&"materials".equals(lease.get("kind").getAsString())&&r.get("task_session").getAsString().equals(lease.get("job_session").getAsString())&&r.get("lease_id").getAsString().equals(lease.get("id").getAsString())&&r.get("world_session").getAsString().equals(s.get("world_session").getAsString())&&r.get("expected_revision").getAsLong()==s.get("control_revision").getAsLong()&&s.get("guard_armed").getAsBoolean()&&s.get("guard_pve_only").getAsBoolean()&&!s.getAsJsonObject("safety_hold").get("active").getAsBoolean();
   var floor=c.level.getBlockState(new net.minecraft.core.BlockPos(0,240,0));boolean built=floor.getBlock() instanceof net.minecraft.world.level.block.SlabBlock&&floor.getValue(net.minecraft.world.level.block.SlabBlock.TYPE)==net.minecraft.world.level.block.state.properties.SlabType.BOTTOM;var roof=c.level.getBlockState(new net.minecraft.core.BlockPos(0,243,0));built=built&&(roof.isAir()||(roof.is(net.minecraft.world.level.block.Blocks.GLASS_PANE)&&roof.getFluidState().isEmpty()));
   LivingEntity target=null;int boats=0;boolean decoration=false;double best=Double.POSITIVE_INFINITY;
   for(var e:c.level.entitiesForRendering()){
    if(Math.abs(e.getX())>3||Math.abs(e.getZ())>3||e.getY()<240||e.getY()>247)continue;String type=net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();if(type.endsWith("_chest_boat"))boats++;
    if(e instanceof net.minecraft.world.entity.decoration.ArmorStand&&e.isAlive())decoration=true;
    if(e instanceof ZombifiedPiglin p&&LocalFarmMeleePolicy.capturedTarget(type,p.isAlive(),p.isPassenger(),p.hasCustomName())&&p.getY()>=242&&p.getY()<=244.5){double score=p.getHealth()*10+p.distanceToSqr(c.player);if(score<best){target=p;best=score;}}
   }
   boolean fire=c.player.getMainHandItem().getEnchantments().entrySet().stream().anyMatch(e->e.getIntValue()>0&&e.getKey().unwrapKey().map(k->k.identifier().toString().equals("minecraft:fire_aspect")).orElse(false));
   boolean ready=LocalFarmMeleePolicy.allowed(server,scoped,c.gameMode!=null&&c.gameMode.getPlayerMode()==GameType.SURVIVAL,c.player.getHealth(),c.player.getFoodData().getFoodLevel(),c.player.onGround(),s.get("flight").getAsBoolean(),s.get("manual_movement").getAsBoolean(),c.gui.screen()!=null,c.player.getMainHandItem().is(ItemTags.SWORDS),fire,LocalFarmMeleePolicy.playerAtStation(c.player.getX(),c.player.getY(),c.player.getZ()),built&&boats==40&&!decoration&&!c.player.isOnFire()&&!c.player.isUnderWater()&&c.level.getEntities(c.player,c.player.getBoundingBox().inflate(12),e->e instanceof net.minecraft.world.entity.projectile.Projectile&&e.isAlive()).isEmpty());
   if(ready&&LocalFarmMeleePolicy.offerAllowed(r.get("id").getAsString(),blockedRequest)){
    if(!conflictsScoped&&target!=null){stopOtherCombat.run();if(!host.prepareMeleeTarget(target.getType())){close(host);return;}hostLease=true;var aura=module("combat.KillAura");if(!meteorFarm.acquire(aura,target.getType())){blockedRequest=r.get("id").getAsString();close(host);return;}criticals=module("combat.Criticals");criticalsWasActive=enabled(criticals);if(criticals!=null)conflicts.pause(criticals);conflictsScoped=true;}
    if(conflictsScoped&&(!meteorFarm.ready()||enabled(criticals))){blockedRequest=r.get("id").getAsString();close(host);return;}armed=conflictsScoped;c.player.setSprinting(false);

   }else close(host);
   var out=new JsonObject();out.addProperty("time",now);out.addProperty("active",armed);out.addProperty("stationary_preconditions",ready);out.addProperty("scoped",scoped);out.addProperty("built_station",built);out.addProperty("boat_count",boats);out.addProperty("nearby_armorstand",decoration);out.addProperty("attack_executor","Meteor KillAura");out.add("meteor_settings",new Gson().toJsonTree(meteorFarm.observe()));out.addProperty("criticals_originally_active",criticalsWasActive);out.addProperty("criticals_currently_active",enabled(criticals));out.addProperty("request_id",r.get("id").getAsString());out.addProperty("reason",armed?(target==null?"waiting_for_captured_piglin":"meteor_killaura_owns_all_attacks"):"local_trial_precondition_not_ready");if(target!=null){out.addProperty("target_uuid",target.getUUID().toString());out.addProperty("target_health",target.getHealth());}Path tmp=root.resolve("local-farm-melee-state.tmp");Files.writeString(tmp,out.toString());Files.move(tmp,root.resolve("local-farm-melee-state.json"),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
  }catch(Exception e){
   close(host);
   try{
    var out=new JsonObject();
    out.addProperty("time",now);out.addProperty("active",false);
    out.addProperty("reason","local_trial_refused_"+e.getClass().getSimpleName());
    Path tmp=root.resolve("local-farm-melee-state.tmp");
    Files.writeString(tmp,out.toString());
    Files.move(tmp,root.resolve("local-farm-melee-state.json"),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
   }catch(Exception ignored){}
  }
 }
}
