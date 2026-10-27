package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Leashable;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.world.entity.vehicle.boat.AbstractBoat;
import net.minecraft.world.entity.vehicle.minecart.AbstractMinecart;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

/** Observe real passengers and leash holders before any village transport input. */
final class LoadedVehicleSurvey {
    static final String SCOPE="current_client_loaded_server_vehicles_and_passengers";
    private final AtomicBoolean writing=new AtomicBoolean();
    private Object level,connection;
    private long enteredAt,next;

    static boolean current(boolean connected,long now,long entered,long observed,
                           String server,String actualServer,String dimension,String actualDimension){
        return connected&&observed>=entered&&now>=observed&&now-observed<=1000
            &&server!=null&&server.equals(actualServer)&&dimension!=null&&dimension.equals(actualDimension);
    }
    private static JsonArray point(double x,double y,double z){
        var result=new JsonArray();result.add(x);result.add(y);result.add(z);return result;
    }
    private static JsonObject identity(Entity e){
        var row=new JsonObject();row.addProperty("id",e.getId());row.addProperty("uuid",e.getUUID().toString());
        row.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());
        row.addProperty("alive",e.isAlive());row.addProperty("has_custom_name",e.hasCustomName());
        row.add("pos",point(e.getX(),e.getY(),e.getZ()));
        if(e instanceof LivingEntity living){row.addProperty("health",living.getHealth());row.addProperty("max_health",living.getMaxHealth());}
        if(e instanceof Villager villager)row.addProperty("is_baby",villager.isBaby());
        if(e instanceof net.minecraft.world.entity.animal.Animal animal)row.addProperty("is_baby",animal.isBaby());
        var bounds=e.getBoundingBox();var box=new JsonObject();
        box.add("min",point(bounds.minX,bounds.minY,bounds.minZ));box.add("max",point(bounds.maxX,bounds.maxY,bounds.maxZ));row.add("bounds",box);
        return row;
    }
    private static void leash(JsonObject row,Leashable leashable){
        row.addProperty("leashed",leashable.isLeashed());var holder=leashable.getLeashHolder();
        row.addProperty("leash_resolved",holder!=null);
        if(holder!=null)row.add("leash_holder",identity(holder));
    }
    void tick(Minecraft c){
        long now=System.currentTimeMillis();
        if(now<next||writing.get())return;next=now+250;
        if(level!=c.level||connection!=c.getConnection()){
            level=c.level;connection=c.getConnection();enteredAt=now;
        }
        if(c.player==null||c.level==null||c.getConnection()==null)return;
        try{
            var root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");var status=root.resolve("status.json");
            if(!Files.isRegularFile(status)||Files.size(status)>1048576)return;
            var state=JsonParser.parseString(Files.readString(status)).getAsJsonObject();
            String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
            String dimension=c.level.dimension().identifier().toString();
            if(!current(state.get("connected").getAsBoolean(),now,enteredAt,state.get("time").getAsLong(),
                    server,state.get("server").getAsString(),dimension,state.get("dimension").getAsString()))return;
            String world=state.get("world_session").getAsString();UUID.fromString(world);
            var rows=new JsonArray();var leashables=new JsonArray();boolean truncated=false,leashablesTruncated=false;
            for(var e:c.level.entitiesForRendering()){
                if(!(e instanceof Leashable||e instanceof AbstractMinecart)||e.isRemoved()||!e.isAlive()
                        ||c.level.getEntity(e.getId())!=e)continue;
                var chunk=c.level.getChunkSource().getChunk(Math.floorDiv(e.blockPosition().getX(),16),
                    Math.floorDiv(e.blockPosition().getZ(),16),net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
                if(!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))continue;
                if(e instanceof Leashable leashable&&!(e instanceof AbstractBoat)){
                    if(leashables.size()>=256)leashablesTruncated=true;
                    else{var observed=identity(e);leash(observed,leashable);leashables.add(observed);}
                    continue;
                }
                if(rows.size()>=128){truncated=true;break;}
                var row=identity(e);var passengers=new JsonArray();
                for(var passenger:e.getPassengers())passengers.add(identity(passenger));
                row.add("passengers",passengers);row.addProperty("visible",c.player.hasLineOfSight(e));
                row.addProperty("distance",e.distanceTo(c.player));row.addProperty("on_ground",e.onGround());
                row.addProperty("in_water",e.isInWater());
                var bounds=e.getBoundingBox();var box=new JsonObject();
                box.add("min",point(bounds.minX,bounds.minY,bounds.minZ));box.add("max",point(bounds.maxX,bounds.maxY,bounds.maxZ));row.add("bounds",box);
                if(e instanceof Leashable leashable){
                    leash(row,leashable);
                }
                rows.add(row);
            }
            var result=new JsonObject();result.addProperty("protocol",1);result.addProperty("time",now);
            result.addProperty("connected",true);result.addProperty("world_session",world);
            result.addProperty("server",server);result.addProperty("dimension",dimension);result.addProperty("scope",SCOPE);
            result.addProperty("player_uuid",c.player.getUUID().toString());result.addProperty("truncated",truncated);result.add("vehicles",rows);
            result.addProperty("leashables_protocol",1);result.addProperty("leashables_truncated",leashablesTruncated);result.add("leashables",leashables);
            if(!writing.compareAndSet(false,true))return;
            CompletableFuture.runAsync(()->{
                try{
                    var temporary=root.resolve("loaded-vehicle-survey.tmp");Files.writeString(temporary,result.toString());
                    Files.move(temporary,root.resolve("loaded-vehicle-survey.json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
                }catch(Exception ignored){}finally{writing.set(false);}
            });
        }catch(Exception ignored){} // Missing observations cannot authorize input.
    }
}
