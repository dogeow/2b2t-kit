package dev.twob2tkit.automation;

import com.google.gson.*;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitKeys;
import dev.twob2tkit.MeteorModules;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.block.EntityBlock;
import net.minecraft.world.level.block.FallingBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import java.lang.reflect.Field;
import java.util.*;
import java.util.function.BooleanSupplier;

/** Owned Meteor Scaffold row, with a pre-placement gate and at most two sent cells. */
public final class ProjectionScaffoldFill implements AutoCloseable {
    /** Implemented only when the required Scaffold.place injection was applied. */
    public interface GateInstalled {}
    enum Outcome { RUNNING,DONE,WAITING }
    private static final Set<String> SPENT=new HashSet<>();
    private static final int ACK_TIMEOUT=100;
    private final ProjectionScaffoldPolicy.Row row;
    private final List<BlockPos> positions;
    private final Set<BlockPos> baseline=new HashSet<>();
    private final Map<BlockPos,BlockState> expected=new HashMap<>();
    private final Map<BlockPos,Attempt> attempts=new LinkedHashMap<>();
    private final AckWindow ackWindow=new AckWindow();
    private final ScaffoldModuleLease scaffold=new ScaffoldModuleLease();
    private final FlightLease flight;
    private final Item item;
    private final String world,requestId,placement;
    private final long revision,damageAt;
    private final float initialHealth;
    private final int inventoryStart;
    private final BooleanSupplier owner;
    private RotationAim.Look look;
    private BlockPos candidate;
    private String failure="",stage="aligning";
    private boolean closed,completed;
    private boolean deferredFlightRestore;
    private int sentCount,confirmedCount,inventoryNow;
    private Vec3 observedPosition,rawVelocity=Vec3.ZERO;
    private long observedMotionTick=Long.MIN_VALUE;
    private double realYStep,realHorizontalStep;

    private static final class Attempt {
        final BlockPos pos;final BlockState state;final long sentTick;
        long ackTick=-1;boolean acknowledged,settled;
        Attempt(BlockPos pos,BlockState state,long tick){this.pos=pos;this.state=state;sentTick=tick;}
    }
    /** Fungible inventory is proved in aggregate; never assigned to individual pending cells. */
    static final class AckWindow {
        private static final class Entry {
            final String expected;final long sentTick;long ack=-1;boolean settled;
            Entry(String expected,long sentTick){this.expected=expected;this.sentTick=sentTick;}
        }
        private final Map<String,Entry> entries=new LinkedHashMap<>();
        private boolean failed;
        private boolean inventoryExact=true;
        private boolean inventoryRecovery;
        private long inventoryExactSince=-1;
        boolean canSend(){return !failed&&inventoryExact&&!inventoryRecovery&&ProjectionScaffoldPolicy.windowAvailable(pending());}
        boolean sent(String target,String expected){return sent(target,expected,0);}
        boolean sent(String target,String expected,long tick){
            if(!canSend()||entries.containsKey(target))return false;
            entries.put(target,new Entry(expected,tick));return true;
        }
        boolean acknowledge(String target,String actual,long tick){
            var entry=entries.get(target);if(entry==null||failed)return false;
            if(!entry.expected.equals(actual)){failed=true;return false;}
            if(entry.ack<0)entry.ack=tick;return true;
        }
        boolean observe(int inventoryStart,int inventoryNow,Map<String,Boolean> currentStates,long tick){
            int delta=inventoryStart-inventoryNow,pending=pending();
            // Only the outstanding, bounded window may have a not-yet-synchronized item delta.
            // Already settled consumption may never roll back; extra consumption is never credited.
            if(failed||inventoryNow<0||pending>2||delta<settled()||delta>entries.size()
                ||entries.size()-delta>pending){failed=true;return false;}
            inventoryExact=delta==entries.size();
            if(!inventoryExact){inventoryRecovery=true;inventoryExactSince=-1;}
            else if(inventoryRecovery&&inventoryExactSince<0)inventoryExactSince=tick;
            for(var pair:entries.entrySet()){
                if(!Boolean.TRUE.equals(currentStates.get(pair.getKey()))){failed=true;return false;}
                var entry=pair.getValue();
                if(!entry.settled&&tick-entry.sentTick>=ACK_TIMEOUT){failed=true;return false;}
                // A server ACK without the exact cumulative inventory remains pending.
                long proofTick=inventoryRecovery?Math.max(entry.ack,inventoryExactSince):entry.ack;
                if(inventoryExact&&entry.ack>=0&&tick-proofTick>=ProjectionScaffoldPolicy.SETTLE_TICKS)entry.settled=true;
            }
            if(inventoryRecovery&&inventoryExact&&pending()==0)inventoryRecovery=false;
            return true;
        }
        boolean inventoryPending(){return (!inventoryExact||inventoryRecovery)&&!failed;}
        boolean settled(String target){var entry=entries.get(target);return entry!=null&&entry.settled;}
        int pending(){int n=0;for(var entry:entries.values())if(!entry.settled)n++;return n;}
        int settled(){return entries.size()-pending();}
    }

