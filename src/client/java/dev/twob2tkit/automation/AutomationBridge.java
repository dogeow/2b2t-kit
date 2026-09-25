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
        pendingGuardReconnect=disconnectGuardCandidate;
        disconnectGuardCandidate=null;
    }
    public static void userTaskStarting(Minecraft c){
        if(!dispatching&&supervisionLease!=null&&Set.of("materials","parking").contains(str(supervisionLease,"kind"))){supervisionLease=null;cancelWork(c,"用户切换自动任务");}
    }
    private static boolean highGuardPark(Minecraft c,JsonObject lease){
        if(c.player==null||c.level==null||!lease.has("park_target"))return false;
        JsonArray target=lease.getAsJsonArray("park_target");if(target==null||target.size()!=3)return false;
        double x=target.get(0).getAsDouble(),y=target.get(1).getAsDouble(),z=target.get(2).getAsDouble();
        if(!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z))return false;
        BlockPos at=BlockPos.containing(x,y,z);if(!c.level.hasChunkAt(at))return false;
        int ground=c.level.getHeight(net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING,at.getX(),at.getZ());
        return GuardParkingPolicy.ready(c.player.getX(),c.player.getY(),c.player.getZ(),x,y,z,ground,
            c.player.getHealth(),MeteorModules.isActive(MeteorModules.FLIGHT),guardScope!=null);
    }
    private static void tickSupervision(Minecraft c) {
        confirmSafety(c);
        if(supervisionLease==null || c.player==null || c.level==null)return;
        var lease=supervisionLease;long now=System.currentTimeMillis();
        try{
            if(str(lease,"kind").equals("parking")&&c.screen!=null){
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
            boolean controllerFinished=false;
            Path file=root(c).resolve("supervision-heartbeat-"+safeId(str(lease,"id"))+".json");
            if(Files.isRegularFile(file) && Files.size(file)<4096){var beat=JsonParser.parseString(Files.readString(file)).getAsJsonObject();long t=beat.get("time").getAsLong();
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
            if(action==dev.twob2tkit.builder.BuildSupervisorSafety.Action.LOGOUT&&!lowHealth&&!quiet){
                if(!str(lease,"kind").equals("parking")){
                    KitClient.stopWork("托管收尾，等待脱离战斗");armPveGuard(c);
                    lease.addProperty("kind","parking");lease.addProperty("revision",controlRevision);
                    if(c.player!=null)c.player.sendSystemMessage(net.minecraft.network.chat.Component.literal("[托管] 工作已停止，防护继续；连续 60 秒无近敌或新受伤后再离线。"));
                }
                phase="parking";detail="等待战斗结束与安静窗口，防护仍开启";return;
            }
            if(action==dev.twob2tkit.builder.BuildSupervisorSafety.Action.NONE)return;
            supervisionLease=null;
            if(action==dev.twob2tkit.builder.BuildSupervisorSafety.Action.REVOKE)return;
            var receipt=new JsonObject();receipt.addProperty("lease",str(lease,"id"));receipt.addProperty("job_session",str(lease,"job_session"));receipt.addProperty("cause",lowHealth?"low_health":complete?"complete":controllerFinished?"controller_finished":"heartbeat_lost");receipt.addProperty("action",action.name());receipt.addProperty("time",now);receipt.add("snapshot",snapshot(c));
            receipt.addProperty("confirmed",false);receipt.addProperty("server_survival_verified",false);safetyReceipt(c,receipt);
            switch(action){
                case PAUSE_LOCAL -> {KitClient.emergencyStop("托管安全暂停："+(lowHealth?"血量不足":complete?"任务完成":controllerFinished?"托管已结束":"控制器失联"));c.pauseGame(false);if(!(c.screen instanceof net.minecraft.client.gui.screens.PauseScreen))c.setScreen(new net.minecraft.client.gui.screens.PauseScreen(true));}
                case LOGOUT -> {suspendAutoReconnect();KitClient.safeLogout(c,"托管收尾退出："+(lowHealth?"血量不足":complete?"任务完成":controllerFinished?"托管已结束":"控制器失联"));}
                case KEEP_PVE_GUARD -> {KitClient.stopWork("托管结束，保留 PvE 防护");armPveGuard(c);}
                default -> {}
            }
            if(action!=dev.twob2tkit.builder.BuildSupervisorSafety.Action.KEEP_PVE_GUARD){pendingSafety=receipt;pendingSafetyTick=ticks;pendingPauseSince=0;}
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
    private static boolean ownedUnderwaterAirReturn(Minecraft c){
        if(c.player==null||c.level==null
                ||!(c.player.isUnderWater()||c.player.getY()<c.level.getSeaLevel()+25)
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
        boolean enabled=guardScope!=null;
        if(enabled&&c.player!=null){lastGuardHealth=c.player.getHealth();lastGuardX=c.player.getX();lastGuardZ=c.player.getZ();}
        if(enabled)try{guard(c,guardScope);}catch(Exception changed){guardScope=null;enabled=false;dev.twob2tkit.combat.GuardFoodLease.release();}
        if(enabled&&ownedUnderwaterAirReturn(c)){
            // Reaching air and the nearby high park outranks ranged combat.
            // Keep guard armed; PvE defense resumes when the owned rise ends.
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
        if(guardBusy){ProfessionalPrinter.pause();if(active!=null)deadline++;mineStarted=false;}
        return guardBusy;
    }
    private static double savedArrival=Double.NaN, temporaryArrival;
    private static boolean restoreFlight;
    private static boolean mineStarted;
    private static boolean guiRequested, initialized, dispatching;
    private static Path root(Minecraft c){return c.gameDirectory.toPath().resolve("config/twob2tkit/automation");}
    public static void requestGui(){guiRequested=true;}
    public static boolean ownsMining(){return active!=null && op.equals("mine_block");}
    public static void cancel(Minecraft c,String reason){
        pendingGuardReconnect=null;
        ownedBorerSession="";
        ProfessionalPrinter.stop(c,true);
        supervisionLease=null;pendingSafety=null;survivalArmed=false;disarmGuard(c);
        cancelWork(c,reason);
    }
    private static void abortOwnedRequest(Minecraft c,String reason){
        if(supervisionLease!=null && active!=null && (str(active,"job_session").equals(str(supervisionLease,"job_session"))||str(active,"task_session").equals(str(supervisionLease,"job_session")))){KitClient.stopWork(reason);if(supervisionLease!=null&&str(supervisionLease,"kind").equals("materials"))supervisionLease.addProperty("revision",controlRevision);}
        else KitClient.emergencyStop(reason);
    }
    public static void cancelWork(Minecraft c,String reason){
        survivalArmed=false;craftTask=null;if(supplyTask!=null){supplyTask.close(c);supplyTask=null;}controlRevision++;ProfessionalPrinter.stop(c,false);restoreArrival();releaseWalk(c);
        active=null;phase="stopped";detail=reason;if(!dispatching)writeStatus(c);
    }
    /** Short-range walking owns input before Minecraft samples keys; it does not use cruise fly-over routing. */
    public static boolean reapplySupplyLook(Minecraft c){if(active==null || !Set.of("build_supply","collect_supply","approach_block","collect_item","concrete_batch").contains(op) || supplyTask==null)return false;supplyTask.reapply(c);return true;}
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
    public static boolean beforeInput(Minecraft c){
        if(active!=null)ownsMaterialMenu(c); // Capture our CraftingMenu even though it is an allowed survival screen.
        if(active!=null && (active.has("job_session")||active.has("task_session")) && c.player!=null && (KitKeys.manualMovementDown(c) || !background(active) && !c.isWindowActive() || !survivalMenu(c) && !ownsMaterialMenu(c) && !(supplyTask!=null && Set.of("build_supply","collect_supply","approach_block","collect_item","concrete_batch").contains(op) && supplyTask.ownsMenu(c)))){KitClient.emergencyStop("托管技能交还控制");return true;}
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
            if(!WaterDescentPolicy.continueDescent(c.player.isUnderWater(),c.player.getHealth(),c.player.getAirSupply())){
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
            if(active.has("underwater_gravel")&&active.get("underwater_gravel").getAsBoolean()){
                boolean breathing=c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING)
                    ||c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER);
                if(!UnderwaterGravelPolicy.continueMining(c.player.isUnderWater(),c.player.getHealth(),
                        c.player.getAirSupply(),breathing)){
                    finish(c,"waiting","Underwater oxygen or health changed; surface before mining more");return true;
                }
            }
            JsonArray a=active.getAsJsonArray("pos");BlockPos target=new BlockPos(a.get(0).getAsInt(),a.get(1).getAsInt(),a.get(2).getAsInt());
            if(c.level.isEmptyBlock(target)){finish(c,"done","target removed");return true;}
            if(!state(c,target).equals(str(active,"expected_state"))){finish(c,"error","mining target changed");return true;}
            Vec3 aim=blockAim(target,active);if(c.player.getEyePosition().distanceTo(aim)>c.player.blockInteractionRange()-.2){finish(c,"waiting","mining target moved out of reach");return true;}RotationAim.Look look=RotationAim.lookAt(c.player,aim);RotationAim.apply(c.player,look);
            BlockHitResult hit=c.level.clip(new ClipContext(c.player.getEyePosition(),aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
            if(!hit.getBlockPos().equals(target)){finish(c,"waiting","mining target is occluded");return true;}
            c.options.keyUp.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);c.options.keyAttack.setDown(false);c.hitResult=hit;
            if(!mineStarted){c.gameMode.startDestroyBlock(target,hit.getDirection());mineStarted=true;}
            else c.gameMode.continueDestroyBlock(target,hit.getDirection());
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
        if(!initialized){initialized=true;try{Path old=root(c).resolve("request.json");if(Files.isRegularFile(old))lastId=str(JsonParser.parseString(Files.readString(old)).getAsJsonObject(),"id");}catch(Exception ignored){}}
        if(guiRequested){guiRequested=false;if(c.player!=null)KitClient.openGui(c);}
        ticks++;
        restoreGuardAfterReconnect(c);
        if(!ownedBorerSession.isEmpty() && (KitClient.borer()==null || !KitClient.borer().isActive()))ownedBorerSession="";
        if(ticks%5==0){
            Path f=root(c).resolve("request.json");
            try{
                if(Files.isRegularFile(f) && Files.size(f)<=16384){
                    JsonObject r=JsonParser.parseString(Files.readString(f)).getAsJsonObject();String id=str(r,"id");
                    if(!id.isBlank() && !id.equals(lastId)){
                        lastId=id;
                        try {
                            if(active!=null && !str(r,"op").equals("stop") && !Set.of("snapshot","scan","scan_trees","projection_audit").contains(str(r,"op")))throw new IllegalStateException("A job is active; stop it first");
                            dispatching=true;
                            try{dispatch(c,r);if(supervisionLease!=null&&str(supervisionLease,"kind").equals("materials")&&str(r,"task_session").equals(str(supervisionLease,"job_session")))supervisionLease.addProperty("revision",controlRevision);}finally{dispatching=false;}
                        } catch(Exception e) {
                            if(active!=null && str(active,"id").equals(id)){abortOwnedRequest(c,"脚本参数无效");active=null;}
                            JsonObject error=snapshot(c);error.addProperty("id",id);error.addProperty("phase","error");error.addProperty("detail",e.getMessage());save(root(c).resolve("reply-"+safeId(id)+".json"),error);
                            if(active==null){statusId=id;phase="error";detail=e.getMessage();writeStatus(c);}
                        }
                    }
                }
            }catch(Exception e){phase="error";detail=e.getClass().getSimpleName()+": "+e.getMessage();writeStatus(c);}
        }
        if(active!=null){
            try{
                guard(c,active);
                if(Set.of("build_supply","collect_supply","approach_block","collect_item").contains(op)){
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
                    else if(ticks>=deadline)finish(c,"done","printer interval ended; verify actual block states");
                }else if(op.equals("use_item")){
                    if(c.player.getHealth()<14 || hostileNearby(c))finish(c,"waiting","food interrupted by health or nearby enemy");
                    else if(count(c,str(active,"item"))<useCount)finish(c,"done","item consumed; verify food and inventory");
                    else c.options.keyUse.setDown(true);
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
                    JsonArray p=active.getAsJsonArray("pos");BlockPos target=new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt());if(c.level.isEmptyBlock(target))finish(c,"done","target removed");
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
                }else if(op.equals("navigate") && !KitClient.controller().isActive()){
                    JsonArray p=active.getAsJsonArray("target");double dx=c.player.getX()-p.get(0).getAsDouble(),dz=c.player.getZ()-p.get(2).getAsDouble();
                    finish(c,Math.hypot(dx,dz)<=KitClient.config().arrivalRadius+1 && Math.abs(c.player.getY()-p.get(1).getAsDouble())<=1?"done":"stopped","navigation ended");
                }else if(op.equals("print") && !KitClient.machines().isPlacing())finish(c,"stopped","printer stopped");
                else if(op.equals("settle") && ticks>=deadline)finish(c,"done","server state available");
                if(active!=null && ticks>=deadline && !op.equals("settle")){
                    abortOwnedRequest(c,"脚本任务达到时间上限");finish(c,"waiting","time limit reached; inspect progress before resuming");
                }
            }catch(Exception e){abortOwnedRequest(c,"脚本世界或人物状态已变化");finish(c,"stopped",e.getMessage());}
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
        JsonArray site=r.getAsJsonArray("site");
        if(site==null || site.size()!=3)throw new IllegalArgumentException("Site is required");
        double dx=c.player.getX()-site.get(0).getAsDouble(),dz=c.player.getZ()-site.get(2).getAsDouble();
        if(!AutomationScope.nearSite(dx,dz))throw new IllegalStateException("Outside authorized worksite; lobby actions refused");
    }
    private static void dispatch(Minecraft c,JsonObject r)throws Exception{
        String command=str(r,"op");
        if(command.equals("stop")){if(r.has("expected_revision") && (r.get("expected_revision").getAsLong()!=controlRevision || !str(r,"world_session").equals(session(c))))throw new IllegalStateException("Stop belongs to an old controller");statusId=lastId;ProfessionalPrinter.stop(c,true);KitClient.emergencyStop("本地脚本停止");active=null;phase="stopped";detail="stopped";writeStatus(c);return;}
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
        if(Set.of("snapshot","scan","scan_trees","projection_audit").contains(command)){
            if(survival(r)){survivalArmed=true;survivalBackground=background(r);}
            JsonObject out=snapshot(c);out.addProperty("id",lastId);
            if(command.equals("scan"))out.add("blocks",scan(c,r));
            if(command.equals("scan_trees"))out.add("tree_survey",TreeSurvey.scan(c,r));
            if(command.equals("projection_audit"))out.add("projection_audit",ProjectionAudit.scan(c));
            save(root(c).resolve("reply-"+safeId(lastId)+".json"),out);writeStatus(c);return;
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
        if(guardBusy && !command.equals("guard") && !command.equals("use_item") && !defensiveRise)throw new IllegalStateException("Construction guard is defending or eating; wait before changing items or starting work");
        statusId=lastId;
        if(command.equals("material_session")){
            long expiry=r.has("expires_at")?r.get("expires_at").getAsLong()-System.currentTimeMillis():-1;
            boolean resumePark=supervisionLease!=null&&str(supervisionLease,"kind").equals("parking")&&str(r,"replace_parking_lease").equals(str(supervisionLease,"id"));
            if(expiry<0||expiry>15000||!r.has("expected_revision")||r.get("expected_revision").getAsLong()!=controlRevision||!str(r,"world_session").equals(session(c))||supervisionLease!=null&&!resumePark||KitClient.anyAfkAuto()||c.screen!=null||KitKeys.manualMovementDown(c)||c.player.getHealth()<14)throw new IllegalStateException("Material session cannot acquire control");
            boolean guardFinish=str(r,"remote_finish").equals("guard");
            if(guardFinish){JsonArray park=r.getAsJsonArray("park_target");if(park==null||park.size()!=3)throw new IllegalArgumentException("High guard finish requires a park target");for(var value:park)if(!Double.isFinite(value.getAsDouble()))throw new IllegalArgumentException("Invalid park target");}
            CraftingCompatibility.requireReady();
            ProfessionalPrinter.stop(c,true); // Inventory/crafting ownership excludes an externally enabled printer.
            if(resumePark)supervisionLease=null;
            String leaseId=safeId(str(r,"supervision_lease")),taskId=safeId(str(r,"task_session"));supervisionLease=new JsonObject();supervisionLease.addProperty("id",leaseId);supervisionLease.addProperty("world_session",session(c));supervisionLease.addProperty("job_session",taskId);supervisionLease.addProperty("kind","materials");supervisionLease.addProperty("revision",controlRevision);supervisionLease.addProperty("remote_finish",guardFinish?"guard":"disconnect");if(guardFinish)supervisionLease.add("park_target",r.getAsJsonArray("park_target").deepCopy());lastSupervisionHeartbeat=System.currentTimeMillis();logoutQuiet.reset(lastSupervisionHeartbeat);armPveGuard(c);phase="done";detail="material session protected";
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
            KitClient.stopWork("使用投影打印机");
            if(c.player.getHealth()<14 || !MeteorModules.isActive(MeteorModules.KILL_AURA) || !MeteorModules.isActive(MeteorModules.AUTO_LOG))throw new IllegalStateException("Health or defense requires attention");
            ProfessionalPrinter.start(!r.has("conservative") || !r.get("conservative").getAsBoolean());active=r.deepCopy();op=command;phase="running";detail="Litematica Printer owns placement";
            deadline=ticks+20*Math.max(1,Math.min(30,r.has("seconds")?r.get("seconds").getAsInt():10));
        }else if(command.equals("craft_recipe")){
            if(!survival(r))throw new IllegalArgumentException("Recipe macros currently require the local survival scope");
            craftSpec=r.deepCopy();craftRemaining=0;craftTask=new SurvivalCraftTask(c,r);active=r.deepCopy();op=command;phase="running";detail="native recipe workflow";deadline=ticks+1200;
        }else if(command.equals("navigate") || command.equals("walk") || command.equals("walk_path") || command.equals("chop") || command.equals("print")){
            ProfessionalPrinter.stop(c,true);KitClient.stopWork("切换到脚本任务");active=r.deepCopy();op=command;phase="running";detail="";
            deadline=ticks+20*Math.max(5,Math.min(600,r.has("seconds")?r.get("seconds").getAsInt():120));
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
                     d,c.player.getY()-p.get(1).getAsDouble()))
                    throw new IllegalStateException("Guarded water descent needs clear vertical pickup and full reserve");
                if(r.has("freefall_brake_y")){
                    double brakeY=r.get("freefall_brake_y").getAsDouble();
                    if(!r.has("task_session")||d>.5||!FreefallPolicy.eligible(c.player.getY(),brakeY,c.player.getHealth(),guardScope!=null,MeteorModules.isActive(MeteorModules.FLIGHT))
                        ||!freefallColumnClear(c,c.player.blockPosition(),(int)Math.floor(brakeY)-2,(int)Math.ceil(c.player.getY())+2))
                        throw new IllegalStateException("Guarded freefall requires a clear loaded column and active Flight");
                }
                restoreFlight=MeteorModules.isActive(MeteorModules.FLIGHT) && (!r.has("restore_flight") || r.get("restore_flight").getAsBoolean());MeteorModules.disable(MeteorModules.FLIGHT);
            }else if(command.equals("navigate")){
                JsonArray p=r.getAsJsonArray("target");checkSiteTarget(r,p);
                if(r.has("arrival")){savedArrival=KitClient.config().arrivalRadius;temporaryArrival=Math.max(1,Math.min(8,r.get("arrival").getAsDouble()));KitClient.config().arrivalRadius=temporaryArrival;}
                MeteorModules.enable(MeteorModules.FLIGHT);
                KitClient.controller().startExact(c,p.get(0).getAsDouble(),p.get(2).getAsDouble(),p.get(1).getAsDouble());
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
            String item=str(r,"item");int found=-1;for(int i=0;i<36;i++)if(itemId(c.player.getInventory().getItem(i)).equals(item)){found=i;break;}
            if(found<0)throw new IllegalStateException("Missing item: "+item);
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
                    c.gameMode.useItemOn(c.player,InteractionHand.MAIN_HAND,checkedHit);settle(r,8);
                }catch(Exception e){finish(c,"error",e.getMessage());}
            });
        }else if(command.equals("mine_block") || command.equals("recover_shulker")){
            JsonArray p=r.getAsJsonArray("pos");checkSiteTarget(r,p);BlockPos pos=new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt());
            if(!state(c,pos).equals(str(r,"expected_state")))throw new IllegalStateException("Mining target changed");
            boolean recovery=command.equals("recover_shulker");
            boolean underwater=r.has("underwater_gravel")&&r.get("underwater_gravel").getAsBoolean();
            if(underwater){
                if(supervisionLease==null||!str(supervisionLease,"kind").equals("materials")
                    ||!str(supervisionLease,"job_session").equals(str(r,"task_session")))
                    throw new IllegalStateException("Guarded material session required for underwater gravel");
                boolean lavaNear=false;
                for(Direction direction:Direction.values())if(c.level.getFluidState(pos.relative(direction)).is(net.minecraft.world.level.material.Fluids.LAVA))lavaNear=true;
                ItemStack held=c.player.getMainHandItem();
                boolean breathing=c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING)
                    ||c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER);
                String rejection=UnderwaterGravelPolicy.startRejection(
                    c.level.getBlockState(pos).is(net.minecraft.world.level.block.Blocks.GRAVEL),
                    c.level.getFluidState(pos.above()).is(net.minecraft.world.level.material.Fluids.WATER),
                    lavaNear,c.player.isUnderWater(),c.player.getHealth(),c.player.getAirSupply(),breathing,
                    held.is(net.minecraft.tags.ItemTags.SHOVELS),held.isDamageableItem()?held.getMaxDamage()-held.getDamageValue():0);
                if(rejection!=null)throw new IllegalStateException(rejection);
            }
            boolean allowed=ContainerRecoveryPolicy.allowed(BuiltInRegistries.BLOCK.getKey(c.level.getBlockState(pos).getBlock()).toString(),recovery,c.player.getInventory().getFreeSlot()>=0?1:0);
            if(recovery && !allowed)throw new IllegalStateException("Shulker retrieval requires an actual shulker box and a free inventory slot");
            if(c.level.getBlockEntity(pos)!=null && !allowed)throw new IllegalStateException("Block entities and containers are protected");
            if(c.level.getBlockState(pos).getDestroySpeed(c.level,pos)<0 || c.level.isEmptyBlock(pos))throw new IllegalStateException("Target is not mineable");
            if(c.player.onGround() && c.player.blockPosition().below().equals(pos))throw new IllegalStateException("Current footing is protected");
            if(!underwater)for(Direction d:Direction.values())if(!c.level.getFluidState(pos.relative(d)).isEmpty())throw new IllegalStateException("Fluid next to target is protected");
            if(c.player.getEyePosition().distanceTo(blockAim(pos,r))>c.player.blockInteractionRange()-.2)throw new IllegalStateException("Mining target out of reach");
            KitClient.stopWork("切换到指定方块修正");active=r.deepCopy();op="mine_block";phase="running";detail="mining the verified target";mineStarted=false;deadline=ticks+20*Math.min(20,r.has("seconds")?r.get("seconds").getAsInt():10);
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
        writeStatus(c);
    }
    private static void settle(JsonObject r,int wait){active=r.deepCopy();op="settle";phase="running";detail="awaiting server acknowledgement";deadline=ticks+wait;}
    private static void finish(Minecraft c,String p,String text){if(op.equals("concrete_batch")){if(KitClient.concrete().isActive())KitClient.concrete().stop(c,"批次结束");if(supplyTask!=null){supplyTask.close(c);supplyTask=null;}concretePreexistingDrops.clear();concreteRetryUuid=null;concreteRetryPos=null;}ProfessionalPrinter.stop(c,false);restoreArrival();releaseWalk(c);active=null;phase=p;detail=text;writeStatus(c);}
    private static void restoreArrival(){if(Double.isFinite(savedArrival)){if(KitClient.config().arrivalRadius==temporaryArrival){KitClient.config().arrivalRadius=savedArrival;KitClient.config().save();}savedArrival=Double.NaN;}}
    private static void checkSiteTarget(JsonObject r,JsonArray p){JsonArray s=r.getAsJsonArray("site");if(p==null || p.size()!=3 || !Double.isFinite(p.get(1).getAsDouble()) || !AutomationScope.nearSite(p.get(0).getAsDouble()-s.get(0).getAsDouble(),p.get(2).getAsDouble()-s.get(2).getAsDouble()))throw new IllegalArgumentException("Target outside worksite");}
    private static JsonArray scan(Minecraft c,JsonObject r){
        JsonArray a=r.getAsJsonArray("min"),b=r.getAsJsonArray("max");checkSiteTarget(r,a);checkSiteTarget(r,b);
        int x1=a.get(0).getAsInt(),y1=a.get(1).getAsInt(),z1=a.get(2).getAsInt(),x2=b.get(0).getAsInt(),y2=b.get(1).getAsInt(),z2=b.get(2).getAsInt();
        if(x2<x1 || y2<y1 || z2<z1 || (long)(x2-x1+1)*(y2-y1+1)*(z2-z1+1)>50000)throw new IllegalArgumentException("Invalid scan volume");
        JsonArray rows=new JsonArray();for(int x=x1;x<=x2;x++)for(int z=z1;z<=z2;z++)for(int y=y1;y<=y2;y++){
            BlockPos p=new BlockPos(x,y,z);if(!c.level.hasChunkAt(p))throw new IllegalStateException("Chunk is not loaded: "+p);
            if(c.level.isEmptyBlock(p))continue;JsonObject v=new JsonObject();v.add("pos",JSON.toJsonTree(new int[]{x,y,z}));v.addProperty("state",state(c,p));
            if(r.has("details") && r.get("details").getAsBoolean()){
                var bs=c.level.getBlockState(p);v.addProperty("solid",bs.isCollisionShapeFullBlock(c.level,p));v.addProperty("replaceable",bs.canBeReplaced());
                v.addProperty("passable",bs.getCollisionShape(c.level,p).isEmpty() && bs.getFluidState().isEmpty());
                v.addProperty("fluid",!bs.getFluidState().isEmpty());v.addProperty("block_entity",c.level.getBlockEntity(p)!=null);
            }rows.add(v);
        }return rows;
    }
    static Vec3 blockAim(BlockPos p,JsonObject request){
        if(!request.has("face"))return Vec3.atCenterOf(p);
        var face=Direction.valueOf(request.get("face").getAsString().toUpperCase(Locale.ROOT));
        return Vec3.atCenterOf(p).add(face.getStepX()*.499,face.getStepY()*.499,face.getStepZ()*.499);
    }
    private static String state(Minecraft c,BlockPos p){return c.level.getBlockState(p).toString();}
    private static boolean hostileNearby(Minecraft c){return c.level.getEntities(c.player,c.player.getBoundingBox().inflate(16)).stream().anyMatch(e->e instanceof net.minecraft.world.entity.monster.Enemy && e.isAlive() && c.player.hasLineOfSight(e));}
    private static String itemId(ItemStack s){return s.isEmpty()?"minecraft:air":BuiltInRegistries.ITEM.getKey(s.getItem()).toString();}
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
        var applied=item.getEnchantments();if(!applied.isEmpty())target.add("enchantments",enchantments(applied));
        var stored=item.get(net.minecraft.core.component.DataComponents.STORED_ENCHANTMENTS);
        if(stored!=null&&!stored.isEmpty())target.add("stored_enchantments",enchantments(stored));
        var potion=item.get(net.minecraft.core.component.DataComponents.POTION_CONTENTS);
        if(potion!=null)target.addProperty("water_breathing",
            potion.is(Potions.WATER_BREATHING)||potion.is(Potions.LONG_WATER_BREATHING));
    }
    private static JsonObject stack(ItemStack s){
        JsonObject j=new JsonObject();j.addProperty("item",itemId(s));j.addProperty("count",s.getCount());j.addProperty("max_stack",s.getMaxStackSize());if(s.isDamageableItem()){j.addProperty("durability",s.getMaxDamage()-s.getDamageValue());j.addProperty("max_durability",s.getMaxDamage());}
        addItemDetails(j,s);
        var contents=s.get(net.minecraft.core.component.DataComponents.CONTAINER);
        if(contents!=null){JsonArray rows=new JsonArray();contents.nonEmptyItemCopyStream().limit(27).forEach(item->{JsonObject v=new JsonObject();v.addProperty("item",itemId(item));v.addProperty("count",item.getCount());addItemDetails(v,item);rows.add(v);});j.add("contains",rows);}
        return j;
    }
    private static JsonObject snapshot(Minecraft c){
        JsonObject j=new JsonObject();j.addProperty("time",System.currentTimeMillis());
        if(supervisionLease!=null)j.add("supervision_lease",supervisionLease.deepCopy());if(lastSafetyEvent!=null)j.add("supervision_safety",lastSafetyEvent.deepCopy());
        j.add("safety_hold",dev.twob2tkit.combat.EmergencyExit.snapshot(c));
        j.addProperty("gui_width",c.getWindow().getGuiScaledWidth());j.addProperty("gui_height",c.getWindow().getGuiScaledHeight());j.addProperty("game_paused",c.isPaused());if(c.getSingleplayerServer()!=null)j.addProperty("server_game_time",c.getSingleplayerServer().overworld().getGameTime());j.addProperty("tree_survey_protocol",1);j.addProperty("material_protocol",2);j.add("inventory_isolation",CraftingCompatibility.snapshot());j.addProperty("supervision_protocol",1);j.addProperty("supply_protocol",1);j.addProperty("freefall_protocol",1);j.addProperty("kit_version",net.fabricmc.loader.api.FabricLoader.getInstance().getModContainer("twob2tkit").map(m->m.getMetadata().getVersion().getFriendlyString()).orElse("unknown"));j.addProperty("bridge_version",4);j.addProperty("runtime_reload_protocol",1);j.addProperty("runtime_host_api",3);j.addProperty("runtime_generation",KitClient.borer().runtimeGeneration());j.addProperty("runtime_version",KitClient.borer().runtimeVersion());j.addProperty("navigation_runtime_version",KitClient.borer().buildNavigation().version());j.addProperty("world_session",session(c));j.addProperty("control_revision",controlRevision);j.addProperty("manual_movement",KitKeys.manualMovementDown(c));j.addProperty("window_active",c.isWindowActive());j.addProperty("screen",c.screen==null?"":c.screen.getClass().getSimpleName());j.addProperty("connected",c.player!=null && c.level!=null);
        if(c.player==null || c.level==null)return j;
        j.addProperty("player_name",c.player.getGameProfile().name());j.addProperty("player_uuid",c.player.getUUID().toString());j.addProperty("experience_level",c.player.experienceLevel);
        c.player.getLastDeathLocation().ifPresent(death->{var marker=new JsonObject();marker.addProperty("dimension",death.dimension().identifier().toString());marker.add("pos",JSON.toJsonTree(new int[]{death.pos().getX(),death.pos().getY(),death.pos().getZ()}));j.add("server_last_death",marker);});
        j.addProperty("recent_hurt_at",KitClient.config().lastAttackTimeEpochMillis);j.addProperty("recent_attacker",KitClient.config().lastAttacker);

        j.addProperty("world_id",c.getSingleplayerServer()==null?"":c.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize().toString());
        j.addProperty("game_mode",c.gameMode.getPlayerMode().getName());j.addProperty("world_name",c.getSingleplayerServer()==null?"":c.getSingleplayerServer().getWorldData().getLevelName());
        j.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);j.addProperty("dimension",c.level.dimension().identifier().toString());
        j.add("pos",JSON.toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));j.addProperty("yaw",c.player.getYRot());j.addProperty("pitch",c.player.getXRot());j.addProperty("health",c.player.getHealth());j.addProperty("food",c.player.getFoodData().getFoodLevel());
        j.addProperty("air_supply",c.player.getAirSupply());j.addProperty("max_air_supply",c.player.getMaxAirSupply());j.addProperty("under_water",c.player.isUnderWater());
        j.addProperty("no_fall_active",dev.twob2tkit.runtime.engine.BorerFlight.meteorNoFallActive());
        j.addProperty("water_breathing_effect",c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING));j.addProperty("conduit_power_effect",c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER));
        j.addProperty("on_ground",c.player.onGround());j.addProperty("horizontal_collision",c.player.horizontalCollision);j.add("velocity",JSON.toJsonTree(new double[]{c.player.getDeltaMovement().x,c.player.getDeltaMovement().y,c.player.getDeltaMovement().z}));
        j.addProperty("world_generator",c.getSingleplayerServer()==null?"":c.getSingleplayerServer().overworld().getChunkSource().getGenerator().getClass().getSimpleName());j.addProperty("day_time",c.level.getOverworldClockTime());j.addProperty("difficulty",c.level.getDifficulty().getSerializedName());
        if(craftTask!=null)j.add("native_skill",craftTask.progress());
        if(supplyTask!=null)j.add("build_supply",supplyTask.snapshot());
        j.add("supply_candidates",BuildSupplyTask.candidates(c));
        if(op.equals("walk_path") && active!=null){j.addProperty("path_index",pathIndex);j.addProperty("path_size",active.getAsJsonArray("path").size());}
        j.addProperty("selected_slot",c.player.getInventory().getSelectedSlot());JsonObject keys=new JsonObject();keys.addProperty("forward",c.options.keyUp.isDown());keys.addProperty("back",c.options.keyDown.isDown());keys.addProperty("jump",c.options.keyJump.isDown());keys.addProperty("sneak",c.options.keyShift.isDown());j.add("movement_keys",keys);
        j.add("hand",stack(c.player.getMainHandItem()));JsonArray inventory=new JsonArray();
        for(int i=0;i<c.player.getInventory().getContainerSize();i++){JsonObject s=stack(c.player.getInventory().getItem(i));s.addProperty("slot",i);inventory.add(s);}j.add("inventory",inventory);
        JsonObject equipment=new JsonObject();equipment.add("head",stack(c.player.getItemBySlot(EquipmentSlot.HEAD)));equipment.add("chest",stack(c.player.getItemBySlot(EquipmentSlot.CHEST)));equipment.add("legs",stack(c.player.getItemBySlot(EquipmentSlot.LEGS)));equipment.add("feet",stack(c.player.getItemBySlot(EquipmentSlot.FEET)));j.add("equipment",equipment);
        var menu=c.player.containerMenu;JsonObject m=new JsonObject();m.addProperty("id",menu.containerId);m.addProperty("type",menu.getClass().getSimpleName());m.add("cursor",stack(menu.getCarried()));JsonArray slots=new JsonArray();
        for(int i=0;i<menu.slots.size();i++){JsonObject s=stack(menu.getSlot(i).getItem());s.addProperty("slot",i);slots.add(s);}m.add("slots",slots);j.add("menu",m);
        try{var selected=dev.twob2tkit.builder.LitematicaAccess.buildSelection();var pick=new JsonObject();pick.addProperty("key",selected.key());pick.addProperty("name",selected.name());pick.add("min",JSON.toJsonTree(new int[]{selected.min().getX(),selected.min().getY(),selected.min().getZ()}));pick.add("max",JSON.toJsonTree(new int[]{selected.max().getX(),selected.max().getY(),selected.max().getZ()}));j.add("projection_selection",pick);}catch(Exception ignored){}
        j.addProperty("borer_control_session",ownedBorerSession);j.addProperty("guard_reconnect_pending",pendingGuardReconnect!=null);j.addProperty("borer_active",KitClient.borer().isActive());j.addProperty("planter_active",KitClient.planter().isActive());j.addProperty("feeder_active",KitClient.feeder().isActive());j.addProperty("fisher_active",KitClient.fisher()!=null&&KitClient.fisher().isActive());j.addProperty("fisher_status",KitClient.fisher()==null?"":KitClient.fisher().status());j.add("build_job",KitClient.buildJob().snapshot());j.add("concrete",KitClient.concrete().snapshot());j.addProperty("guard_busy",guardBusy);j.addProperty("guard_armed",guardScope!=null);j.addProperty("guard_pve_only",guardScope!=null && guardScope.has("pve_only") && guardScope.get("pve_only").getAsBoolean());j.addProperty("health_recovery_hold",healthRecoveryHold);j.add("guard_food",dev.twob2tkit.combat.GuardFoodLease.snapshot());j.addProperty("guard_status",healthRecoveryHold?"等待生命恢复到 19 后继续工作":KitClient.borer().status());j.add("professional_printer",ProfessionalPrinter.status());j.addProperty("chopping",KitClient.chopper().isActive());j.addProperty("chopper_status",KitClient.chopper().status());j.addProperty("chopper_remaining",KitClient.chopper().remainingLogs());j.addProperty("chopper_verified_trees",KitClient.chopper().treesDone());j.addProperty("chopper_platforms",KitClient.chopper().platforms());j.addProperty("guide_active",KitClient.structureGuide().isActive());j.addProperty("guide_status",KitClient.structureGuide().status());j.addProperty("navigating",KitClient.controller().isActive());j.addProperty("printing",KitClient.machines().isPlacing());j.addProperty("printer_status",KitClient.machines().status());
        JsonArray nearby=new JsonArray();for(var e:c.level.entitiesForRendering()){
            if(e==c.player || e.distanceToSqr(c.player)>256)continue;
            JsonObject v=new JsonObject();v.addProperty("id",e.getId());v.addProperty("uuid",e.getUUID().toString());v.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());v.addProperty("name",e.getName().getString());v.addProperty("hostile",e instanceof net.minecraft.world.entity.monster.Enemy);v.addProperty("visible",c.player.hasLineOfSight(e));if(e instanceof net.minecraft.world.entity.LivingEntity living)v.addProperty("health",living.getHealth());if(e instanceof net.minecraft.world.entity.item.ItemEntity drop)v.add("stack",stack(drop.getItem()));v.add("pos",JSON.toJsonTree(new double[]{e.getX(),e.getY(),e.getZ()}));nearby.add(v);
        }j.add("entities",nearby);
        j.addProperty("kill_aura",MeteorModules.isActive(MeteorModules.KILL_AURA));j.addProperty("auto_log",MeteorModules.isActive(MeteorModules.AUTO_LOG));j.addProperty("flight",MeteorModules.isActive(MeteorModules.FLIGHT));return j;
    }
    private static void writeStatus(Minecraft c){try{JsonObject j=snapshot(c);j.addProperty("id",statusId);j.addProperty("last_request",lastId);j.addProperty("phase",phase);j.addProperty("op",op);j.addProperty("detail",detail);save(root(c).resolve("status.json"),j);}catch(Exception ignored){}}
    private static void save(Path file,JsonObject j)throws Exception{Files.createDirectories(file.getParent());Path tmp=file.resolveSibling(file.getFileName()+".tmp");Files.writeString(tmp,JSON.toJson(j));try{Files.move(tmp,file,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);}catch(AtomicMoveNotSupportedException e){Files.move(tmp,file,StandardCopyOption.REPLACE_EXISTING);}}
    private static String str(JsonObject j,String k){return j.has(k)?j.get(k).getAsString():"";}
    private static String safeId(String s){if(!s.matches("[A-Za-z0-9_-]{1,80}"))throw new IllegalArgumentException("Invalid job ID");return s;}
}
