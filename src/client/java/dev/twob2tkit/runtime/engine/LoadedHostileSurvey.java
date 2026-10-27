package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Enemy;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

/** Read only live server entities, including equipment, without scanning blocks or loading chunks. */
final class LoadedHostileSurvey {
    static final String SCOPE="current_client_loaded_server_hostile_entities";
    private final AtomicBoolean writing=new AtomicBoolean();
    private final String observer=UUID.randomUUID().toString();
    private Object level,connection;
    private long enteredAt,next;
    private static JsonArray point(double x,double y,double z){
        var out=new JsonArray();out.add(x);out.add(y);out.add(z);return out;
    }
    static boolean sameGeneration(JsonObject status,JsonObject frame){
        try{return status.get("connected").getAsBoolean()
            &&status.get("runtime_generation").getAsInt()==frame.get("runtime_generation").getAsInt()
            &&status.get("world_session").getAsString().equals(frame.get("world_session").getAsString())
            &&status.get("runtime_version").getAsString().equals(frame.get("runtime_version").getAsString());
        }catch(Exception missing){return false;}
    }
    void tick(Minecraft c){
        long now=System.currentTimeMillis();if(now<next||writing.get())return;next=now+250;
        if(level!=c.level||connection!=c.getConnection()){level=c.level;connection=c.getConnection();enteredAt=now;}
        if(c.player==null||c.level==null||c.getConnection()==null)return;
        try{
            var root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");var path=root.resolve("status.json");
            if(!Files.isRegularFile(path)||Files.size(path)>1048576)return;
            var state=JsonParser.parseString(Files.readString(path)).getAsJsonObject();
            String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
            String dimension=c.level.dimension().identifier().toString();
            if(!LoadedVehicleSurvey.current(state.get("connected").getAsBoolean(),now,enteredAt,state.get("time").getAsLong(),
                    server,state.get("server").getAsString(),dimension,state.get("dimension").getAsString())
                    ||!EngineBuildVersion.VALUE.equals(state.get("runtime_version").getAsString()))return;
            String world=state.get("world_session").getAsString();UUID.fromString(world);
            var rows=new JsonArray();boolean truncated=false;
            for(var entity:c.level.entitiesForRendering()){
                if(!(entity instanceof LivingEntity living)||!(entity instanceof Enemy)||entity.isRemoved()||!entity.isAlive()
                        ||c.level.getEntity(entity.getId())!=entity)continue;
                var pos=entity.blockPosition();var chunk=c.level.getChunkSource().getChunk(Math.floorDiv(pos.getX(),16),
                        Math.floorDiv(pos.getZ(),16),net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
                if(!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))continue;
                if(rows.size()>=256){truncated=true;break;}
                var row=new JsonObject();row.addProperty("id",entity.getId());row.addProperty("uuid",entity.getUUID().toString());
                row.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString());
                row.addProperty("alive",entity.isAlive());row.addProperty("hostile",true);row.addProperty("is_baby",living.isBaby());
                row.addProperty("health",living.getHealth());row.addProperty("has_custom_name",living.hasCustomName());
                row.addProperty("visible",c.player.hasLineOfSight(entity));row.addProperty("distance",entity.distanceTo(c.player));
                row.addProperty("on_fire",entity.isOnFire());row.addProperty("in_water",entity.isInWater());
                row.add("pos",point(entity.getX(),entity.getY(),entity.getZ()));
                var bounds=entity.getBoundingBox();var box=new JsonObject();
                box.add("min",point(bounds.minX,bounds.minY,bounds.minZ));box.add("max",point(bounds.maxX,bounds.maxY,bounds.maxZ));row.add("bounds",box);
                row.addProperty("main_hand",BuiltInRegistries.ITEM.getKey(living.getMainHandItem().getItem()).toString());
                row.addProperty("off_hand",BuiltInRegistries.ITEM.getKey(living.getOffhandItem().getItem()).toString());
                row.addProperty("head_item",BuiltInRegistries.ITEM.getKey(living.getItemBySlot(EquipmentSlot.HEAD).getItem()).toString());
                rows.add(row);
            }
            var result=new JsonObject();result.addProperty("protocol",1);result.addProperty("time",now);
            result.addProperty("id","loaded-hostiles-"+observer+"-"+now);result.addProperty("scope",SCOPE);
            result.addProperty("connected",true);result.addProperty("world_session",world);result.addProperty("server",server);
            result.addProperty("dimension",dimension);result.addProperty("player_uuid",c.player.getUUID().toString());
            result.addProperty("runtime_version",EngineBuildVersion.VALUE);result.addProperty("runtime_generation",state.get("runtime_generation").getAsInt());
            result.addProperty("world_entered_at",enteredAt);result.addProperty("truncated",truncated);result.add("hostiles",rows);
            result.addProperty("equipment_scope","current_client_entity_equipment_not_predicted_drops");
            if(!writing.compareAndSet(false,true))return;
            CompletableFuture.runAsync(()->{
                var temporary=root.resolve("loaded-hostile-survey.tmp-"+observer);
                try{
                    Files.writeString(temporary,result.toString());var fresh=JsonParser.parseString(Files.readString(path)).getAsJsonObject();
                    if(sameGeneration(fresh,result))Files.move(temporary,root.resolve("loaded-hostile-survey.json"),
                            StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
                }catch(Exception ignored){}finally{try{Files.deleteIfExists(temporary);}catch(Exception ignored){}writing.set(false);}
            });
        }catch(Exception ignored){} // Missing, stale or replaced-world observations never authorize input.
    }
}