    ProjectionScaffoldFill(Minecraft c,JsonObject request,String world,long revision,
                           long damageAt,BooleanSupplier owner)throws Exception {
        this.world=world;this.revision=revision;this.damageAt=damageAt;this.owner=owner;
        requestId=text(request,"id");placement=text(request,"placement_key");
        positions=parsePositions(request);int firstY=positions.getFirst().getY(),firstZ=positions.getFirst().getZ();
        String id=text(request,"expected_item");item=BuiltInRegistries.ITEM.getValue(Identifier.parse(id));
        if(!(item instanceof BlockItem block))throw new IllegalArgumentException("Scaffold fill requires an exact BlockItem");
        row=new ProjectionScaffoldPolicy.Row(positions.getFirst().getX(),positions.getLast().getX(),firstY,firstZ,id);
        if(!ProjectionScaffoldPolicy.rowValid(row,positions.size(),plain(block.getBlock().defaultBlockState(),c.level,positions.getFirst())))
            throw new IllegalArgumentException("Scaffold fill supports one continuous plain-cube X row of at most 128 cells");
        var pick=LitematicaAccess.lockedBuildSelection();
        if(!pick.key().equals(placement))throw new IllegalStateException("Selected locked projection changed");
        for(var pos:positions)if(!pick.contains(pos)||!LitematicaAccess.inVisibleLayer(pos))
            throw new IllegalArgumentException("Scaffold row lies outside the selected visible projection");
        String loading=LitematicaAccess.loadingReason(pick);if(!loading.isEmpty())throw new IllegalStateException(loading);
        if(!GateInstalled.class.isAssignableFrom(Class.forName(ScaffoldModuleLease.MODULE)))
            throw new IllegalStateException("Controlled Scaffold placement gate is not installed; restart with the current host");
        if(c.player.hasInfiniteMaterials()||c.gameMode.getPlayerMode()!=GameType.SURVIVAL||c.player.isInWater()
            ||c.player.isInLava()||c.player.isOnFire()||c.player.isUsingItem()
            ||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty())
            throw new IllegalStateException("Scaffold fill requires a dry idle survival inventory");
        // Start in or near the row corridor; external navigation remains separate and Scaffold OFF.
        if(c.player.getX()<row.minX()-2||c.player.getX()>row.maxX()+3
            ||Math.abs(c.player.getZ()-(row.z()+.5))>2)
            throw new IllegalStateException("Move near the row with Scaffold OFF before starting this bounded controller");
        initialHealth=c.player.getHealth();inventoryStart=inventoryNow=count(c,false);
        int potentialExisting=0;
        for(var pos:positions)if(serverChunk(c,pos)&&block.getBlock().defaultBlockState().equals(c.level.getBlockState(pos)))potentialExisting++;
        if(count(c,true)<positions.size()-potentialExisting)
            throw new IllegalStateException("Prepare enough same-item hotbar stock for all remaining row cells first");
        FlightLease borrowed=null;
        try{
            if(!scaffold.acquire(item))throw new IllegalStateException("Scaffold must be OFF and its exact settings must be leasable: "+scaffold.failure());
            borrowed=new FlightLease();flight=borrowed;
        }catch(Exception failure){scaffold.close();if(borrowed!=null)borrowed.close();throw failure;}
    }

