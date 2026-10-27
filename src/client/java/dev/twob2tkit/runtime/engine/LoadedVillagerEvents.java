package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.protocol.game.ClientboundEntityEventPacket;
import net.minecraft.network.protocol.game.ClientboundTakeItemEntityPacket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayDeque;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/** Read server pickup/event packets; disappearing food alone is never a pickup receipt. */
final class LoadedVillagerEvents {
    static final String SCOPE="incoming_server_item_pickups_and_loaded_villager_entity_events";
    static final int LIMIT=256;
    private final ArrayDeque<JsonObject> events=new ArrayDeque<>();
    private final AtomicBoolean writing=new AtomicBoolean();
    private final AtomicLong epoch=new AtomicLong(),packetEvents=new AtomicLong(),captureFailures=new AtomicLong();
    private final String observer=UUID.randomUUID().toString();
    private volatile Minecraft client;
    private MeteorPacketObservation subscription;
    private Object level,connection;
    private String world="",failure="";
    private long enteredAt,next,nextSubscribe,sequence,subscribedAt;
    private int generation=-1;
    private JsonObject lastPotionInventory;

    static boolean validPickup(int amount){return amount>0&&amount<=64;}
    static boolean validPoint(double x,double y,double z){return Double.isFinite(x)&&Double.isFinite(y)&&Double.isFinite(z);}
    static void retain(ArrayDeque<JsonObject> queue,JsonObject event,long now){
        queue.add(event);
        while(queue.size()>LIMIT||!queue.isEmpty()&&now-queue.peekFirst().get("received_at").getAsLong()>120000)queue.removeFirst();
    }
    void stop(){epoch.incrementAndGet();if(subscription!=null)subscription.close();subscription=null;subscribedAt=0;nextSubscribe=0;}
    void workStopped(String reason){
        // These native handoffs only change the character's action. Keeping
        // the read-only listener also keeps already queued pickup callbacks.
        // World exit, manual stops and runtime disposal still unsubscribe.
        if(!"切换到脚本任务".equals(reason)&&!"使用投影打印机".equals(reason))stop();
    }

