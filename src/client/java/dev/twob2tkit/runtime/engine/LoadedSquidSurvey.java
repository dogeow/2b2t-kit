package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.LivingEntity;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

/** Fast read-only survey of the same loaded entity list used by render ESP. */
final class LoadedSquidSurvey {
    private final AtomicBoolean writing=new AtomicBoolean();
    private Object level,connection;
    private long enteredAt,next;

    void tick(Minecraft c){
        long now=System.currentTimeMillis();
        if(now<next||writing.get())return;next=now+250;
        if(level!=c.level||connection!=c.getConnection()){
            level=c.level;connection=c.getConnection();enteredAt=now;
        }
        if(c.player==null||c.level==null||c.getConnection()==null)return;
        try{
            Path root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");
            Path status=root.resolve("status.json");
            if(!Files.isRegularFile(status)||Files.size(status)>1048576)return;
            JsonObject current=JsonParser.parseString(Files.readString(status)).getAsJsonObject();
            long observed=current.get("time").getAsLong();
            String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
            String dimension=c.level.dimension().identifier().toString();
            if(!current.get("connected").getAsBoolean()||observed<enteredAt||now-observed>1000
                ||!server.equals(current.get("server").getAsString())
                ||!dimension.equals(current.get("dimension").getAsString()))return;
            String world=current.get("world_session").getAsString();UUID.fromString(world);
            JsonArray rows=new JsonArray(),glowing=new JsonArray();int loaded=0;
            for(var e:c.level.entitiesForRendering()){
                loaded++;
                if(!(e instanceof LivingEntity living))continue;
                String type=BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();
                boolean ordinary=LoadedSquidSurveyPolicy.target(type,e.isAlive(),e.isRemoved(),living.hasCustomName(),living.getHealth(),e.getY());
                boolean glow=LoadedSquidSurveyPolicy.glowTarget(type,e.isAlive(),e.isRemoved(),living.hasCustomName(),living.getHealth(),e.getY());
                if(!ordinary&&!glow)continue;
                var chunk=c.level.getChunkSource().getChunk(Math.floorDiv(e.blockPosition().getX(),16),
                    Math.floorDiv(e.blockPosition().getZ(),16),net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
                if(!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))continue;
                var row=new JsonObject();row.addProperty("id",e.getId());row.addProperty("uuid",e.getUUID().toString());
                row.addProperty("type",type);row.addProperty("alive",true);
                row.addProperty("has_custom_name",false);row.addProperty("health",living.getHealth());
                row.addProperty("visible",c.player.hasLineOfSight(e));
                JsonArray position=new JsonArray();position.add(e.getX());position.add(e.getY());position.add(e.getZ());
                row.add("pos",position);row.addProperty("distance",e.distanceTo(c.player));(ordinary?rows:glowing).add(row);
            }
            var result=new JsonObject();result.addProperty("protocol",1);result.addProperty("time",now);
            result.addProperty("connected",true);result.addProperty("world_session",world);
            result.addProperty("server",server);result.addProperty("dimension",dimension);
            result.addProperty("scope","current_client_loaded_server_entities_ordinary_unnamed_squid_y50_64");
            result.addProperty("loaded_entities_examined",loaded);result.add("squids",rows);
            result.addProperty("glow_protocol",1);result.addProperty("glow_scope","current_client_loaded_server_entities_wild_glow_squid");result.add("glow_squids",glowing);
            if(!writing.compareAndSet(false,true))return;
            CompletableFuture.runAsync(()->{
                try{
                    Path temporary=root.resolve("loaded-squid-survey.tmp");
                    Files.writeString(temporary,result.toString());
                    Files.move(temporary,root.resolve("loaded-squid-survey.json"),
                        StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
                }catch(Exception ignored){}finally{writing.set(false);}
            });
        }catch(Exception ignored){} // A missing observation never sends game input.
    }
}