    private static String text(JsonObject request,String key){return request.has(key)?request.get(key).getAsString():"";}
    private static BlockPos coordinates(JsonElement raw){
        if(!raw.isJsonArray()||raw.getAsJsonArray().size()!=3)throw new IllegalArgumentException("Row position needs [x,y,z]");
        int[] n=new int[3];for(int i=0;i<3;i++){
            var value=raw.getAsJsonArray().get(i);
            if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Row coordinates must be integers");
            double d=value.getAsDouble();if(!Double.isFinite(d)||d!=Math.rint(d)||Math.abs(d)>30_000_000)throw new IllegalArgumentException("Invalid row coordinate");n[i]=(int)d;
        }return new BlockPos(n[0],n[1],n[2]);
    }
    private static List<BlockPos> parsePositions(JsonObject request){
        var result=new ArrayList<BlockPos>();
        if(request.has("positions")){
            var array=request.getAsJsonArray("positions");if(array==null||array.isEmpty()||array.size()>512)throw new IllegalArgumentException("Row positions require 1..512 points");
            for(var point:array)result.add(coordinates(point));
        }else{
            var min=coordinates(request.get("min"));var max=coordinates(request.get("max"));
            if(min.getY()!=max.getY()||min.getZ()!=max.getZ()||max.getX()<min.getX()||(long)max.getX()-min.getX()>=128)
                throw new IllegalArgumentException("Row min/max must be one bounded horizontal X line");
            for(int x=min.getX();x<=max.getX();x++)result.add(new BlockPos(x,min.getY(),min.getZ()));
        }
        result.sort(Comparator.comparingInt(BlockPos::getX));
        for(int i=0;i<result.size();i++)if(result.get(i).getX()!=result.getFirst().getX()+i
            ||result.get(i).getY()!=result.getFirst().getY()||result.get(i).getZ()!=result.getFirst().getZ())
            throw new IllegalArgumentException("Row positions must be unique, continuous and share Y/Z");
        return List.copyOf(result);
    }
    private static boolean plain(BlockState state,net.minecraft.world.level.BlockGetter world,BlockPos pos){
        return !state.isAir()&&ConfirmedPlacementPacer.safeSimple(state.getProperties().isEmpty(),state.isCollisionShapeFullBlock(world,pos),
            state.getBlock() instanceof FallingBlock,state.getBlock() instanceof EntityBlock)&&state.getFluidState().isEmpty();
    }
    private static boolean serverChunk(Minecraft c,BlockPos pos){
        var chunk=c.level.getChunkSource().getChunk(pos.getX()>>4,pos.getZ()>>4,ChunkStatus.FULL,false);
        return LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    private int count(Minecraft c,boolean hotbar){
        int total=0,limit=hotbar?9:c.player.getInventory().getContainerSize();
        for(int i=0;i<limit;i++){var stack=c.player.getInventory().getItem(i);if(stack.is(item))total+=stack.getCount();}return total;
    }
    private BlockState expected(Minecraft c,BlockPos pos){
        var projection=LitematicaAccess.schematicWorld();if(projection==null)throw new IllegalStateException("Projection data unavailable");
        var state=projection.getBlockState(pos);
        if(!plain(state,projection,pos)||state.getBlock().asItem()!=item)throw new IllegalStateException("Row projection is not the same exact plain block item");
        var prior=expected.putIfAbsent(pos.immutable(),state);
        if(prior!=null&&!prior.equals(state))throw new IllegalStateException("Projected row state changed");return state;
    }
    private boolean safe(Minecraft c){
        return !closed&&failure.isEmpty()&&owner.getAsBoolean()&&c.player!=null&&c.level!=null&&c.gameMode!=null
            &&c.gameMode.getPlayerMode()==GameType.SURVIVAL&&c.screen==null&&!c.player.isDeadOrDying()
            &&c.player.getHealth()>=initialHealth&&!c.player.isInWater()&&!c.player.isInLava()&&!c.player.isOnFire()
            &&KitClient.config().lastAttackTimeEpochMillis<=damageAt
            &&!c.player.isUsingItem()&&c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty()
            &&!KitKeys.isPhysicallyDown(c,c.options.keyUse)&&!KitKeys.isPhysicallyDown(c,c.options.keyAttack)
            &&scaffold.settingsCurrent()&&flight.current();
    }
    private int pending(){int n=0;for(var attempt:attempts.values())if(!attempt.settled)n++;return n;}
    private Map<String,Boolean> currentStates(Minecraft c){
        var states=new LinkedHashMap<String,Boolean>();
        for(var attempt:attempts.values())states.put(attempt.pos.toShortString(),
            serverChunk(c,attempt.pos)&&attempt.state.equals(c.level.getBlockState(attempt.pos)));
        return states;
    }
    private boolean baselineCurrent(Minecraft c){
        for(var pos:baseline)if(!serverChunk(c,pos)||!Objects.equals(expected.get(pos),c.level.getBlockState(pos)))return false;
        return true;
    }
    private void stopPlacement(Minecraft c){
        if(!scaffold.disableOwned()&&failure.isEmpty())failure="Owned Scaffold could not disable; placement gate remains closed";
        candidate=null;look=null;
        // Guard escape may already own movement and Flight. Never overwrite its ascent.
        if(!AutomationBridge.guardBusy()){release(c);try{flight.speed(0);}catch(Exception ignored){}}
    }
    void pauseBeforeGuard(Minecraft c){stopPlacement(c);}
    void fail(Minecraft c,String reason){if(failure.isEmpty())failure=reason;stopPlacement(c);}
    private boolean bodyClear(Minecraft c,Vec3 step){
        AABB swept=c.player.getBoundingBox().expandTowards(step);
        if(!c.level.noCollision(c.player,swept))return false;
        for(var pos:BlockPos.betweenClosed(BlockPos.containing(swept.minX,swept.minY,swept.minZ),
            BlockPos.containing(swept.maxX-1e-7,swept.maxY-1e-7,swept.maxZ-1e-7))){
            if(!serverChunk(c,pos)||!c.level.getBlockState(pos).getFluidState().isEmpty())return false;
        }return true;
    }
    private void move(Minecraft c,Vec3 error,boolean vertical,double actualSpeed){
        if(!failure.isEmpty())return;
        release(c);look=null;
        Vec3 next=vertical?new Vec3(0,Math.copySign(actualSpeed,error.y),0):new Vec3(error.x,0,error.z).normalize().scale(actualSpeed);
        if(!bodyClear(c,next)){fail(c,"Body collision, fluid or unloaded server chunk on bounded flight step");return;}
        flight.speed(actualSpeed/(vertical?5:10));
        if(vertical){c.options.keyJump.setDown(error.y>0);c.options.keyShift.setDown(error.y<0);}
        else{look=new RotationAim.Look(RotationAim.yawToward(error.x,error.z),0);RotationAim.apply(c.player,look);c.options.keyUp.setDown(true);}
    }
    boolean input(Minecraft c,long tick){
        if(!safe(c)){fail(c,"Scaffold ownership, health, UI or settings changed");return true;}
        observe(c,tick,false);if(!failure.isEmpty()||completed){stopPlacement(c);return true;}
        BlockPos next=null;
        for(var pos:positions){
            if(baseline.contains(pos)||attempts.containsKey(pos))continue;
            if(c.player.position().distanceTo(Vec3.atCenterOf(pos))<=4.3&&serverChunk(c,pos)){
                var wanted=expected(c,pos);var actual=c.level.getBlockState(pos);
                if(wanted.equals(actual)){baseline.add(pos);continue;}
                if(!actual.isAir()){fail(c,"Existing row block differs from the projection; preserved");return true;}
            }
            next=pos;break;
        }
        if(next==null||!ackWindow.canSend()){stage=ackWindow.inventoryPending()?"awaiting_inventory_sync":"awaiting_acks";stopPlacement(c);return true;}
        Vec3 goal=new Vec3(next.getX()+.5,row.y()+1.9,row.z()+.5),error=goal.subtract(c.player.position());
        // Never place while correcting height or the row centreline.
        if(Math.abs(error.z)>.08||c.player.getX()<row.minX()+.31||c.player.getX()>row.maxX()+.69){
            stopPlacement(c);stage="aligning_lane";move(c,error,false,Math.min(.08,Math.hypot(error.x,error.z)/10));return true;
        }
        if(Math.abs(error.y)>.03){stopPlacement(c);stage="aligning_height";move(c,error,true,Math.min(.08,Math.abs(error.y)/10));return true;}
        release(c);look=null;
        var v=c.player.getDeltaMovement();
        if(!ProjectionScaffoldPolicy.motionAllowed(row,c.player.getX(),c.player.getY(),c.player.getZ(),v.x,v.y,v.z,false,false)){
            stopPlacement(c);stage="settling_motion";return true;
        }
        if(count(c,true)==0){fail(c,"Expected hotbar blocks exhausted; no inventory UI takeover");return true;}
        if(!scaffold.enableOwned()){fail(c,"Cannot enable the owned Scaffold settings");return true;}
        stage="filling";
        if(Math.abs(error.x)>.03)move(c,error,false,Math.min(.08,Math.abs(error.x)/5));
        else{release(c);flight.speed(0);}
        return true;
    }
    boolean reapply(Minecraft c){if(closed||look==null||!safe(c))return false;RotationAim.apply(c.player,look);return true;}

    boolean allowCandidate(Minecraft c,BlockPos pos,long tick){
        candidate=null;
        if(!safe(c)){fail(c,"Scaffold candidate no longer owns a safe material lease");return false;}
        if(!baselineCurrent(c)){fail(c,"Preexisting confirmed Scaffold row state changed or unloaded");return false;}
        inventoryNow=count(c,false);
        if(!ackWindow.observe(inventoryStart,inventoryNow,currentStates(c),tick)){fail(c,"Scaffold inventory/window diverged before placement");return false;}
        if(!ackWindow.canSend()){stage=ackWindow.inventoryPending()?"awaiting_inventory_sync":"awaiting_acks";stopPlacement(c);return false;}
        if(!scaffold.activeOwned()||!ProjectionScaffoldPolicy.windowAvailable(pending())||!ProjectionScaffoldPolicy.contains(row,pos.getX(),pos.getY(),pos.getZ()))return false;
        String key=world+'|'+pos.toShortString();if(SPENT.contains(key)||baseline.contains(pos)||attempts.containsKey(pos))return false;
        var v=c.player.getDeltaMovement();boolean shift=c.options.keyShift.isDown(),jump=c.options.keyJump.isDown();
        if(!ProjectionScaffoldPolicy.motionAllowed(row,c.player.getX(),c.player.getY(),c.player.getZ(),v.x,v.y,v.z,shift,jump))return false;
        var predicted=ProjectionScaffoldPolicy.predictedFootTarget(c.player.getX(),c.player.getY(),c.player.getZ(),v.x,v.y,v.z,shift,jump);
        if(!serverChunk(c,pos))return false;
        var wanted=expected(c,pos);var actual=c.level.getBlockState(pos);
        if(wanted.equals(actual)){baseline.add(pos);return false;}
        boolean clear=c.level.getEntities((Entity)null,new AABB(pos),Entity::isAlive).isEmpty();
        if(!ProjectionScaffoldPolicy.candidateAllowed(row,new ProjectionScaffoldPolicy.Point(pos.getX(),pos.getY(),pos.getZ()),predicted,
            true,actual.isAir(),!actual.getFluidState().isEmpty(),clear,plain(wanted,c.level,pos),row.item())||count(c,true)==0)return false;
        candidate=pos.immutable();return true;
    }
    /** Called before any ordinary useItemOn prediction/packet, after Scaffold's native autoswitch. */
    boolean prepareInteraction(Minecraft c,LocalPlayer player,InteractionHand hand,BlockHitResult hit,long tick){
        if(!safe(c)||candidate==null){fail(c,"Unowned block interaction during controlled Scaffold");return true;}
        var held=player.getItemInHand(hand);
        BlockPos placed=new BlockPlaceContext(player,hand,held,hit).getClickedPos();
        if(player!=c.player||held.isEmpty()||!held.is(item)||!(held.getItem() instanceof BlockItem)
            ||!placed.equals(candidate)||!allowCandidate(c,placed,tick)){
            fail(c,"Scaffold send differs from the exact allowed target or held item");return true;
        }
        if(c.player.getEyePosition().distanceTo(hit.getLocation())>c.player.blockInteractionRange()-.2){fail(c,"Scaffold send is out of normal reach");return true;}
        String key=world+'|'+placed.toShortString();
        if(!SPENT.add(key)){fail(c,"Scaffold cell was already attempted; no resend");return true;}
        var wanted=expected(c,placed);
        if(!ackWindow.sent(placed.toShortString(),wanted.toString(),tick)){fail(c,"Scaffold pending window or single-send identity changed");return true;}
        attempts.put(placed.immutable(),new Attempt(placed.immutable(),wanted,tick));sentCount++;candidate=null;
        return false;
    }
    void candidateEnded(){candidate=null;}
    void serverBlock(Minecraft c,BlockPos pos,BlockState packet,boolean applied,long tick){
        var attempt=attempts.get(pos);if(closed||attempt==null||!applied)return;
        if(!safe(c)){fail(c,"Scaffold server update belongs to an expired or unsafe owner");return;}
        if(!attempt.state.equals(packet)){fail(c,"Server corrected or rejected a Scaffold cell; all unsent cells stopped");return;}
        if(!ackWindow.acknowledge(pos.toShortString(),packet.toString(),tick)){fail(c,"Scaffold server acknowledgement identity diverged");return;}
        attempt.acknowledged=true;if(attempt.ackTick<0)attempt.ackTick=tick;
        for(var known:attempts.values())if(!known.state.equals(c.level.getBlockState(known.pos))){
            fail(c,"Known pending Scaffold world state diverged after a server update");return;
        }
    }
    Outcome observe(Minecraft c,long tick,boolean timedOut){
        if(closed||!failure.isEmpty())return Outcome.WAITING;
        if(!safe(c)){fail(c,"Controlled Scaffold ownership or safety changed");return Outcome.WAITING;}
        if(!baselineCurrent(c)){fail(c,"Preexisting confirmed Scaffold row state changed or unloaded");return Outcome.WAITING;}
        if(observedMotionTick!=tick){
            Vec3 position=c.player.position();
            if(observedPosition!=null){Vec3 step=position.subtract(observedPosition);realYStep=step.y;realHorizontalStep=Math.hypot(step.x,step.z);}
            observedPosition=position;rawVelocity=c.player.getDeltaMovement();observedMotionTick=tick;
        }
        inventoryNow=count(c,false);
        if(!ackWindow.observe(inventoryStart,inventoryNow,currentStates(c),tick)){fail(c,"Scaffold ACK window, world states or cumulative inventory diverged");return Outcome.WAITING;}
        for(var attempt:attempts.values()){
            if(!attempt.state.equals(c.level.getBlockState(attempt.pos))){fail(c,"Scaffold world state was corrected; no resend");return Outcome.WAITING;}
            if(!attempt.settled&&ackWindow.settled(attempt.pos.toShortString())){attempt.settled=true;confirmedCount++;}
        }
        if(ackWindow.inventoryPending()){stage="awaiting_inventory_sync";stopPlacement(c);}
        if(baseline.size()+confirmedCount==positions.size()){
            if(pending()!=0||!ProjectionScaffoldPolicy.cumulativeInventoryMatches(inventoryStart,inventoryNow,sentCount)){
                fail(c,"Final Scaffold cumulative inventory proof is incomplete");return Outcome.WAITING;
            }
            for(var pos:positions)if(!serverChunk(c,pos)||!expected(c,pos).equals(c.level.getBlockState(pos))){fail(c,"Final row world verification failed");return Outcome.WAITING;}
            completed=true;stage="confirmed";stopPlacement(c);
            if(!failure.isEmpty()){completed=false;return Outcome.WAITING;}return Outcome.DONE;
        }
        if(timedOut){fail(c,"Controlled Scaffold row timed out with partial progress; no replay");return Outcome.WAITING;}
        return Outcome.RUNNING;
    }
    void moduleToggleObserved(Object module){flight.moduleToggleObserved(module);}
    String failure(){return failure;}
    boolean cleanupPending(){return scaffold.acquired()||deferredFlightRestore;}
    JsonObject snapshot(){
        var out=new JsonObject();out.addProperty("schema",1);out.addProperty("request_id",requestId);out.addProperty("world_session",world);
        out.addProperty("placement_key",placement);out.addProperty("stage",stage);out.addProperty("total",positions.size());
        var bounds=new JsonObject();bounds.addProperty("min_x",row.minX());bounds.addProperty("max_x",row.maxX());bounds.addProperty("y",row.y());bounds.addProperty("z",row.z());bounds.addProperty("item",row.item());out.add("row",bounds);
        out.addProperty("baseline_matched",baseline.size());out.addProperty("new_sent",sentCount);out.addProperty("new_server_confirmed",confirmedCount);
        out.addProperty("pending",pending());out.addProperty("pending_limit",2);out.addProperty("inventory_start",inventoryStart);out.addProperty("inventory_now",inventoryNow);
        out.addProperty("cumulative_inventory_verified",ProjectionScaffoldPolicy.cumulativeInventoryMatches(inventoryStart,inventoryNow,sentCount));
        out.addProperty("inventory_sync_pending",ackWindow.inventoryPending());
        out.addProperty("complete",completed);out.addProperty("failure",failure);out.addProperty("automatic_retry_allowed",false);
        out.addProperty("cleanup_pending",cleanupPending());
        out.addProperty("real_y_step",realYStep);out.addProperty("real_horizontal_step",realHorizontalStep);
        var velocity=new JsonArray();velocity.add(rawVelocity.x);velocity.add(rawVelocity.y);velocity.add(rawVelocity.z);out.add("raw_velocity",velocity);
        out.addProperty("confirmation_scope","current_connection_server_updates_plus_exact_cumulative_fungible_inventory_delta");
        out.addProperty("baseline_scope","preexisting_expected_blocks_in_live_server_chunks_checked_when_reachable");return out;
    }
    static void release(Minecraft c){if(c.options!=null)for(var key:KitKeys.movementKeys(c))key.setDown(false);}
    @Override public void close(){
        if(closed)return;var c=Minecraft.getInstance();stopPlacement(c);scaffold.close();
        if(scaffold.acquired()){failure="Owned Scaffold disable is unconfirmed; hover and candidate gate retained";return;}
        if(AutomationBridge.guardBusy()){deferredFlightRestore=true;return;}
        deferredFlightRestore=false;
        closed=true;flight.close();
    }

    /** Dedicated normal Meteor Flight controls, deliberately independent of the mining flight lease. */
    private static final class FlightLease implements AutoCloseable {
        private final Object module;
        private final List<Borrowed> values=new ArrayList<>();
        private boolean lost,toggling;
        private static final class Borrowed {
            final Object setting,original;Object written;
            Borrowed(Object setting)throws Exception{this.setting=setting;original=read(setting);written=original;}
            void write(Object value)throws Exception{if(!Objects.equals(read(setting),written))throw new IllegalStateException("Flight setting changed externally");set(setting,value);written=value;}
            boolean current()throws Exception{return Objects.equals(read(setting),written);}
            void restore(){try{if(current())set(setting,original);}catch(Exception ignored){}}
        }
        FlightLease()throws Exception{
            Class<?> modules=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
            module=modules.getMethod("get",Class.class).invoke(modules.getMethod("get").invoke(null),Class.forName(MeteorModules.FLIGHT));
            if(module==null)throw new IllegalStateException("Meteor Flight unavailable");
            try{
                for(String name:List.of("mode","speed","verticalSpeedMatch","noSneak","antiKickMode"))values.add(new Borrowed(field(module.getClass(),name).get(module)));
                Object velocity=Arrays.stream(values.get(0).original.getClass().getEnumConstants()).filter(v->((Enum<?>)v).name().equals("Velocity")).findFirst().orElseThrow();
                values.get(0).write(velocity);values.get(1).write(0.0);values.get(2).write(false);values.get(3).write(true);
                Object packet=Arrays.stream(values.get(4).original.getClass().getEnumConstants()).filter(v->((Enum<?>)v).name().equals("Packet")).findFirst().orElseThrow();
                values.get(4).write(packet);
                if(!active()){toggling=true;try{module.getClass().getMethod("toggle").invoke(module);}finally{toggling=false;}}
                if(!active())throw new IllegalStateException("Meteor Flight did not enable");
            }catch(Exception error){close();throw error;}
        }
        boolean active()throws Exception{return Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module));}
        boolean current(){try{if(lost||!active())return false;for(var value:values)if(!value.current())return false;return true;}catch(Exception error){return false;}}
        void speed(double speed){try{if(!current())throw new IllegalStateException("Owned Flight settings changed");values.get(1).write(speed);}catch(Exception error){throw new IllegalStateException("Cannot set controlled flight speed",error);}}
        void moduleToggleObserved(Object changed){if(changed==module&&!toggling)lost=true;}
        public void close(){for(int i=values.size()-1;i>=0;i--)values.get(i).restore();/* Keep Flight enabled for safe hover. */}
        private static Object read(Object setting)throws Exception{return setting.getClass().getMethod("get").invoke(setting);}
        private static void set(Object setting,Object value)throws Exception{setting.getClass().getMethod("set",Object.class).invoke(setting,value);if(!Objects.equals(read(setting),value))throw new IllegalStateException("Flight refused requested setting");}
        private static Field field(Class<?> type,String name)throws Exception{for(Class<?> at=type;at!=null;at=at.getSuperclass())try{var field=at.getDeclaredField(name);field.setAccessible(true);return field;}catch(NoSuchFieldException ignored){}throw new NoSuchFieldException(name);}
    }
}
