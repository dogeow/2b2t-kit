package dev.twob2tkit.runtime.engine;

import com.google.gson.*;
import java.nio.file.*;
import java.util.UUID;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.vehicle.boat.AbstractBoat;
import dev.twob2tkit.runtime.api.RotationAim;

/** One normal attack through the retained material lease; actual recovery is verified separately. */
final class EmptyBoatRecovery {
    private String last="",candidate="";
    private long firstSeen,next;
    private static String text(JsonObject o,String k){return o.has(k)?o.get(k).getAsString():"";}
    void tick(Minecraft c,boolean enabled){
        long now=System.currentTimeMillis();if(!enabled||c.player==null||c.level==null||now<next)return;next=now+50;
        Path root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");
        Path input=root.resolve("empty-boat-recovery.json");if(!Files.isRegularFile(input))return;
        String id="";Path claim=null;
        try{
            if(Files.size(input)>4096)return;
            var r=JsonParser.parseString(Files.readString(input)).getAsJsonObject();id=text(r,"id");
            if(id.equals(last))return;
            if(!id.matches("[A-Za-z0-9_-]{1,96}")||r.get("protocol").getAsInt()!=1)throw new IllegalArgumentException("empty recovery protocol invalid");
            UUID boatId=UUID.fromString(text(r,"boat_uuid"));
            claim=root.resolve("empty-boat-recovery-claim-"+boatId+".json");
            if(Files.exists(claim)){last=id;publish(root,id,"retained_attempt","Original boat attack remains retained; no replay",now);return;}
            var h=JsonParser.parseString(Files.readString(root.resolve("status.json"))).getAsJsonObject();
            var lease=h.getAsJsonObject("supervision_lease");
            boolean owner=lease!=null&&"materials".equals(text(lease,"kind"))
                &&text(r,"world_session").equals(text(h,"world_session"))&&text(r,"world_session").equals(text(lease,"world_session"))
                &&text(r,"lease_id").equals(text(lease,"id"))&&text(r,"task_session").equals(text(lease,"job_session"))
                &&text(r,"player_uuid").equals(c.player.getUUID().toString())
                &&r.get("control_revision").getAsLong()==h.get("control_revision").getAsLong()
                &&h.get("guard_armed").getAsBoolean()&&h.get("guard_pve_only").getAsBoolean()
                &&!h.get("manual_movement").getAsBoolean()&&!h.get("guard_busy").getAsBoolean()
                &&!h.getAsJsonObject("safety_hold").get("active").getAsBoolean()
                &&!h.get("health_recovery_hold").getAsBoolean()
                &&EmptyBoatRecoveryPolicy.fresh(now,r.get("issued_at").getAsLong(),r.get("expires_at").getAsLong(),h.get("time").getAsLong());
            var entity=c.level.getEntity(r.get("entity_id").getAsInt());
            if(!(entity instanceof AbstractBoat boat)||!boat.getUUID().equals(boatId))throw new IllegalStateException("Exact boat unavailable");
            var pos=boat.blockPosition();var chunk=c.level.getChunkSource().getChunk(Math.floorDiv(pos.getX(),16),Math.floorDiv(pos.getZ(),16),net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
            boolean real=LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
            var floor=BlockPos.containing(boat.getX(),boat.getY()-.01,boat.getZ());var base=c.level.getBlockState(floor);
            String ground=BuiltInRegistries.BLOCK.getKey(base.getBlock()).toString();
            boolean dry=boat.onGround()&&!boat.isInWater()&&base.isFaceSturdy(c.level,floor,Direction.UP)
                &&c.level.getFluidState(floor).isEmpty()&&!java.util.Set.of("minecraft:magma_block","minecraft:campfire","minecraft:soul_campfire").contains(ground);
            boolean quiet=c.level.getEntities(c.player,c.player.getBoundingBox().inflate(16)).stream()
                .noneMatch(e->e instanceof Enemy&&e.isAlive());
            quiet &= c.level.getEntities(boat,boat.getBoundingBox().inflate(1)).stream()
                .noneMatch(e->e!=c.player&&e instanceof LivingEntity&&e.isAlive());
            boolean free=false;for(int i=0;i<36;i++)if(c.player.getInventory().getItem(i).isEmpty()){free=true;break;}
            var held=c.player.getMainHandItem();var box=boat.getBoundingBox();var eye=c.player.getEyePosition();
            var nearest=new net.minecraft.world.phys.Vec3(Math.max(box.minX,Math.min(eye.x,box.maxX)),Math.max(box.minY,Math.min(eye.y,box.maxY)),Math.max(box.minZ,Math.min(eye.z,box.maxZ)));
            boolean idle=c.gui.screen()==null&&c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty()
                &&!h.get("navigating").getAsBoolean()&&(!h.has("pending_scan")||h.get("pending_scan").isJsonNull());
            boolean healthy=c.player.getHealth()==20&&c.player.getFoodData().getFoodLevel()>=18&&c.player.hurtTime==0
                &&!c.player.isUsingItem()&&!c.player.isInWater()&&!c.player.isOnFire();
            boolean axe=held.is(ItemTags.AXES)&&(!held.isDamageableItem()||held.getMaxDamage()-held.getDamageValue()>32)
                &&c.player.getAttackStrengthScale(0)>=.95F;
            if(!EmptyBoatRecoveryPolicy.allowed(owner&&real,idle,healthy,boat.isAlive()&&!boat.isRemoved()&&!boat.isPassenger()
                    &&!BuiltInRegistries.ENTITY_TYPE.getKey(boat.getType()).toString().contains("chest"),!boat.hasCustomName(),boat.getPassengers().isEmpty(),
                    !boat.isLeashed()||boat.getLeashHolder()==c.player,dry,c.player.hasLineOfSight(boat),axe,free,quiet,
                    eye.distanceTo(nearest),c.player.entityInteractionRange()))throw new IllegalStateException("Exact empty healthy boat recovery preflight refused");
            if(!id.equals(candidate)){candidate=id;firstSeen=now;return;}
            if(now-firstSeen<100)return;
            // Claim first: a crash between this write and the packet is unknown, never an automatic retry.
            Files.writeString(claim,r.toString(),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);
            last=id;RotationAim.apply(c.player,RotationAim.lookAt(c.player,boat.position().add(0,boat.getBbHeight()*.5,0)));
            c.gameMode.attack(c.player,boat);c.player.swing(InteractionHand.MAIN_HAND);
            publish(root,id,"attack_sent","One ordinary empty-boat attack sent; no recovery credit",now);
        }catch(Exception e){if(!id.isEmpty()){
            last=id;publish(root,id,claim!=null&&Files.exists(claim)?"retained_attempt":"rejected_preflight",e.getMessage(),now);
        }}
    }
    private static void publish(Path root,String id,String phase,String detail,long now){
        try{
            var r=new JsonObject();r.addProperty("protocol",1);r.addProperty("runtime_version",EngineBuildVersion.VALUE);r.addProperty("id",id);
            r.addProperty("time",now);r.addProperty("phase",phase);r.addProperty("detail",detail);r.addProperty("recovery_credit",0);
            Path temp=root.resolve("empty-boat-recovery-state.json.writing");Files.writeString(temp,r.toString());
            Files.move(temp,root.resolve("empty-boat-recovery-state.json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        }catch(Exception ignored){/* Missing receipt is unknown, never a second attack. */}
    }
}
