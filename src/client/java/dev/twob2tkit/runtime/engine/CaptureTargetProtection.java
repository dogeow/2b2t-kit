package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import java.nio.file.*;
import java.util.UUID;

/** Optional, same-owner attack veto; all other combat and emergency exits remain unchanged. */
final class CaptureTargetProtection implements AutoCloseable {
    private CaptureTargetPolicy.Scope scope;
    private ClientLevel level;
    private MeteorPacketObservation veto;
    private String id="",blocked="";
    private String consumedReceiver="",receiverId="";
    private boolean named,boatBound;
    private UUID expectedBoat;
    private long nextRead,lastValidated;
    private Path root;

    void tick(Minecraft c,boolean enabled){
        if(!enabled||c.player==null||c.level==null){close();return;}
        long now=System.currentTimeMillis();
        if(level!=null&&level!=c.level)close();
        if(now<nextRead)return;
        nextRead=now+125;
        root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");
        try{
            var host=JsonParser.parseString(Files.readString(root.resolve("status.json"))).getAsJsonObject();
            var lease=host.getAsJsonObject("supervision_lease");
            if(lease==null)throw new IllegalStateException("material owner unavailable");
            var owner=new CaptureTargetPolicy.Owner(text(host,"world_session"),text(lease,"id"),text(lease,"job_session"),
                host.get("control_revision").getAsLong(),c.player.getUUID().toString(),host.get("time").getAsLong(),
                "materials".equals(text(lease,"kind")),host.get("guard_armed").getAsBoolean(),host.get("guard_pve_only").getAsBoolean(),
                host.get("manual_movement").getAsBoolean(),host.has("health_recovery_hold")&&host.get("health_recovery_hold").getAsBoolean()
                    ||host.has("safety_hold")&&host.getAsJsonObject("safety_hold").get("active").getAsBoolean(),
                c.player.getHealth(),host.get("guard_busy").getAsBoolean());
            if(scope==null){
                if(c.gui.screen()!=null){publish(false,"interface_open");return;}
                var r=receiverRequest(c,owner,now);
                boolean fromReceiver=r!=null;
                Path request=root.resolve("capture-target.json");
                if(r==null){
                    if(!Files.isRegularFile(request)){publish(false,"idle");return;}
                    r=JsonParser.parseString(Files.readString(request)).getAsJsonObject();
                }
                String next=text(r,"id");
                if(next.equals(blocked)){publish(false,"retained_request_not_rearmed");return;}
                if(r.get("protocol").getAsInt()!=1||!next.matches("[A-Za-z0-9_-]{1,96}"))throw new IllegalArgumentException("capture protocol or id invalid");
                if(fromReceiver)consumedReceiver=receiverId;
                id=next;
                var candidate=new CaptureTargetPolicy.Scope(text(r,"world_session"),text(r,"lease_id"),text(r,"task_session"),
                    r.get("control_revision").getAsLong(),text(r,"player_uuid"),UUID.fromString(text(r,"entity_uuid")),text(r,"expected_type"),
                    r.get("issued_at").getAsLong(),r.get("expires_at").getAsLong());
                if(!(fromReceiver?CaptureTargetPolicy.owns(candidate,owner,now,false):CaptureTargetPolicy.admit(candidate,owner,now)))
                    throw new IllegalStateException("capture owner stale or unsafe");
                var entity=find(c,candidate.target());
                if(!subject(c,candidate,entity)||entity.getHealth()!=20)throw new IllegalStateException("healthy exact adult zombie unavailable");
                var event=Class.forName("meteordevelopment.meteorclient.events.entity.player.AttackEntityEvent");
                var entityField=event.getField("entity");var cancel=event.getMethod("setCancelled",boolean.class);
                var meteor=Class.forName("meteordevelopment.meteorclient.MeteorClient");
                var listener=Class.forName("meteordevelopment.orbit.listeners.IListener");
                // Reuse the existing tested optional event subscription adapter.
                veto=MeteorPacketObservation.bind(meteor.getField("EVENT_BUS").get(null),listener,event,value->{
                    try{
                        var target=(Entity)entityField.get(value);
                        boolean automatic=!c.options.keyAttack.isDown();
                        if(CaptureTargetPolicy.veto(scope==null?null:scope.target(),target.getUUID(),automatic,
                                protects(target),target.isAlive()))cancel.invoke(value,true);
                    }catch(ReflectiveOperationException failure){close();publish(false,"attack veto unavailable");}
                });
                expectedBoat=r.has("boat_uuid")?UUID.fromString(text(r,"boat_uuid")):null;
                if(fromReceiver){
                    consumedReceiver=receiverId;
                    Path temp=root.resolve("capture-target.json.receiver-writing");
                    Files.writeString(temp,r.toString());Files.move(temp,request,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
                }
                scope=candidate;level=c.level;id=next;named=false;boatBound=false;
            }
            var entity=find(c,scope.target());
            if(entity!=null&&entity.hasCustomName()&&CaptureTargetPolicy.NAME.equals(entity.getName().getString()))named=true;
            var vehicle=entity==null?null:entity.getVehicle();
            boatBound=CaptureTargetPolicy.aboardExpectedBoat(expectedBoat,vehicle==null?null:vehicle.getUUID(),
                entity!=null&&entity.isPassenger(),vehicle instanceof net.minecraft.world.entity.vehicle.boat.AbstractBoat
                    &&!BuiltInRegistries.ENTITY_TYPE.getKey(vehicle.getType()).toString().contains("chest"),vehicle!=null&&vehicle.isAlive());
            if(!named&&!boatBound&&c.gui.screen()!=null)throw new IllegalStateException("capture yielded to interface");
            if(!CaptureTargetPolicy.owns(scope,owner,now,named||boatBound))throw new IllegalStateException("capture ownership ended");
            if(entity!=null&&!subject(c,scope,entity))throw new IllegalStateException("capture subject changed");
            lastValidated=now;publish(true,named?"named_same_owner":boatBound?"boat_bound_same_owner":"bounded_capture");
        }catch(Exception error){close();publish(false,error.getMessage()==null?error.getClass().getSimpleName():error.getMessage());}
    }
    boolean protects(Entity entity){
        var c=Minecraft.getInstance();
        long age=System.currentTimeMillis()-lastValidated;
        return scope!=null&&veto!=null&&level==c.level&&entity.level()==level
            &&age>=0&&age<=300&&subject(c,scope,entity instanceof LivingEntity l?l:null)
            &&(named||boatBound||System.currentTimeMillis()<=scope.expires());
    }
    private static LivingEntity find(Minecraft c,UUID uuid){
        for(var entity:c.level.entitiesForRendering())if(entity.getUUID().equals(uuid)&&entity instanceof LivingEntity living)return living;
        return null;
    }
    private JsonObject receiverRequest(Minecraft c,CaptureTargetPolicy.Owner owner,long now)throws Exception{
        Path path=root.resolve("capture-receiver.json");
        if(!Files.isRegularFile(path)||Files.size(path)>4096)return null;
        var r=JsonParser.parseString(Files.readString(path)).getAsJsonObject();
        if(r.get("protocol").getAsInt()!=1||!"iron_farm_zombie_capture".equals(text(r,"purpose")))return null;
        if(r.has("allow_unleashed")&&(!r.get("allow_unleashed").isJsonPrimitive()||!r.getAsJsonPrimitive("allow_unleashed").isBoolean()))
            throw new IllegalArgumentException("Receiver leash mode must be boolean");
        var request=new CaptureReceiverPolicy.Request(text(r,"id"),text(r,"world_session"),text(r,"lease_id"),text(r,"task_session"),
            r.get("control_revision").getAsLong(),text(r,"player_uuid"),UUID.fromString(text(r,"boat_uuid")),
            r.get("issued_at").getAsLong(),r.get("expires_at").getAsLong(),r.has("allow_unleashed")&&r.get("allow_unleashed").getAsBoolean());
        if(!CaptureReceiverPolicy.authorized(request,owner,now)||c.player.hurtTime!=0)return null;
        receiverId=request.id();
        String prefix="rx-"+receiverId+"-";
        Path claim=root.resolve("capture-receiver-claim-"+receiverId+".json");
        if(CaptureReceiverPolicy.claimed(receiverId,consumedReceiver,null,Files.exists(claim))){consumedReceiver=receiverId;return null;}
        Path prior=root.resolve("capture-target-state.json");
        if(Files.isRegularFile(prior)&&Files.size(prior)<4096){
            var old=JsonParser.parseString(Files.readString(prior)).getAsJsonObject();
            if(CaptureReceiverPolicy.claimed(receiverId,consumedReceiver,text(old,"id"),false)){
                Files.writeString(claim,old.toString(),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);
                consumedReceiver=receiverId;return null;
            }
        }
        net.minecraft.world.entity.vehicle.boat.AbstractBoat boat=null;
        for(var e:c.level.entitiesForRendering())if(e.getUUID().equals(request.boat())
                &&e instanceof net.minecraft.world.entity.vehicle.boat.AbstractBoat found){boat=found;break;}
        if(boat==null||c.level.getEntity(boat.getId())!=boat||boat.isRemoved()||boat.hasCustomName()||boat.isPassenger()
                ||!CaptureReceiverPolicy.receiverBoat(boat.isAlive(),!BuiltInRegistries.ENTITY_TYPE.getKey(boat.getType()).toString().contains("chest"),
                    boat.getPassengers().isEmpty(),boat.isLeashed(),boat.getLeashHolder()==c.player,request.allowUnleashed())
                ||c.player.distanceTo(boat)>9)return null;
        var bp=boat.blockPosition();var bc=c.level.getChunkSource().getChunk(Math.floorDiv(bp.getX(),16),Math.floorDiv(bp.getZ(),16),
            net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
        if(!LoadedServerChunkEvidence.isServerChunk(c.level,bc))return null;
        LivingEntity chosen=null;
        for(var e:c.level.entitiesForRendering()){
            if(!(e instanceof LivingEntity living)||c.level.getEntity(e.getId())!=e||e.isRemoved())continue;
            String type=BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();
            String hand=BuiltInRegistries.ITEM.getKey(living.getMainHandItem().getItem()).toString();
            if(!CaptureReceiverPolicy.candidate(type,e.isAlive(),living.isBaby(),e.hasCustomName(),e.isOnFire(),e.isPassenger(),
                    living.getHealth(),hand,e.distanceTo(boat),c.player.distanceTo(e),e.getY()-boat.getY()))continue;
            var pos=e.blockPosition();var chunk=c.level.getChunkSource().getChunk(Math.floorDiv(pos.getX(),16),Math.floorDiv(pos.getZ(),16),
                net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
            if(!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))continue;
            if(chosen==null||e.distanceTo(boat)<chosen.distanceTo(boat))chosen=living;
        }
        if(chosen==null)return null;
        var result=new JsonObject();result.addProperty("protocol",1);result.addProperty("id",prefix+chosen.getUUID());
        result.addProperty("world_session",owner.world());result.addProperty("lease_id",owner.lease());result.addProperty("task_session",owner.task());
        result.addProperty("control_revision",owner.revision());result.addProperty("player_uuid",owner.player());
        result.addProperty("entity_uuid",chosen.getUUID().toString());result.addProperty("expected_type",BuiltInRegistries.ENTITY_TYPE.getKey(chosen.getType()).toString());
        result.addProperty("boat_uuid",boat.getUUID().toString());result.addProperty("issued_at",now);result.addProperty("expires_at",now+15000);
        result.addProperty("receiver_id",receiverId);
        // Retain the claim before binding or publishing. A failed subscription,
        // manual interruption or later runtime reload must not repeat this attempt.
        Files.writeString(claim,result.toString(),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);
        return result;
    }
    private static boolean subject(Minecraft c,CaptureTargetPolicy.Scope s,LivingEntity e){
        return e!=null&&CaptureTargetPolicy.subject(s,e.getUUID(),BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString(),
            e.isAlive(),e.isBaby(),e.getHealth(),e.hasCustomName(),e.getName().getString(),c.player.distanceTo(e));
    }
    private static String text(JsonObject o,String key){return o.has(key)?o.get(key).getAsString():"";}
    private void publish(boolean active,String reason){
        if(root==null)return;
        try{
            var out=new JsonObject();out.addProperty("protocol",1);out.addProperty("runtime_version",EngineBuildVersion.VALUE);
            out.addProperty("time",System.currentTimeMillis());out.addProperty("active",active);out.addProperty("id",id);
            out.addProperty("entity_uuid",scope==null?"":scope.target().toString());out.addProperty("named",named);out.addProperty("state",reason);
            out.addProperty("boat_bound",boatBound);out.addProperty("boat_uuid",expectedBoat==null?"":expectedBoat.toString());
            out.addProperty("receiver_id",receiverId);out.addProperty("receiver_consumed",receiverId.equals(consumedReceiver)&&!receiverId.isEmpty());
            out.addProperty("capture_expires_at",scope==null?0:scope.expires());
            Path temp=root.resolve("capture-target-state.json.writing"),dest=root.resolve("capture-target-state.json");
            Files.writeString(temp,out.toString());Files.move(temp,dest,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        }catch(Exception ignored){/* An absent fresh acknowledgement grants no capture permission. */}
    }
    @Override public void close(){
        if(!id.isEmpty())blocked=id;
        scope=null;level=null;named=false;boatBound=false;expectedBoat=null;lastValidated=0;
        if(veto!=null){veto.close();veto=null;}
    }
}
