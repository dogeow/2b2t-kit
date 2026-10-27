package dev.twob2tkit.runtime.engine;

import com.google.gson.*;
import com.mojang.serialization.JsonOps;
import java.nio.file.*;
import java.util.UUID;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.RegistryOps;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.alchemy.PotionContents;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.*;
import dev.twob2tkit.runtime.api.RotationAim;

/** One ordinary potion use, durably claimed first; healing is never credited here. */
final class ResidentPotionTreatment {
 private String last="";
 private static String text(JsonObject o,String k){return o!=null&&o.has(k)&&!o.get(k).isJsonNull()?o.get(k).getAsString():"";}
 private static boolean yes(JsonObject o,String k){return o!=null&&o.has(k)&&!o.get(k).isJsonNull()&&o.get(k).getAsBoolean();}
 private static Vec3 point(JsonObject r,String key){var a=r.getAsJsonArray(key);if(a==null||a.size()!=3)throw new IllegalArgumentException("Exact finite position required");double x=a.get(0).getAsDouble(),y=a.get(1).getAsDouble(),z=a.get(2).getAsDouble();if(!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z))throw new IllegalArgumentException("Nonfinite treatment position");return new Vec3(x,y,z);}
 void tick(Minecraft c){
  if(c.player==null||c.level==null||c.gameMode==null)return;
  Path root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation"),input=root.resolve("resident-potion.json");if(!Files.isRegularFile(input))return;
  String id="";Path claim=null;JsonObject r=null;
  try{
   if(Files.size(input)>8192)throw new IllegalArgumentException("Oversized treatment request");r=JsonParser.parseString(Files.readString(input)).getAsJsonObject();id=text(r,"id");if(id.equals(last))return;
   UUID.fromString(id);if(r.get("protocol").getAsInt()!=1)throw new IllegalArgumentException("Treatment protocol invalid");
   var state=JsonParser.parseString(Files.readString(root.resolve("status.json"))).getAsJsonObject();var lease=state.getAsJsonObject("supervision_lease");long now=System.currentTimeMillis();
   String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
   boolean owner=lease!=null&&text(lease,"kind").equals("materials")&&text(r,"world_session").equals(text(state,"world_session"))&&text(r,"world_session").equals(text(lease,"world_session"))
    &&text(r,"lease_id").equals(text(lease,"id"))&&text(r,"task_session").equals(text(lease,"job_session"))&&text(r,"player_uuid").equals(c.player.getUUID().toString())
    &&r.get("control_revision").getAsLong()==state.get("control_revision").getAsLong()&&lease.get("revision").getAsLong()==state.get("control_revision").getAsLong()
    &&text(state,"server").equals(server)&&text(state,"dimension").equals(c.level.dimension().identifier().toString())&&text(state,"runtime_version").equals(EngineBuildVersion.VALUE)
    &&yes(state,"connected")&&yes(state,"guard_armed")&&yes(state,"guard_pve_only")&&!yes(state,"guard_busy")&&!yes(state,"manual_movement")
    &&!yes(state,"health_recovery_hold")&&!yes(state.getAsJsonObject("safety_hold"),"active")&&!yes(state,"navigating")&&!yes(state,"native_material_busy")&&!yes(state,"pending_scan")
    &&!yes(state.getAsJsonObject("build_job"),"active")&&!yes(state.getAsJsonObject("professional_printer"),"owned")&&text(state,"phase").equals("done")
    &&ResidentPotionPolicy.fresh(now,r.get("issued_at").getAsLong(),r.get("expires_at").getAsLong(),state.get("time").getAsLong());
   if(!owner||c.gui.screen()!=null||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty()||c.player.getHealth()!=20
    ||c.player.isInWater()||c.player.isInLava()||c.player.isOnFire()||c.player.isUsingItem()||c.player.hasInfiniteMaterials()
    ||c.options.keyUse.isDown()||c.options.keyAttack.isDown()||c.options.keyUp.isDown()||c.options.keyDown.isDown()||c.options.keyLeft.isDown()||c.options.keyRight.isDown()||c.options.keyJump.isDown()||c.options.keyShift.isDown())throw new IllegalStateException("Healthy idle treatment owner changed; no use");
   if(c.player.position().distanceTo(point(r,"player_pos"))>.15||Math.hypot(c.player.getDeltaMovement().x,c.player.getDeltaMovement().z)>.04||Math.abs(c.player.getDeltaMovement().y)>.1)throw new IllegalStateException("Treatment stand moved; no use");
   var expected=r.getAsJsonObject("potion_contents");var hand=c.player.getMainHandItem();var potion=hand.get(DataComponents.POTION_CONTENTS);
   if(!hand.is(Items.SPLASH_POTION)||hand.getCount()!=1||potion==null||!ResidentPotionPolicy.therapeutic(expected)||c.player.getCooldowns().isOnCooldown(hand))throw new IllegalStateException("Verified therapeutic splash is not held; no use");
   var actual=PotionContents.CODEC.encodeStart(RegistryOps.create(JsonOps.INSTANCE,c.player.registryAccess()),potion).getOrThrow();if(!actual.equals(expected))throw new IllegalStateException("Potion effects differ; no use");
   UUID target=UUID.fromString(text(r,"target_uuid"));Villager patient=null;for(var entity:c.level.entitiesForRendering())if(entity instanceof Villager v&&v.getUUID().equals(target)){patient=v;break;}
   if(patient==null)throw new IllegalStateException("Exact patient is not loaded; no use");
   var chunk=c.level.getChunkSource().getChunk(patient.blockPosition().getX()>>4,patient.blockPosition().getZ()>>4,ChunkStatus.FULL,false);
   Vec3 aim=new Vec3(patient.getX(),patient.getBoundingBox().maxY-.15,patient.getZ());
   if(!LoadedServerChunkEvidence.isServerChunk(c.level,chunk)||!ResidentPotionPolicy.patient(r.get("expected_health").getAsFloat(),patient.getHealth(),!patient.isBaby(),patient.isAlive(),patient.position().distanceTo(point(r,"target_pos")),c.player.getEyePosition().distanceTo(aim)))throw new IllegalStateException("Patient identity, health or range changed; no use");
   if(c.level.clip(new ClipContext(c.player.getEyePosition(),aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player)).getType()!=HitResult.Type.MISS)throw new IllegalStateException("Treatment ray blocked; no use");
   var look=RotationAim.lookAt(c.player,aim);c.player.setYRot(look.yaw());c.player.setXRot(look.pitch());
   Path claims=root.resolve("resident-potion-claims").resolve(text(r,"world_session"));Files.createDirectories(claims);claim=claims.resolve(id+".json");
   var record=r.deepCopy();record.addProperty("use_may_have_been_sent",true);record.addProperty("claimed_at",now);record.addProperty("item",BuiltInRegistries.ITEM.getKey(hand.getItem()).toString());Files.writeString(claim,record.toString(),StandardOpenOption.CREATE_NEW);last=id;
   if(!c.gameMode.useItem(c.player,InteractionHand.MAIN_HAND).consumesAction())throw new IllegalStateException("Potion use returned without acceptance; claim retained");
   publish(root,id,"use_sent","One normal potion use sent; independently verify debit and resident health",now);
  }catch(Exception e){last=id;publish(root,id,claim!=null&&Files.exists(claim)?"retained_attempt":"rejected_preflight",e.getMessage(),System.currentTimeMillis());}
 }
 private static void publish(Path root,String id,String phase,String detail,long now){try{var result=new JsonObject();result.addProperty("protocol",1);result.addProperty("runtime_version",EngineBuildVersion.VALUE);result.addProperty("id",id);result.addProperty("phase",phase);result.addProperty("detail",detail);result.addProperty("time",now);result.addProperty("healing_credit",0);var tmp=root.resolve("resident-potion-state.tmp");Files.writeString(tmp,result.toString());Files.move(tmp,root.resolve("resident-potion-state.json"),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}catch(Exception ignored){}}
}
