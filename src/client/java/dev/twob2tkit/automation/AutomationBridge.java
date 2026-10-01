package dev.twob2tkit.automation;

import com.google.gson.*;
import dev.twob2tkit.*;
import dev.twob2tkit.borer.TunnelBorer;
import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.enchantment.ItemEnchantments;
import net.minecraft.world.item.alchemy.Potions;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.Vec3;
import java.nio.file.*;
import java.util.*;

/** Local, opt-in job files. All game actions execute on the client tick and use normal interactions. */
public final class AutomationBridge {
    private static final Gson JSON=new GsonBuilder().disableHtmlEscaping().create();
    private static String lastId="", statusId="", phase="idle", detail="", op="";
    private static JsonObject active;
    private static ScanJob pendingScan;
    private static final HeartbeatReadCache heartbeatReads=new HeartbeatReadCache();
    private static final StatusFileWriter statusWriter=new StatusFileWriter();
    private static final ExactScanReplyWriter scanReplyWriter=new ExactScanReplyWriter();
    private static final StackSnapshotCache stackSnapshots=new StackSnapshotCache();
    private static final class ScanJob {
        final JsonObject request;final Object level,connection;final String world;final long revision,startedAt;
        final int startedTick;final ScanCursor cursor;final boolean details;final NativeMaterialSession owner;
        final JsonArray rows=new JsonArray();final Path replyPath;int steppedTick=-1;JsonObject terminal;ExactScanReplyWriter.Job replyWrite;long nextIoWarning,nextIoRetry;