    private static JsonArray point(double x,double y,double z){var a=new JsonArray();a.add(x);a.add(y);a.add(z);return a;}
    private static JsonObject identity(Entity e){
        var a=new JsonObject();a.addProperty("entity_id",e.getId());a.addProperty("uuid",e.getUUID().toString());
        a.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());
        a.add("pos",point(e.getX(),e.getY(),e.getZ()));
        if(e instanceof LivingEntity living)a.addProperty("client_health",living.getHealth());
        if(e instanceof Villager v){
            a.addProperty("is_baby",v.isBaby());a.addProperty("sleeping",v.isSleeping());a.addProperty("passenger",v.isPassenger());
            a.addProperty("no_ai_client_flag",v.isNoAi());
            v.getSleepingPos().ifPresent(p->a.add("sleeping_pos",point(p.getX(),p.getY(),p.getZ())));
        }
        return a;
    }
    private static boolean loaded(Minecraft c,Entity e){
        if(e==null||e.isRemoved()||c.level.getEntity(e.getId())!=e||!validPoint(e.getX(),e.getY(),e.getZ()))return false;
        var chunk=c.level.getChunkSource().getChunk(Math.floorDiv(e.blockPosition().getX(),16),Math.floorDiv(e.blockPosition().getZ(),16),
            net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
        return LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    private void incoming(MeteorPacketObservation.Incoming incoming,long token){
        if(token!=epoch.get())return;
        packetEvents.incrementAndGet();Object packet=incoming.packet();
        if(!(packet instanceof ClientboundTakeItemEntityPacket||packet instanceof ClientboundEntityEventPacket))return;
        Minecraft c=client;long received=System.currentTimeMillis();
        if(c==null)return;
        try {c.execute(()->{
            try {
                if(token!=epoch.get()||subscription==null||c.player==null||c.level!=level||c.getConnection()!=connection
                        ||c.getConnection()==null||c.getConnection().getConnection()!=incoming.connection()||received<enteredAt||world.isEmpty())return;
                var row=new JsonObject();row.addProperty("received_at",received);row.addProperty("sequence",++sequence);
                if(packet instanceof ClientboundTakeItemEntityPacket pickup){
                    if(!validPickup(pickup.getAmount()))return;
                    row.addProperty("source_entity_id",pickup.getItemId());row.addProperty("collector_entity_id",pickup.getPlayerId());
                    row.addProperty("amount",pickup.getAmount());var source=c.level.getEntity(pickup.getItemId());var collector=c.level.getEntity(pickup.getPlayerId());
                    if(loaded(c,collector))row.add("collector",identity(collector));
                    if(source instanceof ItemEntity item&&loaded(c,source)&&loaded(c,collector)){
                        row.addProperty("kind","item_pickup");row.add("source",identity(item));
                        row.addProperty("item",BuiltInRegistries.ITEM.getKey(item.getItem().getItem()).toString());
                        row.addProperty("client_stack_before_handler",item.getItem().getCount());
                    }else row.addProperty("kind","pickup_entities_unresolved");
                }else{
                    var event=(ClientboundEntityEventPacket)packet;var entity=event.getEntity(c.level);
                    if(!(entity instanceof Villager)||!loaded(c,entity))return;
                    row.addProperty("kind","villager_entity_event");row.addProperty("event_code",Byte.toUnsignedInt(event.getEventId()));
                    row.add("villager",identity(entity));
                }
                retain(events,row,System.currentTimeMillis());
            }catch(RuntimeException|LinkageError error){captureFailures.incrementAndGet();}
        });}catch(RuntimeException error){captureFailures.incrementAndGet();}
    }

    void tick(Minecraft c){
        client=c;long now=System.currentTimeMillis();
        if(level!=c.level||connection!=c.getConnection()){
            stop();level=c.level;connection=c.getConnection();enteredAt=now;world="";generation=-1;events.clear();lastPotionInventory=null;
        }
        if(c.player==null||c.level==null||c.getConnection()==null)return;
        if(subscription==null&&now>=nextSubscribe){
            nextSubscribe=now+5000;
            try {long token=epoch.incrementAndGet();subscription=MeteorPacketObservation.open(packet->incoming(packet,token));subscribedAt=now;failure="";}
            catch(ReflectiveOperationException|RuntimeException|LinkageError error){failure=error.getClass().getSimpleName();}
        }
        if(now<next||writing.get())return;next=now+250;
        try{
            var root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");var status=root.resolve("status.json");
            if(!Files.isRegularFile(status)||Files.size(status)>1048576)return;
            var state=JsonParser.parseString(Files.readString(status)).getAsJsonObject();
            String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
            String dimension=c.level.dimension().identifier().toString();
            if(!LoadedVehicleSurvey.current(state.get("connected").getAsBoolean(),now,enteredAt,state.get("time").getAsLong(),
                    server,state.get("server").getAsString(),dimension,state.get("dimension").getAsString())
                    ||!EngineBuildVersion.VALUE.equals(state.get("runtime_version").getAsString()))return;
            String current=state.get("world_session").getAsString();UUID.fromString(current);int currentGeneration=state.get("runtime_generation").getAsInt();
            if(!current.equals(world)||currentGeneration!=generation){world=current;generation=currentGeneration;events.clear();enteredAt=now;lastPotionInventory=null;}
            while(!events.isEmpty()&&now-events.peekFirst().get("received_at").getAsLong()>120000)events.removeFirst();
            var rows=new JsonArray();for(var row:events)rows.add(row.deepCopy());var villagers=new JsonArray();boolean truncated=false;
            for(var e:c.level.entitiesForRendering())if(e instanceof Villager&&loaded(c,e)){
                if(villagers.size()==LIMIT){truncated=true;break;}villagers.add(identity(e));
            }
            var potionInventory=LoadedPotionDetails.observe(c,now);
            if(LoadedPotionDetails.retain(potionInventory))lastPotionInventory=potionInventory.deepCopy();
            var result=new JsonObject();result.addProperty("protocol",1);result.addProperty("scope",SCOPE);result.addProperty("time",now);
            result.addProperty("connected",true);result.addProperty("world_session",world);result.addProperty("server",server);result.addProperty("dimension",dimension);
            result.addProperty("player_uuid",c.player.getUUID().toString());result.addProperty("runtime_generation",generation);
            result.addProperty("runtime_version",EngineBuildVersion.VALUE);result.addProperty("observer_id",observer);result.addProperty("world_entered_at",enteredAt);
            result.addProperty("subscriber_active",subscription!=null);result.addProperty("subscribed_at",subscribedAt);result.addProperty("packet_events_seen",packetEvents.get());
            result.addProperty("capture_failures",captureFailures.get());result.addProperty("subscription_failure",failure);result.addProperty("villagers_truncated",truncated);
            result.addProperty("event_retention_ms",120000);result.add("events",rows);result.add("villagers",villagers);
            result.add("potion_inventory",potionInventory);
            if(lastPotionInventory!=null)result.add("last_potion_inventory",lastPotionInventory.deepCopy());
            // Raw clock modulo alone does not prove this world's effective daylight.
            // Publish observations only; never change clocks or visual module settings.
            var environment=new JsonObject();environment.addProperty("scope","current_client_world_environment");
            environment.addProperty("observed_at",now);environment.addProperty("overworld_clock_ticks",c.level.getOverworldClockTime());
            environment.addProperty("default_clock_ticks",c.level.getDefaultClockTime());environment.addProperty("game_ticks",c.level.getGameTime());
            environment.addProperty("sky_darken",c.level.getSkyDarken());environment.addProperty("dark_outside",c.level.isDarkOutside());
            environment.addProperty("bright_outside",c.level.isBrightOutside());
            environment.addProperty("time_changer_active",BorerFlight.meteorTimeChangerActive());result.add("world_environment",environment);
            if(!writing.compareAndSet(false,true))return;
            CompletableFuture.runAsync(()->{
                Path temporary=root.resolve("loaded-villager-events.tmp-"+observer);
                try{
                    Files.writeString(temporary,result.toString());var fresh=JsonParser.parseString(Files.readString(status)).getAsJsonObject();
                    if(fresh.get("runtime_generation").getAsInt()==result.get("runtime_generation").getAsInt()
                            &&fresh.get("world_session").getAsString().equals(result.get("world_session").getAsString())
                            &&fresh.get("runtime_version").getAsString().equals(EngineBuildVersion.VALUE))
                        Files.move(temporary,root.resolve("loaded-villager-events.json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
                }catch(Exception ignored){}finally{try{Files.deleteIfExists(temporary);}catch(Exception ignored){}writing.set(false);}
            });
        }catch(Exception ignored){} // A stale or absent frame cannot prove pickup, breeding, or death.
    }
}
