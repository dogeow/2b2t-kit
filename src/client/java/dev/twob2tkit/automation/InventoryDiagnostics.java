package dev.twob2tkit.automation;

import com.google.gson.*;
import com.mojang.serialization.JsonOps;
import dev.twob2tkit.mixin.InventoryMenuDiagnosticsAccess;
import dev.twob2tkit.mixin.InventoryConnectionDiagnosticsAccess;
import io.netty.channel.Channel;
import net.minecraft.client.Minecraft;
import net.minecraft.core.RegistryAccess;
import net.minecraft.resources.RegistryOps;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.network.protocol.game.ServerboundContainerClickPacket;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import java.nio.file.Path;
import java.util.UUID;
import java.util.ArrayDeque;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.IdentityHashMap;
import java.util.function.Consumer;

/** One normal click, with read-only observations on each side of an integrated server. */
public final class InventoryDiagnostics {
    public static final int PROTOCOL=1;
    private InventoryDiagnostics() {}
    private static volatile Click observing;
    private record Sent(long sequence,JsonObject packet,Click owner) {}
    private static final ArrayDeque<Sent> sent=new ArrayDeque<>();
    private static Channel channel;
    private static MinecraftServer connectionServer;
    private static Object connectionLevel;
    private static UUID connectionPlayer;
    private static long sequence;
    private static boolean connectionPoisoned;
    /** Scope is published on the client thread; encode/receive callbacks never read client world state. */
    public static synchronized void sync(Minecraft c){
        Channel next=c.getConnection()==null?null:((InventoryConnectionDiagnosticsAccess)c.getConnection().getConnection()).kit$getChannel();
        var server=c.getSingleplayerServer();var player=c.player==null?null:c.player.getUUID();
        if(channel!=next||connectionServer!=server||connectionLevel!=c.level||!java.util.Objects.equals(connectionPlayer,player)){
            if(observing!=null)observing.poison("connection_scope_changed",null);
            sent.clear();channel=next;connectionServer=server;connectionLevel=c.level;connectionPlayer=player;sequence=0;connectionPoisoned=false;
        }
    }

    /** Bounded evidence only: no command arguments, credentials or exception messages. */
    static final class Trace {
        static final int LIMIT=16,MAX_CALLERS=8;
        private final ArrayDeque<JsonObject> events=new ArrayDeque<>();
        private final IdentityHashMap<Object,JsonArray> origins=new IdentityHashMap<>();
        private long dropped;
        synchronized void origin(Object packet,JsonArray callers){if(origins.size()<LIMIT)origins.put(packet,callers.deepCopy());}
        synchronized JsonArray origin(Object packet){var value=origins.get(packet);return value==null?new JsonArray():value.deepCopy();}
        synchronized void add(String event,long seq,boolean owned,JsonObject packet,JsonArray caller,JsonObject menu,String reason,String failureType){
            var row=new JsonObject();row.addProperty("event",event);row.addProperty("observed_at",System.currentTimeMillis());
            row.addProperty("native_sequence",seq);row.addProperty("owner",owned?"owned":"foreign");
            if(packet!=null)row.add("packet",packet.deepCopy());
            if(caller!=null&&!caller.isEmpty()){var bounded=new JsonArray();for(int i=0;i<Math.min(MAX_CALLERS,caller.size());i++)bounded.add(caller.get(i).deepCopy());row.add("caller",bounded);}
            if(menu!=null)row.add("menu",menu.deepCopy());if(reason!=null&&!reason.isBlank())row.addProperty("reason",reason);
            if(failureType!=null&&!failureType.isBlank())row.addProperty("failure_type",failureType);
            if(events.size()==LIMIT){events.removeFirst();dropped++;}events.addLast(row);
        }
        synchronized JsonArray snapshot(){var rows=new JsonArray();events.forEach(row->rows.add(row.deepCopy()));return rows;}
        synchronized long dropped(){return dropped;}
    }
    private static JsonArray callers(){
        try{return StackWalker.getInstance().walk(frames->{
            var rows=new JsonArray();frames.filter(frame->!frame.getClassName().equals(InventoryDiagnostics.class.getName())
                &&!frame.getClassName().equals(InventoryDiagnostics.Click.class.getName())
                &&!frame.getMethodName().startsWith("kit$")&&!frame.getClassName().startsWith("java."))
                .limit(Trace.MAX_CALLERS).forEach(frame->rows.add(frame.getClassName()+"."+frame.getMethodName()));return rows;
        });}catch(RuntimeException unavailable){return new JsonArray();}
    }
    private static JsonObject summary(JsonObject snapshot,int slot){
        var out=new JsonObject();for(String key:new String[]{"id","type","state_id","quickcraft_status","cursor","observed_at","game_time"})
            if(snapshot.has(key))out.add(key,snapshot.get(key).deepCopy());
        if(snapshot.has("slots")&&slot>=0&&slot<snapshot.getAsJsonArray("slots").size())out.add("clicked_slot",snapshot.getAsJsonArray("slots").get(slot).deepCopy());return out;
    }