        ScanJob(Minecraft c,JsonObject request,ScanCursor cursor){
            this.request=request.deepCopy();this.level=c.level;this.connection=c.getConnection();
            this.world=session(c);this.revision=controlRevision;this.startedAt=System.currentTimeMillis();this.startedTick=ticks;
            this.cursor=cursor;this.details=request.has("details")&&request.get("details").getAsBoolean();
            this.owner=nativeMaterialDispatch?nativeMaterialOwner:null;
            this.replyPath=root(c).resolve("reply-"+safeId(str(request,"id"))+".json");
        }
    }
    private static final SingleBlockMiningConfirmation ordinaryMiningConfirmation=SingleBlockMiningConfirmation.INSTANCE;
    private static JsonObject lastSingleBlockConfirmation,lastPrinterConfirmation;
    private static final TerrainServerConfirmation terrainServerConfirmation=new TerrainServerConfirmation();
    private static final TerrainServerConfirmation dryPavingServerConfirmation=new TerrainServerConfirmation();
    private static long dryPavingConfirmedTick=-1,dryPavingClientAirTick=-1;
    private static final dev.twob2tkit.material.MaterialTaskChannel materialTaskChannel=new dev.twob2tkit.material.MaterialTaskChannel();
    private static final ProjectionBatchScope<BlockPos> projectionBatch=new ProjectionBatchScope<>();
    private static JsonObject rockQuarryProgress;
    private static JsonObject lastSlaughterAttack;
    private static MaterialAirNavigation materialAirNavigation;
    private static JsonObject lastMaterialAirNavigation;
    private static dev.twob2tkit.runtime.engine.BorerMiningConfirmation rockQuarryConfirmation;
    private static NativeMaterialSession nativeMaterialOwner;
    private static MaterialMiningLease materialMiningLease;
    private static String materialMiningOwner="";
    private static boolean materialMiningCleanupPending;
    private static String materialMiningScope(Minecraft c){
        if(c==null||c.player==null||c.level==null||observedLevel!=c.level||supervisionLease==null
                ||!"materials".equals(str(supervisionLease,"kind"))
                ||!worldSession.equals(str(supervisionLease,"world_session"))
                ||!supervisionLease.has("revision")||supervisionLease.get("revision").getAsLong()!=controlRevision)return "";
        return worldSession+"/"+str(supervisionLease,"id");
    }
    private static void releaseMaterialMiningLease(){
        if(materialMiningCleanupPending)return;
        var previous=materialMiningLease;materialMiningLease=null;materialMiningOwner="";
        if(previous!=null){previous.close();if(!previous.failure().isEmpty())KitClient.LOGGER.warn("[Materials] {}",previous.failure());}
    }
    private static void acquireMaterialMiningLease(Minecraft c){
        if(materialMiningCleanupPending)throw new IllegalStateException("Material controls still need cleanup before isolation can be replaced");
        String scope=materialMiningScope(c);
        if(scope.isEmpty())throw new IllegalStateException("Material mining isolation lacks a current lease");
        if(materialMiningLease!=null&&scope.equals(materialMiningOwner)){
            if(!materialMiningLease.ready())throw new IllegalStateException("Material mining module changed");
            return;
        }
        var next=MaterialMiningLease.acquire();
        var previous=materialMiningLease;materialMiningLease=next;materialMiningOwner=scope;
        if(previous!=null)previous.close();
    }
    private static void syncMaterialMiningLease(Minecraft c){
        if(materialMiningCleanupPending)return;
        String scope=materialMiningScope(c);
        if(scope.isEmpty()){releaseMaterialMiningLease();return;}
        if(materialMiningLease==null||!scope.equals(materialMiningOwner)||!materialMiningLease.ready()){
            supervisionLease=null;
            KitClient.stopWork("材料挖掘模块已由用户切换，交还控制");
            releaseMaterialMiningLease();
        }
    }
    /** Only the current material owner suppresses InstantRebreak's already queued callbacks. */
    public static boolean materialMiningPacketBlocked(){
        String scope=materialMiningScope(Minecraft.getInstance());
        return materialMiningLease!=null&&materialMiningLease.packetBlocked(materialMiningCleanupPending||!scope.isEmpty()&&scope.equals(materialMiningOwner));
    }
    private static boolean nativeMaterialDispatch,materialHandoffDispatch;
    private static JsonObject nativeMaterialReadResult;
    private static final MaterialAirRoute materialAirRoute=new MaterialAirRoute();
    private static boolean nativeAirReturnActive;
    private static String nativeAirReturnPhase="idle",nativeAirReturnOriginalOp="";
    private static long nativeAirReturnStarted, nativeAirReturnMovedAt;
    private static double nativeAirReturnLastY;
    private static long controlRevision;
    private static Object observedLevel;
    private static String worldSession="";
    private static boolean survivalArmed, survivalBackground;
    private static int useCount, pathIndex, foodOriginalSlot=-1, foodUseSlot=-1, concretePickupDeadline;
    private static final Set<UUID> concretePreexistingDrops=new HashSet<>();
    private static UUID concreteRetryUuid;
    private static Vec3 concreteRetryPos;
    private static int concreteRetryTick;
    private static SurvivalCraftTask craftTask;
    private static BucketWaterAction bucketWaterTask;
    private static JsonObject lastBucketWater;
    private static MapAutomation.Creation mapCreationTask;
    private static JsonObject lastMapCreation;
    private static final TerrainServerConfirmation airSeedConfirmation=new TerrainServerConfirmation();
    private static ProjectionAirSeed airSeedTask;
    private static JsonObject lastAirSeed;
    private static ProjectionScaffoldFill scaffoldFillTask;
    private static JsonObject lastScaffoldFill;
    private static BuildSupplyTask supplyTask;
    private static JsonObject craftSpec;
    private static int craftRemaining;
    private static JsonObject supervisionLease,lastSafetyEvent,pendingSafety;
    private static GuardReconnectPolicy.Pending pendingGuardReconnect;
    private static GuardReconnectPolicy.Pending disconnectGuardCandidate;
    private static float lastGuardHealth=20;
    private static double lastGuardX,lastGuardZ;
    private static String ownedBorerSession="";
    private static int pendingSafetyTick;
    private static long pendingPauseSince;
    private static boolean restoreAutoReconnect;
    /** True only while an in-process material child is entering the existing dispatcher. */
    public static boolean internalDispatch(){
		return nativeMaterialDispatch||materialHandoffDispatch;
	}
    /** Read-only launch scope for the Kit material-job UI; does not acquire a second lease. */
    public static JsonObject materialJobContext(Minecraft c){
        if(c.player==null||c.level==null||c.gameMode==null||c.player.isDeadOrDying())
            throw new IllegalStateException("请先进入世界并确认角色存活");
        if(dev.twob2tkit.combat.EmergencyExit.held(c))
            throw new IllegalStateException("安全离线锁仍开启，请先处理角色安全并解除锁");
        if(KitKeys.manualMovementDown(c))throw new IllegalStateException("请先松开移动按键，再开始材料作业");
        if(c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<8)
            throw new IllegalStateException("生命或饥饿值不足，请先恢复后再开始");
        if(c.player==null||c.level==null||c.gameMode==null||c.player.isDeadOrDying()
                ||c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL
                ||dev.twob2tkit.combat.EmergencyExit.held(c)||KitKeys.manualMovementDown(c)
                ||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<8
                ||active!=null||nativeMaterialOwner!=null||KitClient.anyAfkAuto()
                ||supervisionLease!=null&&!str(supervisionLease,"kind").equals("parking")
                ||c.player.containerMenu!=c.player.inventoryMenu
                ||c.screen!=null&&!c.screen.getClass().getName().startsWith("dev.twob2tkit."))
            throw new IllegalStateException("其他任务或物品界面仍在占用，请先结束后再开始材料作业");
        JsonObject result=new JsonObject();result.addProperty("world_session",session(c));
        result.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);
        result.addProperty("dimension",c.level.dimension().identifier().toString());
        result.addProperty("expected_revision",controlRevision);
        result.add("start_pos",JSON.toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));
        return result;
    }
    public static String materialJobWorldSession(Minecraft c){return session(c);}
    private static JsonObject materialTaskReply(Minecraft c,JsonObject request){
        var reply=new JsonObject();reply.addProperty("op",request.has("op")&&request.get("op").isJsonPrimitive()&&request.getAsJsonPrimitive("op").isString()?request.get("op").getAsString():"");
        try{
            var command=dev.twob2tkit.material.MaterialTaskProtocol.parse(request);
            if(command.op().equals("material_task_status")){
                reply.add("material_task",dev.twob2tkit.material.MaterialJobs.snapshot(command.jobId()));
            }else{
                var context=new JsonObject();context.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);
                context.addProperty("dimension",c.level==null?"":c.level.dimension().identifier().toString());
                context.addProperty("world_session",session(c));context.addProperty("expected_revision",controlRevision);
                dev.twob2tkit.material.MaterialTaskProtocol.requireScope(request,context,System.currentTimeMillis(),
                    c.player!=null&&c.level!=null&&c.gameMode!=null&&!c.player.isDeadOrDying(),KitKeys.manualMovementDown(c));
                if(command.op().equals("material_task_start")){
                    // Shared lifecycle checks health, lock, input, UI, existing lease and process ownership.
                    materialJobContext(c);
                    if(command.mode().equals("projection")){
                        if(!command.placementKey().equals(dev.twob2tkit.builder.LitematicaAccess.lockedBuildSelection().key()))throw new IllegalStateException("Selected locked projection changed");
                        dev.twob2tkit.material.MaterialJobs.startProjection(c,KitClient.config());
                    }else dev.twob2tkit.material.MaterialJobs.startItem(c,KitClient.config(),command.item(),command.count());
                }else{
                    dev.twob2tkit.material.MaterialJobs.control(c,command.jobId(),command.op().substring("material_task_".length()));
                }
                reply.add("material_task",dev.twob2tkit.material.MaterialJobs.snapshot());
            }
            reply.addProperty("phase","done");reply.addProperty("detail","Material task request accepted; inspect material_task for actual completion");
        }catch(RuntimeException failure){
            reply.addProperty("phase","error");reply.addProperty("detail",failure.getMessage()==null?failure.getClass().getSimpleName():failure.getMessage());
            reply.add("material_task",dev.twob2tkit.material.MaterialJobs.snapshot());
        }
        reply.addProperty("world_session",session(c));reply.addProperty("control_revision",controlRevision);reply.addProperty("observed_at",System.currentTimeMillis());return reply;
    }
    private static void pollMaterialTasks(Minecraft c){
        try{materialTaskChannel.tick(root(c),request->materialTaskReply(c,request));}
        catch(Exception failure){KitClient.LOGGER.warn("[Materials] command reply could not be persisted: {}",failure.getClass().getSimpleName());}
    }

    private static ProjectionBatchScope.Owner projectionBatchOwner(Minecraft c,String key){
        if(c.player==null||c.level==null||supervisionLease==null||!str(supervisionLease,"kind").equals("materials")
                ||!supervisionLease.has("revision")||supervisionLease.get("revision").getAsLong()!=controlRevision
                ||!str(supervisionLease,"world_session").equals(session(c)))return null;
        return new ProjectionBatchScope.Owner(str(supervisionLease,"id"),str(supervisionLease,"job_session"),session(c),key);
    }
    /** Pure gate used inside native printer callbacks; never destroys that callback's singleton. */
    public static boolean projectionBatchCurrent(Minecraft c){
        if(!projectionBatch.active())return true;
        try{return projectionBatch.current(projectionBatchOwner(c,dev.twob2tkit.builder.LitematicaAccess.buildSelection().key()));}
        catch(RuntimeException ignored){return false;}
    }
    /** Invalidating a mask stops its automatic placer before restoring the unrestricted default. */
    public static boolean validateProjectionBatch(Minecraft c){
        if(projectionBatchCurrent(c))return true;
        ProfessionalPrinter.stop(c,true);
        KitClient.buildJob().stop(c,"施工批次的材料任务、世界或投影已改变");
        projectionBatch.reset();return false;
    }
    public static boolean projectionBatchAllows(Minecraft c,BlockPos target){
        if(!projectionBatch.active())return true;
        // The tick/proposal gates validate the live selected key once, not once per model cell.
        return target!=null&&projectionBatch.allows(projectionBatchOwner(c,projectionBatch.owner().projection()),target);
    }
    public static boolean projectionBatchFeetAllowed(double feetY){return projectionBatch.allowsFeet(feetY);}
    public static boolean projectionBatchStationAllowed(int feetY){return projectionBatch.allowsStation(feetY);}
    private static boolean boundedPrinterComplete(Minecraft c){
        return active!=null&&currentMaterialRequest(c,active)&&projectionBatch.active()
            &&projectionBatch.count()>0&&projectionBatchCurrent(c)
            &&ProfessionalPrinter.batchServerConfirmed(projectionBatch.positions());
    }
    private static JsonObject projectionBatchSnapshot(){
        var out=new JsonObject();out.addProperty("protocol",ProjectionBatchScope.PROTOCOL);
        out.addProperty("active",projectionBatch.active());out.addProperty("count",projectionBatch.count());
        if(projectionBatch.minFeetY()!=null)out.addProperty("min_feet_y",projectionBatch.minFeetY());
        if(projectionBatch.active()){out.addProperty("placement_key",projectionBatch.owner().projection());out.addProperty("task_session",projectionBatch.owner().task());}
        return out;
    }
    private static void changeProjectionBatch(Minecraft c,JsonObject r,boolean clear){
        externalMaterialScope(c,r);
        ProjectionBatchScope.request(ProfessionalPrinter.batchGateAvailable(),
            active==null&&!KitClient.buildJob().isActive()&&!ProfessionalPrinter.owned(),currentMaterialRequest(c,r),
            r.get("expected_revision").getAsLong(),controlRevision,r.get("expires_at").getAsLong()-System.currentTimeMillis());
        var pick=dev.twob2tkit.builder.LitematicaAccess.buildSelection();
        if(!pick.key().equals(str(r,"placement_key")))throw new IllegalStateException("Selected projection changed before projection batch update");
        var owner=projectionBatchOwner(c,pick.key());
        if(clear){projectionBatch.clear(owner);return;}
        String loading=dev.twob2tkit.builder.LitematicaAccess.loadingReason(pick);
        if(!loading.isEmpty())throw new IllegalStateException(loading);
        var model=dev.twob2tkit.builder.LitematicaAccess.schematicWorld();
        if(model==null)throw new IllegalStateException("Projection model is unavailable");
        var points=r.getAsJsonArray("positions");
        if(points==null||points.size()>ProjectionBatchScope.MAX_POSITIONS)throw new IllegalArgumentException("Projection batch positions must contain 0..2048 coordinates");
        Integer minFeetY=null;
        if(r.has("min_feet_y")){
            var raw=r.get("min_feet_y");
            if(!raw.isJsonPrimitive()||!raw.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("min_feet_y must be an integer");
            minFeetY=ProjectionBatchScope.minimumFeet(raw.getAsDouble(),pick.min().getY(),pick.max().getY());
        }
        var positions=new ArrayList<BlockPos>();
        for(var raw:points){
            if(!raw.isJsonArray()||raw.getAsJsonArray().size()!=3)throw new IllegalArgumentException("Projection batch coordinates require [x,y,z]");
            var xyz=raw.getAsJsonArray();int[] values=new int[3];
            for(int i=0;i<3;i++){
                var value=xyz.get(i);
                if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Projection batch coordinates must be integers");
                double number=value.getAsDouble();
                if(!Double.isFinite(number)||number!=Math.rint(number)||number<Integer.MIN_VALUE||number>Integer.MAX_VALUE)throw new IllegalArgumentException("Projection batch coordinates must be finite integers");
                values[i]=(int)number;
            }
            positions.add(new BlockPos(values[0],values[1],values[2]));
        }
        projectionBatch.set(owner,positions,p->pick.contains(p)&&dev.twob2tkit.builder.LitematicaAccess.inVisibleLayer(p)
            &&c.level.hasChunkAt(p)&&!model.getBlockState(p).isAir()&&!model.getBlockState(p).is(net.minecraft.world.level.block.Blocks.STRUCTURE_VOID),minFeetY);
    }

    /** UI stop applies only to its still-current external material task; leave PvE safety armed. */
    public static void materialJobCancel(Minecraft c,String taskSession,String reason){
        if(c.player==null||c.level==null||supervisionLease==null||nativeMaterialOwner!=null
                ||!str(supervisionLease,"kind").equals("materials")
                ||!RockQuarryPolicy.ownsCancel(taskSession,str(supervisionLease,"job_session"),
                    str(supervisionLease,"world_session"),session(c),supervisionLease.get("revision").getAsLong(),controlRevision)
                ||active!=null&&!str(active,"task_session").equals(taskSession))return;
        String stoppedId=active==null?"":str(active,"id");
        boolean previous=dispatching;dispatching=true;
        try{
            KitClient.stopWork(reason==null?"材料作业已暂停":reason);
            if(supervisionLease!=null)supervisionLease.addProperty("revision",controlRevision);
            if(!stoppedId.isEmpty())statusId=stoppedId;
        }finally{dispatching=previous;writeStatus(c);}
    }
    private static final String AUTO_RECONNECT="meteordevelopment.meteorclient.systems.modules.misc.AutoReconnect";
    private static void suspendAutoReconnect(){restoreAutoReconnect|=MeteorModules.isActive(AUTO_RECONNECT);MeteorModules.disable(AUTO_RECONNECT);}
    public static void joined(){try{dev.twob2tkit.combat.GuardFoodLease.recover(Minecraft.getInstance());}catch(IllegalStateException e){KitClient.LOGGER.warn("Food settings recovery unavailable: {}",e.getMessage());}if(dev.twob2tkit.combat.EmergencyExit.held(Minecraft.getInstance())){restoreAutoReconnect=false;dev.twob2tkit.combat.EmergencyExit.joined(Minecraft.getInstance());return;}if(restoreAutoReconnect){restoreAutoReconnect=false;if(!MeteorModules.isActive(AUTO_RECONNECT))MeteorModules.enable(AUTO_RECONNECT);}}
    private static long lastSupervisionHeartbeat;
    private static final dev.twob2tkit.builder.QuietLogoutWindow logoutQuiet=new dev.twob2tkit.builder.QuietLogoutWindow();
    private static void attachSupervision(Minecraft c,JsonObject r) throws Exception {
        String id=str(r,"supervision_lease");safeId(id);
        if(supervisionLease!=null && !str(supervisionLease,"id").equals(id))throw new IllegalStateException("Another supervisor owns this job");
        var job=KitClient.buildJob().snapshot();String expected=str(r,"job_session");
        if(!KitClient.buildJob().supervisionScopeCurrent(c) || KitKeys.manualMovementDown(c))throw new IllegalStateException("Supervisor world, placement or manual control changed");
        if(!expected.isEmpty() && !expected.equals(str(job,"session")))throw new IllegalStateException("Supervisor job changed");
        if(!job.get("active").getAsBoolean() && !Set.of("missing_materials","blocked","complete").contains(str(job,"outcome")))throw new IllegalStateException("No active or material-waiting job to supervise");
        supervisionLease=new JsonObject();supervisionLease.addProperty("id",id);supervisionLease.addProperty("world_session",session(c));supervisionLease.addProperty("job_session",str(job,"session"));
        supervisionLease.addProperty("remote_finish",str(r,"remote_finish").equals("guard")?"guard":"disconnect");lastSupervisionHeartbeat=System.currentTimeMillis();logoutQuiet.reset(lastSupervisionHeartbeat);armPveGuard(c);
    }
    private static void safetyReceipt(Minecraft c,JsonObject receipt) throws Exception {
        save(root(c).resolve("supervision-receipt-"+safeId(str(receipt,"lease"))+".json"),receipt);
        lastSafetyEvent=receipt.deepCopy();lastSafetyEvent.remove("snapshot");
    }
    private static void confirmSafety(Minecraft c){
        if(pendingSafety==null)return;
        try{
            boolean local=str(pendingSafety,"action").equals("PAUSE_LOCAL");
            boolean disconnected=c.player==null || c.level==null;
            if(KitKeys.manualMovementDown(c)){pendingSafety=null;return;}
            if(local && c.isPaused()){
                if(pendingPauseSince==0)pendingPauseSince=System.currentTimeMillis();
                if(System.currentTimeMillis()-pendingPauseSince<3000)return;
            }else pendingPauseSince=0;
            if(local?c.isPaused():disconnected){
                pendingSafety.addProperty("confirmed",true);pendingSafety.addProperty("confirmed_at",System.currentTimeMillis());
                pendingSafety.addProperty("game_paused",c.isPaused());safetyReceipt(c,pendingSafety);pendingSafety=null;return;
            }
            if(KitKeys.manualMovementDown(c)){pendingSafety=null;return;}
            if(local && ticks-pendingSafetyTick<=100){
                if(ticks%5==0)c.setScreen(new net.minecraft.client.gui.screens.PauseScreen(true));
            }else if(ticks-pendingSafetyTick>100){
                var retry=pendingSafety;pendingSafety=null;KitClient.safeLogout(c,"托管暂停未确认，保存并退出");
                retry.addProperty("action","LOGOUT");pendingSafety=retry;pendingSafetyTick=ticks;
            }
        }catch(Exception e){pendingSafety=null;KitClient.safeLogout(c,"托管安全收尾确认失败");}
    }
    /** Network disconnect is authoritative and fires before ordinary cleanup clears the lease. */
    public static void disconnected(Minecraft c){
        materialMiningCleanupPending=false;releaseMaterialMiningLease();
        ProfessionalPrinter.stop(c,true);projectionBatch.reset();
        disconnectGuardCandidate=null;
        if(guardArmed() && pveOnly() && !dev.twob2tkit.combat.EmergencyExit.held(c)){
            var scope=guardScope;
            float health=c.player==null?lastGuardHealth:c.player.getHealth();
            double x=c.player==null?lastGuardX:c.player.getX(),z=c.player==null?lastGuardZ:c.player.getZ();
            disconnectGuardCandidate=GuardReconnectPolicy.capture(true,true,MeteorModules.isActive(AUTO_RECONNECT),
                health,str(scope,"server"),str(scope,"dimension"),x,z,System.currentTimeMillis());
        }
        if(pendingSafety==null || !str(pendingSafety,"action").equals("LOGOUT"))return;
        try{
            pendingSafety.addProperty("confirmed",true);pendingSafety.addProperty("confirmed_at",System.currentTimeMillis());
            pendingSafety.addProperty("confirmation","network_disconnect_event");safetyReceipt(c,pendingSafety);
        }catch(Exception e){org.slf4j.LoggerFactory.getLogger("twob2tkit").warn("Could not persist supervisor disconnect confirmation",e);}
        pendingSafety=null;
    }
    public static void afterDisconnectCleanup(){
        materialMiningCleanupPending=false;releaseMaterialMiningLease();
		SnowSeedExpedition.clearAll();
        projectionBatch.reset();
        pendingGuardReconnect=disconnectGuardCandidate;
        disconnectGuardCandidate=null;
        if(nativeMaterialOwner!=null){nativeMaterialOwner.closed=true;nativeMaterialOwner=null;}
        if(nativeAirReturnActive&&nativeAirReturnPhase.equals("ascending"))nativeAirReturnPhase="disconnected";
        nativeAirReturnActive=false;
        materialAirRoute.clearRoute();
    }
    public static void userTaskStarting(Minecraft c){
        if(!internalDispatch()&&supervisionLease!=null&&Set.of("materials","parking").contains(str(supervisionLease,"kind"))){supervisionLease=null;cancelWork(c,"用户切换自动任务");releaseMaterialMiningLease();}
    }
	private static void syncMaterialRevision(JsonObject request){
		if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")
				||!str(supervisionLease,"world_session").equals(str(request,"world_session"))
				||!str(supervisionLease,"job_session").equals(str(request,"task_session")))return;
		supervisionLease.addProperty("revision",controlRevision);
		request.addProperty("expected_revision",controlRevision);
		if(nativeMaterialOwner!=null&&nativeMaterialOwner.world.equals(str(supervisionLease,"world_session"))
				&&nativeMaterialOwner.lease.equals(str(supervisionLease,"id"))
				&&nativeMaterialOwner.job.equals(str(supervisionLease,"job_session")))
			nativeMaterialOwner.revision=controlRevision;
	}
	private static void stopWorkForScript(JsonObject request,boolean retainMaterial){
		try{KitClient.stopWork("切换到脚本任务");}
		finally{if(retainMaterial)syncMaterialRevision(request);}
	}
    static NativeMaterialSession nativeMaterialOpen(Minecraft c,Vec3 parkTarget){
        boolean resumeParking=c.player!=null&&c.level!=null&&supervisionLease!=null
            &&MaterialJobControlPolicy.resumableParking(str(supervisionLease,"kind"),str(supervisionLease,"world_session"),session(c),
                supervisionLease.has("revision")?supervisionLease.get("revision").getAsLong():-1,controlRevision,
                highGuardPark(c,supervisionLease),guardArmed()&&pveOnly(),guardBusy);
        if(c.player==null||c.level==null||c.gameMode==null||parkTarget==null
                ||c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL
                ||!c.level.dimension().equals(net.minecraft.world.level.Level.OVERWORLD)
                ||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<18
                ||KitKeys.manualMovementDown(c)||dev.twob2tkit.combat.EmergencyExit.held(c)
                ||active!=null||supervisionLease!=null&&!resumeParking||nativeMaterialOwner!=null
                ||KitClient.anyAfkAuto()||c.player.containerMenu!=c.player.inventoryMenu)
            throw new IllegalStateException("Another controller, safety lock, or player interface owns material work");
        BlockPos park=BlockPos.containing(parkTarget);
        if(!Double.isFinite(parkTarget.x)||!Double.isFinite(parkTarget.y)
                ||!Double.isFinite(parkTarget.z)||!c.level.hasChunkAt(park)
                ||parkTarget.y-c.level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING,
                    park.getX(),park.getZ())<20)
            throw new IllegalArgumentException("A loaded high guard park is required");
        String job="native-material-"+UUID.randomUUID().toString().replace("-","");
        String lease="native-lease-"+UUID.randomUUID().toString().replace("-","");
        var owner=new NativeMaterialSession(job,lease,session(c),controlRevision,parkTarget);
        var scope=new JsonObject();scope.addProperty("id",lease);scope.addProperty("kind","materials");
        scope.addProperty("job_session",job);scope.addProperty("world_session",owner.world);
        scope.addProperty("revision",controlRevision);scope.addProperty("remote_finish","guard");
        scope.add("park_target",JSON.toJsonTree(new double[]{parkTarget.x,parkTarget.y,parkTarget.z}));
        JsonObject previousLease=supervisionLease;
        supervisionLease=scope;lastSupervisionHeartbeat=System.currentTimeMillis();
        logoutQuiet.reset(lastSupervisionHeartbeat);
        try{armPveGuard(c);acquireMaterialMiningLease(c);nativeMaterialOwner=owner;}
        catch(RuntimeException failure){supervisionLease=previousLease;releaseMaterialMiningLease();if(previousLease==null)disarmGuard(c);throw failure;}
        return owner;
    }
    private static void nativeMaterialCheck(NativeMaterialSession owner,Minecraft c){
        syncMaterialMiningLease(c);
        if(materialMiningCleanupPending)throw new IllegalStateException("Native material control cleanup remains unconfirmed");
        if(owner==null||owner.closed||owner!=nativeMaterialOwner||c.player==null||c.level==null
                ||dev.twob2tkit.combat.EmergencyExit.held(c)
                ||!owner.world.equals(session(c))||owner.revision!=controlRevision
                ||supervisionLease==null||!str(supervisionLease,"kind").equals("materials")
                ||!owner.lease.equals(str(supervisionLease,"id"))
                ||!owner.job.equals(str(supervisionLease,"job_session"))
                ||supervisionLease.get("revision").getAsLong()!=controlRevision
                ||!guardArmed()||!pveOnly()||KitKeys.manualMovementDown(c)){
            if(owner!=null)owner.closed=true;
            if(nativeMaterialOwner==owner)nativeMaterialOwner=null;
            throw new IllegalStateException("Native material session lost world, revision, guard or manual control");
        }
        owner.lastTouch=System.currentTimeMillis();
    }
	private static void nativeMaterialTickCheck(Minecraft c){
		NativeMaterialSession owner=nativeMaterialOwner;
		if(owner==null)return;
		try{nativeMaterialCheck(owner,c);}
		catch(IllegalStateException lost){
			String id=owner.pendingId,lossDetail="native material ownership lost; task stopped safely";
			boolean ownsActive=active!=null&&id!=null&&str(active,"id").equals(id);
			if(ownsActive){
				if(op.equals("navigate")&&KitClient.controller()!=null)
					KitClient.controller().stop(c,"本机材料控制权失效");
				releaseWalk(c);phase="waiting";detail=lossDetail;
			}
			boolean ownsLease=supervisionLease!=null&&owner.lease.equals(str(supervisionLease,"id"));
			if(ownsLease)
				supervisionLease=null;
			owner.closed=true;owner.queued=null;
			if(nativeMaterialOwner==owner)nativeMaterialOwner=null;
			if(ownsActive)try{KitClient.stopWork(lossDetail);}
			catch(RuntimeException cleanup){lossDetail+="; cleanup="+cleanup.getClass().getSimpleName();}
			if(active!=null&&id!=null&&str(active,"id").equals(id))active=null;
			phase="waiting";detail=lossDetail;
			if(id!=null)owner.immediate=nativeMaterialReceipt(c,id,"waiting",lossDetail);
			writeStatus(c);
		}
	}
    private static void nativeMaterialLoaded(Minecraft c,String command,JsonObject request){
        if(Set.of("mine_block","approach_block").contains(command)){
            JsonArray p=request.getAsJsonArray("pos");
            if(p==null||p.size()!=3||!c.level.hasChunkAt(new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt())))
                throw new IllegalArgumentException("Material target chunk is not loaded");
        }
        if(Set.of("navigate","walk","air_return_set").contains(command)
                &&!request.has("snow_expedition_token")){
            JsonArray p=request.getAsJsonArray("target");
            if(p==null||p.size()!=3||!c.level.hasChunkAt(BlockPos.containing(
                    p.get(0).getAsDouble(),p.get(1).getAsDouble(),p.get(2).getAsDouble())))
                throw new IllegalArgumentException("Material waypoint chunk is not loaded");
        }
    }
    private static JsonObject nativeMaterialReceipt(Minecraft c,String id,String outcome,String message){
        JsonObject result=snapshot(c);result.addProperty("id",id);result.addProperty("phase",outcome);
        if(lastSlaughterAttack!=null&&id.equals(str(lastSlaughterAttack,"id"))
                &&session(c).equals(str(lastSlaughterAttack,"world_session")))
            result.add("slaughter_attack",lastSlaughterAttack.deepCopy());
        attachTerminalConfirmation(c,result,id);
        result.addProperty("phase",outcome);
        result.addProperty("detail",message);result.addProperty("world_session",session(c));
        result.addProperty("control_revision",controlRevision);return result;
    }
    static String nativeMaterialSubmit(NativeMaterialSession owner,Minecraft c,String command,JsonObject params){
        nativeMaterialCheck(owner,c);
        if(owner.pendingId!=null||active!=null)throw new IllegalStateException("Native material child is already running");
        if(!Set.of("guard","select_item","snapshot","scan","scan_snow_biomes","snow_seed_candidates","air_return_set","mine_block","rock_quarry_batch",
                "walk","navigate","collect_item","approach_block","bucket_fill","bucket_place","material_slaughter_attack").contains(command))
            throw new IllegalArgumentException("Native material command is not allowed: "+command);
        JsonObject request=params==null?new JsonObject():params.deepCopy();
        for(String protectedKey:List.of("id","op","task_session","server","dimension","site",
                "world_session","expected_revision","expires_at","background_ok"))
            if(request.has(protectedKey))throw new IllegalArgumentException("Reserved material request field: "+protectedKey);
        nativeMaterialLoaded(c,command,request);
        String id="native-child-"+UUID.randomUUID().toString().replace("-","");
        request.addProperty("id",id);request.addProperty("op",command);
        request.addProperty("task_session",owner.job);
        request.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);
        request.addProperty("dimension",c.level.dimension().identifier().toString());
        request.add("site",JSON.toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));
        request.addProperty("world_session",owner.world);
        request.addProperty("expected_revision",controlRevision);
        request.addProperty("expires_at",System.currentTimeMillis()+5000);
        request.addProperty("background_ok",true);
        if(command.equals("guard"))request.addProperty("pve_only",true);
        owner.pendingId=id;owner.immediate=null;owner.queued=request;
        return id;
    }
    private static void nativeMaterialRunQueued(Minecraft c){
        NativeMaterialSession owner=nativeMaterialOwner;
        if(owner==null||owner.queued==null||interfacePaused(c))return;
        JsonObject request=owner.queued;owner.queued=null;
        try{nativeMaterialCheck(owner,c);}catch(IllegalStateException lost){return;}
        // This in-process child has never dispatched while the screen was open.
        // Revalidate its exact live owner before starting its short action TTL.
        request.addProperty("expires_at",System.currentTimeMillis()+5000);
        String id=str(request,"id");
        String oldLast=lastId;
        boolean wasDispatching=dispatching;
        nativeMaterialDispatch=true;dispatching=true;lastId=id;
        nativeMaterialReadResult=null;
        try{
            dispatch(c,request);
            if(nativeMaterialOwner==owner&&supervisionLease!=null){
                supervisionLease.addProperty("revision",controlRevision);owner.revision=controlRevision;
            }
            if(nativeMaterialReadResult!=null){
                owner.immediate=nativeMaterialReadResult;
                if(!owner.immediate.has("phase"))owner.immediate.addProperty("phase","done");
                if(!owner.immediate.has("detail"))owner.immediate.addProperty("detail","native material read completed");
            }else if(pendingScan==null||!str(pendingScan.request,"id").equals(id)){
                if(active==null||!str(active,"id").equals(id))owner.immediate=nativeMaterialReceipt(c,id,phase,detail);
            }
        }catch(Exception failure){
            if(active!=null&&str(active,"id").equals(id)){
                KitClient.stopWork("本机材料子任务参数无效");
                if(supervisionLease!=null){supervisionLease.addProperty("revision",controlRevision);owner.revision=controlRevision;}
            }
            owner.immediate=nativeMaterialReceipt(c,id,"error",failure.getMessage());
        }finally{
            lastId=oldLast;dispatching=wasDispatching;nativeMaterialDispatch=false;
            nativeMaterialReadResult=null;writeStatus(c);
        }
    }
    static JsonObject nativeMaterialPoll(NativeMaterialSession owner,Minecraft c){
		if(owner!=null&&owner.closed&&owner.immediate!=null){
			JsonObject result=owner.immediate;owner.immediate=null;owner.pendingId=null;return result;
		}
        nativeMaterialCheck(owner,c);
        if(owner.pendingId==null)return null;
        if(owner.queued!=null)return null;
        if(pendingScan!=null&&pendingScan.owner==owner&&owner.pendingId.equals(str(pendingScan.request,"id")))return null;
        if(owner.immediate!=null){JsonObject result=owner.immediate;owner.immediate=null;owner.pendingId=null;return result;}
        if(active!=null&&str(active,"id").equals(owner.pendingId))return null;
        if(!Set.of("done","waiting","stopped","error").contains(phase))return null;
        JsonObject result=nativeMaterialReceipt(c,owner.pendingId,phase,detail);
        owner.pendingId=null;return result;
    }
    static JsonObject nativeMaterialSnapshot(NativeMaterialSession owner,Minecraft c){
        nativeMaterialCheck(owner,c);
        JsonObject state=snapshot(c);state.addProperty("native_material_job",owner.job);
        state.addProperty("native_material_busy",owner.busy());return state;
    }
    static void nativeMaterialInterrupt(NativeMaterialSession owner,Minecraft c,String reason){
        nativeMaterialCheck(owner,c);
        if(owner.pendingId!=null&&owner.queued!=null){
            owner.queued=null;
            owner.immediate=nativeMaterialReceipt(c,owner.pendingId,"waiting","queued material child interrupted: "+reason);
            return;
        }
        if(pendingScan!=null&&pendingScan.owner==owner){finishScan(c,"waiting","native scan interrupted: "+reason);return;}
        if(owner.pendingId==null||active==null||!str(active,"id").equals(owner.pendingId))return;
        boolean wasDispatching=dispatching,wasNative=nativeMaterialDispatch;
        dispatching=true;nativeMaterialDispatch=true;
        try{
            KitClient.stopWork("本机材料子任务中断："+reason);
            if(supervisionLease!=null){supervisionLease.addProperty("revision",controlRevision);owner.revision=controlRevision;}
            owner.immediate=nativeMaterialReceipt(c,owner.pendingId,"waiting","native material child interrupted: "+reason);
        }finally{dispatching=wasDispatching;nativeMaterialDispatch=wasNative;}
    }
    static void nativeMaterialFinish(NativeMaterialSession owner,Minecraft c,boolean keepGuard){
        nativeMaterialCheck(owner,c);
        if(owner.pendingId!=null||active!=null)throw new IllegalStateException("Finish the owned material child first");
        JsonObject lease=supervisionLease;
        if(keepGuard){
            BlockPos here=c.player.blockPosition();
            if(c.player.isUnderWater()||c.player.getHealth()<19
                    ||!c.level.hasChunkAt(here)||!MeteorModules.isActive(MeteorModules.FLIGHT)
                    ||c.player.getY()-c.level.getHeight(
                        net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING,
                        here.getX(),here.getZ())<20)
                throw new IllegalStateException("Remain in the owned material session until the current column is a verified high park");
            supervisionLease.add("park_target",JSON.toJsonTree(new double[]{
                c.player.getX(),c.player.getY(),c.player.getZ()}));
            if(!highGuardPark(c,supervisionLease))
                throw new IllegalStateException("Current high park was not confirmed");
        }
        nativeMaterialOwner=null;owner.closed=true;projectionBatch.reset();
        if(keepGuard){
            boolean previous=nativeMaterialDispatch;nativeMaterialDispatch=true;
            try{retainParkingLease(c,lease,"本机材料任务完成",System.currentTimeMillis());}
            finally{nativeMaterialDispatch=previous;}
        }
        else{supervisionLease=null;KitClient.emergencyStop("本机材料任务结束");releaseMaterialMiningLease();}
    }
    static void nativeMaterialCancel(NativeMaterialSession owner,Minecraft c,String reason){
        if(owner==null||owner.closed||nativeMaterialOwner!=owner)return;
        nativeMaterialOwner=null;owner.closed=true;
        KitClient.emergencyStop("本机材料任务急停："+reason);
    }
    static void nativeMaterialSafeLogout(NativeMaterialSession owner,Minecraft c,String reason){
        nativeMaterialCheck(owner,c);
        suspendAutoReconnect();
        KitClient.safeLogout(c,"本机材料任务安全退出："+reason);
        owner.closed=true;
        if(nativeMaterialOwner==owner)nativeMaterialOwner=null;
    }
    private static boolean highGuardPark(Minecraft c,JsonObject lease){
        if(c.player==null||c.level==null||!lease.has("park_target"))return false;
        JsonArray target=lease.getAsJsonArray("park_target");if(target==null||target.size()!=3)return false;
        double x=target.get(0).getAsDouble(),y=target.get(1).getAsDouble(),z=target.get(2).getAsDouble();
        if(!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z))return false;
        BlockPos at=BlockPos.containing(x,y,z);if(!c.level.hasChunkAt(at))return false;
        int ground=c.level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING,at.getX(),at.getZ());
        return GuardParkingPolicy.ready(c.player.getX(),c.player.getY(),c.player.getZ(),x,y,z,ground,
            c.player.getHealth(),MeteorModules.isActive(MeteorModules.FLIGHT),guardArmed()&&pveOnly());
    }
    private static void retainParkingLease(Minecraft c,JsonObject lease,String reason,long now){
		if(!highGuardPark(c,lease))throw new IllegalStateException("Previous high parking scope is no longer valid");
        KitClient.stopWork(reason);
		BlockPos here=c.player.blockPosition();
		if(!c.level.hasChunkAt(here))throw new IllegalStateException("Parking anchor chunk is not loaded");
		int ground=c.level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING,
			here.getX(),here.getZ());
		var anchor=ParkingLeasePolicy.reanchor(c.player.getX(),c.player.getY(),c.player.getZ(),
			ground,c.player.getHealth(),MeteorModules.isActive(MeteorModules.FLIGHT),guardArmed()&&pveOnly());
		if(anchor==null)throw new IllegalStateException("Current high hover is not safe for parking");
		lease.add("park_target",JSON.toJsonTree(new double[]{anchor.x(),anchor.y(),anchor.z()}));
        lease.remove("finish_waiting");
        lease.addProperty("kind","parking");lease.addProperty("revision",controlRevision);
        lease.addProperty("remote_finish","guard");lease.addProperty("parked_at",now);
        supervisionLease=lease;lastSupervisionHeartbeat=now;armPveGuard(c);
        phase="parking";detail="高空安全待命，防护持续";releaseMaterialMiningLease();writeStatus(c);
    }
    private static void tickSupervision(Minecraft c) {
        confirmSafety(c);
        if(supervisionLease==null || c.player==null || c.level==null)return;
        var lease=supervisionLease;long now=System.currentTimeMillis();
        try{
            if(nativeMaterialOwner!=null&&str(lease,"id").equals(nativeMaterialOwner.lease)
                    &&now-nativeMaterialOwner.lastTouch<=1000)
                lastSupervisionHeartbeat=now;
            if(str(lease,"kind").equals("parking")&&c.screen!=null&&!interfacePaused(c)){
                var menu=c.player.containerMenu;
                var inventory=new ArrayList<ItemStack>();for(int i=0;i<36;i++)inventory.add(c.player.getInventory().getItem(i));
                var returning=new ArrayList<ItemStack>();returning.add(menu.getCarried());
                if(menu instanceof net.minecraft.world.inventory.CraftingMenu)for(int i=1;i<=9;i++)returning.add(menu.getSlot(i).getItem());
                boolean ownedScope=str(lease,"world_session").equals(session(c))&&MaterialControlPolicy.owned(lease.get("revision").getAsLong(),controlRevision,pveOnly());
                var recovery=MaterialMenuRecovery.decide(ownedScope,KitKeys.manualMovementDown(c),ownedMaterialMenu,menu.containerId,MaterialMenuRecovery.fits(inventory,returning));
                if(recovery==MaterialMenuRecovery.Decision.CLOSE_OWNED)c.player.closeContainer();
                else if(recovery==MaterialMenuRecovery.Decision.SAFE_LOGOUT){
                    // Do not leave an unattended player in a GUI that prevents defense.
                    // Vanilla returns what fits on disconnect; an overflow needs manual recovery.
                    suspendAutoReconnect();supervisionLease=null;KitClient.safeLogout(c,"合成收尾背包空间不足，已停止托管，请检查工作台物品");return;
                }else{supervisionLease=null;KitClient.stopWork("界面操作接管，已取消自动离线");phase="stopped";detail="用户界面接管";return;}
            }
            if(str(lease,"kind").equals("parking")){
                var parkingAction=ParkingLeasePolicy.decide(str(lease,"kind"),
                    str(lease,"world_session").equals(session(c)),
                    lease.has("revision")&&lease.get("revision").getAsLong()==controlRevision,
                    KitKeys.manualMovementDown(c),highGuardPark(c,lease));
                if(parkingAction==ParkingLeasePolicy.Action.KEEP){
                    phase="parking";detail="高空安全待命，防护持续";return;
                }
                supervisionLease=null;
                if(parkingAction==ParkingLeasePolicy.Action.REVOKE)return;
                var receipt=new JsonObject();receipt.addProperty("lease",str(lease,"id"));
                receipt.addProperty("job_session",str(lease,"job_session"));
                receipt.addProperty("cause",c.player.getHealth()<18?"low_health":"parking_invalid");
                receipt.addProperty("action","LOGOUT");receipt.addProperty("time",now);
                receipt.add("snapshot",snapshot(c));receipt.addProperty("confirmed",false);
                receipt.addProperty("server_survival_verified",false);safetyReceipt(c,receipt);
                suspendAutoReconnect();KitClient.safeLogout(c,"高空托管防护或位置失效，已安全退出");
                pendingSafety=receipt;pendingSafetyTick=ticks;pendingPauseSince=0;return;
            }
            boolean controllerFinished=false;
            Path file=root(c).resolve("supervision-heartbeat-"+safeId(str(lease,"id"))+".json");
            var beat=heartbeatReads.read(str(lease,"id"),str(lease,"world_session"),session(c),now,()->
                Files.isRegularFile(file)&&Files.size(file)<4096?JsonParser.parseString(Files.readString(file)).getAsJsonObject():null);
            if(beat!=null){long t=beat.get("time").getAsLong();
                if(str(beat,"id").equals(str(lease,"id")) && str(beat,"world_session").equals(str(lease,"world_session")) && t<=now+2000 && t>=lastSupervisionHeartbeat){lastSupervisionHeartbeat=t;controllerFinished=beat.has("finished") && beat.get("finished").getAsBoolean();}
            }
            var job=KitClient.buildJob().snapshot();boolean material=Set.of("materials","parking").contains(str(lease,"kind"));boolean same=str(lease,"world_session").equals(session(c)) && (material?MaterialControlPolicy.owned(lease.get("revision").getAsLong(),controlRevision,pveOnly()):str(lease,"job_session").equals(str(job,"session")) && !Set.of("manual_stop","world_changed","placement_changed").contains(str(job,"outcome")));
            boolean complete=!material&&str(job,"outcome").equals("complete") && job.get("total").getAsInt()>0 && job.get("matched").getAsInt()==job.get("total").getAsInt();
            boolean lowHealth=c.player.getHealth()<14;
            boolean local=c.getSingleplayerServer()!=null && !c.getSingleplayerServer().isPublished();
            boolean nearThreat=c.level.getEntities(c.player,c.player.getBoundingBox().inflate(16)).stream().anyMatch(e->e instanceof net.minecraft.world.entity.monster.Enemy&&e.isAlive()&&c.player.hasLineOfSight(e));
            boolean quiet=logoutQuiet.ready(now,guardBusy||c.player.isUsingItem()||nearThreat,KitClient.config().lastAttackTimeEpochMillis);
            boolean keepGuard=str(lease,"remote_finish").equals("guard")&&!lowHealth&&(!material||highGuardPark(c,lease));
            var action=dev.twob2tkit.builder.BuildSupervisorSafety.decide(same,KitKeys.manualMovementDown(c),local,lowHealth || controllerFinished || now-lastSupervisionHeartbeat>15000,complete,!keepGuard);
            boolean alreadyWaiting=lease.has("finish_waiting")&&lease.get("finish_waiting").isJsonPrimitive()
                &&lease.getAsJsonPrimitive("finish_waiting").isBoolean()
                &&lease.get("finish_waiting").getAsBoolean();
            var quietWait=ParkingLeasePolicy.quietWait(
                action==dev.twob2tkit.builder.BuildSupervisorSafety.Action.LOGOUT,
                lowHealth,quiet,alreadyWaiting);
            if(quietWait!=ParkingLeasePolicy.QuietWait.NONE){
                if(quietWait==ParkingLeasePolicy.QuietWait.START){
                    KitClient.stopWork("托管收尾，等待脱离战斗");
                    lease.addProperty("revision",controlRevision);
                    lease.addProperty("finish_waiting",true);supervisionLease=lease;
                    armPveGuard(c);
                    if(c.player!=null)c.player.sendSystemMessage(net.minecraft.network.chat.Component.literal("[托管] 工作已停止，防护继续；连续 60 秒无近敌或新受伤后再离线。"));
                }
                phase="finish_waiting";detail="工作已停止，等待战斗结束与安静窗口，防护仍开启";return;
            }
            if(action==dev.twob2tkit.builder.BuildSupervisorSafety.Action.NONE)return;
            if(action==dev.twob2tkit.builder.BuildSupervisorSafety.Action.REVOKE){supervisionLease=null;return;}
            if(action==dev.twob2tkit.builder.BuildSupervisorSafety.Action.KEEP_PVE_GUARD){
                retainParkingLease(c,lease,"托管结束，保留 PvE 防护",now);
                var receipt=new JsonObject();receipt.addProperty("lease",str(lease,"id"));receipt.addProperty("job_session",str(lease,"job_session"));
                receipt.addProperty("cause",lowHealth?"low_health":complete?"complete":controllerFinished?"controller_finished":"heartbeat_lost");
                receipt.addProperty("action",action.name());receipt.addProperty("time",now);receipt.add("snapshot",snapshot(c));
                receipt.addProperty("confirmed",false);receipt.addProperty("server_survival_verified",false);safetyReceipt(c,receipt);return;
            }
            supervisionLease=null;
            var receipt=new JsonObject();receipt.addProperty("lease",str(lease,"id"));receipt.addProperty("job_session",str(lease,"job_session"));receipt.addProperty("cause",lowHealth?"low_health":complete?"complete":controllerFinished?"controller_finished":"heartbeat_lost");receipt.addProperty("action",action.name());receipt.addProperty("time",now);receipt.add("snapshot",snapshot(c));
            receipt.addProperty("confirmed",false);receipt.addProperty("server_survival_verified",false);safetyReceipt(c,receipt);
            switch(action){
                case PAUSE_LOCAL -> {KitClient.emergencyStop("托管安全暂停："+(lowHealth?"血量不足":complete?"任务完成":controllerFinished?"托管已结束":"控制器失联"));c.pauseGame(false);if(!(c.screen instanceof net.minecraft.client.gui.screens.PauseScreen))c.setScreen(new net.minecraft.client.gui.screens.PauseScreen(true));}
                case LOGOUT -> {suspendAutoReconnect();KitClient.safeLogout(c,"托管收尾退出："+(lowHealth?"血量不足":complete?"任务完成":controllerFinished?"托管已结束":"控制器失联"));}
                case KEEP_PVE_GUARD -> {}
                default -> {}
            }
            pendingSafety=receipt;pendingSafetyTick=ticks;pendingPauseSince=0;
        }catch(Exception e){supervisionLease=null;KitClient.emergencyStop("托管安全监控读取失败");if(c.getSingleplayerServer()!=null)c.pauseGame(false);else KitClient.safeLogout(c,"托管状态异常，安全退出");}
    }
    private static String session(Minecraft c){
        if(observedLevel!=c.level){ownedMaterialMenu=-1;observedLevel=c.level;worldSession=UUID.randomUUID().toString();survivalArmed=false;controlRevision++;}
        return worldSession;
    }
    private static void restoreGuardAfterReconnect(Minecraft c){
        var pending=pendingGuardReconnect;
        if(pending==null)return;
        long now=System.currentTimeMillis();
        if(now-pending.savedAt()>GuardReconnectPolicy.MAX_AGE_MS
            ||dev.twob2tkit.combat.EmergencyExit.held(c)){pendingGuardReconnect=null;return;}
        if(c.player==null||c.level==null||c.screen!=null)return;
        String server=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
        String dimension=c.level.dimension().identifier().toString();
        if(!GuardReconnectPolicy.restoreHere(pending,server,dimension,c.player.getX(),c.player.getZ(),
                c.player.getHealth(),KitKeys.manualMovementDown(c),false,now))return;
        pendingGuardReconnect=null;
        armPveGuard(c);
        KitClient.LOGGER.info("PvE guard restored after reconnect at {} {} {}",c.player.getX(),c.player.getY(),c.player.getZ());
    }
    private static boolean survival(JsonObject r){return r!=null && r.has("local_survival") && r.get("local_survival").getAsBoolean();}
    private static boolean background(JsonObject r){return r!=null && r.has("background_ok") && r.get("background_ok").getAsBoolean();}
    private static boolean survivalMenu(Minecraft c){return c.screen==null || Set.of("InventoryScreen","CraftingScreen","FurnaceScreen","BlastFurnaceScreen","SmokerScreen").contains(c.screen.getClass().getSimpleName());}
    private static void survivalGuard(Minecraft c,JsonObject r){
        if(!survival(r))return;
        if(!str(r,"world_session").equals(session(c)) || c.getCurrentServer()!=null || c.getSingleplayerServer()==null
            || c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL)throw new IllegalStateException("Survival test world/session changed");
        if(c.player.getHealth()<16 || c.player.getFoodData().getFoodLevel()<8 || c.player.isOnFire() || c.player.isInWater()
            || !background(r) && !c.isWindowActive() || !survivalMenu(c) || KitKeys.manualMovementDown(c))throw new IllegalStateException("Survival test paused for health, menu or manual control");
        for(var e:c.level.entitiesForRendering())if(e instanceof net.minecraft.world.entity.monster.Enemy && e.isAlive() && e.distanceToSqr(c.player)<100 && c.player.hasLineOfSight(e))
            throw new IllegalStateException("Hostile nearby; survival bootstrap paused");
    }
    private static int ticks, deadline, desiredCount;
    private static int ownedMaterialMenu=-1;
    private static JsonObject guardScope;
    private static boolean guardBusy,healthRecoveryHold;
    private static final dev.twob2tkit.combat.HealthRecoveryWindow healthRecovery=new dev.twob2tkit.combat.HealthRecoveryWindow();
    public static boolean ownsMaterialInventory(){
        return survivalArmed || supervisionLease!=null&&Set.of("materials","parking").contains(str(supervisionLease,"kind")) || active!=null&&op.equals("craft_recipe");
    }
    public static boolean guardBusy(){return guardBusy;}
    public static boolean guardArmed(){return guardScope!=null;}
    public static boolean pveOnly(){return guardScope!=null && guardScope.has("pve_only") && guardScope.get("pve_only").getAsBoolean();}
    private static boolean projectionScaffoldOwnerCurrent(Minecraft c){
        if(c.player==null||c.level==null||active==null||!op.equals("projection_scaffold_fill")
            ||!currentMaterialRequest(c,active)||!active.has("expected_revision")
            ||active.get("expected_revision").getAsLong()!=controlRevision
            ||!str(active,"world_session").equals(session(c))
            ||System.currentTimeMillis()-lastSupervisionHeartbeat>15000
            ||c.screen!=null||KitKeys.manualMovementDown(c)||!guardArmed()||!pveOnly()||guardBusy
            ||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<8
            ||dev.twob2tkit.combat.EmergencyExit.held(c))return false;
        try{return dev.twob2tkit.builder.LitematicaAccess.lockedBuildSelection().key().equals(str(active,"placement_key"));}
        catch(RuntimeException unavailable){return false;}
    }
    public static boolean projectionScaffoldTargetAllowed(BlockPos target){
        if(scaffoldFillTask==null)return true;
        var c=Minecraft.getInstance();
        try{return scaffoldFillTask.allowCandidate(c,target,ticks);}
        catch(Exception error){scaffoldFillTask.fail(c,error.getMessage());return false;}
    }
    public static void projectionScaffoldCandidateEnded(){if(scaffoldFillTask!=null)scaffoldFillTask.candidateEnded();}
    public static boolean prepareProjectionScaffoldInteraction(net.minecraft.client.player.LocalPlayer player,InteractionHand hand,BlockHitResult hit){
        if(scaffoldFillTask==null)return false;
        var c=Minecraft.getInstance();
        if(c.isWindowActive()&&KitKeys.isPhysicallyDown(c,c.options.keyUse)){
            scaffoldFillTask.fail(c,"Physical right-click took over the controlled row");
            cancelWork(c,"Manual right-click cancelled the controlled Scaffold row");
            return false; // Let the user's first real click reach vanilla; do not swallow it.
        }
        try{return scaffoldFillTask.prepareInteraction(c,player,hand,hit,ticks);}
        catch(Exception error){scaffoldFillTask.fail(c,error.getMessage());return true;}
    }
    public static void projectionScaffoldModuleToggleObserved(Object module){
        ScaffoldModuleLease.moduleToggleObserved(module);
        if(scaffoldFillTask!=null)scaffoldFillTask.moduleToggleObserved(module);
    }
    /** Stop is an explicit operation, never inferred from translated reason text. */
    public static void disarmGuard(Minecraft c){
        guardScope=null;guardBusy=false;healthRecoveryHold=false;healthRecovery.hold(false,20,false);dev.twob2tkit.combat.GuardFoodLease.release();
        if(KitClient.borer()!=null)KitClient.borer().tickStandaloneGuard(c,false);
    }
    public static boolean yieldGuardToManualInput(Minecraft c){
        if(!guardArmed() || !KitKeys.manualMovementDown(c))return false;
        KitClient.emergencyStop("手动移动接管");
        return true;
    }
    public static void toggleGuard(Minecraft c){
        if(guardArmed()){KitClient.emergencyStop("手动关闭独立防护");return;}
        armCurrentGuard(c);
    }
    public static void armCurrentGuard(Minecraft c){armGuard(c,false);}
    public static void armPveGuard(Minecraft c){armGuard(c,true);}
    private static void armGuard(Minecraft c,boolean pveOnly){
        if(c.player==null || c.level==null || c.player.isDeadOrDying()||dev.twob2tkit.combat.EmergencyExit.held(c))return;
        guardScope=new JsonObject();guardScope.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);
        guardScope.addProperty("dimension",c.level.dimension().identifier().toString());
        guardScope.add("site",JSON.toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));
        guardScope.addProperty("pve_only",pveOnly);
        lastGuardHealth=c.player.getHealth();lastGuardX=c.player.getX();lastGuardZ=c.player.getZ();
        dev.twob2tkit.combat.GuardFoodLease.acquire(c);
        if(pveOnly)MeteorModules.enablePveAura();else MeteorModules.enable(MeteorModules.KILL_AURA);MeteorModules.enable(MeteorModules.AUTO_LOG);
        MeteorModules.enable("meteordevelopment.meteorclient.systems.modules.player.AutoEat");
    }
	private static boolean rebaseSnowExpeditionGuard(Minecraft c){
		boolean scoped=activeSnowNavigationScope(c,active);
		if(active!=null&&active.has("snow_expedition_token")&&!scoped)
			throw new IllegalStateException("Snow expedition permit, lease, or guard scope changed");
		boolean permitted=SnowGuardScopePolicy.rebase(active!=null,op.equals("navigate"),
			active!=null&&active.has("snow_expedition_token"),
			scoped,scoped,
			pveOnly(),KitClient.controller()!=null&&KitClient.controller().isActive());
		if(!permitted||guardScope==null||c.player==null)return false;
		guardScope.add("site",JSON.toJsonTree(new double[]{
			c.player.getX(),c.player.getY(),c.player.getZ()}));
		return true;
	}
	private static boolean rebaseParkingGuard(Minecraft c){
		if(supervisionLease==null||guardScope==null||c.player==null)return false;
		boolean permitted=ParkingLeasePolicy.guardRebase(str(supervisionLease,"kind"),
			str(supervisionLease,"world_session").equals(session(c)),
			supervisionLease.has("revision")&&supervisionLease.get("revision").getAsLong()==controlRevision,
			KitKeys.manualMovementDown(c),pveOnly(),active==null,highGuardPark(c,supervisionLease));
		if(!permitted)return false;
		JsonArray target=supervisionLease.getAsJsonArray("park_target");
		guardScope.add("site",target.deepCopy());return true;
	}
    private static String airEquipmentSignature(ItemStack item){
        var entries=new ArrayList<String>();
        var applied=item.getEnchantments();
        for(var enchantment:applied.keySet())
            entries.add(enchantment.unwrapKey().map(key->key.identifier().toString()).orElse("unknown")
                +"="+applied.getLevel(enchantment));
        Collections.sort(entries);
        return itemId(item)+":"+String.join(",",entries);
    }
    private static String airGear(Minecraft c){
        if(c.player==null)return "";
        return airEquipmentSignature(c.player.getItemBySlot(EquipmentSlot.HEAD))+"|"
            +airEquipmentSignature(c.player.getItemBySlot(EquipmentSlot.FEET))+"|"
            +c.player.getMaxAirSupply();
    }
    private static boolean respirationThree(Minecraft c){
        return c.player!=null&&airEquipmentSignature(c.player.getItemBySlot(EquipmentSlot.HEAD))
            .contains("minecraft:respiration=3");
    }
    private static boolean materialAirScope(Minecraft c){
        return c.player!=null&&c.level!=null&&guardScope!=null&&pveOnly()
            &&supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")
            &&str(supervisionLease,"world_session").equals(session(c))
            &&supervisionLease.has("revision")
            &&supervisionLease.get("revision").getAsLong()==controlRevision;
    }
    private static MaterialAirBudget.Estimate airEstimate(Minecraft c){
        return materialAirRoute.estimate(c,session(c),
            supervisionLease==null?"":str(supervisionLease,"job_session"),
            respirationThree(c)&&MeteorModules.isActive(MeteorModules.AUTO_LOG)
                ?airGear(c):"unqualified",System.currentTimeMillis());
    }
    private static boolean beginNativeAirReturn(Minecraft c,MaterialAirBudget.Estimate budget,
                                                boolean boundedDiveDue){
        if(!materialAirScope(c)||!c.player.isUnderWater()||nativeAirReturnActive
                ||c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING)
                ||c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER)
                ||!materialAirRoute.configuredJob(session(c),str(supervisionLease,"job_session"))
                ||c.player.getAirSupply()>budget.returnFloor()&&!boundedDiveDue)return false;
        Vec3 target=materialAirRoute.emergencyTarget(c,session(c),
            str(supervisionLease,"job_session"),airGear(c));
        if(target==null){
            nativeAirReturnPhase="no_verified_route";
            suspendAutoReconnect();KitClient.safeLogout(c,"水下氧气不足且返气路线失效，停止并退出");
            return true;
        }
        if(active!=null&&op.equals("navigate")&&KitClient.controller().isActive()
                &&active.has("target")){
            JsonArray current=active.getAsJsonArray("target");
            if(current!=null&&current.size()==3
                    &&current.get(1).getAsDouble()>=target.y
                    &&Math.hypot(current.get(0).getAsDouble()-target.x,
                                  current.get(2).getAsDouble()-target.z)<=.2){
                active.addProperty("auto_air_return",true);
                active.addProperty("interrupted_op","navigate");
                KitClient.controller().keepConnectedOnArrival();
                nativeAirReturnActive=true;nativeAirReturnPhase="ascending";
                nativeAirReturnOriginalOp="navigate";
                nativeAirReturnStarted=System.currentTimeMillis();
                nativeAirReturnMovedAt=nativeAirReturnStarted;
                nativeAirReturnLastY=c.player.getY();
                return true;
            }
        }
        String previous=op;
        JsonObject rescue=active==null?guardScope.deepCopy():active.deepCopy();
        if(active==null)rescue.addProperty("id","native-air-"+UUID.randomUUID());
        rescue.addProperty("task_session",str(supervisionLease,"job_session"));
        rescue.addProperty("world_session",session(c));
        rescue.addProperty("expected_revision",controlRevision-1);
        rescue.add("target",JSON.toJsonTree(new double[]{target.x,target.y,target.z}));
        rescue.addProperty("auto_air_return",true);
        rescue.addProperty("interrupted_op",previous);
        if(c.gameMode!=null)c.gameMode.stopDestroyBlock();
        if(active!=null)releaseWalk(c);
        if(supplyTask!=null){supplyTask.close(c);supplyTask=null;}
        active=rescue;op="navigate";phase="running";
        nativeAirReturnActive=true;nativeAirReturnPhase="ascending";
        nativeAirReturnOriginalOp=previous;nativeAirReturnStarted=System.currentTimeMillis();
        nativeAirReturnMovedAt=nativeAirReturnStarted;nativeAirReturnLastY=c.player.getY();
        detail="native air return interrupted "+previous;
        deadline=ticks+20*20;
        boolean wasDispatching=dispatching;dispatching=true;
        try{
            MeteorModules.enable(MeteorModules.FLIGHT);
            KitClient.controller().startExact(c,target.x,target.z,target.y);
            KitClient.controller().keepConnectedOnArrival();
            materialAirRoute.beginAscent(c,str(rescue,"id"),target.y);
        }catch(Exception failed){
            nativeAirReturnActive=false;nativeAirReturnPhase="launch_failed";
            suspendAutoReconnect();KitClient.safeLogout(c,"水下返气启动失败，停止并退出");
        }finally{dispatching=wasDispatching;}
        return true;
    }
    private static boolean ownedUnderwaterAirReturn(Minecraft c){
        if(c.player==null||c.level==null||!c.player.isUnderWater()
                ||active==null
                ||!op.equals("navigate")||!active.has("task_session")||guardScope==null
                ||supervisionLease==null||!str(supervisionLease,"kind").equals("materials")
                ||!supervisionLease.has("revision")||!active.has("expected_revision")
                ||!GuardEscapePolicy.currentLease(session(c),controlRevision,
                    str(supervisionLease,"world_session"),supervisionLease.get("revision").getAsLong(),
                    str(active,"world_session"),active.get("expected_revision").getAsLong(),
                    str(supervisionLease,"job_session"),str(active,"task_session")))
            return false;
        JsonArray target=active.getAsJsonArray("target");
        if(target==null||target.size()!=3)return false;
        double x=target.get(0).getAsDouble(),y=target.get(1).getAsDouble(),z=target.get(2).getAsDouble();
        if(!GuardEscapePolicy.underwaterAirReturn(true,true,true,true,
                c.player.getX(),c.player.getY(),c.player.getZ(),x,y,z,c.level.getSeaLevel()))return false;
        BlockPos breathingFeet=BlockPos.containing(x,y,z);
        BlockPos breathingHead=BlockPos.containing(x,y+1.6,z);
        if(!c.level.hasChunkAt(breathingFeet)||!c.level.hasChunkAt(breathingHead)
                ||!c.level.getFluidState(breathingFeet).isEmpty()
                ||!c.level.getFluidState(breathingHead).isEmpty())return false;
        int steps=(int)Math.ceil(y-c.player.getY());
        if(steps<2||steps>64)return false;
        for(int step=1;step<=steps;step++){
            for(int sample=0;sample<=1;sample++){
                var body=c.player.getBoundingBox().move((x-c.player.getX())*sample,step,
                                                        (z-c.player.getZ())*sample);
                for(int xx=(int)Math.floor(body.minX);xx<=Math.floor(body.maxX-1e-6);xx++)
                    for(int yy=(int)Math.floor(body.minY);yy<=Math.floor(body.maxY-1e-6);yy++)
                        for(int zz=(int)Math.floor(body.minZ);zz<=Math.floor(body.maxZ-1e-6);zz++){
                            BlockPos p=new BlockPos(xx,yy,zz);
                            if(!c.level.hasChunkAt(p)
                                    ||c.level.getFluidState(p).is(net.minecraft.world.level.material.Fluids.LAVA)
                                    ||!c.level.getBlockState(p).getCollisionShape(c.level,p).isEmpty())return false;
                        }
            }
        }
        return true;
    }
    public static boolean beforeGuard(Minecraft c){
        if(scaffoldFillTask!=null&&c.player!=null&&(guardBusy||!projectionScaffoldOwnerCurrent(c)||loadedHostileNearby(c)))
            scaffoldFillTask.pauseBeforeGuard(c);
        boolean enabled=guardScope!=null;
        if(enabled&&c.player!=null){lastGuardHealth=c.player.getHealth();lastGuardX=c.player.getX();lastGuardZ=c.player.getZ();}
        if(enabled)try{
			rebaseParkingGuard(c);guard(c,guardScope);rebaseSnowExpeditionGuard(c);
		}catch(Exception changed){guardScope=null;enabled=false;dev.twob2tkit.combat.GuardFoodLease.release();}
        if(active!=null&&op.equals("navigate")&&materialAirScope(c))
            materialAirRoute.observeAscent(c,str(active,"id"));
        if(enabled&&materialAirScope(c)&&c.player.isUnderWater()){
            long now=System.currentTimeMillis();
            if(beginNativeAirReturn(c,airEstimate(c),
                    materialAirRoute.returnDue(session(c),str(supervisionLease,"job_session"),
                        airGear(c),now))&&!nativeAirReturnActive)return true;
        }
        if(nativeAirReturnActive&&active!=null&&c.player!=null){
            materialAirRoute.observeAscent(c,str(active,"id"));
            long now=System.currentTimeMillis();
            if(c.player.getY()>nativeAirReturnLastY+.2){
                nativeAirReturnLastY=c.player.getY();nativeAirReturnMovedAt=now;
            }
            if(c.player.isUnderWater() && (c.player.getAirSupply()<=Math.ceil(c.player.getMaxAirSupply()/10.0)
                    ||now-nativeAirReturnMovedAt>3000)){
                nativeAirReturnPhase="stalled_underwater";
                suspendAutoReconnect();KitClient.safeLogout(c,"水下返气停止前进，停止并退出");
                return true;
            }
        }
        if(enabled&&ownedUnderwaterAirReturn(c)){
            // Reaching air from underwater outranks ranged combat. Keep guard
            // armed; PvE defense resumes immediately after leaving the water.
            if(KitClient.borer().suspendStandaloneCombatForAirReturn(c)){
                guardBusy=false;
                healthRecoveryHold=healthRecovery.hold(false,c.player.getHealth(),false);
                return false;
            }
        }
        guardBusy=KitClient.borer().tickStandaloneGuard(c,enabled);
        healthRecoveryHold=healthRecovery.hold(enabled,c.player==null?20:c.player.getHealth(),guardBusy);
        if(healthRecoveryHold){
            for(var key:new net.minecraft.client.KeyMapping[]{c.options.keyUp,c.options.keyDown,c.options.keyLeft,c.options.keyRight,c.options.keyJump,c.options.keyShift,c.options.keySprint,c.options.keyAttack})key.setDown(false);
            if(c.gameMode!=null)c.gameMode.stopDestroyBlock();guardBusy=true;
        }
        if(guardBusy){ProfessionalPrinter.pause();if(active!=null&&!interfacePaused(c))deadline++;mineStarted=false;}
        return guardBusy;
    }
    private static double savedArrival=Double.NaN, temporaryArrival;
    private static Boolean savedClearCeiling;
    private static boolean restoreFlight;
    private static boolean mineStarted;
    private static boolean guiRequested, initialized, dispatching;
    private static Path root(Minecraft c){return c.gameDirectory.toPath().resolve("config/twob2tkit/automation");}
    public static void requestGui(){guiRequested=true;}
    public static boolean ownsMining(){return active!=null && op.equals("mine_block");}
	private static boolean pendingSnowReturnScope(Minecraft c,JsonObject request){
		return request!=null&&guardArmed()&&SnowGuardScopePolicy.pendingReturn(
			"navigate".equals(str(request,"op")),request.has("snow_expedition_token"),
			currentMaterialRequest(c,request),pveOnly(),
			SnowSeedExpedition.pendingReturn(request,session(c)));
	}
	private static boolean activeSnowNavigationScope(Minecraft c,JsonObject request){
		return request!=null&&guardArmed()&&SnowGuardScopePolicy.inFlight(
			request==active,op.equals("navigate")&&"navigate".equals(str(request,"op")),
			request.has("snow_expedition_token"),currentMaterialRequest(c,request),pveOnly(),
			SnowSeedExpedition.activeNavigation(request,session(c)));
	}
	private static void finishSnowNavigation(Minecraft c,JsonObject request,boolean arrived){
		if(request==null||!"navigate".equals(str(request,"op"))
				||!request.has("snow_expedition_token"))return;
		SnowSeedExpedition.navigationFinished(c,request,session(c),arrived);
	}
    public static void cancel(Minecraft c,String reason){
        materialMiningCleanupPending=true;
        pendingGuardReconnect=null;
        ownedBorerSession="";
        ProfessionalPrinter.stop(c,true);
        supervisionLease=null;pendingSafety=null;survivalArmed=false;disarmGuard(c);projectionBatch.reset();
        cancelWork(c,reason);
        releaseMaterialMiningLease();
    }
    private static void abortOwnedRequest(Minecraft c,String reason){
        if(supervisionLease!=null && active!=null && (str(active,"job_session").equals(str(supervisionLease,"job_session"))||str(active,"task_session").equals(str(supervisionLease,"job_session")))){
            boolean nativeChild=nativeMaterialOwner!=null&&active.has("id")
                &&str(active,"id").equals(nativeMaterialOwner.pendingId)
                &&nativeMaterialOwner.world.equals(session(c))&&!KitKeys.manualMovementDown(c);
            boolean previous=nativeMaterialDispatch;
            if(nativeChild)nativeMaterialDispatch=true;
            try{KitClient.stopWork(reason);}
            finally{nativeMaterialDispatch=previous;}
            if(supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")){
                supervisionLease.addProperty("revision",controlRevision);
                if(nativeChild&&nativeMaterialOwner!=null)nativeMaterialOwner.revision=controlRevision;
            }
            if(nativeChild&&nativeMaterialOwner!=null)
                nativeMaterialOwner.immediate=nativeMaterialReceipt(c,nativeMaterialOwner.pendingId,"stopped",reason);
        }
        else KitClient.emergencyStop(reason);
    }
    public static void cancelWork(Minecraft c,String reason){
        if(pendingScan!=null)finishScan(c,"waiting","scan interrupted by control cleanup: "+reason);
        JsonObject cancelledMining=ordinaryMiningRequested(active)?active.deepCopy():null;
        JsonObject cancelledPrinter=active!=null&&op.equals("professional_print")?active.deepCopy():null;
        if(cancelledMining!=null){
            lastSingleBlockConfirmation=singleBlockConfirmation(c,cancelledMining,"stopped",reason,false);
            ordinaryMiningConfirmation.close(str(cancelledMining,"id"),false);
        }
        if(cancelledPrinter!=null)lastPrinterConfirmation=printerConfirmation(cancelledPrinter,"stopped",reason,false);
        materialMiningCleanupPending=true;
		finishSnowNavigation(c,active,false);
        if(bucketWaterTask!=null){
            lastBucketWater=bucketWaterTask.snapshot(false);
            try{bucketWaterTask.terminal("stopped");}catch(Exception failure){KitClient.LOGGER.error("[Bucket] stopped receipt could not be saved; claim retained",failure);}
            bucketWaterTask=null;
        }
        if(mapCreationTask!=null){lastMapCreation=mapCreationTask.snapshot(false);mapCreationTask=null;}
        if(airSeedTask!=null){lastAirSeed=airSeedTask.snapshot(false);airSeedTask.close();airSeedTask=null;}
        if(scaffoldFillTask!=null){scaffoldFillTask.close();lastScaffoldFill=scaffoldFillTask.snapshot();if(!scaffoldFillTask.cleanupPending())scaffoldFillTask=null;}
        terrainServerConfirmation.clear();
        dryPavingServerConfirmation.clear();dryPavingConfirmedTick=-1;dryPavingClientAirTick=-1;
        closeMaterialAirNavigation(c,"stopped");
        if(active!=null&&Set.of("quarry_batch","rock_quarry_batch").contains(op)&&KitClient.borer()!=null)
            KitClient.borer().stop(c,reason);
        if(active!=null&&op.equals("rock_quarry_batch"))rockQuarryStopped("stopped",reason);
        if(nativeMaterialOwner!=null&&!nativeMaterialDispatch){
            nativeMaterialOwner.closed=true;nativeMaterialOwner=null;supervisionLease=null;
        }
        if(nativeAirReturnActive){
            nativeAirReturnActive=false;
            if(nativeAirReturnPhase.equals("ascending"))nativeAirReturnPhase="cancelled";
        }
        deferredInterfaceRequest=null;
        survivalArmed=false;craftTask=null;if(supplyTask!=null){supplyTask.close(c);supplyTask=null;}controlRevision++;ProfessionalPrinter.stop(c,false);restoreArrival();releaseWalk(c);
        active=null;phase="stopped";detail=reason;if(supervisionLease==null||!dispatching&&!nativeMaterialDispatch)projectionBatch.reset();
        // Only successful control cleanup can restore a borrowed mining module.
        // A thrown cleanup retains both its pause and queued-packet suppression.
        materialMiningCleanupPending=false;
        if(supervisionLease==null||!"materials".equals(str(supervisionLease,"kind")))releaseMaterialMiningLease();
        if(cancelledMining!=null)saveTerminalConfirmation(c,lastSingleBlockConfirmation);
        if(cancelledPrinter!=null)saveTerminalConfirmation(c,lastPrinterConfirmation);
        if(!dispatching)writeStatus(c);
    }
    /** Short-range walking owns input before Minecraft samples keys; it does not use cruise fly-over routing. */
    public static boolean reapplySupplyLook(Minecraft c){
        if(scaffoldFillTask!=null&&scaffoldFillTask.reapply(c))return true;
        if(materialAirNavigation!=null&&materialAirNavigation.reapply(c))return true;
        if(active==null || !Set.of("build_supply","collect_supply","approach_block","collect_item","concrete_batch").contains(op) || supplyTask==null)return false;
        supplyTask.reapply(c);return true;
    }
    private static boolean ownsMaterialMenu(Minecraft c){
        if(active==null||!active.has("task_session")||c.player==null)return false;
        var menu=c.player.containerMenu;String command=str(active,"op");
        if(command.equals("slot_click"))return active.has("menu_id")&&menu.containerId==active.get("menu_id").getAsInt();
        // An interact request is waiting for the server-opened container, so no menu id exists yet.
        if(command.equals("interact")){
            boolean owned=menu instanceof net.minecraft.world.inventory.ChestMenu||menu instanceof net.minecraft.world.inventory.ShulkerBoxMenu||menu instanceof net.minecraft.world.inventory.CraftingMenu||menu instanceof net.minecraft.world.inventory.AbstractFurnaceMenu||menu instanceof net.minecraft.world.inventory.AnvilMenu||menu instanceof net.minecraft.world.inventory.BrewingStandMenu;
            if(owned)ownedMaterialMenu=menu.containerId;return owned;
        }
        return false;
    }
    private static boolean nativeKitMenu(Minecraft c){
        if(c.screen==null||!c.screen.getClass().getName().startsWith("dev.twob2tkit."))return false;
        if(nativeMaterialOwner!=null)return true;
        // The local Python material worker must remain pausable from its own
        // Kit page. Freeze its inputs there; do not turn UI inspection into an
        // emergency stop that destroys both the worker and its PvE protection.
        return supervisionLease!=null&&supervisionLease.has("revision")
            &&str(supervisionLease,"kind").equals("materials")
            &&str(supervisionLease,"world_session").equals(session(c))
            &&supervisionLease.get("revision").getAsLong()==controlRevision
            &&(active==null||str(active,"task_session").equals(str(supervisionLease,"job_session")));
    }
    /** Passive screens suspend the current task; they never acquire an inventory menu. */
    public static boolean interfacePaused(Minecraft c){
        return InterfacePausePolicy.pauses(c.player!=null&&c.level!=null&&!c.player.isDeadOrDying(),
            c.screen!=null,c.screen instanceof net.minecraft.client.gui.screens.inventory.AbstractContainerScreen<?>,
            c.player!=null&&c.player.containerMenu==c.player.inventoryMenu,nativeAirReturnActive);
    }
    private static void pauseInterfaceInput(Minecraft c){
        ProfessionalPrinter.pause();
        if(materialAirNavigation!=null)try{materialAirNavigation.pause(c);}
        catch(RuntimeException failure){abortOwnedRequest(c,"材料精确停靠无法暂停："+failure.getMessage());}
        // Only task movement/mining inputs are released. AutoEat retains its food-use input.
        for(var key:KitKeys.movementKeys(c))key.setDown(false);
        c.options.keyAttack.setDown(false);
        if(c.gameMode!=null)c.gameMode.stopDestroyBlock();
        mineStarted=false;
        if(active!=null&&op.equals("walk")&&active.has("freefall_brake_y"))MeteorModules.enable(MeteorModules.FLIGHT);
    }
    private static JsonObject deferredInterfaceRequest;
    private static long deferredInterfaceSince;
    private static boolean interfaceReadOrStop(String command){
        return InterfacePausePolicy.readOrStop(command);
    }
    private static void deferInterfaceRequest(Minecraft c,JsonObject request){
        if(deferredInterfaceRequest!=null&&deferredInterfaceRequest.equals(request))return;
        deferredInterfaceRequest=null;
        long now=System.currentTimeMillis();
        if(currentMaterialRequest(c,request)&&request.has("expected_revision")
                &&request.get("expected_revision").getAsLong()==controlRevision&&request.has("expires_at")
                &&request.get("expires_at").getAsLong()>=now&&request.get("expires_at").getAsLong()-now<=15000){
            deferredInterfaceRequest=request.deepCopy();deferredInterfaceSince=now;
        }
    }
    private static void resumeInterfaceRequest(Minecraft c,JsonObject request){
        if(deferredInterfaceRequest!=null&&deferredInterfaceRequest.equals(request)
                &&currentMaterialRequest(c,request)&&request.has("expected_revision")
                &&request.get("expected_revision").getAsLong()==controlRevision)
            request.addProperty("expires_at",request.get("expires_at").getAsLong()
                +Math.max(0,System.currentTimeMillis()-deferredInterfaceSince));
        deferredInterfaceRequest=null;
    }
    private static void tickInterfacePause(Minecraft c){
        pauseInterfaceInput(c);
        if(active!=null){
            deadline++;
            if(concretePickupDeadline>0)concretePickupDeadline++;
            if(dryPavingConfirmedTick>=0)dryPavingConfirmedTick++;
            if(dryPavingClientAirTick>=0)dryPavingClientAirTick++;
        }
        // UI inspection is no proof of completion and no reason to cancel the heartbeat.
        tickSupervision(c);
        if(ticks%5==0)writeStatus(c);
    }
    public static boolean beforeInput(Minecraft c){
        syncMaterialMiningLease(c);
        if(materialMiningCleanupPending)return true;
        if(active!=null)ownsMaterialMenu(c); // Capture our CraftingMenu even though it is an allowed survival screen.
        if(interfacePaused(c)){pauseInterfaceInput(c);return true;}
        if(active!=null && (active.has("job_session")||active.has("task_session")) && c.player!=null && (KitKeys.manualMovementDown(c) || !background(active) && !c.isWindowActive() || !survivalMenu(c) && !nativeKitMenu(c) && !ownsMaterialMenu(c) && !(supplyTask!=null && Set.of("build_supply","collect_supply","approach_block","collect_item","concrete_batch").contains(op) && supplyTask.ownsMenu(c)))){KitClient.emergencyStop("托管技能交还控制");return true;}
        if(active!=null&&op.equals("projection_scaffold_fill")&&scaffoldFillTask!=null){
            try{guard(c,active);return scaffoldFillTask.input(c,ticks);}
            catch(Exception error){scaffoldFillTask.fail(c,error.getMessage());finish(c,"waiting",error.getMessage());return true;}
        }
        if(active!=null&&op.equals("rock_quarry_batch")){
            tickRockQuarry(c,true);
            if(active==null)return true;
        }
        if(active!=null&&op.equals("navigate")&&active.has("air_only")&&active.get("air_only").getAsBoolean()){
            if(KitClient.config().clearCeiling||!airNavigationClear(c,active.getAsJsonArray("target"))){
                KitClient.controller().stop(c,"已观察空气通道发生变化，停止移动");
                finish(c,"waiting","air-only path changed; no blocks were excavated");return true;
            }
        }
        if(materialAirNavigation!=null&&active!=null&&op.equals("navigate")){
            try{
                guard(c,active);
                if(!currentMaterialRequest(c,active)||!guardArmed()||!pveOnly())throw new IllegalStateException("Air waypoint ownership or protection changed");
                return materialAirNavigation.input(c);
            }
            catch(Exception error){KitClient.controller().stop(c,"材料精确停靠停止");finish(c,"waiting",error.getMessage());return true;}
        }
        if(survivalArmed && c.player!=null && (KitKeys.manualMovementDown(c) || !survivalBackground && !c.isWindowActive() || !survivalMenu(c))){KitClient.emergencyStop("生存试运行交还控制");return true;}
        if(active!=null && Set.of("build_supply","collect_supply","approach_block","collect_item","concrete_batch").contains(op) && supplyTask!=null){supplyTask.input(c);return true;}
        if(active==null || !Set.of("walk","walk_path","mine_block","use_item").contains(op) || c.player==null || c.level==null)return false;
        if(survival(active))try{survivalGuard(c,active);}catch(Exception e){KitClient.emergencyStop(e.getMessage());return true;}
        if(op.equals("walk")&&active.has("freefall_brake_y")){
            double brakeY=active.get("freefall_brake_y").getAsDouble();
            int low=Math.max((int)Math.floor(brakeY)-2,c.player.blockPosition().getY()-8);
            boolean blocked=!freefallColumnClear(c,c.player.blockPosition(),low,c.player.blockPosition().getY()+2);
            if(FreefallPolicy.brake(c.player.getY(),brakeY,c.player.getHealth(),c.screen!=null)||blocked){
                MeteorModules.enable(MeteorModules.FLIGHT);
                if(!MeteorModules.isActive(MeteorModules.FLIGHT)){
                    KitClient.safeLogout(c,"快速下降刹车未确认，已安全退出");return true;
                }
                finish(c,"done",blocked?"freefall braked before a new obstacle":"freefall braked above target");
            }else{c.options.keyUp.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);}
            return true;
        }
        if(op.equals("walk")&&active.has("water_descend")&&active.get("water_descend").getAsBoolean()){
            var air=airEstimate(c);
            int floor=air.source().equals("observed")?air.returnFloor():245;
            if(!WaterDescentPolicy.continueDescent(c.player.isUnderWater(),c.player.getHealth(),c.player.getAirSupply(),floor)){
                finish(c,"waiting","water descent stopped for surface air or health");return true;
            }
            JsonArray target=active.getAsJsonArray("target");
            double dx=target.get(0).getAsDouble()-c.player.getX(),dz=target.get(2).getAsDouble()-c.player.getZ();
            boolean align=WaterDescentPolicy.align(Math.hypot(dx,dz));
            if(align)RotationAim.apply(c.player,RotationAim.yawToward(dx,dz),10);
            c.options.keyUp.setDown(align);c.options.keyJump.setDown(false);
            c.options.keyShift.setDown(!align&&WaterDescentPolicy.sink(c.player.getY(),target.get(1).getAsDouble()));
            return true;
        }
        if(op.equals("use_item")){c.options.keyUse.setDown(true);return true;}
        if(c.screen!=null){c.options.keyUp.setDown(false);c.options.keyJump.setDown(false);c.options.keyAttack.setDown(false);return true;}
        if(op.equals("mine_block")){
            try{guard(c,active);}catch(Exception e){finish(c,"stopped",e.getMessage());return true;}
            if(dryPavingRequested(active))try{dryPavingRequestGuard(c,active);}
            catch(Exception e){finish(c,"waiting",e.getMessage());return true;}
            if(active.has("required_silk_shovel")&&active.get("required_silk_shovel").getAsBoolean()
                    &&!silkShovelReady(c,active)){
                finish(c,"waiting","Silk Touch shovel or selected slot changed; guarded mining stopped");return true;
            }
            if(active.has("required_plain_shovel")&&active.get("required_plain_shovel").getAsBoolean()
                    &&!snowShovelReady(c,active,false)){
                finish(c,"waiting","Non-Silk-Touch shovel or selected slot changed; snow harvesting stopped");return true;
            }
            if(active.has("underwater_gravel")&&active.get("underwater_gravel").getAsBoolean()){
                var air=airEstimate(c);
                boolean breathing=c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING)
                    ||c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER);
                if(!UnderwaterGravelPolicy.continueMining(c.player.isUnderWater(),c.player.getHealth(),
                        c.player.getAirSupply(),breathing,air.returnFloor())){
                    finish(c,"waiting","Underwater oxygen or health changed; surface before mining more");return true;
                }
            }
            JsonArray a=active.getAsJsonArray("pos");BlockPos target=new BlockPos(a.get(0).getAsInt(),a.get(1).getAsInt(),a.get(2).getAsInt());
            if(ordinaryMiningRequested(active)){
                if(singleBlockConfirmed(c,active)){
                    finish(c,"done","single target removal confirmed by server block update and native sequence acknowledgement");return true;
                }
                if(ordinaryMiningConfirmation.hold(c,str(active,"single_block_world"),str(active,"id"),target)){
                    c.options.keyAttack.setDown(false);c.gameMode.stopDestroyBlock();
                    detail="single target outcome pending; no second excavation sent";return true;
                }
            }
            if(active.has("footing_gravel")&&active.get("footing_gravel").getAsBoolean()
                    &&(!c.player.onGround()||!c.player.blockPosition().below().equals(target)
                        ||!GravelFootingPolicy.stableFloor(c.level,target))){
                finish(c,"waiting","Safe gravel footing changed");return true;
            }
            if(c.level.isEmptyBlock(target)){
                if(terrainReplaceRequested(active)){
                    c.options.keyAttack.setDown(false);
                    if(c.gameMode!=null)c.gameMode.stopDestroyBlock();
                    return true; // client air alone cannot acknowledge a guarded excavation
                }
                if(dryPavingRequested(active)){
                    c.options.keyAttack.setDown(false);
                    if(dryPavingClientAirTick<0)dryPavingClientAirTick=ticks;
                    return true; // predicted air is not an exact server acknowledgement
                }
                finish(c,"waiting","target became empty without current-request server confirmation; outcome pending");return true;
            }
            if(dryPavingRequested(active)&&dryPavingClientAirTick>=0){
                c.options.keyAttack.setDown(false);
                return true; // a correction must not start a second excavation
            }
            if(active.has("dry_paving_guard")&&active.get("dry_paving_guard").getAsBoolean()){
                try{dryPavingMiningGuard(c,target,str(active,"expected_state"));}
                catch(Exception e){finish(c,"waiting",e.getMessage());return true;}
            }
            if(terrainReplaceRequested(active)){
                try{terrainReplacementGuard(c,active);}
                catch(Exception e){finish(c,"waiting",e.getMessage());return true;}
            }
            if(!state(c,target).equals(str(active,"expected_state"))){finish(c,"error","mining target changed");return true;}
            Vec3 aim=blockAim(target,active);if(c.player.getEyePosition().distanceTo(aim)>c.player.blockInteractionRange()-.2){finish(c,"waiting","mining target moved out of reach");return true;}RotationAim.Look look=RotationAim.lookAt(c.player,aim);RotationAim.apply(c.player,look);
            BlockHitResult hit=c.level.clip(new ClipContext(c.player.getEyePosition(),aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
            if(!hit.getBlockPos().equals(target)){finish(c,"waiting","mining target is occluded");return true;}
            c.options.keyUp.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);c.options.keyAttack.setDown(false);c.hitResult=hit;
            if(ordinaryMiningRequested(active)){
                try{
                    boolean accepted=ordinaryMiningConfirmation.mine(c,str(active,"single_block_world"),str(active,"id"),target,hit.getDirection(),!mineStarted);
                    if(!accepted&&!mineStarted){finish(c,"waiting","native mining start was rejected; no completion claimed");return true;}
                    mineStarted=true;
                }catch(Exception failure){
                    finish(c,"waiting","single target mining send interrupted; outcome pending, no second excavation sent: "+failure.getMessage());return true;
                }
            }else if(!mineStarted){
                if(terrainReplaceRequested(active))terrainServerConfirmation.sent(session(c),
                    str(active,"id"),str(active,"terrain_replace_stage"),terrainAckTarget(active));
                if(dryPavingRequested(active))dryPavingServerConfirmation.sent(session(c),
                    str(active,"id"),dryPavingAckStage(active),dryPavingAckTarget(active));
                c.gameMode.startDestroyBlock(target,hit.getDirection());mineStarted=true;
            }
            else c.gameMode.continueDestroyBlock(target,hit.getDirection());
            // Record local prediction before a server correction can be applied on the next client event.
            if(dryPavingRequested(active)&&c.level.isEmptyBlock(target)&&dryPavingClientAirTick<0)
                dryPavingClientAirTick=ticks;
            return true;
        }
        JsonArray p=active.getAsJsonArray("target");double dx=p.get(0).getAsDouble()-c.player.getX(),dz=p.get(2).getAsDouble()-c.player.getZ();
        double distance=Math.hypot(dx,dz),arrival=active.has("arrival")?active.get("arrival").getAsDouble():.65;
        if(c.player.onGround() && distance>arrival){
            BlockPos foot=BlockPos.containing(c.player.getX()+dx/distance*.7,c.player.getY()-.1,c.player.getZ()+dz/distance*.7);boolean supported=false;
            for(int down=0;down<3;down++){BlockPos q=foot.below(down);if(!c.level.getBlockState(q).getCollisionShape(c.level,q).isEmpty()){supported=true;break;}}
            if(!supported){finish(c,"waiting","unsafe drop ahead; choose another walking waypoint");return true;}
        }
        RotationAim.apply(c.player,RotationAim.yawToward(dx,dz),10);
        c.options.keyUp.setDown(distance>arrival);c.options.keyDown.setDown(false);c.options.keyLeft.setDown(false);c.options.keyRight.setDown(false);c.options.keyShift.setDown(false);
        double dy=p.get(1).getAsDouble()-c.player.getY();c.options.keyJump.setDown(c.player.onGround() && dy>.5 && dy<1.3);
        return true;
    }
    private static void releaseWalk(Minecraft c){if(op.equals("use_item")){c.options.keyUse.setDown(false);if(c.gameMode!=null && c.player!=null)c.gameMode.releaseUsingItem(c.player);if(c.player!=null && foodOriginalSlot>=0 && c.player.getInventory().getSelectedSlot()==foodUseSlot)c.player.getInventory().setSelectedSlot(foodOriginalSlot);foodOriginalSlot=foodUseSlot=-1;return;}if(!Set.of("walk","walk_path","mine_block").contains(op))return;if(c.options!=null){c.options.keyUp.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);c.options.keyAttack.setDown(false);}if(op.equals("mine_block") && c.gameMode!=null)c.gameMode.stopDestroyBlock();if(op.equals("walk")&&active!=null&&active.has("freefall_brake_y"))MeteorModules.enable(MeteorModules.FLIGHT);if(restoreFlight){MeteorModules.enable(MeteorModules.FLIGHT);restoreFlight=false;}}
    private static boolean freefallColumnClear(Minecraft c,BlockPos center,int lowY,int highY){
        if(c.level==null||highY<lowY||highY-lowY>256)return false;
        for(int x=center.getX()-1;x<=center.getX()+1;x++)for(int z=center.getZ()-1;z<=center.getZ()+1;z++)for(int y=lowY;y<=highY;y++){
            BlockPos p=new BlockPos(x,y,z);if(!c.level.hasChunkAt(p))return false;
            var state=c.level.getBlockState(p);
            if(!state.getCollisionShape(c.level,p).isEmpty()||!state.getFluidState().isEmpty())return false;
        }
        return true;
    }
    public static void tick(Minecraft c){
        syncMaterialMiningLease(c);
        if(materialMiningCleanupPending){writeStatus(c);return;}
        if(!initialized){initialized=true;try{Path old=root(c).resolve("request.json");if(Files.isRegularFile(old))lastId=str(JsonParser.parseString(Files.readString(old)).getAsJsonObject(),"id");}catch(Exception ignored){}}
        if(guiRequested){guiRequested=false;if(c.player!=null)KitClient.openGui(c);}
        ticks++;
        if(active==null&&scaffoldFillTask!=null){scaffoldFillTask.close();lastScaffoldFill=scaffoldFillTask.snapshot();if(!scaffoldFillTask.cleanupPending())scaffoldFillTask=null;}
        if(ticks%5==0)pollMaterialTasks(c);
        validateProjectionBatch(c);
        nativeMaterialRunQueued(c);
		nativeMaterialTickCheck(c);
        restoreGuardAfterReconnect(c);
        if(!ownedBorerSession.isEmpty() && (KitClient.borer()==null || !KitClient.borer().isActive()))ownedBorerSession="";
        if(ticks%5==0){
            Path f=root(c).resolve("request.json");
            try{
                if(Files.isRegularFile(f) && Files.size(f)<=131072){
                    JsonObject r=JsonParser.parseString(Files.readString(f)).getAsJsonObject();String id=str(r,"id");
                    if(!id.isBlank() && !id.equals(lastId)){
                        if(interfacePaused(c)&&!interfaceReadOrStop(str(r,"op"))){deferInterfaceRequest(c,r);}
                        else{
                            resumeInterfaceRequest(c,r);
                            lastId=id;
                            try {
                                if(Files.size(f)>16384&&!str(r,"op").equals("projection_batch_set"))throw new IllegalArgumentException("Request exceeds the bounded action size");
                                if(nativeMaterialOwner!=null&&!Set.of("snapshot","scan","scan_snow_biomes","snow_seed_candidates","scan_trees","projection_audit","projection_model","map_audit","gravel_stop").contains(str(r,"op")))
                                    throw new IllegalStateException("A local material session owns all write actions");
                                if(active!=null && !str(r,"op").equals("stop") && !Set.of("snapshot","scan","scan_snow_biomes","snow_seed_candidates","scan_trees","projection_audit","projection_model","map_audit","gravel_stop","material_job_pause").contains(str(r,"op")))throw new IllegalStateException("A job is active; stop it first");
                                boolean previousDispatching=dispatching,previousHandoff=materialHandoffDispatch;
                                try{
                                dispatching=true;
                                materialHandoffDispatch=currentMaterialRequest(c,r);
                                dispatch(c,r);
                                if(supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")&&str(r,"task_session").equals(str(supervisionLease,"job_session")))supervisionLease.addProperty("revision",controlRevision);
                            }finally{
                                materialHandoffDispatch=previousHandoff;
                                dispatching=previousDispatching;
                            }
                            } catch(Exception e) {
                                if(active!=null && str(active,"id").equals(id)){abortOwnedRequest(c,"脚本参数无效");active=null;}
                                JsonObject error=snapshot(c);attachTerminalConfirmation(c,error,id);error.addProperty("id",id);error.addProperty("phase","error");error.addProperty("detail",e.getMessage());save(root(c).resolve("reply-"+safeId(id)+".json"),error);
                                if(active==null){statusId=id;phase="error";detail=e.getMessage();writeStatus(c);}
                            }
                        }
                    }
                }
            }catch(Exception e){phase="error";detail=e.getClass().getSimpleName()+": "+e.getMessage();writeStatus(c);}
        }
        tickScan(c);
        if(interfacePaused(c)){tickInterfacePause(c);return;}
        if(active!=null){
            try{
                guard(c,active);
                if(nativeAirReturnActive&&op.equals("navigate")&&c.player!=null
                        &&!c.player.isUnderWater()&&c.player.getY()>=materialAirRoute.returnY()-1){
                    materialAirRoute.finishAscent(c,str(active,"id"),true);
                    KitClient.controller().stop(c,"已从水下返气");
                    nativeAirReturnActive=false;nativeAirReturnPhase="recovered";
                    finish(c,"waiting","native air return reached breathable air; "+nativeAirReturnOriginalOp+" interrupted");
                    return;
                }
                if(op.equals("rock_quarry_batch")){
                    tickRockQuarry(c,false);
                }else if(op.equals("quarry_batch")){
                    int gained=count(c,"minecraft:sand")-active.get("sand_before").getAsInt();
                    if(c.player.getHealth()<19){finish(c,"waiting","quarry stopped for health; verify safe parking");}
                    else if(gained>=active.get("target_count").getAsInt())finish(c,"done","sand inventory target reached");
                    else if(!KitClient.borer().isActive())finish(c,"waiting","native quarry stopped: "+KitClient.borer().status());
                }else if(Set.of("build_supply","collect_supply","approach_block","collect_item").contains(op)){
                    if(guardBusy || c.player.getHealth()<14)deadline++;
                    try{supplyTask.tick(c);}catch(Exception e){supplyTask.fail(c,e.getMessage());}
                    if(!supplyTask.failure().isEmpty())finish(c,"waiting",supplyTask.failure());
                    else if(supplyTask.done())finish(c,"done",op.equals("collect_item")?"drop pickup verified in inventory":op.equals("approach_block")?"work block reach and visibility verified":"depot withdrawal verified in inventory");
                }else if(op.equals("craft_recipe")){
                    if(guardBusy || c.player.getHealth()<14){detail="recipe paused for defense or health";deadline++;}
                    else craftTask.tick(c);
                    if(!craftTask.failure().isEmpty())finish(c,"waiting",craftTask.failure());
                    else if(craftTask.done()){
                        if(craftRemaining>0){craftRemaining--;craftTask=new SurvivalCraftTask(c,craftSpec);}
                        else finish(c,"done","recipe confirmed in inventory");
                    }
                }else if(op.equals("professional_print")){
                    if(!ProfessionalPrinter.failure().isEmpty()){finish(c,"error",ProfessionalPrinter.failure());return;}
                    if(!guardBusy && c.screen==null && c.player.getHealth()>=14)ProfessionalPrinter.resume();
                    if(!guardBusy && (c.player.getHealth()<14 || !MeteorModules.isActive(MeteorModules.KILL_AURA) || !MeteorModules.isActive(MeteorModules.AUTO_LOG))){finish(c,"waiting","health or defense requires attention");}
                    else if(!guardBusy&&c.screen==null&&boundedPrinterComplete(c))
                        finish(c,"done","all bounded printer targets server-confirmed; batch finished early");
                    else if(ticks>=deadline)finish(c,"waiting","printer interval ended without complete current bounded-mask server confirmation");
                }else if(op.equals("projection_scaffold_fill")){
                    switch(scaffoldFillTask.observe(c,ticks,ticks>=deadline)){
                        case DONE->finish(c,"done","entire controlled row matches with exact cumulative inventory delta and new-cell server updates");
                        case WAITING->finish(c,"waiting",scaffoldFillTask.failure());
                        case RUNNING->detail="owned bounded Scaffold row; at most two pending server acknowledgements";
                    }
                }else if(op.equals("projection_air_seed")){
                    if(!currentMaterialRequest(c,active)||!guardArmed()||!pveOnly()||guardBusy
                        ||KitKeys.manualMovementDown(c)||c.player.getHealth()<19||loadedHostileNearby(c))
                        finish(c,"waiting","air seed ownership or protection changed; no second interaction sent");
                    else switch(airSeedTask.poll(c,ticks,ticks>=deadline)){
                        case DONE->finish(c,"done","one projected air seed confirmed by server block update and material delta");
                        case WAITING->finish(c,"waiting","air seed is unconfirmed; no second interaction sent");
                        case RUNNING->detail="waiting for exact server air-seed confirmation; no retry";
                    }
                }else if(Set.of("bucket_fill","bucket_place").contains(op)){
                    switch(bucketWaterTask.poll(c,ticks,ticks>=deadline)){
                        case DONE->finish(c,"done","one normal water bucket use confirmed by current-connection block and inventory packets");
                        case WAITING->finish(c,"waiting","bucket outcome unconfirmed or protection changed; durable claim retained, no second use sent");
                        case RUNNING->detail="waiting for target block and bucket inventory server packets; no retry";
                    }
                }else if(op.equals("map_create")){
                    if(!currentMaterialRequest(c,active)||!guardArmed()||!pveOnly()||guardBusy
                        ||KitKeys.manualMovementDown(c)||c.player.getHealth()<19||loadedHostileNearby(c))
                        finish(c,"waiting","map creation protection or ownership changed; no second use sent");
                    else switch(mapCreationTask.poll(c,ticks>=deadline)){
                        case DONE->finish(c,"done","one empty map consumed and one new map ID confirmed in inventory");
                        case WAITING->finish(c,"waiting","map creation inventory result is unconfirmed; no second use sent");
                        case RUNNING->detail="waiting for the single map use inventory result; no retry";
                    }
                }else if(op.equals("use_item")){
                    if(c.player.getHealth()<14 || hostileNearby(c))finish(c,"waiting","food interrupted by health or nearby enemy");
                    else if(count(c,str(active,"item"))<useCount)finish(c,"done","item consumed; verify food and inventory");
                    else c.options.keyUse.setDown(true);
                }else if(op.equals("nudge_horse")){
                    tickHorseNudge(c);
                }else if(op.equals("concrete_batch")){
                    var maker=KitClient.concrete();var progress=maker.snapshot();
                    int completed=progress.get("completed").getAsInt(),target=active.get("target_count").getAsInt();
                    if(guardBusy)deadline++;
                    if(c.player.getHealth()<14 || hostileNearby(c)){maker.stop(c,"防护接管");finish(c,"waiting","concrete paused for health or nearby hostile");}
                    else if(!maker.isActive()){
                        if(completed<target)finish(c,"waiting",maker.status());
                        else if(supplyTask!=null){
                            try{supplyTask.tick(c);}catch(Exception e){supplyTask.fail(c,e.getMessage());}
                            if(!supplyTask.failure().isEmpty())finish(c,"waiting","concrete drop recovery: "+supplyTask.failure());
                            else if(supplyTask.done())supplyTask=null;
                        }else if(count(c,str(active,"solid_item"))>=active.get("solid_before").getAsInt()+target)finish(c,"done","concrete hardened, mined and recovered in inventory");
                        else if(concretePickupDeadline==0)concretePickupDeadline=ticks+400;
                        else if(ticks>=concretePickupDeadline)finish(c,"waiting","concrete mined but drops were not all recovered");
                        else{
                            int missing=active.get("solid_before").getAsInt()+target-count(c,str(active,"solid_item"));
                            BlockPos cell=new BlockPos(active.getAsJsonArray("support").get(0).getAsInt(),active.getAsJsonArray("support").get(1).getAsInt()+1,active.getAsJsonArray("support").get(2).getAsInt());
                            var drop=java.util.stream.StreamSupport.stream(c.level.entitiesForRendering().spliterator(),false).filter(e->e instanceof net.minecraft.world.entity.item.ItemEntity)
                                .map(e->(net.minecraft.world.entity.item.ItemEntity)e)
                                .filter(e->ConcreteDropPolicy.eligible(e.isAlive(),concretePreexistingDrops.contains(e.getUUID()),itemId(e.getItem()).equals(str(active,"solid_item")),
                                    e.getItem().getCount(),missing,e.position().distanceToSqr(Vec3.atCenterOf(cell)),e.distanceTo(c.player)))
                                .min(Comparator.comparingDouble(e->e.distanceToSqr(c.player))).orElse(null);
                            if(drop!=null){
                                boolean same=drop.getUUID().equals(concreteRetryUuid);
                                double moved=concreteRetryPos==null?Double.POSITIVE_INFINITY:drop.position().distanceToSqr(concreteRetryPos);
                                if(ConcreteDropPolicy.shouldRetry(same,moved,ticks-concreteRetryTick)){
                                    var pickup=new JsonObject();pickup.addProperty("expected_uuid",drop.getUUID().toString());pickup.addProperty("expected_item",str(active,"solid_item"));pickup.addProperty("expected_count",drop.getItem().getCount());
                                    try{supplyTask=BuildSupplyTask.pickup(c,pickup);concretePickupDeadline=ticks+600;detail="collecting concrete drops from verified batch";}
                                    catch(Exception e){
                                        if(Set.of("No visible collision-free depot approach","No collision-free start for depot path","Drop is no longer loaded; observe again").contains(e.getMessage())){
                                            concreteRetryUuid=drop.getUUID();concreteRetryPos=drop.position();concreteRetryTick=ticks;detail="waiting for drifting concrete drop to reach a safe pickup pose";
                                        }else finish(c,"waiting","concrete drop pickup could not start: "+e.getMessage());
                                    }
                                }
                            }
                        }
                    }else detail=maker.status();
                }else if(op.equals("mine_block")){
                    if(terrainReplaceRequested(active)){
                        if(terrainServerConfirmation.confirmed(session(c),str(active,"id"),
                                str(active,"terrain_replace_stage"),terrainAckTarget(active)))
                            finish(c,"done","matching server block update acknowledged the guarded excavation");
                        else detail="waiting for exact server block update after guarded excavation";
                    }else if(dryPavingRequested(active)){
                        BlockPos target=dryPavingAckTarget(active);
                        if(dryPavingServerConfirmation.confirmed(session(c),str(active,"id"),
                                dryPavingAckStage(active),target)
                                && dryPavingConfirmedTick>=0 && ticks-dryPavingConfirmedTick>=8
                                && state(c,target).equals(dryPavingAckExpected(active)))
                            finish(c,"done","matching server block update acknowledged the dry paving excavation");
                        else if(dryPavingClientAirTick>=0 && ticks-dryPavingClientAirTick>=60)
                            finish(c,"waiting","server air update missing or corrected after one dry paving excavation");
                        else detail="waiting for exact server block update after dry paving excavation";
                    }else{
                        if(singleBlockConfirmed(c,active))
                            finish(c,"done","single target removal confirmed by server block update and native sequence acknowledgement");
                        else detail="waiting for single target server block update and native sequence acknowledgement";
                    }
                }else if(op.equals("walk") || op.equals("walk_path")){
                    JsonArray p=active.getAsJsonArray("target");double dx=c.player.getX()-p.get(0).getAsDouble(),dz=c.player.getZ()-p.get(2).getAsDouble();
                    double arrival=active.has("arrival")?active.get("arrival").getAsDouble():.65;
                    boolean waterDescend=op.equals("walk")&&active.has("water_descend")&&active.get("water_descend").getAsBoolean();
                    boolean vertical=survival(active)?c.player.onGround() && Math.abs(c.player.getY()-p.get(1).getAsDouble())<=.2:waterDescend?WaterDescentPolicy.atTarget(c.player.getY(),p.get(1).getAsDouble()):Math.abs(c.player.getY()-p.get(1).getAsDouble())<=1.2;
                    if(Math.hypot(dx,dz)<=arrival && vertical){
                        if(op.equals("walk_path") && ++pathIndex<active.getAsJsonArray("path").size())active.add("target",active.getAsJsonArray("path").get(pathIndex).deepCopy());
                        else finish(c,"done","walk target reached");
                    }
                }else if(op.equals("chop")){
                    if(count(c,str(active,"item"))>=desiredCount)KitClient.chopper().finishCurrentTree();
                    if(KitClient.chopper().waitingForTree()){KitClient.chopper().stop(c,"当前附近没有该树种，交回跑图搜索");finish(c,"waiting","no matching tree in local reach");}
                    else if(!KitClient.chopper().isActive())finish(c,KitClient.chopper().materialTargetFinished()?"done":"stopped",KitClient.chopper().materialTargetFinished()?"tree batch and pickup completed; verify material count":"chopper stopped");
                }else if(op.equals("navigate")&&materialAirNavigation!=null){
                    if(guardBusy)materialAirNavigation.defensePause();
                    else{
                        materialAirNavigation.observe(c);
                        if(materialAirNavigation.done())finish(c,"done","air-only waypoint reached and stable after restoring Flight settings");
                    }
                }else if(op.equals("navigate") && !KitClient.controller().isActive()){
                    JsonArray p=active.getAsJsonArray("target");double dx=c.player.getX()-p.get(0).getAsDouble(),dz=c.player.getZ()-p.get(2).getAsDouble();
                    boolean arrived=Math.hypot(dx,dz)<=KitClient.config().arrivalRadius+1 && Math.abs(c.player.getY()-p.get(1).getAsDouble())<=1;
                    materialAirRoute.finishAscent(c,str(active,"id"),arrived);
                    if(nativeAirReturnActive){
                        nativeAirReturnActive=false;
                        if(c.player.isUnderWater()){
                            nativeAirReturnPhase="stopped_underwater";
                            suspendAutoReconnect();KitClient.safeLogout(c,"水下返气导航中断，停止并退出");
                        }else{
                            nativeAirReturnPhase="recovered";
                            finish(c,"waiting","native air return reached breathable air; "+nativeAirReturnOriginalOp+" interrupted");
                        }
                    }else finish(c,arrived?"done":"stopped","navigation ended");
                }else if(op.equals("print") && !KitClient.machines().isPlacing())finish(c,"stopped","printer stopped");
                else if(op.equals("settle") && terrainReplaceRequested(active)){
                    if(terrainServerConfirmation.confirmed(session(c),str(active,"id"),
                            str(active,"terrain_replace_stage"),terrainAckTarget(active)))
                        finish(c,"done","matching server block update acknowledged the guarded placement");
                    else if(ticks>=deadline)
                        finish(c,"waiting","server block update missing; terrain placement outcome unknown");
                }else if(op.equals("settle") && dryPavingRequested(active)){
                    BlockPos target=dryPavingAckTarget(active);
                    if(dryPavingServerConfirmation.confirmed(session(c),str(active,"id"),
                            dryPavingAckStage(active),target)
                            && dryPavingConfirmedTick>=0 && ticks-dryPavingConfirmedTick>=8
                            && state(c,target).equals(dryPavingAckExpected(active)))
                        finish(c,"done","matching server block update acknowledged the dry paving placement");
                    else if(ticks>=deadline)
                        finish(c,"waiting","server block update missing or corrected; dry paving placement outcome unknown");
                }else if(op.equals("settle") && ticks>=deadline)finish(c,"done","server state available");
                if(active!=null && ticks>=deadline && !op.equals("settle")){
                    boolean terrain=terrainReplaceRequested(active);
                    if(terrain)finish(c,"waiting","server block update missing; terrain excavation outcome unknown");
                    else if(dryPavingRequested(active))finish(c,"waiting","server block update missing; dry paving excavation outcome unknown");
                    else if(ordinaryMiningRequested(active))finish(c,"waiting","single target confirmation timed out; outcome pending, no second excavation sent");
                    else{abortOwnedRequest(c,"脚本任务达到时间上限");finish(c,"waiting","time limit reached; inspect progress before resuming");}
                }
            }catch(Exception e){
                if(active!=null&&op.equals("nudge_horse"))
                    finish(c,"waiting","one horse nudge was spent; observation stopped without a second hit: "+e.getMessage());
                else if(active!=null&&terrainReplaceRequested(active))
                    finish(c,"waiting","guarded terrain action changed; outcome unknown: "+e.getMessage());
                else if(ordinaryMiningRequested(active))
                    finish(c,"waiting","single target mining interrupted; outcome pending, no second excavation sent: "+e.getMessage());
                else{abortOwnedRequest(c,"脚本世界或人物状态已变化");finish(c,"stopped",e.getMessage());}
            }
        }
        ProfessionalPrinter.tick(c);
        tickSupervision(c);
        if(ticks%20==0)writeStatus(c);
    }
    private static void guard(Minecraft c,JsonObject r){
        if(c.player==null || c.level==null || c.gameMode==null || c.player.isDeadOrDying())throw new IllegalStateException("Not alive in a world");
        survivalGuard(c,r);
        String current=c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;
        if(!AutomationScope.sameServer(current,str(r,"server")))throw new IllegalStateException("Wrong server");
        if(!c.level.dimension().identifier().toString().equals(str(r,"dimension")))throw new IllegalStateException("Wrong dimension");
		if(r==active&&r.has("snow_expedition_token")&&!activeSnowNavigationScope(c,r))
			throw new IllegalStateException("Snow expedition permit, lease, or PvE guard changed");
        JsonArray site=r.getAsJsonArray("site");
        if(site==null || site.size()!=3)throw new IllegalArgumentException("Site is required");
        double dx=c.player.getX()-site.get(0).getAsDouble(),dz=c.player.getZ()-site.get(2).getAsDouble();
        if(!AutomationScope.nearSite(dx,dz)
				&&!pendingSnowReturnScope(c,r)&&!activeSnowNavigationScope(c,r))
            throw new IllegalStateException("Outside authorized worksite; lobby actions refused");
    }
    private static void gravelScope(Minecraft c,JsonObject r){
        if(c.player==null||c.level==null||c.player.isDeadOrDying()
                ||!str(r,"world_session").equals(session(c))
                ||!r.has("expected_revision")||r.get("expected_revision").getAsLong()!=controlRevision
                ||!r.has("expires_at")||r.get("expires_at").getAsLong()<System.currentTimeMillis()
                ||r.get("expires_at").getAsLong()-System.currentTimeMillis()>15000)
            throw new IllegalStateException("Gravel control belongs to an old world or controller");
    }
    private static void configureGravel(JsonObject r){
        var config=KitClient.config();
        int radius=r.has("radius")?r.get("radius").getAsInt():config.gravelRadius;
        int depth=r.has("depth")?r.get("depth").getAsInt():config.gravelDepth;
        int limit=r.has("limit")?r.get("limit").getAsInt():config.gravelLimit;
        if(radius<4||radius>64||depth<6||depth>32||limit<0||limit>2304)
            throw new IllegalArgumentException("Gravel radius 4..64, depth 6..32, limit 0..2304 required");
        config.gravelRadius=radius;config.gravelDepth=depth;config.gravelLimit=limit;config.gravelWaterMode=true;
        config.save();
    }
    private static void gravelReceipt(Minecraft c)throws Exception{
        JsonObject receipt=snapshot(c);
        receipt.addProperty("id",lastId);receipt.addProperty("phase",phase);receipt.addProperty("detail",detail);
        save(root(c).resolve("reply-"+safeId(lastId)+".json"),receipt);
    }
    private static void dispatch(Minecraft c,JsonObject r)throws Exception{
        String command=str(r,"op");
        if(command.equals("stop")){if(r.has("expected_revision") && (r.get("expected_revision").getAsLong()!=controlRevision || !str(r,"world_session").equals(session(c))))throw new IllegalStateException("Stop belongs to an old controller");statusId=lastId;ProfessionalPrinter.stop(c,true);KitClient.emergencyStop("本地脚本停止");active=null;phase="stopped";detail="stopped";writeStatus(c);return;}
        if(command.equals("gravel_stop")){
            gravelScope(c,r);
            if(!GravelCollector.isActive())throw new IllegalStateException("No gravel collection is active");
            GravelCollector.stop(c,"本机接口停止");
            statusId=lastId;phase="done";op=command;detail="gravel returning to safe height";
            gravelReceipt(c);writeStatus(c);return;
        }
        if(command.equals("material_job_pause")){
            externalMaterialScope(c,r);
            if(c.screen!=null&&!interfacePaused(c)&&!c.screen.getClass().getName().startsWith("dev.twob2tkit."))
                throw new IllegalStateException("Material pause cannot take over a different item interface");
            if(r.has("release")&&(!r.get("release").isJsonPrimitive()||!r.getAsJsonPrimitive("release").isBoolean()))
                throw new IllegalArgumentException("Material release must be boolean");
            boolean release=r.has("release")&&r.get("release").getAsBoolean();
            materialJobCancel(c,str(r,"task_session"),"材料作业已暂停，防护继续");
            if(release){supervisionLease=null;releaseMaterialMiningLease();lastSupervisionHeartbeat=0;projectionBatch.reset();}
            statusId=lastId;op=command;phase="done";detail=release?"owned material task stopped and lease released; PvE guard retained":"owned material task stopped; PvE guard and lease retained";
            writeStatus(c);return;
        }
        guard(c,r);
        if(r.has("task_session")&&!command.equals("material_session")){
            long expiry=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")||!str(r,"task_session").equals(str(supervisionLease,"job_session"))||!str(r,"world_session").equals(session(c))||!r.has("expected_revision")||r.get("expected_revision").getAsLong()!=controlRevision||expiry<0||expiry>15000)throw new IllegalStateException("Material action scope changed");
        }
        if(command.equals("safe_logout")){
            if(!r.has("expires_at")||r.get("expires_at").getAsLong()<System.currentTimeMillis()||!str(r,"world_session").equals(session(c))||!r.has("expected_revision")||r.get("expected_revision").getAsLong()!=controlRevision)throw new IllegalStateException("Logout scope changed");
            suspendAutoReconnect();KitClient.safeLogout(c,"本机控制器已结束本次操作");return;
        }
        if(survival(r)){
            if(!r.has("expected_revision") || r.get("expected_revision").getAsLong()!=controlRevision)throw new IllegalStateException("Control was handed over; restart explicitly");
            long remaining=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            if(remaining<0 || remaining>15000)throw new IllegalStateException("Expired survival action");
        }
        if(Set.of("snapshot","scan","scan_snow_biomes","snow_seed_candidates","scan_trees","projection_audit","projection_model","map_audit").contains(command)){
            if(survival(r)){survivalArmed=true;survivalBackground=background(r);}
            if(command.equals("scan")){startScan(c,r);writeStatus(c);return;}
            JsonObject out=snapshot(c);out.addProperty("id",lastId);
            if(command.equals("scan_snow_biomes"))out.add("snow_biome_survey",SnowBiomeSurvey.scan(c,r));
            if(command.equals("snow_seed_candidates"))out.add("snow_seed_candidates",
                snowSeedCandidates(c,r));
            if(command.equals("scan_trees"))out.add("tree_survey",TreeSurvey.scan(c,r));
            if(command.equals("projection_audit"))out.add("projection_audit",ProjectionAudit.scan(c));
            if(command.equals("projection_model"))out.add("projection_model",ProjectionAudit.model(c));
            if(command.equals("map_audit")){
                out.add("map_audit",MapAutomation.audit(c,r));out.addProperty("phase","done");
                out.addProperty("detail","current loaded client map pixels read; geographic metadata and freshness are not server-verified");
            }
            if(nativeMaterialDispatch)nativeMaterialReadResult=out;
            else save(root(c).resolve("reply-"+safeId(lastId)+".json"),out);
            writeStatus(c);return;
        }
        if(dev.twob2tkit.combat.EmergencyExit.held(c))throw new IllegalStateException("Safety lock: manual in-game acknowledgement required; do not reconnect automatically");
        boolean defensiveRise=false;
        if(guardBusy && command.equals("navigate") && r.has("task_session") && r.has("target")
                && supervisionLease!=null && str(supervisionLease,"kind").equals("materials")){
            JsonArray point=r.getAsJsonArray("target");
            if(point!=null && point.size()==3)defensiveRise=GuardEscapePolicy.allowed(true,guardScope!=null,
                c.player.getX(),c.player.getY(),c.player.getZ(),
                point.get(0).getAsDouble(),point.get(1).getAsDouble(),point.get(2).getAsDouble());
        }
        if(guardBusy && !Set.of("guard","use_item","air_return_set").contains(command) && !defensiveRise)throw new IllegalStateException("Construction guard is defending or eating; wait before changing items or starting work");
        statusId=lastId;
        if(command.equals("gravel_start")||command.equals("gravel_config")){
            gravelScope(c,r);
            if(GravelCollector.isActive()||nativeMaterialOwner!=null||active!=null)
                throw new IllegalStateException("Gravel collection or another task already owns control");
            configureGravel(r);
            if(command.equals("gravel_start")){
                if(!GravelCollector.start(c))throw new IllegalStateException(GravelCollector.status());
                detail="gravel collector started";
            }else detail="gravel collector settings saved";
            phase="done";op=command;
        }else if(command.equals("air_return_set")){
            if(!materialAirScope(c)||!r.has("task_session")
                    ||!str(r,"task_session").equals(str(supervisionLease,"job_session"))
                    ||!respirationThree(c)||!MeteorModules.isActive(MeteorModules.AUTO_LOG))
                throw new IllegalStateException("Current guarded material lease is required for an air route");
            JsonArray t=r.getAsJsonArray("target");checkSiteTarget(r,t);
            if(t==null||t.size()!=3)throw new IllegalArgumentException("Expected air-return target");
            materialAirRoute.configure(c,session(c),str(supervisionLease,"job_session"),airGear(c),
                new Vec3(t.get(0).getAsDouble(),t.get(1).getAsDouble(),t.get(2).getAsDouble()),
                System.currentTimeMillis());
            nativeAirReturnPhase="armed";phase="done";op=command;detail="verified material air route refreshed";
        }else if(command.equals("material_session")){
            long expiry=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            boolean replacing=r.has("replace_parking_lease");
            boolean resumePark=supervisionLease!=null&&replacing
                &&MaterialJobControlPolicy.replaceableParking(str(r,"replace_parking_lease"),str(supervisionLease,"id"),
                    str(supervisionLease,"kind"),str(supervisionLease,"world_session"),session(c),
                    supervisionLease.has("revision")?supervisionLease.get("revision").getAsLong():-1,controlRevision,
                    highGuardPark(c,supervisionLease),guardArmed()&&pveOnly(),guardBusy);
            boolean leaseAvailable=replacing?resumePark:supervisionLease==null;
            if(expiry<0||expiry>15000||!r.has("expected_revision")||r.get("expected_revision").getAsLong()!=controlRevision||!str(r,"world_session").equals(session(c))||!leaseAvailable||KitClient.anyAfkAuto()||c.screen!=null||KitKeys.manualMovementDown(c)||c.player.getHealth()<14)throw new IllegalStateException("Material session cannot acquire control");
            boolean guardFinish=str(r,"remote_finish").equals("guard");
            if(guardFinish){JsonArray park=r.getAsJsonArray("park_target");if(park==null||park.size()!=3)throw new IllegalArgumentException("High guard finish requires a park target");for(var value:park)if(!Double.isFinite(value.getAsDouble()))throw new IllegalArgumentException("Invalid park target");}
            CraftingCompatibility.requireReady();
            ProfessionalPrinter.stop(c,true); // Inventory/crafting ownership excludes an externally enabled printer.
            if(resumePark)supervisionLease=null;
            String leaseId=safeId(str(r,"supervision_lease")),taskId=safeId(str(r,"task_session"));supervisionLease=new JsonObject();supervisionLease.addProperty("id",leaseId);supervisionLease.addProperty("world_session",session(c));supervisionLease.addProperty("job_session",taskId);supervisionLease.addProperty("kind","materials");supervisionLease.addProperty("revision",controlRevision);supervisionLease.addProperty("remote_finish",guardFinish?"guard":"disconnect");supervisionLease.add("search_origin",JSON.toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));supervisionLease.add("return_target",materialReturnTarget(KitClient.config().homeTarget(),c.level.dimension().identifier().toString(),c.player.getX(),c.player.getY(),c.player.getZ()));if(guardFinish)supervisionLease.add("park_target",r.getAsJsonArray("park_target").deepCopy());lastSupervisionHeartbeat=System.currentTimeMillis();logoutQuiet.reset(lastSupervisionHeartbeat);
            try{armPveGuard(c);acquireMaterialMiningLease(c);}
            catch(RuntimeException failure){supervisionLease=null;releaseMaterialMiningLease();throw failure;}
            phase="done";detail="material session protected";
        }else if(command.equals("material_job_park")){
            externalMaterialScope(c,r);updateMaterialPark(c,r);
            phase="done";op=command;detail="local guard parking target updated; movement not started";
        }else if(command.equals("rock_quarry_batch")){
            startRockQuarry(c,r);
        }else if(command.equals("quarry_batch")){
            boolean owned=supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")
                &&str(supervisionLease,"job_session").equals(str(r,"task_session"));
            var borer=KitClient.borer();
            if(!owned||!guardArmed()||!pveOnly()||c.player.getHealth()<19
                    ||c.player.getFoodData().getFoodLevel()<8||c.player.isUnderWater()
                    ||c.screen!=null||KitKeys.manualMovementDown(c)||hostileNearby(c)
                    ||borer==null||borer.isActive()||KitClient.controller().isActive()
                    ||KitClient.anyAfkAuto()||!KitClient.config().borerAutoDefend)
                throw new IllegalStateException("Guarded, healthy, idle dry quarry scope required");
            if(!c.level.dimension().equals(net.minecraft.world.level.Level.OVERWORLD)
                    ||!str(r,"item").equals("minecraft:sand"))
                throw new IllegalArgumentException("Only dry Overworld sand is supported by the material quarry");
            var low=r.getAsJsonArray("min");var high=r.getAsJsonArray("max");
            checkSiteTarget(r,low);checkSiteTarget(r,high);
            for(var point:List.of(low,high))for(var v:point)
                if(!Double.isFinite(v.getAsDouble())||v.getAsDouble()!=Math.rint(v.getAsDouble()))
                    throw new IllegalArgumentException("Quarry coordinates must be integers");
            BlockPos min=new BlockPos(low.get(0).getAsInt(),low.get(1).getAsInt(),low.get(2).getAsInt());
            BlockPos max=new BlockPos(high.get(0).getAsInt(),high.get(1).getAsInt(),high.get(2).getAsInt());
            int amount=r.get("target_count").getAsInt();
            if(!MaterialQuarryPolicy.bounds(max.getX()-min.getX()+1,max.getY()-min.getY()+1,
                    max.getZ()-min.getZ()+1,amount)||min.getY()<c.level.getSeaLevel()+1
                    ||c.player.getY()<max.getY()+2
                    ||Math.hypot(c.player.getX()-(min.getX()+max.getX()+1)/2.0,
                        c.player.getZ()-(min.getZ()+max.getZ()+1)/2.0)>64)
                throw new IllegalArgumentException("Quarry bounds or clear aerial start are invalid");
            int available=0;
            for(BlockPos p:BlockPos.betweenClosed(min.offset(-3,-2,-3),max.offset(3,2,3))){
                boolean inside=p.getX()>=min.getX()&&p.getX()<=max.getX()
                    &&p.getY()>=min.getY()&&p.getY()<=max.getY()
                    &&p.getZ()>=min.getZ()&&p.getZ()<=max.getZ();
                var state=c.level.getBlockState(p);
                if(!MaterialQuarryPolicy.cellAllowed(c.level.hasChunkAt(p),inside,state.isAir(),
                        state.is(net.minecraft.world.level.block.Blocks.SAND),!state.getFluidState().isEmpty(),
                        c.level.getBlockEntity(p)!=null))
                    throw new IllegalStateException("Quarry changed: non-sand, liquid, container or unloaded buffer at "+p);
                if(inside&&state.is(net.minecraft.world.level.block.Blocks.SAND))available++;
                boolean column=p.getX()>=min.getX()&&p.getX()<=max.getX()
                    &&p.getZ()>=min.getZ()&&p.getZ()<=max.getZ();
                if(column&&p.getY()>max.getY()&&!state.isAir())
                    throw new IllegalStateException("Sand quarry top is not open air");
                if(column&&p.getY()==min.getY()-1&&!state.isCollisionShapeFullBlock(c.level,p))
                    throw new IllegalStateException("Sand quarry lacks a solid bottom");
            }
            int capacity=0;for(int i=0;i<36;i++){var stack=c.player.getInventory().getItem(i);
                if(stack.isEmpty())capacity+=64;else if(stack.is(net.minecraft.world.item.Items.SAND))capacity+=64-stack.getCount();}
            var held=c.player.getMainHandItem();
            if(available<amount||capacity<amount||!held.is(net.minecraft.tags.ItemTags.SHOVELS)
                    ||held.getMaxDamage()-held.getDamageValue()<Math.min(amount,256)+32)
                throw new IllegalStateException("Quarry sand, backpack room or shovel durability is insufficient");
            borer.startMaterialArea(c,min,max);
            if(!borer.isActive())throw new IllegalStateException("Native sand quarry could not start: "+borer.status());
            active=r.deepCopy();active.addProperty("sand_before",count(c,"minecraft:sand"));
            op=command;phase="running";detail="native bounded sand quarry running";
            deadline=ticks+20*Math.max(30,Math.min(600,r.has("seconds")?r.get("seconds").getAsInt():300));
        }else if(command.equals("borer_start")){
            var borer=KitClient.borer();
            boolean materialOwned=supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")
                &&str(supervisionLease,"job_session").equals(str(r,"task_session"));
            boolean gravelOnly=str(r,"mode").equals("ORE")&&str(r,"ore_target").equals("GRAVEL")
                &&KitClient.config().borerLastMode.equals("ORE")&&KitClient.config().borerOreTarget.equals("GRAVEL");
            boolean free=borer!=null&&!borer.isActive()&&!KitClient.controller().isActive()
                &&!KitClient.buildJob().isActive()&&!KitClient.chopper().isActive()
                &&!ProfessionalPrinter.status().get("enabled").getAsBoolean();
            String rejection=BorerControlPolicy.startRejection(materialOwned,gravelOnly,
                c.player.getHealth()>=19&&c.player.getFoodData().getFoodLevel()>=8,
                c.player.onGround(),!guardBusy&&!hostileNearby(c)&&c.screen==null
                    &&!KitKeys.manualMovementDown(c),free,guardArmed()&&pveOnly());
            if(rejection!=null)throw new IllegalStateException(rejection);
            borer.start(c,TunnelBorer.Mode.ORE);
            if(!borer.isActive())throw new IllegalStateException("Gravel-only ore miner did not start");
            supervisionLease=null;cancelWork(c,"自动挖矿接管");
            ownedBorerSession=lastId;op=command;phase="done";detail="gravel-only ore miner started";
        }else if(command.equals("borer_stop")){
            var borer=KitClient.borer();
            if(!str(r,"world_session").equals(session(c))||!r.has("expected_revision")
                ||r.get("expected_revision").getAsLong()!=controlRevision||!r.has("expires_at")
                ||r.get("expires_at").getAsLong()<System.currentTimeMillis())
                throw new IllegalStateException("Ore miner stop belongs to an old controller");
            if(!BorerControlPolicy.ownsStop(ownedBorerSession,str(r,"borer_session"),borer!=null&&borer.isActive()))
                throw new IllegalStateException("Ore miner belongs to another or completed session");
            borer.stop(c,"自动挖矿阶段结束");ownedBorerSession="";armPveGuard(c);
            op=command;phase="done";detail="owned ore miner stopped; PvE guard remains armed";
        }else if(command.equals("runtime_reload")){
            if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")||!str(supervisionLease,"job_session").equals(str(r,"task_session")))throw new IllegalStateException("Material session required for managed hot update");
            if(c.screen!=null||supplyTask!=null&&!supplyTask.done()||KitClient.borer().isActive()||KitClient.chopper().isActive()||KitClient.controller().isActive())throw new IllegalStateException("Wait for the current movement or inventory operation to finish before hot update");
            var result=KitClient.reloadBorerRuntime(c,false);
            if(!result.success())throw new IllegalStateException(result.message());
            active=null;phase="done";op=command;detail=result.message();
        }else if(command.equals("collect_item")){
            if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")||!str(supervisionLease,"job_session").equals(str(r,"task_session")))throw new IllegalStateException("Material session required");
            supplyTask=BuildSupplyTask.pickup(c,r);active=r.deepCopy();op=command;phase="running";detail="collecting observed item drop";deadline=ticks+2400;
        }else if(command.equals("approach_block")){
            if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")||!str(supervisionLease,"job_session").equals(str(r,"task_session")))throw new IllegalStateException("Material session required");
            checkSiteTarget(r,r.getAsJsonArray("pos"));supplyTask=BuildSupplyTask.approach(c,r);active=r.deepCopy();op=command;phase="running";detail="approaching verified work block";deadline=ticks+3600;
        }else if(command.equals("collect_supply")){
            if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")||!str(supervisionLease,"job_session").equals(str(r,"task_session")))throw new IllegalStateException("Material session required");
            supplyTask=BuildSupplyTask.collect(c,r);active=r.deepCopy();op=command;phase="running";detail="collecting approved material stock";deadline=ticks+3600;
        }else if(command.equals("concrete_batch")){
            if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")||!str(supervisionLease,"job_session").equals(str(r,"task_session")))throw new IllegalStateException("Material session required for concrete");
            JsonArray p=r.getAsJsonArray("support");checkSiteTarget(r,p);
            BlockPos support=new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt());
            if(!c.level.hasChunkAt(support)||!state(c,support).equals(str(r,"expected_state")))throw new IllegalStateException("Concrete support changed");
            int target=r.get("target_count").getAsInt();if(target<1||target>4096)throw new IllegalArgumentException("Concrete batch must be 1..4096");
            String powder=str(r,"powder"),solid=dev.twob2tkit.concrete.ConcretePolicy.solidId(powder);
            if(solid==null||!itemId(c.player.getMainHandItem()).equals(powder))throw new IllegalStateException("Hold the expected concrete powder before starting");
            if(!KitClient.concrete().startAt(c,support,target))throw new IllegalStateException(KitClient.concrete().status());
            active=r.deepCopy();active.addProperty("solid_item",solid);active.addProperty("solid_before",count(c,solid));op=command;phase="running";detail="concrete batch under material lease";
            concretePreexistingDrops.clear();for(var entity:c.level.entitiesForRendering())if(entity instanceof net.minecraft.world.entity.item.ItemEntity drop && itemId(drop.getItem()).equals(solid)&&drop.position().distanceToSqr(Vec3.atCenterOf(support.above()))<100)concretePreexistingDrops.add(drop.getUUID());
            supplyTask=null;concretePickupDeadline=0;concreteRetryUuid=null;concreteRetryPos=null;concreteRetryTick=0;deadline=ticks+20*Math.max(20,Math.min(600,r.has("seconds")?r.get("seconds").getAsInt():180));
        }else if(command.equals("supervision_attach")){
            long expiry=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            if(expiry<0 || expiry>15000 || str(r,"job_session").isEmpty())throw new IllegalStateException("Supervisor attachment expired or has no job");
            if(!r.has("expected_revision") || r.get("expected_revision").getAsLong()!=controlRevision || !str(r,"world_session").equals(session(c)))throw new IllegalStateException("Supervisor attachment scope changed");
            attachSupervision(c,r);phase="done";detail="native safety watchdog attached";
        }else if(command.equals("projection_load")||command.equals("projection_load_rollback")){
            projectionLoadScope(c,r);
            JsonObject loaded=command.equals("projection_load")?ProjectionLoader.load(c,r,()->projectionLoadScope(c,r))
                :ProjectionLoader.rollback(c,r,()->projectionLoadScope(c,r));
            if(loaded.get("success").getAsBoolean()){
                projectionBatch.reset();controlRevision++;
                if(supervisionLease!=null&&str(supervisionLease,"kind").equals("parking"))supervisionLease.addProperty("revision",controlRevision);
            }
            op=command;phase=loaded.get("success").getAsBoolean()?"done":"error";
            detail=phase.equals("done")?"Projection configuration updated; real blocks were not changed; verify projection_model after chunk loading":str(loaded,"error");
            var reply=snapshot(c);reply.addProperty("id",lastId);reply.addProperty("phase",phase);reply.addProperty("detail",detail);reply.add("projection_load",loaded);
            save(root(c).resolve("reply-"+safeId(lastId)+".json"),reply);
        }else if(command.equals("projection_batch_set")||command.equals("projection_batch_clear")){
            changeProjectionBatch(c,r,command.equals("projection_batch_clear"));
            op=command;phase="done";detail=projectionBatch.active()?"projection batch installed; full-model completion unchanged":"projection batch cleared; unrestricted selected projection restored";
            var reply=snapshot(c);reply.addProperty("id",lastId);reply.addProperty("phase",phase);reply.addProperty("detail",detail);
            save(root(c).resolve("reply-"+safeId(lastId)+".json"),reply);
        }else if(command.equals("projection_start")){
            long requestedExpiry=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            if(requestedExpiry<0 || requestedExpiry>15000 || c.screen!=null || c.player.getHealth()<14 || KitKeys.manualMovementDown(c))throw new IllegalStateException("Projection start expired or player input/state changed");
            if(!r.has("manual_start") || !r.get("manual_start").getAsBoolean() || KitClient.buildJob().isActive())throw new IllegalStateException("Explicit idle projection start required");
            if(!r.has("expected_revision") || r.get("expected_revision").getAsLong()!=controlRevision || !str(r,"world_session").equals(session(c)))throw new IllegalStateException("Projection start scope changed");
            if(!dev.twob2tkit.builder.LitematicaAccess.buildSelection().key().equals(str(r,"placement_key")))throw new IllegalStateException("Selected projection changed");
            if(r.has("task_session")){if(!KitClient.startProjectionForMaterialGoal(c))throw new IllegalStateException(KitClient.buildJob().status());}else KitClient.toggleProjectionBuild(c);if(!KitClient.buildJob().isActive())throw new IllegalStateException(KitClient.buildJob().status());
            if(r.has("supervision_lease"))attachSupervision(c,r);
            statusId=lastId;phase="done";detail="projection job started by explicit request";
        }else if(command.equals("build_supply")){
            if(supervisionLease==null || !str(supervisionLease,"job_session").equals(str(r,"job_session")))throw new IllegalStateException("Supply requires an attached native safety watchdog");
            long expiry=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            if(expiry<0 || expiry>15000 || !r.has("expected_revision") || r.get("expected_revision").getAsLong()!=controlRevision || !str(r,"world_session").equals(session(c)))throw new IllegalStateException("Supply request expired or control changed");
            supplyTask=new BuildSupplyTask(c,str(r,"job_session"),str(r,"source_key"));
            active=r.deepCopy();op=command;phase="running";detail="native depot supply";deadline=ticks+3600;
        }else if(command.equals("build_craft")){
            if(!r.has("expected_revision") || r.get("expected_revision").getAsLong()!=controlRevision || !str(r,"world_session").equals(session(c)))throw new IllegalStateException("Build craft belongs to an old controller");
            long expiry=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            if(expiry<0 || expiry>15000)throw new IllegalStateException("Build recipe request expired");
            craftSpec=KitClient.buildJob().plankRecipe(c,str(r,"job_session"),str(r,"output"));craftRemaining=craftSpec.get("repetitions").getAsInt()-1;
            craftTask=new SurvivalCraftTask(c,craftSpec);active=r.deepCopy();op="craft_recipe";phase="running";detail="native supply crafting";deadline=ticks+1200;
        }else if(command.equals("build_control")){
            if(!r.has("expected_revision") || r.get("expected_revision").getAsLong()!=controlRevision || !str(r,"world_session").equals(session(c)))throw new IllegalStateException("Build control belongs to an old controller");
            long expiry=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            if(expiry<0 || expiry>15000)throw new IllegalStateException("Build decision expired");
            KitClient.buildJob().supervise(c,str(r,"action"),str(r,"job_session"));phase="done";detail="build supervision applied; verify subsequent progress";
        }else if(command.equals("professional_print")){
            var completionTargets=currentMaterialRequest(c,r)&&projectionBatch.active()&&projectionBatchCurrent(c)
                ?projectionBatch.positions():Set.<BlockPos>of();
            KitClient.stopWork("使用投影打印机");
            if(c.player.getHealth()<14 || !MeteorModules.isActive(MeteorModules.KILL_AURA) || !MeteorModules.isActive(MeteorModules.AUTO_LOG))throw new IllegalStateException("Health or defense requires attention");
            ProfessionalPrinter.start(!r.has("conservative") || !r.get("conservative").getAsBoolean(),completionTargets);active=r.deepCopy();op=command;phase="running";detail="Litematica Printer owns placement";
            active.add("printer_completion_targets",JSON.toJsonTree(completionTargets.stream().map(pos->new int[]{pos.getX(),pos.getY(),pos.getZ()}).toList()));
            active.addProperty("printer_completion_world",session(c));
            active.addProperty("printer_completion_key",completionTargets.isEmpty()?"":projectionBatch.owner().projection());
            deadline=ticks+20*Math.max(1,Math.min(30,r.has("seconds")?r.get("seconds").getAsInt():10));
        }else if(command.equals("craft_recipe")){
            if(!survival(r))throw new IllegalArgumentException("Recipe macros currently require the local survival scope");
            craftSpec=r.deepCopy();craftRemaining=0;craftTask=new SurvivalCraftTask(c,r);active=r.deepCopy();op=command;phase="running";detail="native recipe workflow";deadline=ticks+1200;
        }else if(command.equals("navigate") || command.equals("walk") || command.equals("walk_path") || command.equals("chop") || command.equals("print")){
            // stopWork advances the owned revision; remember the verified scope
            // before that transition so an external material job keeps precision.
            boolean materialHandoff=Set.of("navigate","walk","walk_path","chop","print").contains(command)
				&&currentMaterialRequest(c,r);
			boolean materialNavigation=command.equals("navigate")&&materialHandoff;
            if(command.equals("navigate")&&r.has("air_only")){
                if(!r.get("air_only").isJsonPrimitive()||!r.getAsJsonPrimitive("air_only").isBoolean())
                    throw new IllegalArgumentException("air_only must be boolean");
                if(r.get("air_only").getAsBoolean()&&(!materialNavigation||!airNavigationClear(c,r.getAsJsonArray("target"))))
                    throw new IllegalStateException("Air-only navigation requires the current material lease and a loaded clear dry path");
            }
            boolean snowCruise=command.equals("navigate")&&r.has("snow_expedition_token");
			ProfessionalPrinter.stop(c,true);stopWorkForScript(r,materialHandoff);
			active=snowCruise?null:r.deepCopy();op=command;phase="running";detail="";
            int maximumSeconds=snowCruise?5400:600;
            deadline=ticks+20*Math.max(5,Math.min(maximumSeconds,r.has("seconds")?r.get("seconds").getAsInt():120));
            if(command.equals("walk_path")){
                if(!survival(r))throw new IllegalArgumentException("Path batches require the local survival scope");
                JsonArray path=r.getAsJsonArray("path");
                if(path==null || path.isEmpty() || path.size()>32)throw new IllegalArgumentException("Path must contain 1..32 observed waypoints");
                Vec3 previous=c.player.position();
                for(var value:path){JsonArray point=value.getAsJsonArray();checkSiteTarget(r,point);Vec3 next=new Vec3(point.get(0).getAsDouble(),point.get(1).getAsDouble(),point.get(2).getAsDouble());if(previous.distanceTo(next)>2 || Math.abs(previous.y-next.y)>1.1)throw new IllegalArgumentException("Path has an unsafe gap");previous=next;}
                pathIndex=0;active.add("target",path.get(0).deepCopy());restoreFlight=false;MeteorModules.disable(MeteorModules.FLIGHT);
            }else if(command.equals("walk")){
                JsonArray p=r.getAsJsonArray("target");checkSiteTarget(r,p);
                double d=Math.hypot(p.get(0).getAsDouble()-c.player.getX(),p.get(2).getAsDouble()-c.player.getZ());if(d>32)throw new IllegalArgumentException("Walking waypoint must be within 32 blocks");
                if(r.has("water_descend")&&r.get("water_descend").getAsBoolean()&&
                    !WaterDescentPolicy.allowed(r.has("task_session"),guardScope!=null,
                     c.player.isUnderWater(),c.player.getHealth(),c.player.getAirSupply(),
                     d,c.player.getY()-p.get(1).getAsDouble(),airEstimate(c).pickupFloor()))
                    throw new IllegalStateException("Guarded water descent needs clear vertical pickup and full reserve");
                if(r.has("freefall_brake_y")){
                    double brakeY=r.get("freefall_brake_y").getAsDouble();
                    if(!r.has("task_session")||d>.5||!FreefallPolicy.eligible(c.player.getY(),brakeY,c.player.getHealth(),guardScope!=null,MeteorModules.isActive(MeteorModules.FLIGHT))
                        ||!freefallColumnClear(c,c.player.blockPosition(),(int)Math.floor(brakeY)-2,(int)Math.ceil(c.player.getY())+2))
                        throw new IllegalStateException("Guarded freefall requires a clear loaded column and active Flight");
                }
                restoreFlight=MeteorModules.isActive(MeteorModules.FLIGHT) && (!r.has("restore_flight") || r.get("restore_flight").getAsBoolean());MeteorModules.disable(MeteorModules.FLIGHT);
            }else if(command.equals("navigate")){
                boolean snowExpedition=r.has("snow_expedition_token");
                if(snowExpedition){
                    if(r.has("air_only")&&r.get("air_only").getAsBoolean())
                        throw new IllegalArgumentException("Snow expedition cruise cannot claim an unloaded air-only corridor");
                    SnowSeedExpedition.authorizeNavigate(c,r,session(c));
					active=r.deepCopy();
                }
                JsonArray p=r.getAsJsonArray("target");if(!snowExpedition)checkSiteTarget(r,p);
                if(r.has("arrival")){savedArrival=KitClient.config().arrivalRadius;
                    temporaryArrival=MaterialJobControlPolicy.arrival(r.get("arrival").getAsDouble(),materialNavigation);
                    KitClient.config().arrivalRadius=temporaryArrival;}
                MeteorModules.enable(MeteorModules.FLIGHT);
                KitClient.controller().startExact(c,p.get(0).getAsDouble(),p.get(2).getAsDouble(),p.get(1).getAsDouble());
                if(r.has("air_only")&&r.get("air_only").getAsBoolean()){
                    // startExact persists the user's original preference first.
                    // Borrow the in-memory setting only for this bounded command.
                    savedClearCeiling=KitClient.config().clearCeiling;KitClient.config().clearCeiling=false;
                    KitClient.controller().keepConnectedOnArrival();
                    materialAirNavigation=new MaterialAirNavigation(new Vec3(p.get(0).getAsDouble(),p.get(1).getAsDouble(),p.get(2).getAsDouble()),
                        r.has("arrival")?temporaryArrival:.25);
                }
                if(supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")
                        &&str(supervisionLease,"job_session").equals(str(r,"task_session"))
                        &&materialAirRoute.owned(session(c),str(supervisionLease,"job_session"),airGear(c),c))
                    materialAirRoute.beginAscent(c,str(r,"id"),p.get(1).getAsDouble());
            }else if(command.equals("chop")){
                if(!r.has("item"))active.addProperty("item","minecraft:oak_log");
                desiredCount=Math.max(1,Math.min(512,r.get("target_count").getAsInt()));
                String logId=str(active,"item");if(!Set.of("minecraft:oak_log","minecraft:spruce_log","minecraft:birch_log","minecraft:jungle_log","minecraft:acacia_log","minecraft:dark_oak_log","minecraft:mangrove_log","minecraft:cherry_log","minecraft:pale_oak_log").contains(logId))throw new IllegalArgumentException("A natural log target is required");
                KitClient.chopper().startMaterial(c,logId);
                if(r.has("tree_limit"))KitClient.chopper().limitTrees(Math.max(1,Math.min(16,r.get("tree_limit").getAsInt())));
            }else if(!KitClient.machines().start(c))throw new IllegalStateException("Could not start printer");
        }else if(command.equals("guard")){
            if(r.has("expected_revision") && (r.get("expected_revision").getAsLong()!=controlRevision || !str(r,"world_session").equals(session(c)) || !r.has("expires_at") || r.get("expires_at").getAsLong()<System.currentTimeMillis()))throw new IllegalStateException("Guard request belongs to an old controller");
            dev.twob2tkit.combat.GuardFoodLease.acquire(c);guardScope=r.deepCopy();
            if(r.has("pve_only") && r.get("pve_only").getAsBoolean())MeteorModules.enablePveAura();else MeteorModules.enable(MeteorModules.KILL_AURA);MeteorModules.enable(MeteorModules.AUTO_LOG);
            MeteorModules.enable("meteordevelopment.meteorclient.systems.modules.player.AutoEat");
            phase="done";detail="guard modules enabled";
        }else if(command.equals("fisher_start")){
            if(c.screen!=null||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<18
                ||!guardArmed()||!MeteorModules.isActive(MeteorModules.FLIGHT)
                ||!c.player.getMainHandItem().is(net.minecraft.world.item.Items.FISHING_ROD)
                ||KitClient.anyAfkAuto())throw new IllegalStateException("Safe guarded fishing start requires a held rod and no other task");
            KitClient.startFisher(c);
            if(KitClient.fisher()==null||!KitClient.fisher().isActive())throw new IllegalStateException("Auto fisher did not start");
            phase="done";detail="auto fisher started; PvE guard remains armed";
        }else if(command.equals("fisher_stop")){
            if(KitClient.fisher()!=null&&KitClient.fisher().isActive())KitClient.fisher().stop(c,"脚本停止钓鱼");
            phase="done";detail="auto fisher stopped; PvE guard remains armed";
        }else if(command.equals("guide")){
            if(r.has("stop") && r.get("stop").getAsBoolean())KitClient.structureGuide().stop();
            else{JsonArray pos=r.getAsJsonArray("pos");checkSiteTarget(r,pos);String name=str(r,"name");
                if(name.isBlank() || name.length()>48)throw new IllegalArgumentException("Guide name required (max 48 characters)");
                KitClient.structureGuide().start(name,pos.get(0).getAsInt(),pos.get(1).getAsInt(),pos.get(2).getAsInt());}
            phase="done";detail="guide updated; no movement";
        }else if(command.equals("look")){
            PlacementRotation.after(c,r.get("yaw").getAsFloat(),Math.max(-90,Math.min(90,r.get("pitch").getAsFloat())),null);phase="done";detail="rotation queued";
        }else if(command.equals("select_item")){
            if(c.player.containerMenu.containerId!=0)throw new IllegalStateException("Close the container before selecting a held item");
            String item=str(r,"item");var inventoryIds=new ArrayList<String>();
            for(int i=0;i<36;i++)inventoryIds.add(itemId(c.player.getInventory().getItem(i)));
            int found=matchingInventorySlot(inventoryIds,item,r.has("slot")?r.get("slot").getAsInt():null);
            if(found<9)c.player.getInventory().setSelectedSlot(found);
            else{int hotbar=5;c.gameMode.handleContainerInput(0,found,hotbar,ContainerInput.SWAP,c.player);c.player.getInventory().setSelectedSlot(hotbar);}
            settle(r,8);
        }else if(command.equals("distribute")){
            var menu=c.player.containerMenu;String type=menu.getClass().getSimpleName();int limit=type.equals("InventoryMenu")?4:type.equals("CraftingMenu")?9:0;
            if(limit==0 || menu.containerId!=r.get("menu_id").getAsInt())throw new IllegalStateException("Expected crafting menu changed");
            if(!itemId(menu.getCarried()).equals(str(r,"expected_cursor")) || menu.getCarried().getCount()!=r.get("expected_cursor_count").getAsInt())throw new IllegalStateException("Cursor stack changed");
            Set<Integer> slots=new LinkedHashSet<>();for(var v:r.getAsJsonArray("slots")){int i=v.getAsInt();if(i<1 || i>limit || !menu.getSlot(i).getItem().isEmpty())throw new IllegalArgumentException("Crafting grid target is occupied or invalid");slots.add(i);}
            if(slots.isEmpty() || menu.getCarried().getCount()<slots.size())throw new IllegalArgumentException("Insufficient ingredients for distribution");
            c.gameMode.handleContainerInput(menu.containerId,-999,0,ContainerInput.QUICK_CRAFT,c.player);
            for(int i:slots)c.gameMode.handleContainerInput(menu.containerId,i,1,ContainerInput.QUICK_CRAFT,c.player);
            c.gameMode.handleContainerInput(menu.containerId,-999,2,ContainerInput.QUICK_CRAFT,c.player);settle(r,8);
        }else if(command.equals("slot_click")){
            var menu=c.player.containerMenu;int slot=r.get("slot").getAsInt();
            if(menu.containerId!=r.get("menu_id").getAsInt() || slot<0 || slot>=menu.slots.size())throw new IllegalStateException("Container changed");
            if(r.has("expected_cursor")!=r.has("expected_cursor_count"))throw new IllegalArgumentException("Expected cursor item and count must be supplied together");
            if(r.has("expected_cursor")&&(!itemId(menu.getCarried()).equals(str(r,"expected_cursor"))
                    ||menu.getCarried().getCount()!=r.get("expected_cursor_count").getAsInt()))
                throw new IllegalStateException("Cursor stack changed");
            if(!itemId(menu.getSlot(slot).getItem()).equals(str(r,"expected_item")))throw new IllegalStateException("Slot item changed");
            if(r.has("expected_count") && menu.getSlot(slot).getItem().getCount()!=r.get("expected_count").getAsInt())throw new IllegalStateException("Slot count changed");
            String kind=str(r,"kind");ContainerInput input=switch(kind){case "pickup"->ContainerInput.PICKUP;case "quick_move"->ContainerInput.QUICK_MOVE;case "swap"->ContainerInput.SWAP;default->throw new IllegalArgumentException("Unsupported slot action");};
            int button=r.has("button")?r.get("button").getAsInt():0;
            if(button<0 || button>(kind.equals("swap")?8:1))throw new IllegalArgumentException("Bad slot button");
            c.gameMode.handleContainerInput(menu.containerId,slot,button,input,c.player);settle(r,8);
        }else if(command.equals("interact")){
            JsonArray p=r.getAsJsonArray("pos");checkSiteTarget(r,p);BlockPos pos=new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt());
            if(!state(c,pos).equals(str(r,"expected_state")))throw new IllegalStateException("Target block changed");
            if(!itemId(c.player.getMainHandItem()).equals(str(r,"expected_hand")))throw new IllegalStateException("Held item changed");
            Direction face=Direction.valueOf(str(r,"face").toUpperCase(Locale.ROOT));
            if(r.has("dry_paving_guard")&&(!r.get("dry_paving_guard").isJsonPrimitive()||!r.getAsJsonPrimitive("dry_paving_guard").isBoolean()))
                throw new IllegalArgumentException("Dry paving guard must be boolean");
            boolean dryPaving=r.has("dry_paving_guard")&&r.get("dry_paving_guard").getAsBoolean();
            boolean terrainReplace=terrainReplaceRequested(r);
            if(dryPaving&&terrainReplace)throw new IllegalArgumentException("Only one terrain guard may own an interaction");
            if(dryPaving){dryPavingRequestGuard(c,r);dryPavingPlacementGuard(c,pos,face);dryPavingAckExpected(r);}
            if(terrainReplace)terrainReplacementGuard(c,r);
            var visible=BlockFaceTarget.visible(c,c.player.getEyePosition(),pos,face,c.player.blockInteractionRange());
            // The material client opens containers with a sword. That empty-hand-like
            // block use can target any visible face; placements still require the requested face.
            if(visible==null&&c.player.getMainHandItem().is(net.minecraft.world.item.Items.DIAMOND_SWORD))visible=BlockFaceTarget.visible(c,c.player.getEyePosition(),pos,null,c.player.blockInteractionRange());
            if(visible==null)throw new IllegalStateException("Target interaction face is occluded or out of reach");
            Vec3 aim=BlockFaceTarget.inside(visible);Direction usedFace=visible.getDirection();
            var level=c.level;RotationAim.Look look=RotationAim.lookAt(c.player,aim);active=r.deepCopy();op="rotation";phase="running";deadline=ticks+40;
            PlacementRotation.after(c,look.yaw(),look.pitch(),()->{
                try{
                    if(active==null || !str(active,"id").equals(str(r,"id")))return;guard(c,r);if(c.level!=level || !state(c,pos).equals(str(r,"expected_state")) || !itemId(c.player.getMainHandItem()).equals(str(r,"expected_hand")))throw new IllegalStateException("Placement context changed while rotating");
                    if(c.player.getEyePosition().distanceTo(aim)>c.player.blockInteractionRange())throw new IllegalStateException("Target moved out of reach");
                    var checkedHit=c.level.clip(new ClipContext(c.player.getEyePosition(),aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
                    if(!BlockFaceTarget.matches(checkedHit,pos,usedFace))throw new IllegalStateException("Interaction became occluded while rotating");
                    if(dryPaving){dryPavingRequestGuard(c,r);dryPavingPlacementGuard(c,pos,usedFace);}
                    if(terrainReplace)terrainReplacementGuard(c,r);
                    if(terrainReplace){
                        terrainServerConfirmation.begin(session(c),str(r,"id"),str(r,"terrain_replace_stage"),
                            terrainAckTarget(r),terrainAckExpected(r));
                        terrainServerConfirmation.sent(session(c),str(r,"id"),str(r,"terrain_replace_stage"),
                            terrainAckTarget(r));
                    }
                    if(dryPaving){
                        dryPavingServerConfirmation.begin(session(c),str(r,"id"),dryPavingAckStage(r),
                            dryPavingAckTarget(r),dryPavingAckExpected(r));
                        dryPavingServerConfirmation.sent(session(c),str(r,"id"),dryPavingAckStage(r),
                            dryPavingAckTarget(r));
                        dryPavingConfirmedTick=-1;
                    }
                    c.gameMode.useItemOn(c.player,InteractionHand.MAIN_HAND,checkedHit);settle(r,terrainReplace||dryPaving?80:8);
                }catch(Exception e){finish(c,"error",e.getMessage());}
            });
        }else if(command.equals("mine_block") || command.equals("recover_shulker")){
            JsonArray p=r.getAsJsonArray("pos");checkSiteTarget(r,p);BlockPos pos=new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt());
            if(!state(c,pos).equals(str(r,"expected_state")))throw new IllegalStateException("Mining target changed");
            if(r.has("dry_paving_guard")&&(!r.get("dry_paving_guard").isJsonPrimitive()||!r.getAsJsonPrimitive("dry_paving_guard").isBoolean()))
                throw new IllegalArgumentException("Dry paving guard must be boolean");
            boolean dryPaving=r.has("dry_paving_guard")&&r.get("dry_paving_guard").getAsBoolean();
            boolean terrainReplace=terrainReplaceRequested(r);
            if(dryPaving&&terrainReplace)throw new IllegalArgumentException("Only one terrain guard may own an excavation");
            if(dryPaving){
                if(!command.equals("mine_block"))throw new IllegalArgumentException("Dry paving guard requires mine_block");
                dryPavingRequestGuard(c,r);
                dryPavingMiningGuard(c,pos,str(r,"expected_state"));
            }
            if(terrainReplace){
                if(!command.equals("mine_block"))throw new IllegalArgumentException("Terrain replacement requires mine_block");
                terrainReplacementGuard(c,r);
            }
            String guardedBlock=BuiltInRegistries.BLOCK.getKey(c.level.getBlockState(pos).getBlock()).toString();
            if(r.has("required_silk_shovel")&&r.get("required_silk_shovel").getAsBoolean()
                    &&r.has("required_plain_shovel")&&r.get("required_plain_shovel").getAsBoolean())
                throw new IllegalArgumentException("One mining request cannot require both Silk Touch and plain shovel modes");
            if(r.has("required_silk_shovel")&&r.get("required_silk_shovel").getAsBoolean()){
                if(!command.equals("mine_block") || !Set.of("minecraft:grass_block","minecraft:snow","minecraft:snow_block").contains(guardedBlock)
                        || !silkShovelReady(c,r))
                    throw new IllegalStateException("Grass or snow harvesting requires the selected Silk Touch diamond or netherite shovel with 33 durability");
            }
            if(r.has("required_plain_shovel")&&r.get("required_plain_shovel").getAsBoolean()){
                if(!command.equals("mine_block") || !Set.of("minecraft:snow","minecraft:snow_block").contains(guardedBlock)
                        || !snowShovelReady(c,r,false))
                    throw new IllegalStateException("Snowball harvesting requires the selected non-Silk-Touch diamond or netherite shovel with 33 durability");
            }
            boolean recovery=command.equals("recover_shulker");
            boolean underwater=r.has("underwater_gravel")&&r.get("underwater_gravel").getAsBoolean();
            if(underwater){
                if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")
                    ||!str(supervisionLease,"job_session").equals(str(r,"task_session")))
                    throw new IllegalStateException("Guarded material session required for underwater gravel");
                boolean lavaNear=false;
                for(Direction direction:Direction.values())if(c.level.getFluidState(pos.relative(direction)).is(net.minecraft.tags.FluidTags.LAVA))lavaNear=true;
                ItemStack held=c.player.getMainHandItem();
                boolean breathing=c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING)
                    ||c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER);
                String rejection=UnderwaterGravelPolicy.startRejection(
                    c.level.getBlockState(pos).is(net.minecraft.world.level.block.Blocks.GRAVEL),
                    c.level.getFluidState(pos.above()).is(net.minecraft.tags.FluidTags.WATER),
                    lavaNear,c.player.isUnderWater(),c.player.getHealth(),c.player.getAirSupply(),breathing,
                    held.is(net.minecraft.tags.ItemTags.SHOVELS),held.isDamageableItem()?held.getMaxDamage()-held.getDamageValue():0,
                    airEstimate(c).workFloor());
                if(rejection!=null){
                    KitClient.LOGGER.warn("[Gravel] mine preflight rejected pos={} block={} aboveFluid={} air={} health={} reason={}",
                        pos,c.level.getBlockState(pos),c.level.getFluidState(pos.above()),c.player.getAirSupply(),c.player.getHealth(),rejection);
                    throw new IllegalStateException(rejection);
                }
            }
            boolean allowed=ContainerRecoveryPolicy.allowed(BuiltInRegistries.BLOCK.getKey(c.level.getBlockState(pos).getBlock()).toString(),recovery,c.player.getInventory().getFreeSlot()>=0?1:0);
            if(recovery && !allowed)throw new IllegalStateException("Shulker retrieval requires an actual shulker box and a free inventory slot");
            if(c.level.getBlockEntity(pos)!=null && !allowed)throw new IllegalStateException("Block entities and containers are protected");
            if(c.level.getBlockState(pos).getDestroySpeed(c.level,pos)<0 || c.level.isEmptyBlock(pos))throw new IllegalStateException("Target is not mineable");
            if(c.player.onGround() && c.player.blockPosition().below().equals(pos)){
                boolean ownedMaterial=supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")
                    &&str(supervisionLease,"job_session").equals(str(r,"task_session"));
                boolean footing=r.has("footing_gravel")&&r.get("footing_gravel").getAsBoolean();
                if(!footing||!GravelFootingPolicy.mayMineUnderfoot(ownedMaterial,underwater,
                        GravelFootingPolicy.stableFloor(c.level,pos),true,c.player.isUnderWater(),
                        c.player.getHealth(),c.player.getAirSupply(),airEstimate(c).workFloor()))
                    throw new IllegalStateException("Current footing is protected");
            }
            if(!underwater)for(Direction d:Direction.values())if(!c.level.getFluidState(pos.relative(d)).isEmpty())throw new IllegalStateException("Fluid next to target is protected");
            if(c.player.getEyePosition().distanceTo(blockAim(pos,r))>c.player.blockInteractionRange()-.2)throw new IllegalStateException("Mining target out of reach");
            KitClient.stopWork("切换到指定方块修正");
            if(terrainReplace)terrainServerConfirmation.begin(session(c),str(r,"id"),
                str(r,"terrain_replace_stage"),terrainAckTarget(r),terrainAckExpected(r));
            if(dryPaving){
                dryPavingServerConfirmation.begin(session(c),str(r,"id"),dryPavingAckStage(r),
                    dryPavingAckTarget(r),dryPavingAckExpected(r));
                dryPavingConfirmedTick=-1;dryPavingClientAirTick=-1;
            }
            if(!terrainReplace&&!dryPaving)ordinaryMiningConfirmation.begin(c,session(c),str(r,"id"),pos,underwater);
            active=r.deepCopy();active.addProperty("single_block_world",session(c));op="mine_block";phase="running";detail="mining the verified target";mineStarted=false;deadline=ticks+20*Math.min(20,r.has("seconds")?r.get("seconds").getAsInt():10);
        }else if(command.equals("projection_scaffold_fill")){
            if(!r.has("task_session")||!currentMaterialRequest(c,r)||!guardArmed()||!pveOnly()||guardBusy
                ||KitKeys.manualMovementDown(c)||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<8
                ||active!=null||scaffoldFillTask!=null||KitClient.buildJob().isActive()||KitClient.borer().isActive()
                ||KitClient.machines().isPlacing()||ProfessionalPrinter.owned()||KitClient.controller().isActive()
                ||KitClient.chopper().isActive())throw new IllegalStateException("Scaffold row requires the current healthy idle guarded material lease");
            scaffoldFillTask=new ProjectionScaffoldFill(c,r,session(c),controlRevision,
                KitClient.config().lastAttackTimeEpochMillis,()->projectionScaffoldOwnerCurrent(c));lastScaffoldFill=null;
            active=r.deepCopy();op="projection_scaffold_fill";phase="running";
            deadline=ticks+20*Math.max(10,Math.min(600,r.has("seconds")?r.get("seconds").getAsInt():300));
            detail="controlled Meteor Scaffold row admitted; scope gate installed before enabling module";
        }else if(command.equals("projection_air_seed")){
            if(!r.has("task_session")||!currentMaterialRequest(c,r)||!guardArmed()||!pveOnly()
                ||guardBusy||KitKeys.manualMovementDown(c)||c.player.getHealth()<19||loadedHostileNearby(c)
                ||c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL
                ||active!=null||KitClient.buildJob().isActive()||KitClient.borer().isActive()||ProfessionalPrinter.owned()
                ||KitClient.controller().isActive()||KitClient.chopper().isActive())
                throw new IllegalStateException("Air seed requires the current healthy idle guarded material lease");
            airSeedTask=new ProjectionAirSeed(c,r,session(c),lastId,airSeedConfirmation);lastAirSeed=null;
            active=r.deepCopy();op="projection_air_seed";phase="running";deadline=ticks+100;
            detail="sending one verified Meteor air-seed interaction";airSeedTask.sendOnce(c);
        }else if(Set.of("bucket_fill","bucket_place").contains(command)){
            if(!bucketOwnerCurrent(c,r)||active!=null||bucketWaterTask!=null||KitClient.buildJob().isActive()
                ||KitClient.borer().isActive()||KitClient.machines().isPlacing()||ProfessionalPrinter.owned()
                ||KitClient.controller().isActive()||KitClient.chopper().isActive())
                throw new IllegalStateException("Water bucket action requires the current healthy idle guarded material lease");
            checkSiteTarget(r,r.getAsJsonArray("pos"));
            if(command.equals("bucket_place"))checkSiteTarget(r,r.getAsJsonArray("support"));
            var plannedBucket=new BucketWaterAction(c,r,session(c),lastId,root(c),()->bucketOwnerCurrent(c,r));
            Vec3 aim=plannedBucket.aim(c);RotationAim.Look look=RotationAim.lookAt(c.player,aim);
            bucketWaterTask=plannedBucket;lastBucketWater=null;
            active=r.deepCopy();op=command;phase="running";deadline=ticks+100;
            detail="rotating for exactly one bounded normal water bucket use";
            PlacementRotation.after(c,look.yaw(),look.pitch(),()->{
                try{
                    if(active==null||!str(active,"id").equals(str(r,"id"))||bucketWaterTask==null)return;
                    guard(c,r);bucketWaterTask.useOnce(c);
                }catch(Exception failure){finish(c,"waiting","bucket use stopped or unconfirmed; no second use sent: "+failure.getMessage());}
            });
        }else if(command.equals("map_create")){
            if(!r.has("task_session")||!currentMaterialRequest(c,r)||!guardArmed()||!pveOnly()
                ||guardBusy||KitKeys.manualMovementDown(c)||c.player.getHealth()<19||loadedHostileNearby(c)
                ||c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL
                ||active!=null||KitClient.buildJob().isActive()||KitClient.borer().isActive()||ProfessionalPrinter.owned()
                ||KitClient.controller().isActive()||KitClient.chopper().isActive())
                throw new IllegalStateException("Map creation requires the current healthy idle guarded material lease");
            mapCreationTask=new MapAutomation.Creation(c,session(c),lastId,r);lastMapCreation=null;
            active=r.deepCopy();op="map_create";phase="running";deadline=ticks+100;
            detail="sending exactly one normal empty-map use";mapCreationTask.useOnce(c);
        }else if(command.equals("use_item")){
            String item=str(r,"item");
            boolean ownedMaterials=supervisionLease!=null && str(supervisionLease,"kind").equals("materials") && r.has("task_session");
            if(!AutomationFoodPolicy.allow(survival(r),ownedMaterials,hostileNearby(c),c.screen!=null,KitKeys.manualMovementDown(c),c.player.getHealth(),c.player.getFoodData().getFoodLevel()))
                throw new IllegalStateException("Food use requires a safe local world or owned material session");
            int found=-1;for(int i=0;i<9;i++)if(itemId(c.player.getInventory().getItem(i)).equals(item) && c.player.getInventory().getItem(i).get(net.minecraft.core.component.DataComponents.FOOD)!=null){found=i;break;}
            if(found<0)throw new IllegalStateException("Expected edible item in hotbar");
            foodOriginalSlot=c.player.getInventory().getSelectedSlot();foodUseSlot=found;c.player.getInventory().setSelectedSlot(found);
            useCount=count(c,item);active=r.deepCopy();op="use_item";phase="running";deadline=ticks+80;
            c.options.keyUse.setDown(true);c.gameMode.useItem(c.player,InteractionHand.MAIN_HAND);
        }else if(command.equals("nudge_horse")){
            startHorseNudge(c,r);
        }else if(command.equals("material_slaughter_attack")){
            slaughterAttack(c,r);
        }else if(command.equals("attack_passive")){
            var entity=c.level.getEntity(r.get("entity_id").getAsInt());
            if(!survival(r) || entity==null || !entity.getUUID().toString().equals(str(r,"expected_uuid"))
                || !Set.of("minecraft:cow","minecraft:pig","minecraft:chicken","minecraft:sheep").contains(BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString()))throw new IllegalStateException("Expected survival food animal required");
            if(c.player.getEyePosition().distanceTo(entity.position().add(0,entity.getBbHeight()*.5,0))>c.player.entityInteractionRange()-.2
                || !c.player.hasLineOfSight(entity) || c.player.getAttackStrengthScale(0)<.95)throw new IllegalStateException("Animal out of reach, occluded or attack cooling down");
            RotationAim.apply(c.player,RotationAim.lookAt(c.player,entity.position().add(0,entity.getBbHeight()*.5,0)));
            c.gameMode.attack(c.player,entity);c.player.swing(InteractionHand.MAIN_HAND);settle(r,22);
        }else if(command.equals("interact_entity")){
            var entity=c.level.getEntity(r.get("entity_id").getAsInt());
            if(entity==null || !entity.getUUID().toString().equals(str(r,"expected_uuid")))throw new IllegalStateException("Entity changed");
            Vec3 hit=entity.position().add(0,entity.getBbHeight()*.55,0);
            if(c.player.getEyePosition().distanceTo(hit)>c.player.entityInteractionRange())throw new IllegalStateException("Entity out of reach");
            RotationAim.apply(c.player,RotationAim.lookAt(c.player,hit));
            c.gameMode.interact(c.player,entity,new EntityHitResult(entity,hit),InteractionHand.MAIN_HAND);
            phase="done";detail="entity interaction sent; verify resulting world state";
        }else if(command.equals("close_menu")){
            if(!c.player.containerMenu.getCarried().isEmpty())throw new IllegalStateException("Cursor holds an item");c.player.closeContainer();phase="done";detail="menu closed";
        }else throw new IllegalArgumentException("Unknown operation");
        if(survival(r)){survivalArmed=true;survivalBackground=background(r);}
        if(command.equals("gravel_start")||command.equals("gravel_config"))gravelReceipt(c);
        writeStatus(c);
    }
    private static void settle(JsonObject r,int wait){active=r.deepCopy();op="settle";phase="running";detail="awaiting server acknowledgement";deadline=ticks+wait;}
    private static boolean ordinaryMiningRequested(JsonObject request){
        return request!=null&&Set.of("mine_block","recover_shulker").contains(str(request,"op"))
            &&!terrainReplaceRequested(request)&&!dryPavingRequested(request);
    }
    private static BlockPos singleBlockTarget(JsonObject request){
        var pos=request.getAsJsonArray("pos");return new BlockPos(pos.get(0).getAsInt(),pos.get(1).getAsInt(),pos.get(2).getAsInt());
    }
    private static boolean singleBlockConfirmed(Minecraft c,JsonObject request){
        return ordinaryMiningRequested(request)&&ordinaryMiningConfirmation.confirmed(c,
            str(request,"single_block_world"),str(request,"id"),singleBlockTarget(request));
    }
    private static JsonObject singleBlockConfirmation(Minecraft c,JsonObject request,String outcome,String message,boolean confirmed){
        String world=str(request,"single_block_world"),id=str(request,"id");BlockPos target=singleBlockTarget(request);
        int sequence=ordinaryMiningConfirmation.sentSequence(world,id,target);
        JsonObject proof=new JsonObject();proof.addProperty("id",id);proof.addProperty("world_session",world);
        proof.addProperty("phase",outcome);proof.addProperty("detail",message);proof.addProperty("op",str(request,"op"));
        proof.add("mining_target",request.get("pos").deepCopy());proof.addProperty("server_confirmed",confirmed);
        proof.addProperty("confirmation_scope",confirmed?ordinaryMiningConfirmation.scope():"none");
        proof.addProperty("requested_confirmation_scope",ordinaryMiningConfirmation.scope());
        proof.addProperty("outcome_pending",sequence>=0&&!confirmed);
        proof.addProperty("server_update_seen",ordinaryMiningConfirmation.serverUpdateSeen(c,world,id,target));
        String observed=ordinaryMiningConfirmation.serverState(c,world,id,target);
        if(observed!=null)proof.addProperty("server_observed_state",observed);
        proof.addProperty("native_sequence",sequence);proof.addProperty("server_ack_sequence",ordinaryMiningConfirmation.ackSequence(world,id,target));
        return proof;
    }
    private static JsonObject printerConfirmation(JsonObject request,String outcome,String message,boolean confirmed){
        JsonObject proof=new JsonObject();proof.addProperty("id",str(request,"id"));
        proof.addProperty("world_session",str(request,"printer_completion_world"));
        proof.addProperty("phase",outcome);proof.addProperty("detail",message);proof.addProperty("op","professional_print");
        proof.addProperty("server_confirmed",confirmed);proof.addProperty("full_projection_confirmed",false);
        proof.addProperty("confirmation_scope",confirmed?"current_bounded_mask_distinct_exact_final_server_updates":"none");
        var targets=request.has("printer_completion_targets")?request.getAsJsonArray("printer_completion_targets"):new JsonArray();
        proof.addProperty("bounded_target_count",targets.size());proof.add("bounded_targets",targets.deepCopy());
        proof.addProperty("placement_key",str(request,"printer_completion_key"));proof.addProperty("outcome_pending",!confirmed);
        return proof;
    }
    private static void attachTerminalConfirmation(Minecraft c,JsonObject receipt,String id){
        for(JsonObject proof:new JsonObject[]{lastSingleBlockConfirmation,lastPrinterConfirmation})
            if(proof!=null&&id.equals(str(proof,"id"))&&session(c).equals(str(proof,"world_session")))
                for(var field:proof.entrySet())receipt.add(field.getKey(),field.getValue().deepCopy());
    }
    private static void saveTerminalConfirmation(Minecraft c,JsonObject proof){
        try{
            JsonObject receipt=snapshot(c);for(var field:proof.entrySet())receipt.add(field.getKey(),field.getValue().deepCopy());
            save(root(c).resolve("reply-"+safeId(str(proof,"id"))+".json"),receipt);
        }catch(Exception failure){KitClient.LOGGER.error("[Confirmation] terminal evidence could not be saved; no retry allowed",failure);}
    }
    private static void finish(Minecraft c,String p,String text){
        String completedId=active==null?"":str(active,"id");
        JsonObject ordinaryMining=ordinaryMiningRequested(active)?active.deepCopy():null;
        JsonObject printing=active!=null&&op.equals("professional_print")?active.deepCopy():null;
        boolean ordinaryConfirmed=ordinaryMining!=null&&singleBlockConfirmed(c,ordinaryMining);
        boolean printerConfirmed=printing!=null&&boundedPrinterComplete(c);
        if(ordinaryMining!=null&&p.equals("done")&&!ordinaryConfirmed){
            p="waiting";text="single target server block update or native sequence acknowledgement missing; outcome pending";
        }
        if(printing!=null&&p.equals("done")&&!printerConfirmed){
            p="waiting";text="current bounded printer mask lacks complete server confirmation; full projection remains unverified";
        }
        if(ordinaryMining!=null)lastSingleBlockConfirmation=singleBlockConfirmation(c,ordinaryMining,p,text,p.equals("done")&&ordinaryConfirmed);
        if(printing!=null)lastPrinterConfirmation=printerConfirmation(printing,p,text,p.equals("done")&&printerConfirmed);
        var completedBucket=active!=null&&Set.of("bucket_fill","bucket_place").contains(op)?bucketWaterTask:null;
        var completedMap=active!=null&&op.equals("map_create")?mapCreationTask:null;
        var completedAirSeed=active!=null&&op.equals("projection_air_seed")?airSeedTask:null;
        var completedScaffold=active!=null&&op.equals("projection_scaffold_fill")?scaffoldFillTask:null;
		finishSnowNavigation(c,active,p.equals("done"));
        JsonObject terrainRequest=active!=null&&terrainReplaceRequested(active)?active.deepCopy():null;
        JsonObject dryPavingRequest=dryPavingRequested(active)?active.deepCopy():null;
        JsonObject horseNudgeRequest=active!=null&&op.equals("nudge_horse")?active.deepCopy():null;
        boolean terrainConfirmed=terrainRequest!=null&&terrainServerConfirmation.confirmed(
            session(c),completedId,str(terrainRequest,"terrain_replace_stage"),terrainAckTarget(terrainRequest));
        boolean dryPavingConfirmed=dryPavingRequest!=null&&dryPavingConfirmedTick>=0
            &&ticks-dryPavingConfirmedTick>=8
            &&dryPavingServerConfirmation.confirmed(session(c),completedId,
                dryPavingAckStage(dryPavingRequest),dryPavingAckTarget(dryPavingRequest))
            &&state(c,dryPavingAckTarget(dryPavingRequest)).equals(dryPavingAckExpected(dryPavingRequest));
        if(terrainRequest!=null&&p.equals("done")&&!terrainConfirmed){
            p="waiting";text="matching server block update was not received; terrain outcome unknown";
        }
        if(dryPavingRequest!=null&&p.equals("done")&&!dryPavingConfirmed){
            p="waiting";text="matching server block update was not received; dry paving outcome unknown";
        }
        closeMaterialAirNavigation(c,p);
        if(Set.of("quarry_batch","rock_quarry_batch").contains(op)&&KitClient.borer()!=null)KitClient.borer().stop(c,text);
        if(op.equals("rock_quarry_batch"))rockQuarryStopped(p,text);
        if(op.equals("concrete_batch")){if(KitClient.concrete().isActive())KitClient.concrete().stop(c,"批次结束");if(supplyTask!=null){supplyTask.close(c);supplyTask=null;}concretePreexistingDrops.clear();concreteRetryUuid=null;concreteRetryPos=null;}
        if(completedBucket!=null){
            lastBucketWater=completedBucket.snapshot(p.equals("done"));
            try{completedBucket.terminal(p);}catch(Exception failure){KitClient.LOGGER.error("[Bucket] terminal receipt could not be saved; claim retained",failure);}
            bucketWaterTask=null;
        }
        if(completedMap!=null){lastMapCreation=completedMap.snapshot(p.equals("done"));mapCreationTask=null;}
        if(completedAirSeed!=null){lastAirSeed=completedAirSeed.snapshot(p.equals("done"));completedAirSeed.close();airSeedTask=null;}
        if(completedScaffold!=null){completedScaffold.close();lastScaffoldFill=completedScaffold.snapshot();if(!completedScaffold.cleanupPending())scaffoldFillTask=null;}
        ProfessionalPrinter.stop(c,false);restoreArrival();releaseWalk(c);active=null;phase=p;detail=text;
        if(nativeMaterialOwner!=null&&completedId.equals(nativeMaterialOwner.pendingId))
            nativeMaterialOwner.immediate=nativeMaterialReceipt(c,completedId,p,text);
        if(ordinaryMining!=null){
            saveTerminalConfirmation(c,lastSingleBlockConfirmation);
            ordinaryMiningConfirmation.close(completedId,p.equals("done")&&ordinaryConfirmed);
        }
        if(printing!=null)saveTerminalConfirmation(c,lastPrinterConfirmation);
        if(completedBucket!=null){
            JsonObject receipt=snapshot(c);receipt.addProperty("id",completedId);
            receipt.addProperty("phase",p);receipt.addProperty("detail",text);receipt.add("bucket_water",lastBucketWater.deepCopy());
            try{save(root(c).resolve("reply-"+safeId(completedId)+".json"),receipt);}
            catch(Exception failure){KitClient.LOGGER.error("[Bucket] terminal reply could not be saved; no replay allowed",failure);}
        }
        if(completedMap!=null){
            JsonObject receipt=snapshot(c);receipt.addProperty("id",completedId);
            receipt.addProperty("phase",p);receipt.addProperty("detail",text);receipt.add("map_creation",lastMapCreation.deepCopy());
            try{save(root(c).resolve("reply-"+safeId(completedId)+".json"),receipt);}
            catch(Exception failure){KitClient.LOGGER.error("[Map] terminal creation reply could not be saved",failure);}
        }
        if(completedAirSeed!=null){
            JsonObject receipt=snapshot(c);receipt.addProperty("id",completedId);
            receipt.addProperty("phase",p);receipt.addProperty("detail",text);receipt.add("projection_air_seed",lastAirSeed.deepCopy());
            try{save(root(c).resolve("reply-"+safeId(completedId)+".json"),receipt);}
            catch(Exception failure){KitClient.LOGGER.error("[Air seed] terminal seed reply could not be saved",failure);}
        }
        if(completedScaffold!=null){
            JsonObject receipt=snapshot(c);receipt.addProperty("id",completedId);receipt.addProperty("phase",p);receipt.addProperty("detail",text);
            receipt.add("projection_scaffold_fill",lastScaffoldFill.deepCopy());
            try{save(root(c).resolve("reply-"+safeId(completedId)+".json"),receipt);}
            catch(Exception error){KitClient.LOGGER.error("[Scaffold] terminal row receipt could not be saved",error);}
        }
        if(terrainRequest!=null){
            JsonObject receipt=snapshot(c);receipt.addProperty("id",completedId);
            receipt.addProperty("phase",p);receipt.addProperty("detail",text);
            receipt.addProperty("terrain_replace_stage",str(terrainRequest,"terrain_replace_stage"));
            receipt.add("terrain_replace_pos",terrainRequest.get("replacement_pos").deepCopy());
            receipt.addProperty("server_confirmed",terrainConfirmed);
            receipt.addProperty("confirmation_scope",terrainConfirmed?terrainServerConfirmation.scope():"none");
            try{save(root(c).resolve("reply-"+safeId(completedId)+".json"),receipt);}
            catch(Exception failure){KitClient.LOGGER.error("[Terrain] exact server confirmation receipt could not be saved",failure);}
            terrainServerConfirmation.close(completedId);
        }
        if(dryPavingRequest!=null){
            String stage=dryPavingAckStage(dryPavingRequest);
            BlockPos target=dryPavingAckTarget(dryPavingRequest);
            boolean seen=dryPavingServerConfirmation.serverUpdateSeen(session(c),completedId,stage,target);
            JsonObject receipt=snapshot(c);receipt.addProperty("id",completedId);
            receipt.addProperty("phase",p);receipt.addProperty("detail",text);
            receipt.addProperty("dry_paving_stage",stage.equals("dry_paving_mine")?"mine":"place");
            receipt.add("dry_paving_pos",JSON.toJsonTree(new int[]{target.getX(),target.getY(),target.getZ()}));
            receipt.addProperty("server_confirmed",dryPavingConfirmed);
            receipt.addProperty("confirmation_scope",dryPavingConfirmed?dryPavingServerConfirmation.scope():"none");
            receipt.addProperty("server_update_seen",seen);
            String observed=dryPavingServerConfirmation.serverObservedState(session(c),completedId,stage,target);
            if(observed!=null)receipt.addProperty("server_observed_state",observed);
            try{save(root(c).resolve("reply-"+safeId(completedId)+".json"),receipt);}
            catch(Exception failure){KitClient.LOGGER.error("[Dry Paving] exact server confirmation receipt could not be saved",failure);}
            dryPavingServerConfirmation.close(completedId);
            dryPavingConfirmedTick=-1;dryPavingClientAirTick=-1;
        }
        if(horseNudgeRequest!=null){
            JsonObject receipt=snapshot(c);receipt.addProperty("id",completedId);
            receipt.addProperty("phase",p);receipt.addProperty("detail",text);
            JsonObject nudge=new JsonObject();nudge.addProperty("spent_key",str(horseNudgeRequest,"spent_key"));
            nudge.addProperty("expected_uuid",str(horseNudgeRequest,"expected_uuid"));
            nudge.addProperty("attack_count",horseNudgeRequest.has("horse_attack_count")
                ?horseNudgeRequest.get("horse_attack_count").getAsInt():0);
            nudge.addProperty("clearance_radius",HorseNudgePolicy.REQUIRED_CLEARANCE);
            var entity=c.level==null?null:c.level.getEntity(horseNudgeRequest.get("entity_id").getAsInt());
            boolean exact=entity instanceof net.minecraft.world.entity.animal.equine.Horse
                &&entity.getUUID().toString().equals(str(horseNudgeRequest,"expected_uuid"));
            boolean alive=exact&&entity.isAlive()
                &&((net.minecraft.world.entity.LivingEntity)entity).getHealth()>0;
            nudge.addProperty("same_uuid_observed",exact);nudge.addProperty("alive",alive);
            if(exact){
                BlockPos cell=horseNudgeCell(horseNudgeRequest);
                double clearance=Math.hypot(entity.getX()-cell.getX()-.5,entity.getZ()-cell.getZ()-.5);
                nudge.addProperty("health",((net.minecraft.world.entity.LivingEntity)entity).getHealth());
                nudge.addProperty("clearance_distance",clearance);
                nudge.add("pos",JSON.toJsonTree(new double[]{entity.getX(),entity.getY(),entity.getZ()}));
            }
            nudge.addProperty("pve_guard_armed",guardArmed()&&pveOnly());
            nudge.addProperty("kill_aura_active",MeteorModules.isActive(MeteorModules.KILL_AURA));
            nudge.addProperty("kill_aura_can_target_horse",dev.twob2tkit.combat.PveAuraPolicy.allowed("minecraft:horse"));
            receipt.add("horse_nudge",nudge);
            try{save(root(c).resolve("reply-"+safeId(completedId)+".json"),receipt);}
            catch(Exception failure){KitClient.LOGGER.error("[Horse Nudge] terminal reply could not be saved",failure);}
            JsonObject durable=nudge.deepCopy();durable.addProperty("schema",1);durable.addProperty("request_id",completedId);
            durable.addProperty("world_session",str(horseNudgeRequest,"world_session"));
            durable.addProperty("placement_key",str(horseNudgeRequest,"placement_key"));
            durable.add("clearance_cell",horseNudgeRequest.getAsJsonArray("clearance_cell").deepCopy());
            durable.add("escape_target",horseNudgeRequest.getAsJsonArray("escape_target").deepCopy());
            durable.addProperty("stage","terminal_"+p);durable.addProperty("finished_at",System.currentTimeMillis());
            try{HorseNudgeStore.update(HorseNudgeStore.path(root(c),str(horseNudgeRequest,"spent_key")),durable);}
            catch(Exception failure){KitClient.LOGGER.error("[Horse Nudge] terminal spent receipt could not be updated",failure);}
        }
        writeStatus(c);
    }
    private static void restoreArrival(){
        boolean save=false;
        if(savedClearCeiling!=null){
            if(!KitClient.config().clearCeiling){KitClient.config().clearCeiling=savedClearCeiling;save=true;}
            savedClearCeiling=null;
        }
        if(Double.isFinite(savedArrival)){
            if(KitClient.config().arrivalRadius==temporaryArrival){KitClient.config().arrivalRadius=savedArrival;save=true;}
            savedArrival=Double.NaN;
        }
        if(save)KitClient.config().save();
    }
    private static void closeMaterialAirNavigation(Minecraft c,String outcome){
        if(materialAirNavigation==null)return;
        lastMaterialAirNavigation=materialAirNavigation.snapshot(c);
        lastMaterialAirNavigation.addProperty("world_session",session(c));
        lastMaterialAirNavigation.addProperty("outcome",outcome);
        materialAirNavigation.close(c);materialAirNavigation=null;
    }
    private static HorseNudgePolicy.Point horsePoint(JsonObject request,String key){
        JsonArray values=request.getAsJsonArray(key);
        if(values==null||values.size()!=3)throw new IllegalArgumentException(key+" requires three coordinates");
        double[] point=new double[3];
        for(int i=0;i<3;i++){
            var value=values.get(i);
            if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber()
                    ||!Double.isFinite(point[i]=value.getAsDouble()))
                throw new IllegalArgumentException(key+" requires finite numeric coordinates");
        }
        return new HorseNudgePolicy.Point(point[0],point[1],point[2]);
    }
    private static BlockPos horseNudgeCell(JsonObject request){
        var point=horsePoint(request,"clearance_cell");
        if(point.x()!=Math.rint(point.x())||point.y()!=Math.rint(point.y())||point.z()!=Math.rint(point.z()))
            throw new IllegalArgumentException("Horse nudge construction cell must be integral");
        return new BlockPos((int)point.x(),(int)point.y(),(int)point.z());
    }
    private static net.minecraft.world.entity.animal.equine.Horse horseNudgeTarget(Minecraft c,JsonObject request){
        if(!request.has("entity_id")||!request.has("expected_uuid"))
            throw new IllegalArgumentException("Exact horse id and UUID are required");
        UUID uuid;
        try{uuid=UUID.fromString(str(request,"expected_uuid"));}
        catch(IllegalArgumentException invalid){throw new IllegalArgumentException("Expected horse UUID is invalid");}
        var entity=c.level.getEntity(request.get("entity_id").getAsInt());
        if(!(entity instanceof net.minecraft.world.entity.animal.equine.Horse horse)
                ||!horse.getUUID().equals(uuid)
                ||!BuiltInRegistries.ENTITY_TYPE.getKey(horse.getType()).toString().equals("minecraft:horse"))
            throw new IllegalStateException("Exact observed horse changed");
        return horse;
    }
    private static boolean loadedHostileNearby(Minecraft c){
        return c.level.getEntities(c.player,c.player.getBoundingBox().inflate(16)).stream()
            .anyMatch(entity->entity instanceof net.minecraft.world.entity.monster.Enemy&&entity.isAlive());
    }
    private static void startHorseNudge(Minecraft c,JsonObject request)throws Exception{
        externalMaterialScope(c,request);long now=System.currentTimeMillis();
        if(!HorseNudgePolicy.scopeValid(str(request,"world_session"),session(c),
                request.get("expected_revision").getAsLong(),controlRevision,
                request.get("expires_at").getAsLong(),request.get("observed_at").getAsLong(),now))
            throw new IllegalStateException("Horse observation, world or controller is stale");
        if(c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL
                ||c.screen!=null||c.player.containerMenu!=c.player.inventoryMenu
                ||!c.player.containerMenu.getCarried().isEmpty()||KitKeys.manualMovementDown(c))
            throw new IllegalStateException("Horse nudge requires an idle survival inventory state");
        if(!guardArmed()||!pveOnly()||guardBusy||c.player.getHealth()<19
                ||c.player.isInWater()||c.player.isInLava()||c.player.isOnFire()||loadedHostileNearby(c))
            throw new IllegalStateException("Healthy idle PvE guard is required before a horse nudge");
        if(dev.twob2tkit.combat.PveAuraPolicy.allowed("minecraft:horse")
                ||!MeteorModules.enablePveAura()||!MeteorModules.isActive(MeteorModules.KILL_AURA)
                ||!MeteorModules.isActive(MeteorModules.AUTO_LOG))
            throw new IllegalStateException("Verified hostile-only KillAura is required before a horse nudge");
        if(!str(request,"expected_type").equals("minecraft:horse"))
            throw new IllegalArgumentException("Only an explicit regular horse blocker is supported");
        var horse=horseNudgeTarget(c,request);var expected=horsePoint(request,"expected_pos");
        float expectedHealth=request.get("expected_health").getAsFloat();
        var actual=new HorseNudgePolicy.Point(horse.getX(),horse.getY(),horse.getZ());
        if(!HorseNudgePolicy.exactObservation(expected,actual,expectedHealth,horse.getHealth()))
            throw new IllegalStateException("Horse position or health changed since observation");
        if(!horse.isAlive()||horse.isDeadOrDying()||horse.isBaby()||horse.isVehicle()
                ||horse.isPassenger()||horse.isLeashed()||!horse.onGround()||horse.isInWater()
                ||horse.isInLava()||horse.isOnFire())
            throw new IllegalStateException("Horse is not an unoccupied, untethered adult on dry ground");
        BlockPos cell=horseNudgeCell(request);checkSiteTarget(request,request.getAsJsonArray("clearance_cell"));
        var selected=dev.twob2tkit.builder.LitematicaAccess.lockedBuildSelection();
        if(!selected.key().equals(str(request,"placement_key"))||!selected.contains(cell)
                ||!dev.twob2tkit.builder.LitematicaAccess.inVisibleLayer(cell)
                ||!dev.twob2tkit.builder.LitematicaAccess.loadingReason(selected).isEmpty())
            throw new IllegalStateException("Protected construction selection changed");
        var model=dev.twob2tkit.builder.LitematicaAccess.schematicWorld();
        if(model==null||model.getBlockState(cell).isAir()
                ||model.getBlockState(cell).is(net.minecraft.world.level.block.Blocks.STRUCTURE_VOID)
                ||!model.getBlockState(cell).toString().equals(str(request,"expected_construction_state")))
            throw new IllegalStateException("Protected construction cell changed");
        var cellPoint=new HorseNudgePolicy.Point(cell.getX()+.5,cell.getY()+.5,cell.getZ()+.5);
        var playerPoint=new HorseNudgePolicy.Point(c.player.getX(),c.player.getY(),c.player.getZ());
        var escapePoint=horsePoint(request,"escape_target");
        String geometry=HorseNudgePolicy.geometryRejection(cellPoint,actual,playerPoint,escapePoint,
            c.player.entityInteractionRange());
        if(geometry!=null)throw new IllegalStateException(geometry);
        Vec3 hit=horse.position().add(0,horse.getBbHeight()*.5,0);
        if(c.player.getEyePosition().distanceTo(hit)>c.player.entityInteractionRange()-.2
                ||!c.player.hasLineOfSight(horse))throw new IllegalStateException("Horse is occluded or out of reach");
        String escape=HorseNudgeAction.escapeRejection(c,horse,new Vec3(escapePoint.x(),escapePoint.y(),escapePoint.z()));
        if(escape!=null)throw new IllegalStateException(escape);
        int emptySlot=HorseNudgeAction.emptyHotbar(c);
        if(emptySlot<0)throw new IllegalStateException("A temporary empty hotbar slot is required for minimum damage");
        double damage=HorseNudgeAction.emptyAttackDamage(c,emptySlot);
        if(c.player.hasEffect(net.minecraft.world.effect.MobEffects.STRENGTH)
                ||!HorseNudgePolicy.safeEmptyHandHit(horse.getHealth(),damage,true,c.player.onGround(),
                c.player.fallDistance,c.player.isSprinting(),c.player.getAttackStrengthScale(0)))
            throw new IllegalStateException("One empty-hand hit lacks a verified survival margin or full cooldown");
        String spent=str(request,"spent_key");
        String canonicalSpent=HorseNudgeStore.canonicalKey(str(request,"server"),str(request,"dimension"),
            str(request,"placement_key"),horse.getUUID().toString(),cell.getX(),cell.getY(),cell.getZ());
        if(!spent.equals(canonicalSpent))throw new IllegalArgumentException("Horse nudge spent key does not match the exact construction blocker");
        JsonObject claim=new JsonObject();
        claim.addProperty("schema",1);claim.addProperty("spent_key",spent);claim.addProperty("request_id",str(request,"id"));
        claim.addProperty("world_session",session(c));claim.addProperty("horse_uuid",horse.getUUID().toString());
        claim.addProperty("horse_health_before",horse.getHealth());claim.add("horse_pos_before",JSON.toJsonTree(new double[]{horse.getX(),horse.getY(),horse.getZ()}));
        claim.add("clearance_cell",request.getAsJsonArray("clearance_cell").deepCopy());claim.add("escape_target",request.getAsJsonArray("escape_target").deepCopy());
        claim.addProperty("attack_count",0);claim.addProperty("stage","claimed_before_attack");claim.addProperty("claimed_at",now);
        Path spentPath;
        try{spentPath=HorseNudgeStore.claim(root(c),spent,claim);}
        catch(FileAlreadyExistsException replay){throw new IllegalStateException("Horse nudge spent key already exists; no replay allowed");}
        active=request.deepCopy();active.addProperty("horse_health_before",horse.getHealth());
        active.addProperty("horse_attack_damage",damage);active.addProperty("horse_attack_tick",ticks);
        active.addProperty("horse_attack_count",0);op="nudge_horse";phase="running";
        detail="one empty-hand horse nudge claimed; observing clearance";deadline=ticks+120;
        RotationAim.apply(c.player,RotationAim.lookAt(c.player,hit));
        try{
            HorseNudgeAction.attackOnce(c,horse,emptySlot);active.addProperty("horse_attack_count",1);
            claim.addProperty("attack_count",1);claim.addProperty("stage","attack_sent_once");claim.addProperty("attack_sent_at",System.currentTimeMillis());
            try{HorseNudgeStore.update(spentPath,claim);}
            catch(Exception evidence){KitClient.LOGGER.error("[Horse Nudge] spent receipt update failed after the sole attack",evidence);}
        }catch(RuntimeException ambiguous){
            active.addProperty("horse_attack_count",-1);active.addProperty("horse_attack_error",ambiguous.getClass().getSimpleName());
            finish(c,"waiting","horse nudge send outcome is uncertain; spent key blocks any replay");return;
        }
        MeteorModules.enablePveAura();MeteorModules.enable(MeteorModules.AUTO_LOG);
        if(!guardArmed()||!pveOnly()||!MeteorModules.isActive(MeteorModules.KILL_AURA))
            finish(c,"waiting","sole horse nudge sent; PvE module state needs inspection and will not be retried");
    }
    private static void tickHorseNudge(Minecraft c){
        int id=active.get("entity_id").getAsInt();UUID uuid=UUID.fromString(str(active,"expected_uuid"));
        var entity=c.level.getEntity(id);boolean exact=entity instanceof net.minecraft.world.entity.animal.equine.Horse
            &&entity.getUUID().equals(uuid);
        boolean alive=exact&&entity.isAlive()&&entity instanceof net.minecraft.world.entity.LivingEntity living
            &&living.getHealth()>0;
        float health=alive?((net.minecraft.world.entity.LivingEntity)entity).getHealth():0;
        BlockPos cell=horseNudgeCell(active);double clearance=exact?Math.hypot(entity.getX()-cell.getX()-.5,
            entity.getZ()-cell.getZ()-.5):Double.NaN;
        if(exact){active.add("horse_observed_pos",JSON.toJsonTree(new double[]{entity.getX(),entity.getY(),entity.getZ()}));
            active.addProperty("horse_observed_health",health);active.addProperty("horse_clearance_distance",clearance);}
        int attackTick=active.get("horse_attack_tick").getAsInt();boolean timedOut=ticks>=deadline;
        var outcome=HorseNudgePolicy.outcome(exact,alive,health,clearance,timedOut);
        if(ticks-attackTick<4&&outcome==HorseNudgePolicy.Outcome.DONE)outcome=HorseNudgePolicy.Outcome.RUNNING;
        switch(outcome){
            case DONE->finish(c,"done","same horse is alive and beyond the six-block construction clearance after exactly one hit");
            case WAITING->finish(c,"waiting","same horse was not confirmed alive beyond six-block clearance; no second hit sent");
            case RUNNING->detail=exact?"observing the same living horse after exactly one hit":"horse observation temporarily unavailable; no second hit will be sent";
        }
    }
    private static int slaughterInt(JsonObject request,String key,int fallback){
        if(!request.has(key))return fallback;
        long number=ProjectionLoadPolicy.integer(request,key);
        if(number<Integer.MIN_VALUE||number>Integer.MAX_VALUE)
            throw new IllegalArgumentException("Slaughter "+key+" exceeds integer coordinates");
        return (int)number;
    }
    private static BlockPos slaughterPoint(JsonObject request,String key){
        JsonArray point=request.getAsJsonArray(key);
        if(point==null||point.size()!=3)throw new IllegalArgumentException("Slaughter region requires integer [x,y,z]");
        int[] values=new int[3];
        for(int i=0;i<3;i++){
            var coordinate=new JsonObject();coordinate.add("coordinate",point.get(i));
            values[i]=slaughterInt(coordinate,"coordinate",0);
        }
        return new BlockPos(values[0],values[1],values[2]);
    }
    private static void slaughterAttack(Minecraft c,JsonObject request)throws Exception{
        boolean attackDispatchStarted=false;
        lastSlaughterAttack=null;
        try{
        safeId(str(request,"id"));
        long now=System.currentTimeMillis();
        if(c.player==null||c.level==null||c.gameMode==null||supervisionLease==null
            ||!SlaughterPolicy.owned("materials".equals(str(supervisionLease,"kind")),
                str(request,"task_session"),str(supervisionLease,"job_session"),str(request,"world_session"),
                str(supervisionLease,"world_session"),session(c),
                request.has("expected_revision")?ProjectionLoadPolicy.integer(request,"expected_revision"):-1,
                supervisionLease.has("revision")?supervisionLease.get("revision").getAsLong():-1,controlRevision,
                request.has("expires_at")?ProjectionLoadPolicy.integer(request,"expires_at")-now:-1,now-lastSupervisionHeartbeat))
            throw new IllegalStateException("Slaughter requires the current owned material lease, world and revision");
        guard(c,request);
        var low=slaughterPoint(request,"region_min");
        var high=slaughterPoint(request,"region_max");
        var bounds=new SlaughterPolicy.Bounds(low.getX(),low.getY(),low.getZ(),high.getX(),high.getY(),high.getZ());
        int keep=slaughterInt(request,"keep_adults",SlaughterPolicy.DEFAULT_KEEP);
        if(!bounds.valid()||keep<2)throw new IllegalArgumentException("Slaughter requires bounded loaded region and at least two retained adults");
        checkSiteTarget(request,request.getAsJsonArray("region_min"));
        checkSiteTarget(request,request.getAsJsonArray("region_max"));
        if(low.getY()<c.level.getMinY()||high.getY()>=c.level.getMaxY())
            throw new IllegalArgumentException("Slaughter region is outside world height");
        for(BlockPos cell:BlockPos.betweenClosed(low,high))
            if(!c.level.hasChunkAt(cell))throw new IllegalStateException("Slaughter region has an unloaded chunk");
        int id=slaughterInt(request,"entity_id",-1);var entity=c.level.getEntity(id);
        UUID uuid=UUID.fromString(str(request,"expected_uuid"));
        if(!(entity instanceof net.minecraft.world.entity.animal.Animal animal)
            ||!entity.getUUID().equals(uuid)||!bounds.contains(entity.getX(),entity.getY(),entity.getZ()))
            throw new IllegalStateException("Slaughter target identity or region changed");
        String type=BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString();
        if(!SlaughterPolicy.adult(type,animal.isAlive(),animal.isRemoved(),animal.isBaby(),animal.hasCustomName(),animal.getHealth()))
            throw new IllegalStateException("Slaughter only permits living unnamed adult cow, sheep, pig or chicken");
        int adults=0;
        for(var observed:c.level.entitiesForRendering()){
            if(!(observed instanceof net.minecraft.world.entity.animal.Animal candidate)
                ||!bounds.contains(observed.getX(),observed.getY(),observed.getZ()))continue;
            String candidateType=BuiltInRegistries.ENTITY_TYPE.getKey(candidate.getType()).toString();
            if(type.equals(candidateType)&&SlaughterPolicy.adult(candidateType,candidate.isAlive(),candidate.isRemoved(),
                    candidate.isBaby(),candidate.hasCustomName(),candidate.getHealth()))adults++;
        }
        if(!SlaughterPolicy.surplus(adults,keep))
            throw new IllegalStateException("Slaughter would reduce the freshly loaded adult breeding reserve");
        // Also guard vanilla's actual sweep volume against a stale server onGround value.
        var sweepBox=animal.getBoundingBox().inflate(1.0,.25,1.0);
        for(BlockPos cell:BlockPos.betweenClosed(BlockPos.containing(sweepBox.minX,sweepBox.minY,sweepBox.minZ),
                BlockPos.containing(sweepBox.maxX,sweepBox.maxY,sweepBox.maxZ)))
            if(!c.level.hasChunkAt(cell))throw new IllegalStateException("Slaughter sweep buffer has an unloaded chunk");
        boolean sweepClear=c.level.getEntitiesOfClass(net.minecraft.world.entity.LivingEntity.class,
            sweepBox).stream()
            .noneMatch(other->other!=animal&&other!=c.player&&other.isAlive()&&!other.isRemoved());
        ItemStack weapon=c.player.getMainHandItem();
        boolean ordinaryWeapon=!weapon.isEmpty()&&(weapon.is(net.minecraft.tags.ItemTags.SWORDS)
            ||weapon.is(net.minecraft.tags.ItemTags.AXES))
            &&(!weapon.isDamageableItem()||weapon.getMaxDamage()-weapon.getDamageValue()>32);
        boolean otherWork=active!=null||KitClient.anyAfkAuto()||KitClient.borer().isActive()
            ||KitClient.controller().isActive()||KitClient.chopper().isActive()||ProfessionalPrinter.owned()
            ||c.screen!=null||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty();
        if(!SlaughterPolicy.safe(guardArmed()&&pveOnly(),guardBusy||loadedHostileNearby(c),KitKeys.manualMovementDown(c),
                dev.twob2tkit.combat.EmergencyExit.held(c),c.gameMode.getPlayerMode()==net.minecraft.world.level.GameType.SURVIVAL,
                c.player.getHealth(),c.player.getFoodData().getFoodLevel(),c.player.onGround(),c.player.isUsingItem(),
                c.player.hurtTime>0,c.player.isInWater()||c.player.isOnFire(),otherWork,ordinaryWeapon,sweepClear))
            throw new IllegalStateException("Slaughter requires healthy idle PvE guard, actual airborne pose and isolated target");
        Vec3 hit=animal.position().add(0,animal.getBbHeight()*.5,0);
        if(!SlaughterPolicy.aim(entity.getId()==id&&entity.getUUID().equals(uuid),c.player.hasLineOfSight(animal),
                c.player.getEyePosition().distanceTo(hit),c.player.entityInteractionRange(),c.player.getAttackStrengthScale(0)))
            throw new IllegalStateException("Slaughter target out of reach, occluded or attack cooling down");
        float targetHealthBefore=animal.getHealth();
        RotationAim.apply(c.player,RotationAim.lookAt(c.player,hit));
        // Mark BEFORE attack: an exception after packet dispatch is unknown, never a safe rejection.
        attackDispatchStarted=true;
        c.gameMode.attack(c.player,animal);c.player.swing(InteractionHand.MAIN_HAND);
        lastSlaughterAttack=new JsonObject();lastSlaughterAttack.addProperty("id",str(request,"id"));
        lastSlaughterAttack.addProperty("action_sent",true);lastSlaughterAttack.addProperty("result_scope","normal_attack_dispatch_only");
        lastSlaughterAttack.addProperty("entity_id",id);lastSlaughterAttack.addProperty("expected_uuid",uuid.toString());
        lastSlaughterAttack.addProperty("adult_count_before",adults);lastSlaughterAttack.addProperty("keep_adults",keep);
        lastSlaughterAttack.addProperty("target_health_before",targetHealthBefore);
        lastSlaughterAttack.addProperty("observed_at",now);lastSlaughterAttack.addProperty("world_session",session(c));
        lastSlaughterAttack.addProperty("control_revision",controlRevision);
        statusId=str(request,"id");op="material_slaughter_attack";phase="done";
        detail="normal animal attack sent; verify health, death and new drops";
        var receipt=snapshot(c);receipt.addProperty("id",statusId);receipt.addProperty("phase",phase);receipt.addProperty("detail",detail);
        receipt.add("slaughter_attack",lastSlaughterAttack.deepCopy());
        save(root(c).resolve("reply-"+safeId(statusId)+".json"),receipt);
        }catch(Exception failure){
            if(attackDispatchStarted||c.player==null||c.level==null)throw failure;
            String rejectedId=safeId(str(request,"id"));
            var rejected=new JsonObject();rejected.addProperty("id",rejectedId);
            rejected.addProperty("world_session",session(c));
            rejected.addProperty("expected_uuid",str(request,"expected_uuid"));
            rejected.addProperty("result_scope","normal_attack_dispatch_only");
            rejected.addProperty("action_sent",false);rejected.addProperty("pre_dispatch_rejected",true);
            rejected.addProperty("control_revision",controlRevision);rejected.addProperty("observed_at",System.currentTimeMillis());
            lastSlaughterAttack=rejected;
            statusId=rejectedId;op="material_slaughter_attack";phase="error";detail=failure.getMessage();
            var denied=snapshot(c);denied.addProperty("id",rejectedId);denied.addProperty("phase","error");
            denied.addProperty("detail",detail);denied.add("slaughter_attack",rejected.deepCopy());
            save(root(c).resolve("reply-"+rejectedId+".json"),denied);
        }
    }
    private static boolean bucketOwnerCurrent(Minecraft c,JsonObject r){
        if(c.player==null||c.level==null||c.gameMode==null||!currentMaterialRequest(c,r)
            ||!r.has("expected_revision")||r.get("expected_revision").getAsLong()!=controlRevision
            ||!str(r,"world_session").equals(session(c))||!r.has("expires_at")
            ||r.get("expires_at").getAsLong()<System.currentTimeMillis()
            ||r.get("expires_at").getAsLong()-System.currentTimeMillis()>15000
            ||System.currentTimeMillis()-lastSupervisionHeartbeat>15000
            ||!guardArmed()||!pveOnly()||guardBusy||KitKeys.manualMovementDown(c)
            ||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<8
            ||loadedHostileNearby(c)||c.player.isDeadOrDying()
            ||dev.twob2tkit.combat.EmergencyExit.held(c)
            ||c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL)return false;
        try{guard(c,r);return true;}catch(RuntimeException changed){return false;}
    }
    /** Called after vanilla applies an inventory packet from the current connection. */
    public static void serverBucketInventory(Object connection,int containerId,int slot,boolean direct,ItemStack packet){
        Minecraft c=Minecraft.getInstance();
        if(c.player==null||c.level==null||connection!=c.getConnection()||active==null||bucketWaterTask==null
            ||!Set.of("bucket_fill","bucket_place").contains(op))return;
        bucketWaterTask.serverInventory(c,connection,containerId,slot,direct,packet,ticks);
    }
    private static boolean currentMaterialRequest(Minecraft c,JsonObject r){
        return supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")
            &&supervisionLease.has("revision")&&supervisionLease.get("revision").getAsLong()==controlRevision
            &&str(supervisionLease,"world_session").equals(session(c))
            &&!str(r,"task_session").isBlank()&&str(r,"task_session").equals(str(supervisionLease,"job_session"));
    }
    private static boolean airNavigationClear(Minecraft c,JsonArray target){
        if(c.player==null||c.level==null||target==null||target.size()!=3)return false;
        double x=target.get(0).getAsDouble(),y=target.get(1).getAsDouble(),z=target.get(2).getAsDouble();
        if(!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z)
                ||y<c.level.getMinY()+2||y>c.level.getMaxY()+64)return false;
        var sweep=c.player.getBoundingBox().expandTowards(new Vec3(x-c.player.getX(),y-c.player.getY(),z-c.player.getZ()));
        if((sweep.maxX-sweep.minX+1)*(sweep.maxY-sweep.minY+1)*(sweep.maxZ-sweep.minZ+1)>8192
                ||!c.level.noCollision(c.player,sweep))return false;
        for(BlockPos p:BlockPos.betweenClosed(BlockPos.containing(sweep.minX,sweep.minY,sweep.minZ),
                BlockPos.containing(sweep.maxX-1e-7,sweep.maxY-1e-7,sweep.maxZ-1e-7))){
            if(!c.level.hasChunkAt(p))return false;
            var state=c.level.getBlockState(p);
            if(!state.getFluidState().isEmpty()||state.is(net.minecraft.world.level.block.Blocks.FIRE)
                    ||state.is(net.minecraft.world.level.block.Blocks.SOUL_FIRE)||state.is(net.minecraft.world.level.block.Blocks.COBWEB)
                    ||state.is(net.minecraft.world.level.block.Blocks.POWDER_SNOW))return false;
        }
        return true;
    }
    private static void externalMaterialScope(Minecraft c,JsonObject r){
        if(c.player==null||c.level==null||c.gameMode==null||c.player.isDeadOrDying()
                ||supervisionLease==null||!supervisionLease.has("revision")||!r.has("expected_revision")||!r.has("expires_at")
                ||!MaterialJobControlPolicy.owned(str(r,"task_session"),str(supervisionLease,"job_session"),
                    str(r,"world_session"),str(supervisionLease,"world_session"),r.get("expected_revision").getAsLong(),
                    controlRevision,supervisionLease.get("revision").getAsLong(),r.get("expires_at").getAsLong()-System.currentTimeMillis(),
                    nativeMaterialOwner!=null,str(supervisionLease,"kind").equals("materials"),KitKeys.manualMovementDown(c))
                ||!str(r,"world_session").equals(session(c))
                ||!AutomationScope.sameServer(c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip,str(r,"server"))
                ||!c.level.dimension().identifier().toString().equals(str(r,"dimension"))
                ||active!=null&&!str(active,"task_session").equals(str(r,"task_session")))
            throw new IllegalStateException("Material job control no longer owns this world and revision");
    }
    private static void updateMaterialPark(Minecraft c,JsonObject r){
        JsonArray target=r.getAsJsonArray("park_target");
        if(target==null||target.size()!=3||active!=null||c.screen!=null
                ||c.player.containerMenu!=c.player.inventoryMenu||c.player.isUnderWater())
            throw new IllegalStateException("Local park update requires an idle dry material task");
        double x=target.get(0).getAsDouble(),y=target.get(1).getAsDouble(),z=target.get(2).getAsDouble();
        if(!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z)
                ||Math.hypot(c.player.getX()-x,c.player.getZ()-z)>2||y<c.player.getY()||y>=320)
            throw new IllegalArgumentException("Local guard target must be finite, above this column and within two blocks horizontally");
        BlockPos at=BlockPos.containing(x,y,z);
        if(!c.level.hasChunkAt(at))throw new IllegalStateException("Local parking column is not loaded");
        var sweep=c.player.getBoundingBox().expandTowards(new Vec3(x-c.player.getX(),y-c.player.getY(),z-c.player.getZ()));
        boolean clear=c.level.noCollision(c.player,sweep);
        for(BlockPos p:BlockPos.betweenClosed(BlockPos.containing(sweep.minX,sweep.minY,sweep.minZ),
                BlockPos.containing(sweep.maxX-1e-7,sweep.maxY-1e-7,sweep.maxZ-1e-7)))
            if(!c.level.hasChunkAt(p)||!c.level.getFluidState(p).isEmpty())clear=false;
        int ground=c.level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING,at.getX(),at.getZ());
        if(!MaterialJobControlPolicy.localPark(c.player.getX(),c.player.getY(),c.player.getZ(),x,y,z,ground,
                c.player.getHealth(),MeteorModules.isActive(MeteorModules.FLIGHT),guardArmed()&&pveOnly(),clear))
            throw new IllegalStateException("Local park needs a clear dry ascent and twenty blocks of ground clearance");
        supervisionLease.add("park_target",target.deepCopy());supervisionLease.addProperty("remote_finish","guard");
    }
    private static void rockQuarryStopped(String outcome,String reason){
        if(rockQuarryProgress!=null){rockQuarryProgress.addProperty("active",false);
            rockQuarryProgress.addProperty("phase",outcome);rockQuarryProgress.addProperty("reason",reason);}
    }
    private static RockQuarryPolicy.Bounds rockBounds(JsonObject r){
        int[] a=rockPoint(r.getAsJsonArray("min")),b=rockPoint(r.getAsJsonArray("max"));
        return new RockQuarryPolicy.Bounds(a[0],a[1],a[2],b[0],b[1],b[2]);
    }
    private static int[] rockPoint(JsonArray point){
        if(point==null||point.size()!=3)throw new IllegalArgumentException("Rock quarry requires min/max coordinates");
        int[] result=new int[3];
        for(int i=0;i<3;i++){double n=point.get(i).getAsDouble();
            if(!Double.isFinite(n)||n!=Math.rint(n)||n<Integer.MIN_VALUE+8.0||n>Integer.MAX_VALUE-8.0)
                throw new IllegalArgumentException("Rock quarry coordinates must be finite integers");
            result[i]=(int)n;
        }
        return result;
    }
    private static int rockInt(JsonObject r,String key,int fallback){
        if(!r.has(key))return fallback;double n=r.get(key).getAsDouble();
        if(!Double.isFinite(n)||n!=Math.rint(n)||n<Integer.MIN_VALUE||n>Integer.MAX_VALUE)
            throw new IllegalArgumentException("Invalid rock quarry "+key);
        return (int)n;
    }
    private static boolean silk(ItemStack item){
        for(var enchantment:item.getEnchantments().keySet())
            if(enchantment.unwrapKey().map(key->key.identifier().toString()).orElse("").equals("minecraft:silk_touch")
                    &&item.getEnchantments().getLevel(enchantment)>0)return true;
        return false;
    }
    private static boolean silkShovelReady(Minecraft c,JsonObject request){
        if(!request.has("expected_tool_slot")||!request.has("expected_tool_item")||c.player==null)return false;
        ItemStack held=c.player.getMainHandItem();
        return GrassBlockToolPolicy.ready(str(request,"expected_tool_item"),itemId(held),
            request.get("expected_tool_slot").getAsInt(),c.player.getInventory().getSelectedSlot(),
            silk(held),held.isDamageableItem()?held.getMaxDamage()-held.getDamageValue():0);
    }
    private static boolean snowShovelReady(Minecraft c,JsonObject request,boolean requireSilk){
        if(!request.has("expected_tool_slot")||!request.has("expected_tool_item")||c.player==null)return false;
        ItemStack held=c.player.getMainHandItem();
        return SnowHarvestToolPolicy.ready(str(request,"expected_tool_item"),itemId(held),
            request.get("expected_tool_slot").getAsInt(),c.player.getInventory().getSelectedSlot(),
            silk(held),requireSilk,held.isDamageableItem()?held.getMaxDamage()-held.getDamageValue():0);
    }
    private static int rockFreeSlots(Minecraft c){int n=0;for(int i=0;i<36;i++)if(c.player.getInventory().getItem(i).isEmpty())n++;return n;}
    private static int rockCapacity(Minecraft c,String item){
        int n=0;for(int i=0;i<36;i++){ItemStack stack=c.player.getInventory().getItem(i);
            if(stack.isEmpty())n+=64;else if(itemId(stack).equals(item))n+=Math.max(0,stack.getMaxStackSize()-stack.getCount());}
        return n;
    }
    private static RockQuarryPolicy.Inspection inspectRockQuarry(Minecraft c,RockQuarryPolicy.Bounds bounds,String item){
        if(rockQuarryConfirmation==null)rockQuarryConfirmation=new dev.twob2tkit.runtime.engine.BorerMiningConfirmation();
        return RockQuarryPolicy.inspect((x,y,z)->{
            BlockPos pos=new BlockPos(x,y,z);
            if(y<c.level.getMinY()||y>=c.level.getMaxY()||!c.level.hasChunkAt(pos))
                return new RockQuarryPolicy.Cell(false,"unloaded",false,false,false,false,false,false);
            var block=c.level.getBlockState(pos);
            return new RockQuarryPolicy.Cell(true,BuiltInRegistries.BLOCK.getKey(block.getBlock()).toString(),block.isAir(),
                !block.getFluidState().isEmpty(),c.level.getBlockEntity(pos)!=null,
                block.getBlock() instanceof net.minecraft.world.level.block.FallingBlock,
                block.isCollisionShapeFullBlock(c.level,pos),rockQuarryConfirmation.pending(c.level,pos));
        },bounds,item);
    }
    private static void projectionLoadScope(Minecraft c,JsonObject request){
        ProjectionLoadPolicy.envelope(request,str(request,"op").equals("projection_load_rollback"));
        boolean idle=active==null&&nativeMaterialOwner==null&&!KitClient.anyAfkAuto()
            &&!dev.twob2tkit.material.MaterialJobs.snapshot().get("occupied").getAsBoolean()
            &&!ProfessionalPrinter.owned()&&!guardBusy
            &&(supervisionLease==null||str(supervisionLease,"kind").equals("parking"));
        var printer=ProfessionalPrinter.status();if(printer.has("enabled")&&printer.get("enabled").getAsBoolean())idle=false;
        ProjectionLoadPolicy.scope(c.player!=null&&c.level!=null&&c.gameMode!=null&&!c.player.isDeadOrDying(),idle,
            c.player!=null&&c.player.getHealth()>=19&&c.player.getFoodData().getFoodLevel()>=8
                &&!c.player.isInWater()&&!c.player.isInLava()&&!c.player.isOnFire(),
            KitKeys.manualMovementDown(c),c.screen==null&&c.player!=null&&c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty(),
            !dev.twob2tkit.combat.EmergencyExit.held(c),str(request,"world_session"),session(c),
            ProjectionLoadPolicy.integer(request,"expected_revision"),controlRevision,
            ProjectionLoadPolicy.integer(request,"expires_at"),System.currentTimeMillis());
    }
    private static boolean rockFlightAllowed(Minecraft c,JsonObject request){
        boolean flying=MeteorModules.isActive(MeteorModules.FLIGHT);
        boolean current=active!=null&&request==active&&op.equals("rock_quarry_batch");
        boolean material=current&&currentMaterialRequest(c,request);
        boolean ownedArea=false;
        if(material&&KitClient.borer()!=null){
            var bounds=rockBounds(request);
            ownedArea=KitClient.borer().ownsMaterialArea(
                new BlockPos(bounds.minX(),bounds.minY(),bounds.minZ()),new BlockPos(bounds.maxX(),bounds.maxY(),bounds.maxZ()));
        }
        // AREA's own flight lease rejects an external off-toggle; its intentional
        // digOnFoot transition must not be mistaken for lost material ownership.
        return RockQuarryPolicy.flightAllowed(flying,current,material,ownedArea);
    }
    private static void rockScope(Minecraft c,JsonObject request){
        if(c.player==null||c.level==null||c.gameMode==null
                ||c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL
                ||!c.level.dimension().equals(net.minecraft.world.level.Level.OVERWORLD)
                ||supervisionLease==null||!str(supervisionLease,"kind").equals("materials")
                ||!str(supervisionLease,"job_session").equals(str(request,"task_session"))
                ||!str(supervisionLease,"world_session").equals(session(c))
                ||supervisionLease.get("revision").getAsLong()!=controlRevision
                ||!str(request,"world_session").equals(session(c))
                ||dev.twob2tkit.combat.EmergencyExit.held(c)||!guardArmed()||!pveOnly()
                ||!RockQuarryPolicy.healthy(c.player.getHealth(),c.player.getFoodData().getFoodLevel(),c.player.isUnderWater())
                ||KitKeys.manualMovementDown(c)||c.player.containerMenu!=c.player.inventoryMenu
                ||c.screen!=null&&!nativeKitMenu(c)||!KitClient.config().borerAutoDefend
                ||!MeteorModules.isActive(MeteorModules.AUTO_LOG))
            throw new IllegalStateException("Current guarded, healthy, dry material quarry scope required");
        if(!rockFlightAllowed(c,request))throw new IllegalStateException("Rock quarry Flight is off outside its current owned AREA");
        if(str(request,"completion").equals("collect")){
            // AREA may auto-select a reserve pickaxe; inspect all eligible sources, not only the current hand.
            for(int i=0;i<=36;i++){ItemStack tool=i==36?c.player.getOffhandItem():c.player.getInventory().getItem(i);
                if(tool.is(net.minecraft.tags.ItemTags.PICKAXES)&&silk(tool))
                    throw new IllegalStateException("Store Silk Touch pickaxes before collecting ordinary rock or ore drops");}
        }
    }
    private static void startRockQuarry(Minecraft c,JsonObject request){
        JsonObject r=request.deepCopy();if(!r.has("completion"))r.addProperty("completion","collect");
        var bounds=rockBounds(r);String item=str(r,"item"),completion=str(r,"completion");
        int target=rockInt(r,"target_count",-1),seconds=rockInt(r,"seconds",300);
        if(!RockQuarryPolicy.requestAllowed(bounds,item,completion,target)||seconds<30||seconds>600)
            throw new IllegalArgumentException("Rock quarry requires 1..6 x 2..18 x 1..6 bounds, collect count or explicit clear count zero, and 30..600 seconds");
        checkSiteTarget(r,r.getAsJsonArray("min"));checkSiteTarget(r,r.getAsJsonArray("max"));rockScope(c,r);
        var borer=KitClient.borer();
        if(borer==null||borer.isActive()||KitClient.anyAfkAuto()||KitClient.controller().isActive()||hostileNearby(c)
                ||c.player.getY()<bounds.maxY()+1
                ||Math.hypot(c.player.getX()-(bounds.minX()+bounds.maxX()+1)/2.0,
                    c.player.getZ()-(bounds.minZ()+bounds.maxZ()+1)/2.0)>32
                ||!c.level.noCollision(c.player,c.player.getBoundingBox()))
            throw new IllegalStateException("Rock quarry needs an idle clear aerial or shaft-entry start near its top");
        var observed=inspectRockQuarry(c,bounds,item);boolean collect=completion.equals("collect");
        ItemStack held=c.player.getMainHandItem();boolean strong=held.is(net.minecraft.world.item.Items.DIAMOND_PICKAXE)
            ||held.is(net.minecraft.world.item.Items.NETHERITE_PICKAXE);
        if(!RockQuarryPolicy.toolAllowed(strong,held.getMaxDamage()-held.getDamageValue(),observed.remaining(),silk(held),collect)
                ||rockFreeSlots(c)<2||collect&&(observed.available()<target||rockCapacity(c,item)<target))
            throw new IllegalStateException("Rock quarry source blocks, inventory room or suitable durable pickaxe are insufficient");
        int before=count(c,item);r.addProperty("item_before",before);r.addProperty("rock_deadline_ms",System.currentTimeMillis()+seconds*1000L);
        rockQuarryProgress=new JsonObject();rockQuarryProgress.addProperty("id",str(r,"id"));
        rockQuarryProgress.addProperty("world_session",session(c));rockQuarryProgress.add("min",r.getAsJsonArray("min").deepCopy());
        rockQuarryProgress.add("max",r.getAsJsonArray("max").deepCopy());rockQuarryProgress.addProperty("item",item);
        rockQuarryProgress.addProperty("completion",completion);rockQuarryProgress.addProperty("target_count",target);
        rockQuarryProgress.addProperty("before",before);rockQuarryProgress.addProperty("clear_semantics","natural_blocks_removed_lights_retained");
        active=r;op="rock_quarry_batch";phase="running";deadline=ticks+20*seconds;
        updateRockQuarry(c,observed);
        if(!collect&&observed.remaining()==0){finish(c,"done","rock area already clear; retained lighting preserved");return;}
        try{borer.startMaterialArea(c,new BlockPos(bounds.minX(),bounds.minY(),bounds.minZ()),new BlockPos(bounds.maxX(),bounds.maxY(),bounds.maxZ()));}
        catch(RuntimeException error){finish(c,"error","native rock quarry could not start: "+error.getMessage());throw error;}
        if(!borer.isActive()){finish(c,"waiting","native rock quarry did not start: "+borer.status());return;}
        detail="native bounded rock quarry running; inventory gain is confirmed separately from cleared rock";
    }
    private static void updateRockQuarry(Minecraft c,RockQuarryPolicy.Inspection observed){
        int current=count(c,str(active,"item"));rockQuarryProgress.addProperty("current",current);
        rockQuarryProgress.addProperty("gained",current-active.get("item_before").getAsInt());
        rockQuarryProgress.addProperty("remaining_blocks",observed.remaining());
        rockQuarryProgress.addProperty("available_target_blocks",observed.available());
        rockQuarryProgress.addProperty("retained_lights",observed.retainedLights());
        rockQuarryProgress.addProperty("pending_blocks",observed.pendingBlocks());
        rockQuarryProgress.addProperty("area_cleared",observed.remaining()==0);
        rockQuarryProgress.addProperty("active",true);rockQuarryProgress.addProperty("phase","running");
        rockQuarryProgress.addProperty("observed_at",System.currentTimeMillis());
    }
    private static void tickRockQuarry(Minecraft c,boolean beforeInput){
        if(active==null||!op.equals("rock_quarry_batch"))return;
        try{
            rockScope(c,active);
            if(System.currentTimeMillis()>=active.get("rock_deadline_ms").getAsLong()){
                finish(c,"waiting","rock quarry time limit reached; inspect actual inventory gain");return;}
            boolean minerActive=KitClient.borer()!=null&&KitClient.borer().isActive();
            if(!beforeInput&&minerActive)return;
            // Revalidate the whole bounded buffer before AREA can issue its next mining input.
            var observed=inspectRockQuarry(c,rockBounds(active),str(active,"item"));updateRockQuarry(c,observed);
            var outcome=RockQuarryPolicy.result(str(active,"completion"),active.get("target_count").getAsInt(),
                active.get("item_before").getAsInt(),count(c,str(active,"item")),observed.remaining(),minerActive);
            if(outcome==RockQuarryPolicy.Result.DONE){finish(c,"done",str(active,"completion").equals("collect")
                ?"rock inventory target reached":"rock area cleared; retained lighting preserved");return;}
            if(outcome==RockQuarryPolicy.Result.WAITING){finish(c,"waiting","rock excavation stopped or is clear but inventory target is not reached");return;}
            if(rockFreeSlots(c)<2){finish(c,"waiting","rock quarry backpack reserve exhausted; store materials before resuming");return;}
            ItemStack held=c.player.getMainHandItem();
            if(!guardBusy&&held.isDamageableItem()&&(held.is(net.minecraft.tags.ItemTags.PICKAXES)
                    ||held.is(net.minecraft.tags.ItemTags.SHOVELS))&&held.getMaxDamage()-held.getDamageValue()<32)
                finish(c,"waiting","rock quarry tool durability reserve reached; replace the tool");
        }catch(Exception error){
            finish(c,"waiting",error.getMessage());
            if(c.player!=null&&c.player.getHealth()<14)
                dev.twob2tkit.combat.EmergencyExit.begin(c,"材料采坑生命过低，停止并安全离线");
        }
    }
    private static void checkSiteTarget(JsonObject r,JsonArray p){JsonArray s=r.getAsJsonArray("site");if(p==null || p.size()!=3 || !Double.isFinite(p.get(1).getAsDouble()) || !AutomationScope.nearSite(p.get(0).getAsDouble()-s.get(0).getAsDouble(),p.get(2).getAsDouble()-s.get(2).getAsDouble()))throw new IllegalArgumentException("Target outside worksite");}
    private static DryPavingMiningPolicy.World dryPavingWorld(Minecraft c){
        return new DryPavingMiningPolicy.World(){
            public boolean loaded(BlockPos p){return c.level.hasChunkAt(p);}
            public boolean air(BlockPos p){return c.level.isEmptyBlock(p);}
            public boolean fluid(BlockPos p){return !c.level.getFluidState(p).isEmpty();}
            public boolean blockEntity(BlockPos p){return c.level.getBlockEntity(p)!=null;}
            public boolean solid(BlockPos p){return c.level.getBlockState(p).isCollisionShapeFullBlock(c.level,p);}
            public boolean ordinaryLeaves(BlockPos p){
                var block=c.level.getBlockState(p);
                return block.is(net.minecraft.tags.BlockTags.LEAVES)
                    && block.isCollisionShapeFullBlock(c.level,p);
            }
            public String state(BlockPos p){return AutomationBridge.state(c,p);}
            public boolean naturalSurface(BlockPos p){
                return Set.of("minecraft:stone","minecraft:andesite","minecraft:grass_block","minecraft:dirt")
                    .contains(BuiltInRegistries.BLOCK.getKey(c.level.getBlockState(p).getBlock()).toString());
            }
            public boolean naturalSupport(BlockPos p){
                return naturalSurface(p)&&solid(p);
            }
            public boolean playerStandingOn(BlockPos p){return c.player.onGround()&&c.player.blockPosition().below().equals(p);}
            public Iterable<Vec3> nearbyEntities(BlockPos destination){
                var positions=new ArrayList<Vec3>();
                for(var entity:c.level.getEntities(c.player,new net.minecraft.world.phys.AABB(destination).inflate(4)))
                    positions.add(entity.position());
                return positions;
            }
            public net.minecraft.world.phys.AABB playerBody(){return c.player.getBoundingBox();}
        };
    }
    private static void dryPavingPlacementGuard(Minecraft c,BlockPos support,Direction face){
        String rejection=DryPavingPlacementPolicy.rejection(dryPavingWorld(c),support,face);
        if(rejection!=null)throw new IllegalStateException(rejection);
    }
    private static void dryPavingMiningGuard(Minecraft c,BlockPos target,String expectedState){
        String rejection=DryPavingMiningPolicy.rejection(dryPavingWorld(c),target,expectedState);
        if(rejection!=null)throw new IllegalStateException(rejection);
    }
    private static boolean dryPavingRequested(JsonObject r){
        return r!=null&&r.has("dry_paving_guard")&&r.get("dry_paving_guard").getAsBoolean();
    }
    private static void dryPavingRequestGuard(Minecraft c,JsonObject r){
        boolean miningContinuation=active==r&&op.equals("mine_block");
        long expectedRevision=r.has("expected_revision")?r.get("expected_revision").getAsLong():-1;
        long expiresAt=r.has("expires_at")?r.get("expires_at").getAsLong():-1;
        if(!TerrainReplacePolicy.scopeValid(str(r,"world_session"),session(c),expectedRevision,
                controlRevision,miningContinuation,expiresAt,System.currentTimeMillis()))
            throw new IllegalStateException("Dry paving world, controller, or request lease changed");
    }
    private static String dryPavingAckStage(JsonObject r){
        return str(r,"op").equals("interact")?"dry_paving_place":"dry_paving_mine";
    }
    private static BlockPos dryPavingAckTarget(JsonObject r){
        BlockPos action=terrainPosition(r.getAsJsonArray("pos"));
        return str(r,"op").equals("interact")?action.above():action;
    }
    private static String dryPavingAckExpected(JsonObject r){
        if(str(r,"op").equals("mine_block"))return "Block{minecraft:air}";
        String expected=str(r,"expected_placed_state"),hand=str(r,"expected_hand");
        if(!Set.of("Block{minecraft:stone_bricks}","Block{minecraft:polished_andesite}").contains(expected)
                ||!expected.equals("Block{"+hand+"}"))
            throw new IllegalArgumentException("Dry paving placement needs its exact stone brick or andesite result state");
        return expected;
    }
    private static boolean terrainReplaceRequested(JsonObject r){
        if(!r.has("terrain_replace_guard")){
            if(r.has("terrain_replace_stage"))throw new IllegalArgumentException("Terrain stage requires the explicit guard");
            return false;
        }
        if(!r.get("terrain_replace_guard").isJsonPrimitive()
                || !r.getAsJsonPrimitive("terrain_replace_guard").isBoolean())
            throw new IllegalArgumentException("Terrain replacement guard must be boolean");
        boolean enabled=r.get("terrain_replace_guard").getAsBoolean();
        if(enabled!=r.has("terrain_replace_stage"))
            throw new IllegalArgumentException("Terrain guard and stage must both be present");
        return enabled;
    }
    private static BlockPos terrainPosition(JsonArray coordinates){
        if(coordinates==null||coordinates.size()!=3)
            throw new IllegalArgumentException("Exact terrain replacement coordinates are required");
        int[] values=new int[3];
        for(int i=0;i<3;i++){
            if(!coordinates.get(i).isJsonPrimitive()||!coordinates.get(i).getAsJsonPrimitive().isNumber())
                throw new IllegalArgumentException("Terrain replacement coordinates must be numbers");
            double number=coordinates.get(i).getAsDouble();
            if(!Double.isFinite(number)||number!=Math.rint(number)
                    ||number<Integer.MIN_VALUE||number>Integer.MAX_VALUE)
                throw new IllegalArgumentException("Terrain replacement coordinates must be finite integers");
            values[i]=(int)number;
        }
        return new BlockPos(values[0],values[1],values[2]);
    }
    private static BlockPos terrainAckTarget(JsonObject r){
        return TerrainServerConfirmation.target(str(r,"terrain_replace_stage"),
            terrainPosition(r.getAsJsonArray("replacement_pos")));
    }
    private static String terrainAckExpected(JsonObject r){
        return TerrainServerConfirmation.expectedState(str(r,"terrain_replace_stage"),
            str(r,"expected_surface_state"));
    }
    /** Called only after vanilla applied a packet from the current connection. */
    public static void serverBlock(BlockPos pos,net.minecraft.world.level.block.state.BlockState packetState){
        Minecraft c=Minecraft.getInstance();
        if(c.player==null||c.level==null||active==null||!c.level.hasChunkAt(pos))return;
        String actual=packetState.toString();
        boolean applied=state(c,pos).equals(actual);
        if(bucketWaterTask!=null&&Set.of("bucket_fill","bucket_place").contains(op))
            bucketWaterTask.serverBlock(c,pos,packetState,applied,ticks);
        if(op.equals("projection_scaffold_fill")&&scaffoldFillTask!=null)
            scaffoldFillTask.serverBlock(c,pos,packetState,applied,ticks);
        if(op.equals("projection_air_seed")&&airSeedTask!=null)
            airSeedTask.serverBlock(session(c),pos,packetState,applied,ticks);
        if(terrainReplaceRequested(active))terrainServerConfirmation.serverBlock(session(c),str(active,"id"),
            str(active,"terrain_replace_stage"),pos,actual,applied);
        if(dryPavingRequested(active)){
            String stage=dryPavingAckStage(active);
            BlockPos target=dryPavingAckTarget(active);
            if(dryPavingServerConfirmation.serverBlock(session(c),str(active,"id"),stage,pos,actual,applied)){
                if(dryPavingConfirmedTick<0)dryPavingConfirmedTick=ticks;
            }
            else if(pos.equals(target)&&dryPavingServerConfirmation.serverUpdateSeen(session(c),
                    str(active,"id"),stage,target)
                    &&!dryPavingServerConfirmation.confirmed(session(c),str(active,"id"),stage,target)){
                dryPavingConfirmedTick=-1;
            }
        }
    }
    private static void terrainReplacementGuard(Minecraft c,JsonObject r){
        boolean miningContinuation=active==r&&op.equals("mine_block");
        long expectedRevision=r.has("expected_revision")?r.get("expected_revision").getAsLong():-1;
        long expiresAt=r.has("expires_at")?r.get("expires_at").getAsLong():-1;
        if(!TerrainReplacePolicy.scopeValid(str(r,"world_session"),session(c),expectedRevision,
                controlRevision,miningContinuation,expiresAt,System.currentTimeMillis()))
            throw new IllegalStateException("Terrain replacement world, controller, or request lease changed");
        JsonArray requested=r.getAsJsonArray("replacement_pos"),action=r.getAsJsonArray("pos");
        BlockPos target=terrainPosition(requested),actionPos=terrainPosition(action);
        checkSiteTarget(r,requested);
        TerrainReplacePolicy.Stage stage=switch(str(r,"terrain_replace_stage")){
            case "lift_grass"->TerrainReplacePolicy.Stage.LIFT_GRASS;
            case "mine_stone"->TerrainReplacePolicy.Stage.MINE_STONE;
            case "place_dirt"->TerrainReplacePolicy.Stage.PLACE_DIRT;
            case "restore_grass"->TerrainReplacePolicy.Stage.RESTORE_GRASS;
            default->throw new IllegalArgumentException("Unknown terrain replacement stage");
        };
        boolean placing=stage==TerrainReplacePolicy.Stage.PLACE_DIRT
            ||stage==TerrainReplacePolicy.Stage.RESTORE_GRASS;
        BlockPos expectedAction=switch(stage){
            case LIFT_GRASS->target.above();
            case MINE_STONE,RESTORE_GRASS->target;
            case PLACE_DIRT->target.below();
        };
        String expectedState=switch(stage){
            case LIFT_GRASS->str(r,"expected_surface_state");
            case MINE_STONE->"Block{minecraft:stone}";
            case PLACE_DIRT->str(r,"expected_below_state");
            case RESTORE_GRASS->str(r,"expected_state");
        };
        if(!actionPos.equals(expectedAction)||!"up".equalsIgnoreCase(str(r,"face"))
                ||!str(r,"expected_state").equals(expectedState)
                ||placing&&!str(r,"expected_hand").equals(stage==TerrainReplacePolicy.Stage.PLACE_DIRT
                    ?"minecraft:dirt":"minecraft:grass_block")
                ||!placing&&!"mine_block".equals(str(r,"op"))
                ||placing&&!"interact".equals(str(r,"op")))
            throw new IllegalArgumentException("Terrain replacement action must address the exact upper face");
        TerrainReplacePolicy.World world=new TerrainReplacePolicy.World(){
            public boolean loaded(BlockPos p){return c.level.hasChunkAt(p);}
            public boolean air(BlockPos p){return c.level.isEmptyBlock(p);}
            public boolean solid(BlockPos p){return c.level.getBlockState(p).isCollisionShapeFullBlock(c.level,p);}
            public boolean fluid(BlockPos p){return !c.level.getFluidState(p).isEmpty();}
            public boolean blockEntity(BlockPos p){return c.level.getBlockEntity(p)!=null;}
            public String state(BlockPos p){return AutomationBridge.state(c,p);}
            public boolean selectedDirtAndGrassColumn(BlockPos p,String key){
                var selection=dev.twob2tkit.builder.LitematicaAccess.lockedBuildSelection();
                if(!selection.name().equals("晴庭-完整前后庭院")
                        ||!selection.key().equals(key)||selection.max().getZ()!=p.getZ()
                        ||!selection.contains(p)||!selection.contains(p.above())
                        ||!dev.twob2tkit.builder.LitematicaAccess.inVisibleLayer(p)
                        ||!dev.twob2tkit.builder.LitematicaAccess.inVisibleLayer(p.above())
                        ||!dev.twob2tkit.builder.LitematicaAccess.loadingReason(selection).isEmpty())return false;
                var schematic=dev.twob2tkit.builder.LitematicaAccess.schematicWorld();
                return schematic!=null&&schematic.getBlockState(p).is(net.minecraft.world.level.block.Blocks.DIRT)
                    &&schematic.getBlockState(p.above()).is(net.minecraft.world.level.block.Blocks.GRASS_BLOCK);
            }
            public Iterable<net.minecraft.world.phys.AABB> nearbyEntityBoxes(BlockPos p){
                var boxes=new ArrayList<net.minecraft.world.phys.AABB>();
                for(var entity:c.level.getEntities(c.player,new net.minecraft.world.phys.AABB(p).inflate(4)))
                    if(entity.isAlive())boxes.add(entity.getBoundingBox());
                return boxes;
            }
            public net.minecraft.world.phys.AABB playerBody(){return c.player.getBoundingBox();}
            public Vec3 playerPosition(){return c.player.position();}
            public double playerEyeY(){return c.player.getEyePosition().y;}
            public boolean standingPose(){return c.player.getPose()==net.minecraft.world.entity.Pose.STANDING;}
            public boolean guardedFlight(){return guardArmed()&&pveOnly()&&!guardBusy
                &&c.player.getHealth()>=19&&!c.player.onGround()&&!KitKeys.manualMovementDown(c)
                &&!dev.twob2tkit.combat.EmergencyExit.held(c)
                &&MeteorModules.isActive(MeteorModules.FLIGHT);}
            private boolean reserve(ItemStack tool){return tool.isDamageableItem()
                &&tool.getMaxDamage()-tool.getDamageValue()>=64;}
            public boolean silkShovelReady(){
                ItemStack tool=c.player.getMainHandItem();
                return (tool.is(net.minecraft.world.item.Items.DIAMOND_SHOVEL)
                    ||tool.is(net.minecraft.world.item.Items.NETHERITE_SHOVEL))
                    &&silk(tool)&&reserve(tool);
            }
            public boolean pickReady(){
                ItemStack tool=c.player.getMainHandItem();
                return (tool.is(net.minecraft.world.item.Items.DIAMOND_PICKAXE)
                    ||tool.is(net.minecraft.world.item.Items.NETHERITE_PICKAXE))
                    &&reserve(tool);
            }
            public boolean dirtReady(){return c.player.getMainHandItem().is(net.minecraft.world.item.Items.DIRT)
                &&c.player.getMainHandItem().getCount()>=1;}
            public boolean grassReady(){return c.player.getMainHandItem().is(net.minecraft.world.item.Items.GRASS_BLOCK)
                &&c.player.getMainHandItem().getCount()>=1;}
        };
        String rejection=TerrainReplacePolicy.rejection(world,target,stage,str(r,"placement_key"),
            str(r,"expected_surface_state"),str(r,"expected_below_state"),str(r,"expected_state"));
        if(rejection!=null)throw new IllegalStateException(rejection);
        if(!placing){
            Vec3 aim=blockAim(actionPos,r);
            if(c.player.getEyePosition().distanceTo(aim)>c.player.blockInteractionRange()-.2)
                throw new IllegalStateException("Terrain replacement mining face moved out of reach");
            var hit=c.level.clip(new ClipContext(c.player.getEyePosition(),aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
            if(!hit.getBlockPos().equals(actionPos)||hit.getDirection()!=Direction.UP)
                throw new IllegalStateException("Terrain replacement mining upper face is not visible");
        }
    }
    private static JsonObject snowSeedCandidates(Minecraft c,JsonObject r){
        if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")
                ||!str(supervisionLease,"job_session").equals(str(r,"task_session"))
                ||!str(supervisionLease,"world_session").equals(session(c)))
            throw new IllegalStateException("Current material lease is required for seed snow candidates");
        JsonArray origin=supervisionLease.getAsJsonArray("search_origin");
        if(origin==null||origin.size()!=3)throw new IllegalStateException("Material search origin was not recorded by the host");
        return SnowSeedExpedition.candidates(c,r,session(c),origin.get(0).getAsDouble(),
            origin.get(1).getAsDouble(),origin.get(2).getAsDouble());
    }
    private static void startScan(Minecraft c,JsonObject request){
        if(pendingScan!=null)throw new IllegalStateException("Another scan is pending; its records are retained");
        var low=request.getAsJsonArray("min");var high=request.getAsJsonArray("max");checkSiteTarget(request,low);checkSiteTarget(request,high);
        var cursor=new ScanCursor(low.get(0).getAsInt(),low.get(1).getAsInt(),low.get(2).getAsInt(),
            high.get(0).getAsInt(),high.get(1).getAsInt(),high.get(2).getAsInt());
        pendingScan=new ScanJob(c,request,cursor);tickScan(c);
    }
    private static void tickScan(Minecraft c){
        var scan=pendingScan;if(scan==null)return;
        if(scan.terminal!=null){publishScan(scan);return;}
        if(scan.steppedTick==ticks)return;
        try{
            if(c.player==null||c.level!=scan.level||c.getConnection()!=scan.connection
                ||!scan.world.equals(session(c))||controlRevision!=scan.revision
                ||KitKeys.manualMovementDown(c)){
                finishScan(c,"waiting","scan world, controller or manual ownership changed; partial records retained");return;
            }
            guard(c,scan.request);scan.steppedTick=ticks;
            scan.cursor.advance(scan.details,System::nanoTime,cell->scanCell(c,scan,cell));
            if(scan.cursor.done())finishScan(c,"done","bounded loaded-world scan completed");
        }catch(Exception failure){finishScan(c,"waiting","scan stopped; partial records retained: "+failure.getMessage());}
    }
    private static void finishScan(Minecraft c,String outcome,String message){
        var scan=pendingScan;if(scan==null)return;
        if(scan.terminal!=null){publishScan(scan);return;} // Submitted terminal trees stay immutable, including during stop/world cleanup.
        JsonObject out;
        try{out=snapshot(c);}catch(Exception failure){
            // A status supplement failure must not discard cells already read.
            out=new JsonObject();out.addProperty("time",System.currentTimeMillis());
            out.addProperty("connected",c.player!=null&&c.level!=null);out.addProperty("control_revision",controlRevision);
            out.addProperty("scan_snapshot_failure",failure.getClass().getSimpleName());
        }
        out.addProperty("id",str(scan.request,"id"));out.addProperty("phase",outcome);out.addProperty("detail",message);
        out.addProperty("world_session",scan.world);out.addProperty("scan_coherent",ticks==scan.startedTick&&outcome.equals("done"));
        out.addProperty("scan_started_at",scan.startedAt);out.addProperty("scan_ended_at",System.currentTimeMillis());
        out.addProperty("scan_start_tick",scan.startedTick);out.addProperty("scan_end_tick",ticks);out.addProperty("scan_elapsed_ticks",ticks-scan.startedTick);
        out.addProperty("scan_start_revision",scan.revision);out.addProperty("scan_end_revision",controlRevision);
        out.addProperty("scan_cells_read",scan.cursor.read());out.addProperty("scan_total_cells",scan.cursor.total());
        out.addProperty("scan_scope","loaded_client_cells_sampled_on_client_ticks_not_atomic_server_snapshot");out.add("blocks",scan.rows);
        if(scan.details&&outcome.equals("done")){
            try{out.add("scan_entities",scanEntities(c,scan.request));}
            catch(Exception failure){
                out.addProperty("phase","waiting");out.addProperty("detail","scan entity supplement failed; sampled block records retained");
                out.addProperty("scan_coherent",false);
            }
            out.addProperty("scan_entity_scope","current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd");
            out.addProperty("light_survey_scope","client_light_layers_and_ordinary_zombie_geometry_block_light_only_not_complete_spawn_rules");
        }
        scan.terminal=out;publishScan(scan);
    }
    private static void publishScan(ScanJob scan){
        if(scan.owner!=null){
            if(nativeMaterialDispatch&&scan.owner==nativeMaterialOwner)nativeMaterialReadResult=scan.terminal;
            else scan.owner.immediate=scan.terminal;
            pendingScan=null;return;
        }
        if(scan.replyWrite==null){scan.replyWrite=scanReplyWriter.submit(scan.replyPath,scan.terminal);return;}
        if(scan.replyWrite.state==ExactScanReplyWriter.State.SAVED){
            scanReplyWriter.release(scan.replyWrite);pendingScan=null;return;
        }
        if(scan.replyWrite.state==ExactScanReplyWriter.State.FAILED){
            long now=System.currentTimeMillis();
            if(now>=scan.nextIoWarning){
                scan.nextIoWarning=now+10_000;
                KitClient.LOGGER.warn("[Scan] exact reply IO failed type={}; sampled records retained for retry",scan.replyWrite.failureType);
            }
            if(now>=scan.nextIoRetry){scan.nextIoRetry=now+1000;scanReplyWriter.retry(scan.replyWrite);}
        }
    }
    private static void scanCell(Minecraft c,ScanJob scan,ScanCursor.Cell cell){
        int x=cell.x(),y=cell.y(),z=cell.z();
        var chunk=c.level.getChunkSource().getChunk(Math.floorDiv(x,16),Math.floorDiv(z,16),
            net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
        if(!dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence.isServerChunk(c.level,chunk))
            throw new IllegalStateException("Server chunk is not loaded: "+x+" "+z);
        BlockPos p=new BlockPos(x,y,z);var bs=c.level.getBlockState(p);if(bs.isAir())return;
        JsonObject v=new JsonObject();v.add("pos",JSON.toJsonTree(new int[]{x,y,z}));v.addProperty("state",bs.toString());
        if(scan.details){
                v.addProperty("solid",bs.isCollisionShapeFullBlock(c.level,p));v.addProperty("replaceable",bs.canBeReplaced());
                v.addProperty("passable",bs.getCollisionShape(c.level,p).isEmpty() && bs.getFluidState().isEmpty());
                v.addProperty("fluid",!bs.getFluidState().isEmpty());v.addProperty("block_entity",c.level.getBlockEntity(p)!=null);
                BlockPos spawn=p.above();
                boolean zombieFloor=p.getY()>=c.level.getMinY()&&spawn.above().getY()<=c.level.getMaxY()
                    &&net.minecraft.world.entity.SpawnPlacements.isSpawnPositionOk(net.minecraft.world.entity.EntityType.ZOMBIE,c.level,spawn)
                    &&c.level.noBlockCollision(null,net.minecraft.world.entity.EntityType.ZOMBIE.getDimensions()
                        .makeBoundingBox(spawn.getX()+.5,spawn.getY(),spawn.getZ()+.5),true);
                int lightLimit=c.level.dimensionType().monsterSpawnBlockLightLimit();
                var light=LightSurveyPolicy.sample(
                    c.level.getBrightness(net.minecraft.world.level.LightLayer.BLOCK,p),
                    c.level.getBrightness(net.minecraft.world.level.LightLayer.SKY,p),
                    c.level.getBrightness(net.minecraft.world.level.LightLayer.BLOCK,spawn),
                    c.level.getBrightness(net.minecraft.world.level.LightLayer.SKY,spawn),zombieFloor,lightLimit);
                v.addProperty("block_light",light.blockLight());v.addProperty("sky_light",light.skyLight());
                v.addProperty("spawn_block_light",light.spawnBlockLight());v.addProperty("spawn_sky_light",light.spawnSkyLight());
                v.addProperty("zombie_spawn_floor",light.zombieSpawnFloor());
                v.addProperty("zombie_block_light_risk",light.zombieBlockLightRisk());
                v.addProperty("monster_spawn_block_light_limit",lightLimit);
        }
        scan.rows.add(v);
    }
    /** Already-loaded client entities only; no server query and no breeding-timer inference. */
    private static JsonArray scanEntities(Minecraft c,JsonObject r){
        var low=r.getAsJsonArray("min");var high=r.getAsJsonArray("max");
        var bounds=new net.minecraft.world.phys.AABB(low.get(0).getAsInt(),low.get(1).getAsInt(),low.get(2).getAsInt(),
            high.get(0).getAsInt()+1.0,high.get(1).getAsInt()+1.0,high.get(2).getAsInt()+1.0);
        var rows=new JsonArray();
        for(var e:c.level.getEntities(c.player,bounds)){
            if(e.isRemoved()||!bounds.intersects(e.getBoundingBox()))continue;
            var row=new JsonObject();row.addProperty("id",e.getId());row.addProperty("uuid",e.getUUID().toString());
            row.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());
            row.add("pos",JSON.toJsonTree(new double[]{e.getX(),e.getY(),e.getZ()}));
            row.addProperty("visible",c.player.hasLineOfSight(e));row.addProperty("alive",e.isAlive());
            if(e instanceof net.minecraft.world.entity.LivingEntity living){row.addProperty("is_baby",living.isBaby());row.addProperty("has_custom_name",living.hasCustomName());row.addProperty("health",living.getHealth());}
            rows.add(row);
        }
        return rows;
    }
    static Vec3 blockAim(BlockPos p,JsonObject request){
        if(!request.has("face"))return Vec3.atCenterOf(p);
        var face=Direction.valueOf(request.get("face").getAsString().toUpperCase(Locale.ROOT));
        return Vec3.atCenterOf(p).add(face.getStepX()*.499,face.getStepY()*.499,face.getStepZ()*.499);
    }
    private static String state(Minecraft c,BlockPos p){return c.level.getBlockState(p).toString();}
    private static boolean hostileNearby(Minecraft c){return c.level.getEntities(c.player,c.player.getBoundingBox().inflate(16)).stream().anyMatch(e->e instanceof net.minecraft.world.entity.monster.Enemy && e.isAlive() && c.player.hasLineOfSight(e));}
    private static String itemId(ItemStack s){return s.isEmpty()?"minecraft:air":BuiltInRegistries.ITEM.getKey(s.getItem()).toString();}
    static int matchingInventorySlot(List<String> inventory,String item,Integer exact){
        if(exact!=null){
            if(exact<0||exact>=36||exact>=inventory.size()||!inventory.get(exact).equals(item))
                throw new IllegalStateException("Selected material slot no longer holds the expected item");
            return exact;
        }
        for(int i=0;i<Math.min(36,inventory.size());i++)if(inventory.get(i).equals(item))return i;
        throw new IllegalStateException("Missing item: "+item);
    }
    private static int count(Minecraft c,String id){int n=0;for(int i=0;i<c.player.getInventory().getContainerSize();i++){ItemStack s=c.player.getInventory().getItem(i);if(itemId(s).equals(id))n+=s.getCount();}return n;}
    private static JsonArray enchantments(ItemEnchantments values){
        JsonArray rows=new JsonArray();if(values==null)return rows;
        for(var enchantment:values.keySet()){
            JsonObject row=new JsonObject();row.addProperty("id",enchantment.unwrapKey().map(key->key.identifier().toString()).orElse("unknown"));
            row.addProperty("level",values.getLevel(enchantment));rows.add(row);
        }
        return rows;
    }
    private static void addItemDetails(JsonObject target,ItemStack item){
        target.addProperty("max_stack",item.getMaxStackSize());
        MapAutomation.addItemDetails(target,item);
        if(item.isDamageableItem()){
            target.addProperty("durability",item.getMaxDamage()-item.getDamageValue());
            target.addProperty("max_durability",item.getMaxDamage());
        }
        var applied=item.getEnchantments();if(!applied.isEmpty())target.add("enchantments",enchantments(applied));
        var stored=item.get(net.minecraft.core.component.DataComponents.STORED_ENCHANTMENTS);
        if(stored!=null&&!stored.isEmpty())target.add("stored_enchantments",enchantments(stored));
        var potion=item.get(net.minecraft.core.component.DataComponents.POTION_CONTENTS);
        if(potion!=null)target.addProperty("water_breathing",
            potion.is(Potions.WATER_BREATHING)||potion.is(Potions.LONG_WATER_BREATHING));
    }
    private static JsonObject stack(ItemStack s){
        JsonObject j=new JsonObject();j.addProperty("item",itemId(s));j.addProperty("count",s.getCount());
        addItemDetails(j,s);
        var contents=s.get(net.minecraft.core.component.DataComponents.CONTAINER);
        if(contents!=null){JsonArray rows=new JsonArray();contents.nonEmptyItemCopyStream().limit(27).forEach(item->{JsonObject v=new JsonObject();v.addProperty("item",itemId(item));v.addProperty("count",item.getCount());addItemDetails(v,item);rows.add(v);});j.add("contains",rows);}
        return j;
    }
    /**
     * Freeze the host-owned return destination when a material session starts.
     * A same-dimension saved Home wins; otherwise the immutable session origin
     * remains the fallback. Python may read this value but never supplies it.
     */
    static JsonObject materialReturnTarget(KitConfig.HomeTarget home,String dimension,
            double originX,double originY,double originZ){
        var immutable=home==null?null:new MaterialReturnTargetPolicy.Home(
            home.x(),home.z(),home.cruiseY(),home.dimension());
        var selected=MaterialReturnTargetPolicy.choose(
            immutable,dimension,originX,originY,originZ);
        JsonObject result=new JsonObject();
        result.addProperty("x",selected.x());result.addProperty("z",selected.z());
        result.addProperty("cruise_y",selected.cruiseY());
        result.addProperty("dimension",selected.dimension());
        result.addProperty("source",selected.source());
        return result;
    }
    private static JsonObject snapshot(Minecraft c){
        JsonObject j=new JsonObject();j.addProperty("time",System.currentTimeMillis());
        if(supervisionLease!=null)j.add("supervision_lease",supervisionLease.deepCopy());if(lastSafetyEvent!=null)j.add("supervision_safety",lastSafetyEvent.deepCopy());
        j.add("safety_hold",dev.twob2tkit.combat.EmergencyExit.snapshot(c));
        j.addProperty("interface_pause_protocol",1);j.addProperty("interface_paused",interfacePaused(c));
        j.addProperty("gui_width",c.getWindow().getGuiScaledWidth());j.addProperty("gui_height",c.getWindow().getGuiScaledHeight());j.addProperty("game_paused",c.isPaused());if(c.getSingleplayerServer()!=null)j.addProperty("server_game_time",c.getSingleplayerServer().overworld().getGameTime());j.addProperty("job_hud_protocol",1);j.addProperty("quarry_protocol",1);j.addProperty("raw_iron_block_quarry_protocol",1);j.addProperty("tree_survey_protocol",1);j.addProperty("snow_biome_survey_protocol",SnowBiomeSurvey.PROTOCOL);j.addProperty("snow_seed_locator_protocol",SnowSeedExpedition.PROTOCOL);j.addProperty("snow_seed_locator_available",KitClient.seedScout()!=null&&KitClient.seedScout().hasStoredWorldSeed());j.addProperty("material_protocol",2);j.addProperty("air_return_protocol",1);j.addProperty("horse_nudge_protocol",1);j.addProperty("inventory_cursor_precondition_protocol",1);j.add("inventory_isolation",CraftingCompatibility.snapshot());j.addProperty("material_mining_isolation_protocol",1);j.addProperty("material_mining_cleanup_pending",materialMiningCleanupPending);j.add("material_mining_isolation",MaterialMiningLease.snapshot(materialMiningLease,!materialMiningScope(c).isEmpty()&&materialMiningScope(c).equals(materialMiningOwner)));j.addProperty("supervision_protocol",1);j.addProperty("supply_protocol",1);j.addProperty("freefall_protocol",1);j.addProperty("kit_version",net.fabricmc.loader.api.FabricLoader.getInstance().getModContainer("twob2tkit").map(m->m.getMetadata().getVersion().getFriendlyString()).orElse("unknown"));j.addProperty("bridge_version",4);j.addProperty("runtime_reload_protocol",1);j.addProperty("runtime_host_api",3);j.addProperty("runtime_generation",KitClient.borer().runtimeGeneration());j.addProperty("runtime_version",KitClient.borer().runtimeVersion());j.addProperty("navigation_runtime_version",KitClient.borer().buildNavigation().version());j.addProperty("world_session",session(c));j.addProperty("control_revision",controlRevision);j.addProperty("manual_movement",KitKeys.manualMovementDown(c));j.addProperty("window_active",c.isWindowActive());j.addProperty("screen",c.screen==null?"":c.screen.getClass().getSimpleName());j.addProperty("connected",c.player!=null && c.level!=null);
        var gravelState=GravelCollector.snapshot();
        if(nativeMaterialOwner!=null&&GravelCollector.isActive())gravelState.addProperty("session",nativeMaterialOwner.job);
        j.add("gravel",gravelState);
        j.addProperty("rock_quarry_protocol",1);
        j.addProperty("air_only_navigation_protocol",2);
        if(materialAirNavigation!=null)j.add("material_air_navigation",materialAirNavigation.snapshot(c));
        else if(lastMaterialAirNavigation!=null&&str(lastMaterialAirNavigation,"world_session").equals(session(c)))
            j.add("material_air_navigation",lastMaterialAirNavigation.deepCopy());
        j.addProperty("material_job_control_protocol",1);
        j.addProperty("material_task_api_protocol",dev.twob2tkit.material.MaterialTaskProtocol.VERSION);j.add("material_task",dev.twob2tkit.material.MaterialJobs.snapshot());
        j.addProperty("projection_load_protocol",1);
        j.addProperty("projection_batch_protocol",ProjectionBatchScope.PROTOCOL);j.addProperty("projection_model_protocol",1);j.addProperty("dry_paving_protocol",2);j.addProperty("terrain_replace_protocol",1);j.add("projection_batch",projectionBatchSnapshot());
        if(rockQuarryProgress!=null&&str(rockQuarryProgress,"world_session").equals(session(c)))
            j.add("rock_quarry",rockQuarryProgress.deepCopy());
        if(pendingScan!=null){
            var progress=new JsonObject();progress.addProperty("id",str(pendingScan.request,"id"));
            progress.addProperty("world_session",pendingScan.world);progress.addProperty("control_revision",pendingScan.revision);
            progress.addProperty("cells_read",pendingScan.cursor.read());progress.addProperty("total_cells",pendingScan.cursor.total());
            progress.addProperty("started_at",pendingScan.startedAt);progress.addProperty("elapsed_ticks",ticks-pendingScan.startedTick);
            progress.addProperty("reading_complete",pendingScan.terminal!=null);
            progress.addProperty("reply_write_state",pendingScan.replyWrite==null?"not_submitted":pendingScan.replyWrite.state.name().toLowerCase(Locale.ROOT));j.add("pending_scan",progress);
        }
        if(c.player==null || c.level==null)return j;
        j.addProperty("player_name",c.player.getGameProfile().name());j.addProperty("player_uuid",c.player.getUUID().toString());j.addProperty("experience_level",c.player.experienceLevel);
        c.player.getLastDeathLocation().ifPresent(death->{var marker=new JsonObject();marker.addProperty("dimension",death.dimension().identifier().toString());marker.add("pos",JSON.toJsonTree(new int[]{death.pos().getX(),death.pos().getY(),death.pos().getZ()}));j.add("server_last_death",marker);});
        j.addProperty("attack_strength",c.player.getAttackStrengthScale(0));
        j.addProperty("recent_hurt_at",KitClient.config().lastAttackTimeEpochMillis);j.addProperty("recent_attacker",KitClient.config().lastAttacker);

        j.addProperty("world_id",c.getSingleplayerServer()==null?"":c.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize().toString());
        j.addProperty("game_mode",c.gameMode.getPlayerMode().getName());j.addProperty("world_name",c.getSingleplayerServer()==null?"":c.getSingleplayerServer().getWorldData().getLevelName());
        j.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);j.addProperty("dimension",c.level.dimension().identifier().toString());
        j.add("pos",JSON.toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));j.addProperty("yaw",c.player.getYRot());j.addProperty("pitch",c.player.getXRot());j.addProperty("health",c.player.getHealth());j.addProperty("food",c.player.getFoodData().getFoodLevel());
        j.addProperty("air_supply",c.player.getAirSupply());j.addProperty("max_air_supply",c.player.getMaxAirSupply());j.addProperty("under_water",c.player.isUnderWater());
        double oxygenBonus=c.player.getAttributeValue(net.minecraft.world.entity.ai.attributes.Attributes.OXYGEN_BONUS);
        j.addProperty("oxygen_bonus",oxygenBonus);
        j.addProperty("air_expected_seconds",EquipmentAirBudget.expectedSeconds(c.player.getAirSupply(),oxygenBonus));
        var airBudget=airEstimate(c);
        j.addProperty("air_return_floor",airBudget.returnFloor());
        j.addProperty("air_pickup_floor",airBudget.pickupFloor());
        j.addProperty("air_work_floor",airBudget.workFloor());
        j.addProperty("air_return_y",materialAirRoute.owned(session(c),supervisionLease==null?"":str(supervisionLease,"job_session"),airGear(c),c)?materialAirRoute.returnY():c.level.getSeaLevel()+2);
        j.addProperty("air_budget_source",airBudget.source());
        j.addProperty("air_budget_samples",airBudget.samples());
        j.addProperty("air_budget_valid_until",airBudget.source().equals("observed")
            ?materialAirRoute.budgetValidUntil(session(c),supervisionLease==null?"":str(supervisionLease,"job_session"),airGear(c)):0);
        j.addProperty("air_estimated_loss",airBudget.estimatedLoss());
        j.addProperty("air_return_active",nativeAirReturnActive);
        j.addProperty("air_return_phase",nativeAirReturnPhase);
        j.addProperty("air_return_job_session",nativeAirReturnActive&&supervisionLease!=null?str(supervisionLease,"job_session"):"");
        j.addProperty("air_return_revision",nativeAirReturnActive?controlRevision:-1);
        j.addProperty("no_fall_active",dev.twob2tkit.runtime.engine.BorerFlight.meteorNoFallActive());
        j.addProperty("water_breathing_effect",c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING));j.addProperty("conduit_power_effect",c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER));
        j.addProperty("on_ground",c.player.onGround());j.addProperty("horizontal_collision",c.player.horizontalCollision);j.add("velocity",JSON.toJsonTree(new double[]{c.player.getDeltaMovement().x,c.player.getDeltaMovement().y,c.player.getDeltaMovement().z}));
        j.addProperty("world_generator",c.getSingleplayerServer()==null?"":c.getSingleplayerServer().overworld().getChunkSource().getGenerator().getClass().getSimpleName());j.addProperty("day_time",c.level.getOverworldClockTime());j.addProperty("difficulty",c.level.getDifficulty().getSerializedName());
        if(craftTask!=null)j.add("native_skill",craftTask.progress());
        if(supplyTask!=null)j.add("build_supply",supplyTask.snapshot());
        j.add("supply_candidates",BuildSupplyTask.candidates(c));
        if(op.equals("walk_path") && active!=null){j.addProperty("path_index",pathIndex);j.addProperty("path_size",active.getAsJsonArray("path").size());}
        j.addProperty("selected_slot",c.player.getInventory().getSelectedSlot());JsonObject keys=new JsonObject();keys.addProperty("forward",c.options.keyUp.isDown());keys.addProperty("back",c.options.keyDown.isDown());keys.addProperty("jump",c.options.keyJump.isDown());keys.addProperty("sneak",c.options.keyShift.isDown());j.add("movement_keys",keys);
        j.addProperty("grass_block_tool_protocol",1);
        j.addProperty("snow_harvest_protocol",1);
        var menu=c.player.containerMenu;stackSnapshots.begin(session(c),menu,menu.containerId,menu.getCarried());
        j.add("hand",snapshotStack("hand",c.player.getMainHandItem()));JsonArray inventory=new JsonArray();
        for(int i=0;i<c.player.getInventory().getContainerSize();i++){JsonObject s=snapshotStack("inventory:"+i,c.player.getInventory().getItem(i));s.addProperty("slot",i);inventory.add(s);}j.add("inventory",inventory);
        JsonObject equipment=new JsonObject();equipment.add("head",snapshotStack("equipment:head",c.player.getItemBySlot(EquipmentSlot.HEAD)));equipment.add("chest",snapshotStack("equipment:chest",c.player.getItemBySlot(EquipmentSlot.CHEST)));equipment.add("legs",snapshotStack("equipment:legs",c.player.getItemBySlot(EquipmentSlot.LEGS)));equipment.add("feet",snapshotStack("equipment:feet",c.player.getItemBySlot(EquipmentSlot.FEET)));j.add("equipment",equipment);
        JsonObject m=new JsonObject();m.addProperty("id",menu.containerId);m.addProperty("type",menu.getClass().getSimpleName());m.add("cursor",snapshotStack("cursor",menu.getCarried()));JsonArray slots=new JsonArray();
        for(int i=0;i<menu.slots.size();i++){JsonObject s=snapshotStack("menu:"+i,menu.getSlot(i).getItem());s.addProperty("slot",i);slots.add(s);}m.add("slots",slots);
        if(menu instanceof net.minecraft.world.inventory.AnvilMenu anvil){
            m.addProperty("anvil_cost",anvil.getCost());
            m.addProperty("anvil_result_present",anvil.getSlot(net.minecraft.world.inventory.AnvilMenu.RESULT_SLOT).hasItem());
            m.addProperty("anvil_result_may_pickup",anvil.getSlot(net.minecraft.world.inventory.AnvilMenu.RESULT_SLOT).mayPickup(c.player));
            m.addProperty("anvil_too_expensive",anvil.getCost()>=40&&!c.player.hasInfiniteMaterials());
        }
        j.add("menu",m);j.addProperty("map_audit_protocol",1);j.addProperty("map_create_protocol",1);
        j.addProperty("projection_air_seed_protocol",1);j.addProperty("air_place",MeteorModules.isActive(MeteorModules.AIR_PLACE));
        j.addProperty("projection_scaffold_fill_protocol",1);
        j.addProperty("bucket_water_protocol",1);
        j.addProperty("material_slaughter_protocol",SlaughterPolicy.PROTOCOL);
        if(lastSlaughterAttack!=null&&session(c).equals(str(lastSlaughterAttack,"world_session")))
            j.add("last_slaughter_attack",lastSlaughterAttack.deepCopy());
        if(bucketWaterTask!=null)j.add("bucket_water",bucketWaterTask.snapshot(false));
        if(lastBucketWater!=null)j.add("last_bucket_water",lastBucketWater.deepCopy());
        if(mapCreationTask!=null)j.add("map_creation",mapCreationTask.snapshot(false));
        if(lastMapCreation!=null)j.add("last_map_creation",lastMapCreation.deepCopy());
        if(airSeedTask!=null)j.add("projection_air_seed",airSeedTask.snapshot(false));
        if(lastAirSeed!=null)j.add("last_projection_air_seed",lastAirSeed.deepCopy());
        if(scaffoldFillTask!=null)j.add("projection_scaffold_fill",scaffoldFillTask.snapshot());
        if(lastScaffoldFill!=null)j.add("last_projection_scaffold_fill",lastScaffoldFill.deepCopy());
        try{var selected=dev.twob2tkit.builder.LitematicaAccess.buildSelection();var pick=new JsonObject();pick.addProperty("key",selected.key());pick.addProperty("name",selected.name());pick.add("min",JSON.toJsonTree(new int[]{selected.min().getX(),selected.min().getY(),selected.min().getZ()}));pick.add("max",JSON.toJsonTree(new int[]{selected.max().getX(),selected.max().getY(),selected.max().getZ()}));j.add("projection_selection",pick);}catch(Exception ignored){}
        j.addProperty("borer_status",KitClient.borer().status());
        j.addProperty("planter_status",KitClient.planter().status());j.addProperty("planter_count",KitClient.planter().plantedCount());j.addProperty("harvest_count",KitClient.planter().harvestedCount());
        j.addProperty("feeder_status",KitClient.feeder().status());j.addProperty("feeder_count",KitClient.feeder().fedCount());
        j.addProperty("borer_control_session",ownedBorerSession);j.addProperty("guard_reconnect_pending",pendingGuardReconnect!=null);j.addProperty("borer_active",KitClient.borer().isActive());j.addProperty("planter_active",KitClient.planter().isActive());j.addProperty("feeder_active",KitClient.feeder().isActive());j.addProperty("fisher_active",KitClient.fisher()!=null&&KitClient.fisher().isActive());j.addProperty("fisher_status",KitClient.fisher()==null?"":KitClient.fisher().status());j.add("build_job",KitClient.buildJob().snapshot());j.add("concrete",KitClient.concrete().snapshot());j.addProperty("guard_busy",guardBusy);j.addProperty("guard_armed",guardScope!=null);j.addProperty("guard_pve_only",guardScope!=null && guardScope.has("pve_only") && guardScope.get("pve_only").getAsBoolean());j.addProperty("health_recovery_hold",healthRecoveryHold);j.add("guard_food",dev.twob2tkit.combat.GuardFoodLease.snapshot());j.addProperty("guard_status",healthRecoveryHold?"等待生命恢复到 19 后继续工作":KitClient.borer().status());j.add("professional_printer",ProfessionalPrinter.status());j.addProperty("chopping",KitClient.chopper().isActive());j.addProperty("chopper_status",KitClient.chopper().status());j.addProperty("chopper_remaining",KitClient.chopper().remainingLogs());j.addProperty("chopper_verified_trees",KitClient.chopper().treesDone());j.addProperty("chopper_platforms",KitClient.chopper().platforms());j.addProperty("guide_active",KitClient.structureGuide().isActive());j.addProperty("guide_status",KitClient.structureGuide().status());j.addProperty("navigating",KitClient.controller().isActive());j.addProperty("printing",KitClient.machines().isPlacing());j.addProperty("printer_status",KitClient.machines().status());
        JsonArray nearby=new JsonArray();for(var e:c.level.getEntities(c.player,c.player.getBoundingBox().inflate(16))){
            if(e.distanceToSqr(c.player)>256)continue;
            JsonObject v=new JsonObject();v.addProperty("id",e.getId());v.addProperty("uuid",e.getUUID().toString());v.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());v.addProperty("name",e.getName().getString());v.addProperty("hostile",e instanceof net.minecraft.world.entity.monster.Enemy);v.addProperty("visible",c.player.hasLineOfSight(e));if(e instanceof net.minecraft.world.entity.LivingEntity living){v.addProperty("health",living.getHealth());v.addProperty("has_custom_name",living.hasCustomName());v.addProperty("is_baby",living.isBaby());}if(e instanceof net.minecraft.world.entity.item.ItemEntity drop)v.add("stack",stack(drop.getItem()));v.add("pos",JSON.toJsonTree(new double[]{e.getX(),e.getY(),e.getZ()}));nearby.add(v);
        }j.add("entities",nearby);
        j.addProperty("kill_aura",MeteorModules.isActive(MeteorModules.KILL_AURA));j.addProperty("auto_log",MeteorModules.isActive(MeteorModules.AUTO_LOG));j.addProperty("flight",MeteorModules.isActive(MeteorModules.FLIGHT));return j;
    }
    private static JsonObject snapshotStack(String key,ItemStack item){return stackSnapshots.cached(key,item,AutomationBridge::stack);}
    private static long nextSnapshotSlowWarningAt,nextSnapshotFailureWarningAt,observedStatusWriterFailures;
    private static void writeStatus(Minecraft c){
        if(nativeMaterialDispatch)return; // Internal child IDs never replace the consumed external request cursor.
        long began=System.nanoTime();
        try{
            JsonObject j=snapshot(c);j.addProperty("id",statusId);j.addProperty("last_request",lastId);
            j.addProperty("phase",phase);j.addProperty("op",op);j.addProperty("detail",detail);
            dev.twob2tkit.hud.WorkHud.update(j,root(c));statusWriter.submit(root(c).resolve("status.json"),j,session(c),controlRevision);
            long failures=statusWriter.failureCount();
            if(failures>observedStatusWriterFailures&&System.currentTimeMillis()>=nextSnapshotFailureWarningAt){
                observedStatusWriterFailures=failures;nextSnapshotFailureWarningAt=System.currentTimeMillis()+10_000;
                KitClient.LOGGER.warn("[Automation] async status IO failed type={} failures={}",statusWriter.lastFailureType(),failures);
            }
            long elapsed=(System.nanoTime()-began)/1_000_000;
            if(elapsed>=250 && System.currentTimeMillis()>=nextSnapshotSlowWarningAt){
                nextSnapshotSlowWarningAt=System.currentTimeMillis()+10_000;
                KitClient.LOGGER.warn("[Automation] slow status snapshot duration_ms={} op={}",elapsed,op);
            }
        }catch(Exception error){
            if(System.currentTimeMillis()>=nextSnapshotFailureWarningAt){
                nextSnapshotFailureWarningAt=System.currentTimeMillis()+10_000;
                // The type and first source frame explain silent stale-state failures without dumping state or credentials.
                var frames=error.getStackTrace();
                KitClient.LOGGER.warn("[Automation] status snapshot failed type={} at={} op={}",
                    error.getClass().getSimpleName(),frames.length==0?"unknown":frames[0],op);
            }
        }
    }
    private static void save(Path file,JsonObject j)throws Exception{Files.createDirectories(file.getParent());Path tmp=file.resolveSibling(file.getFileName()+".tmp");Files.writeString(tmp,JSON.toJson(j));try{Files.move(tmp,file,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}catch(AtomicMoveNotSupportedException e){Files.move(tmp,file,StandardCopyOption.REPLACE_EXISTING);}}
    private static String str(JsonObject j,String k){return j.has(k)?j.get(k).getAsString():"";}
    private static String safeId(String s){if(!s.matches("[A-Za-z0-9_-]{1,80}"))throw new IllegalArgumentException("Invalid job ID");return s;}
}
