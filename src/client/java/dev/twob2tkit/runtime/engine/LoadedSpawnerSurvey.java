package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.entity.SpawnerBlockEntity;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;

/** Bounded observations of ordinary spawners in server-loaded chunks; never loads terrain. */
final class LoadedSpawnerSurvey {
    static final int RADIUS=12, WIDTH=2*RADIUS+1, CHUNKS=WIDTH*WIDTH;
    static final String SCOPE="current_client_loaded_server_spawners";
    private final AtomicBoolean writing=new AtomicBoolean();
    private final String observer=UUID.randomUUID().toString();
    private Object level,connection;
    private long enteredAt,next;
    private int cursor,originX,originZ,loaded;
    private JsonArray rows=new JsonArray();
    private boolean truncated;

    static int chunkX(int origin,int index){return origin+index/WIDTH-RADIUS;}
    static int chunkZ(int origin,int index){return origin+index%WIDTH-RADIUS;}
    static boolean sameGeneration(JsonObject state,JsonObject frame){
        try{return state.get("connected").getAsBoolean()
                &&state.get("runtime_generation").getAsInt()==frame.get("runtime_generation").getAsInt()
                &&state.get("runtime_version").getAsString().equals(frame.get("runtime_version").getAsString())
                &&state.get("world_session").getAsString().equals(frame.get("world_session").getAsString());
        }catch(Exception missing){return false;}
    }
    static boolean current(boolean connected,long now,long entered,long observed,
                           String server,String actualServer,String dimension,String actualDimension){
        return connected&&observed>=entered&&now>=observed&&now-observed<=1000
                &&server!=null&&server.equals(actualServer)&&dimension!=null&&dimension.equals(actualDimension);
    }
    void tick(Minecraft c){
        long now=System.currentTimeMillis();
        if(now<next||writing.get())return;
        next=now+50;
        if(level!=c.level||connection!=c.getConnection()){
            level=c.level;connection=c.getConnection();enteredAt=now;cursor=0;rows=new JsonArray();loaded=0;truncated=false;
        }
        if(c.player==null||c.level==null||c.getConnection()==null)return;
        try{
            var root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");
            var path=root.resolve("status.json");
            if(!Files.isRegularFile(path)||Files.size(path)>1048576)return;
            var state=JsonParser.parseString(Files.readString(path)).getAsJsonObject();
            String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
            String dimension=c.level.dimension().identifier().toString();
            if(!current(state.get("connected").getAsBoolean(),now,enteredAt,state.get("time").getAsLong(),
                    server,state.get("server").getAsString(),dimension,state.get("dimension").getAsString())
                    ||!EngineBuildVersion.VALUE.equals(state.get("runtime_version").getAsString()))return;
            String world=state.get("world_session").getAsString();UUID.fromString(world);
            int playerX=c.player.chunkPosition().x(),playerZ=c.player.chunkPosition().z();
            if(cursor==0||playerX!=originX||playerZ!=originZ){
                cursor=0;originX=playerX;originZ=playerZ;rows=new JsonArray();loaded=0;truncated=false;
            }
            // At most sixteen already-loaded chunks and 256 block entities per chunk per tick.
            for(int n=0;n<16&&cursor<CHUNKS;n++,cursor++){
                var chunk=c.level.getChunkSource().getChunk(chunkX(originX,cursor),chunkZ(originZ,cursor),ChunkStatus.FULL,false);
                if(!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))continue;
                loaded++;
                int inspected=0;
                for(var entity:chunk.getBlockEntities().values()){
                    if(inspected++>=256){truncated=true;break;}
                    if(!(entity instanceof SpawnerBlockEntity spawner))continue;
                    var pos=entity.getBlockPos();
                    if(c.level.getBlockEntity(pos)!=entity||entity.isRemoved())continue;
                    if(rows.size()>=256){truncated=true;break;}
                    var row=new JsonObject();var point=new JsonArray();point.add(pos.getX());point.add(pos.getY());point.add(pos.getZ());
                    row.add("pos",point);row.addProperty("block","minecraft:spawner");
                    var display=spawner.getSpawner().getOrCreateDisplayEntity(c.level,pos);
                    row.addProperty("display_entity_type",display==null?"unknown":BuiltInRegistries.ENTITY_TYPE.getKey(display.getType()).toString());
                    row.addProperty("observed_at",now);rows.add(row);
                }
            }
            if(cursor<CHUNKS)return;
            var result=new JsonObject();result.addProperty("protocol",1);result.addProperty("time",now);
            result.addProperty("id","loaded-spawners-"+observer+"-"+now);result.addProperty("scope",SCOPE);
            result.addProperty("connected",true);result.addProperty("world_session",world);result.addProperty("server",server);
            result.addProperty("dimension",dimension);result.addProperty("player_uuid",c.player.getUUID().toString());
            result.addProperty("runtime_version",EngineBuildVersion.VALUE);result.addProperty("runtime_generation",state.get("runtime_generation").getAsInt());
            result.addProperty("world_entered_at",enteredAt);result.addProperty("truncated",truncated);
            result.addProperty("chunk_origin_x",originX);result.addProperty("chunk_origin_z",originZ);
            result.addProperty("radius_chunks",RADIUS);result.addProperty("chunks_considered",cursor);result.addProperty("server_chunks_observed",loaded);
            result.addProperty("absence_scope","only_server_chunks_observed_not_unloaded_terrain");result.add("spawners",rows);
            cursor=0;next=now+2000;
            if(!writing.compareAndSet(false,true))return;
            CompletableFuture.runAsync(()->{
                var temporary=root.resolve("loaded-spawner-survey.tmp-"+observer);
                try{
                    Files.writeString(temporary,result.toString());
                    var fresh=JsonParser.parseString(Files.readString(path)).getAsJsonObject();
                    if(sameGeneration(fresh,result))Files.move(temporary,root.resolve("loaded-spawner-survey.json"),
                            StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
                }catch(Exception ignored){}finally{try{Files.deleteIfExists(temporary);}catch(Exception ignored){}writing.set(false);}
            });
        }catch(Exception ignored){} // Missing evidence cannot authorize construction or excavation.
    }
}