    public static final class Scope {
        final Object level,connection,menu;
        final MinecraftServer server;
        final UUID player;
        final String session,world,dimension;
        final long revision;
        Scope(Minecraft c,String session,long revision){
            if(c.player==null||c.level==null||c.getSingleplayerServer()==null)
                throw new IllegalStateException("Inventory diagnostics require the current singleplayer world");
            this.level=c.level;this.connection=c.getConnection();this.menu=c.player.containerMenu;
            this.server=c.getSingleplayerServer();this.player=c.player.getUUID();
            this.session=session;this.revision=revision;
            this.world=world(server);this.dimension=c.level.dimension().identifier().toString();
        }
        boolean current(Minecraft c,String currentSession,long currentRevision){
            return c.player!=null&&c.level==level&&c.getConnection()==connection
                &&c.getSingleplayerServer()==server&&c.player.getUUID().equals(player)
                &&c.player.containerMenu==menu&&session.equals(currentSession)&&revision==currentRevision
                &&dimension.equals(c.level.dimension().identifier().toString())&&world.equals(world(server));
        }
        ServerPlayer serverPlayer(){
            var p=server.getPlayerList().getPlayer(player);
            return p!=null&&p.level().getServer()==server&&dimension.equals(p.level().dimension().identifier().toString())?p:null;
        }
    }
    public static final class Click {
        final Scope scope;
        public final String requestId;
        public final Path replyPath;
        final int slot,button,stateId,menuId;
        final ContainerInput input;
        final JsonObject before;
        JsonObject predicted;
        volatile JsonObject serverBefore,processedAfter,processingAfter;
        final Trace trace=new Trace();
        volatile String poisonReason="";
        volatile boolean serverProcessed,poisoned;
        volatile long sentSequence;
        volatile long processedAt;
        volatile ServerboundContainerClickPacket outbound,received;
        volatile long receivedSequence;
        volatile boolean closed;
        final long started=System.currentTimeMillis();
        Click(Minecraft c,String requestId,String session,long revision,int slot,int button,ContainerInput input,Path replyPath){
            this.scope=new Scope(c,session,revision);this.requestId=requestId;this.replyPath=replyPath;
            this.slot=slot;this.button=button;this.input=input;
            this.menuId=c.player.containerMenu.containerId;this.stateId=c.player.containerMenu.getStateId();
            this.before=snapshot(c.player,scope.world);
        }
        boolean packet(ServerPlayer player,ServerboundContainerClickPacket packet){
            return !closed&&!poisoned&&received==packet&&sentSequence>0&&player.level().getServer()==scope.server&&scope.server.isSameThread()
                &&player.getUUID().equals(scope.player)&&scope.dimension.equals(player.level().dimension().identifier().toString())
                &&headersMatch(packet);
        }
        boolean headersMatch(ServerboundContainerClickPacket packet){return packet.containerId()==menuId&&packet.stateId()==stateId&&packet.slotNum()==slot&&packet.buttonNum()==button&&packet.containerInput()==input;}
        public boolean current(Minecraft c,String session,long revision){return !closed&&scope.current(c,session,revision);}
        public long ageMillis(){return System.currentTimeMillis()-started;}
        public void predicted(Minecraft c){predicted=snapshot(c.player,scope.world);}
        synchronized void poison(String reason,Throwable failure){
            poisoned=true;if(poisonReason.isEmpty())poisonReason=reason;
            trace.add("poison",sentSequence,false,null,null,null,reason,failure==null?"":failure.getClass().getSimpleName());
        }
        public JsonObject receipt(Minecraft c,String session,long revision,boolean allowFinal){
            boolean current=scope.current(c,session,revision);
            JsonObject client=current?snapshot(c.player,scope.world):null;
            JsonObject server=serverProcessed?processedAfter:null;
            String classification=allowFinal&&current&&!poisoned?classify(serverProcessed,before,predicted,server,client):"unknown";
            var out=new JsonObject();out.addProperty("protocol",PROTOCOL);out.addProperty("request_id",requestId);
            out.addProperty("world_session",scope.session);out.addProperty("control_revision",scope.revision);
            out.addProperty("classification",classification);out.addProperty("server_processed",serverProcessed);
            out.addProperty("scope_current",current);out.addProperty("confirmation_scope","integrated_server_processed_click_and_matching_final_inventory");
            out.addProperty("native_sequence",sentSequence);out.addProperty("correlation_ambiguous",poisoned);
            out.addProperty("poison_reason",poisonReason);out.add("click_trace",trace.snapshot());out.addProperty("click_trace_dropped",trace.dropped());
            out.addProperty("server_processed_at",processedAt);
            out.addProperty("slot",slot);out.addProperty("button",button);out.addProperty("kind",input.name().toLowerCase());
            out.add("before",before.deepCopy());if(predicted!=null)out.add("predicted_after",predicted.deepCopy());
            if(serverBefore!=null)out.add("server_processing_before",serverBefore.deepCopy());
            if(processingAfter!=null)out.add("server_processing_after",processingAfter.deepCopy());
            if(server!=null)out.add("server",server.deepCopy());if(client!=null)out.add("client",client);
            return out;
        }
        public void close(){closed=true;if(observing==this)observing=null;}
    }
    public static Click begin(Minecraft c,String id,String session,long revision,int slot,int button,ContainerInput input,Path replyPath){
        sync(c);
        if(observing!=null)throw new IllegalStateException("An inventory click still awaits a terminal receipt");
        synchronized(InventoryDiagnostics.class){
            if(connectionPoisoned)throw new IllegalStateException("Local container packet order is uncertain; confirmation unavailable in this connection");
            if(!sent.isEmpty())throw new IllegalStateException("An earlier local container click still awaits processing");
        }
        if(!supported(c.player.containerMenu))throw new IllegalArgumentException("Confirmed inventory clicks support InventoryMenu and CraftingMenu only");
        var click=new Click(c,id,session,revision,slot,button,input,replyPath);observing=click;return click;
    }
    /** The argument is returned unchanged, and this observation sends no packet. */
    public static void outbound(ServerboundContainerClickPacket packet){
        var click=observing;
        if(click!=null&&!click.closed){
            var caller=callers();click.trace.origin(packet,caller);
            try{click.trace.add("normal_outbound",0,click.outbound==null&&click.headersMatch(packet),fingerprint(packet),caller,null,"","");}
            catch(RuntimeException failure){click.poison("outbound_observation_failed",failure);}
        }
        if(click!=null&&!click.closed&&packet.containerId()==click.menuId&&packet.stateId()==click.stateId
            &&packet.slotNum()==click.slot&&packet.buttonNum()==click.button&&packet.containerInput()==click.input){
            if(click.outbound!=null)click.poison("duplicate_matching_outbound_click",null);else click.outbound=packet;
        }
    }
    /** Called only after the actual encoder succeeds, beyond Meteor's cancellable send event. */
    public static synchronized void encoded(Channel encodedChannel,ServerboundContainerClickPacket packet){
        if(encodedChannel!=channel||connectionServer==null)return;
        var click=observing;Click owner=click!=null&&!click.closed&&click.outbound==packet?click:null;
        if(click!=null&&owner==null)click.poison("foreign_encoded_click",null);
        if(sent.size()>=32){if(click!=null)click.poison("encoded_queue_overflow",null);connectionPoisoned=true;sent.clear();return;}
        long seq=++sequence;if(owner!=null)owner.sentSequence=seq;
        try{
            var frame=fingerprint(packet);sent.addLast(new Sent(seq,frame,owner));
            if(click!=null)click.trace.add("encoded",seq,owner==click,frame,click.trace.origin(packet),null,"","");
        }catch(RuntimeException observationFailed){if(click!=null)click.poison("encoded_fingerprint_failed",observationFailed);connectionPoisoned=true;sent.clear();}
    }
    /** Every received click consumes one encoded FIFO entry, including early-returned clicks. */
    public static synchronized void received(ServerPlayer player,ServerboundContainerClickPacket packet){
        if(player.level().getServer()!=connectionServer||!player.getUUID().equals(connectionPlayer)||!connectionServer.isSameThread())return;
        var entry=sent.pollFirst();var click=observing;
        boolean match=false;try{match=entry!=null&&entry.packet.equals(fingerprint(packet));}
        catch(RuntimeException observationFailed){if(click!=null)click.poison("received_fingerprint_failed",observationFailed);}
        if(!match){if(click!=null)click.poison(entry==null?"received_without_encoded_entry":"received_fingerprint_mismatch",null);connectionPoisoned=true;sent.clear();return;}
        if(click!=null){click.receivedSequence=entry.sequence;click.trace.add("received",entry.sequence,entry.owner==click,entry.packet,null,null,"","");}
        if(entry.owner!=null&&entry.owner==click&&entry.sequence==click.sentSequence)click.received=packet;
    }
    private static JsonObject fingerprint(ServerboundContainerClickPacket packet){
        var out=new JsonObject();out.addProperty("menu",packet.containerId());out.addProperty("state",packet.stateId());
        out.addProperty("slot",packet.slotNum());out.addProperty("button",packet.buttonNum());out.addProperty("input",packet.containerInput().name());
        var slots=new JsonObject();var sorted=new TreeMap<Integer,net.minecraft.network.HashedStack>();packet.changedSlots().forEach(sorted::put);
        sorted.forEach((slot,item)->slots.add(slot.toString(),hashed(item)));out.add("slots",slots);out.add("cursor",hashed(packet.carriedItem()));return out;
    }
    private static JsonObject hashed(net.minecraft.network.HashedStack stack){
        var out=new JsonObject();if(!(stack instanceof net.minecraft.network.HashedStack.ActualItem actual)){out.addProperty("empty",true);return out;}
        out.addProperty("item",net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(actual.item().value()).toString());out.addProperty("count",actual.count());
        var added=new TreeMap<String,Integer>();actual.components().addedComponents().forEach((type,hash)->added.put(net.minecraft.core.registries.BuiltInRegistries.DATA_COMPONENT_TYPE.getKey(type).toString(),hash));
        var json=new JsonObject();added.forEach(json::addProperty);out.add("added",json);var removed=new TreeSet<String>();
        actual.components().removedComponents().forEach(type->removed.add(net.minecraft.core.registries.BuiltInRegistries.DATA_COMPONENT_TYPE.getKey(type).toString()));
        var array=new JsonArray();removed.forEach(array::add);out.add("removed",array);return out;
    }
    private static boolean supported(AbstractContainerMenu menu){
        return menu instanceof net.minecraft.world.inventory.InventoryMenu||menu instanceof net.minecraft.world.inventory.CraftingMenu;
    }
    /** Called immediately around the actual server menu.clicked invocation, never a timer or packet send. */
    public static void serverBefore(ServerPlayer player,ServerboundContainerClickPacket packet){
        var click=observing;if(!serverTraceScope(click,player))return;
        boolean owned=click.packet(player,packet);
        try{
            var view=snapshot(player,click.scope.world);click.trace.add("server_before",click.receivedSequence,owned,fingerprint(packet),null,summary(view,packet.slotNum()),"","");
            if(owned)click.serverBefore=view;
        }catch(RuntimeException failure){click.poison("server_before_snapshot_failed",failure);}
    }
    public static void serverAfter(ServerPlayer player,ServerboundContainerClickPacket packet){
        var click=observing;if(!serverTraceScope(click,player))return;
        boolean owned=click.packet(player,packet);
        try{
            long processed=System.currentTimeMillis();var view=snapshot(player,click.scope.world);
            click.trace.add("server_after",click.receivedSequence,owned,fingerprint(packet),null,summary(view,packet.slotNum()),"","");
            if(owned){click.processedAt=processed;click.processedAfter=view;click.processingAfter=view.deepCopy();click.serverProcessed=true;}
        }catch(RuntimeException failure){click.poison("server_after_snapshot_failed",failure);}
    }
    private static boolean serverTraceScope(Click click,ServerPlayer player){
        return click!=null&&!click.closed&&player.level().getServer()==click.scope.server&&click.scope.server.isSameThread()
            &&player.getUUID().equals(click.scope.player)&&click.scope.dimension.equals(player.level().dimension().identifier().toString());
    }
    public static void refreshServer(Click click){
        if(!click.serverProcessed||click.closed)return;
        click.scope.server.execute(()->{
            var p=click.scope.serverPlayer();
            if(p!=null&&!click.closed&&observing==click&&p.containerMenu.containerId==click.menuId)
                try{click.processedAfter=snapshot(p,click.scope.world);}catch(RuntimeException failure){click.poison("server_refresh_snapshot_failed",failure);}
        });
    }
    /** Complete player inventory is included; stack_data retains all native item components. */
    public static JsonObject snapshot(Player player,String world){
        var menu=player.containerMenu;var out=new JsonObject();out.addProperty("id",menu.containerId);
        out.addProperty("type",menu.getClass().getSimpleName());out.addProperty("state_id",menu.getStateId());
        out.addProperty("quickcraft_status",((InventoryMenuDiagnosticsAccess)menu).kit$getQuickcraftStatus());
        out.add("cursor",stack(player.registryAccess(),menu.getCarried()));var slots=new JsonArray();
        for(int i=0;i<menu.slots.size();i++){var row=stack(player.registryAccess(),menu.getSlot(i).getItem());row.addProperty("slot",i);slots.add(row);}out.add("slots",slots);
        var inventory=new JsonArray();for(int i=0;i<player.getInventory().getContainerSize();i++){
            var row=stack(player.registryAccess(),player.getInventory().getItem(i));row.addProperty("slot",i);inventory.add(row);
        }out.add("inventory",inventory);out.addProperty("player_uuid",player.getUUID().toString());
        out.addProperty("dimension",player.level().dimension().identifier().toString());out.addProperty("world_id",world);
        out.addProperty("observed_at",System.currentTimeMillis());out.addProperty("game_time",player.level().getGameTime());return out;
    }
    private static JsonObject stack(RegistryAccess registries,ItemStack item){
        var out=new JsonObject();out.addProperty("item",item.isEmpty()?"minecraft:air":net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(item.getItem()).toString());
        out.addProperty("count",item.getCount());out.addProperty("max_stack",item.getMaxStackSize());
        out.add("stack_data",ItemStack.OPTIONAL_CODEC.encodeStart(RegistryOps.create(JsonOps.INSTANCE,registries),item.copy()).getOrThrow());return out;
    }
    private static String world(MinecraftServer server){return server.getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize().toString();}
    /** State ids/timestamps are observations; full stacks, menu identity and drag state carry semantics. */
    static boolean same(JsonObject a,JsonObject b){
        if(a==null||b==null)return false;
        for(String key:new String[]{"id","type","quickcraft_status","cursor","slots","inventory"})
            if(!a.has(key)||!b.has(key)||!a.get(key).equals(b.get(key)))return false;
        return true;
    }
    static boolean sameItems(JsonObject a,JsonObject b){
        if(a==null||b==null)return false;
        for(String key:new String[]{"id","type","cursor","slots","inventory"})
            if(!a.has(key)||!b.has(key)||!a.get(key).equals(b.get(key)))return false;
        return true;
    }
    static String classify(boolean processed,JsonObject before,JsonObject predicted,JsonObject server,JsonObject client){
        if(!processed||!same(server,client))return "unknown";
        // A drag reset alone is an actual processed no-effect click, not proof of no dispatch.
        if(sameItems(before,server))return server.get("quickcraft_status").getAsInt()==0?"no_effect":"unknown";
        return samePrediction(predicted,server)?"confirmed":"unknown";
    }
    static boolean samePrediction(JsonObject predicted,JsonObject server){
        if(predicted==null||server==null)return false;
        // Only the virtual recipe result may differ from local prediction. Every
        // real ingredient, cursor and inventory stack must still match exactly.
        String type=server.has("type")?server.get("type").getAsString():"";
        if(!java.util.Set.of("InventoryMenu","CraftingMenu").contains(type))return same(predicted,server);
        var a=predicted.deepCopy();var b=server.deepCopy();
        if(!a.has("slots")||!b.has("slots")||a.getAsJsonArray("slots").isEmpty()||b.getAsJsonArray("slots").isEmpty())return false;
        a.getAsJsonArray("slots").set(0,JsonNull.INSTANCE);b.getAsJsonArray("slots").set(0,JsonNull.INSTANCE);
        return same(a,b);
    }
    public static void probe(Minecraft c,String id,String session,long revision,
                             java.util.function.Supplier<String> currentSession,java.util.function.LongSupplier currentRevision,
                             long expiresAt,Consumer<JsonObject> reply){
        var scope=new Scope(c,session,revision);var client=snapshot(c.player,scope.world);
        scope.server.execute(()->{
            JsonObject server=null;String failure="";
            try{var p=scope.serverPlayer();if(p!=null)server=snapshot(p,scope.world);else failure="Current server player disappeared";}
            catch(RuntimeException error){failure="Server inventory observation failed: "+error.getClass().getSimpleName();}
            final JsonObject observed=server;final String message=failure;
            c.execute(()->{
                boolean valid=System.currentTimeMillis()<=expiresAt&&scope.current(c,currentSession.get(),currentRevision.getAsLong());
                var out=new JsonObject();out.addProperty("protocol",PROTOCOL);out.addProperty("request_id",id);
                out.addProperty("world_session",session);out.addProperty("control_revision",revision);out.addProperty("scope_current",valid);
                out.addProperty("server_observed",valid&&observed!=null);out.addProperty("audit_scope","current_state_only_not_historical_dispatch");
                if(valid&&observed!=null){out.add("client",snapshot(c.player,scope.world));out.add("server",observed);out.add("client_at_request",client);}
                else out.addProperty("error",valid?message:"Inventory probe world, menu or controller changed");
                reply.accept(out);
            });
        });
    }
}
