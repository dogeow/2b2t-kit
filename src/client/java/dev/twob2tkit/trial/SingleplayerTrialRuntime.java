package dev.twob2tkit.trial;

import com.google.gson.*;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitKeys;
import dev.twob2tkit.material.LocalDecisionRuntime;
import dev.twob2tkit.material.MaterialJobProtocol;
import dev.twob2tkit.material.MaterialJobs;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.DeathScreen;
import net.minecraft.resources.Identifier;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.storage.LevelResource;
import java.nio.file.*;
import java.util.UUID;

/** Game-owned local experiment, isolated by the actual save and an exact run. */
public final class SingleplayerTrialRuntime {
    private static Process process;
    private static JsonObject registry=new JsonObject();
    private static boolean loaded,wasDead,dragonDefeated,advancementPending,cancelled;
    private static final java.util.Map<String,Boolean> disabledModules=new java.util.HashMap<>();
    private static int deaths,lastRespawn=-1;
    private static long deadAt,nextAdvancementPoll,lastStatusCheck;
    private static String run="",world="",notice="尚未启动单人试验";
    private SingleplayerTrialRuntime() {}
    private static Path folder(Minecraft c){return c.gameDirectory.toPath().resolve("config/twob2tkit/singleplayer-trial");}
    private static String text(JsonObject j,String k){return j.has(k)&&!j.get(k).isJsonNull()?j.get(k).getAsString():"";}
    private static String worldId(Minecraft c){
        if(c.getSingleplayerServer()==null)return "";
        Path path=c.getSingleplayerServer().getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize();
        if(Files.isSymbolicLink(path))return "";return path.toString();
    }
    private static void load(Minecraft c){
        if(loaded)return;loaded=true;
        try{var p=folder(c).resolve("registry.json");if(Files.isRegularFile(p))registry=JsonParser.parseString(Files.readString(p)).getAsJsonObject();}
        catch(Exception e){registry=new JsonObject();notice="试验登记不可读";}
    }
    private static void write(Path file,JsonObject value)throws Exception{
        Files.createDirectories(file.getParent());Path temp=file.resolveSibling(file.getFileName()+".tmp");Files.writeString(temp,value.toString());
        Files.move(temp,file,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
    }
    public static boolean registeredHere(Minecraft c){
        load(c);var server=c.getSingleplayerServer();
        return registry.has("enabled")&&registry.get("enabled").getAsBoolean()&&SingleplayerTrialPolicy.world(
            server!=null,c.getCurrentServer()!=null,server!=null&&server.isPublished(),
            c.gameMode!=null&&c.gameMode.getPlayerMode()==GameType.SURVIVAL,
            server!=null&&server.getWorldData().isHardcore(),worldId(c),text(registry,"world_id"));
    }
    public static boolean activeHere(Minecraft c){return !cancelled&&process!=null&&process.isAlive()&&!run.isBlank()&&registeredHere(c);}
    public static boolean expectedDeath(Minecraft c){return activeHere(c)&&c.player!=null&&c.player.isDeadOrDying();}
    public static String goal(){return "击败末影龙";}
    public static void start(Minecraft c,KitConfig config){
        if(c.getSingleplayerServer()==null||c.getCurrentServer()!=null||c.getSingleplayerServer().isPublished()
                ||c.player==null||c.gameMode.getPlayerMode()!=GameType.SURVIVAL||c.getSingleplayerServer().getWorldData().isHardcore())
            throw new IllegalStateException("只在未开放局域网的普通单人生存试验存档启动");
        String name=c.getSingleplayerServer().getWorldData().getLevelName();
        Path actualSave=Path.of(worldId(c));Path saves=c.getLevelSource().getBaseDir().toAbsolutePath().normalize();
        if(!actualSave.isAbsolute()||!actualSave.getParent().equals(saves)||Files.isSymbolicLink(actualSave))throw new IllegalStateException("试验必须绑定本机独立存档");
        if(MaterialJobs.running()||dev.twob2tkit.material.CaretakerJobs.occupied())throw new IllegalStateException("先停止其它工作再开始单人试验");
        if(process!=null&&process.isAlive())throw new IllegalStateException("已有试验，请使用暂停或继续");
        Path worker=c.gameDirectory.toPath().resolve("config/twob2tkit/material-worker");
        Path script=worker.resolve("singleplayer_trial.py");if(!Files.isRegularFile(script))throw new IllegalStateException("单人试验控制器尚未安装");
        Path python=MaterialJobProtocol.resolvePython(config.materialJobsPython,worker,System.getenv("HOME"),System.getProperty("user.home"));
        java.util.Map<String,Boolean> previous=new java.util.HashMap<>();
        for(String module:java.util.List.of(dev.twob2tkit.MeteorModules.AUTO_LOG,dev.twob2tkit.MeteorModules.FLIGHT,"meteordevelopment.meteorclient.systems.modules.misc.AutoReconnect","meteordevelopment.meteorclient.systems.modules.player.AutoRespawn"))
            previous.put(module,dev.twob2tkit.MeteorModules.isActive(module));
        KitClient.emergencyStop("开始独立单人试验");disabledModules.clear();disabledModules.putAll(previous);
        load(c);String currentWorld=worldId(c);boolean same=currentWorld.equals(text(registry,"world_id"));
        if(!same){registry=new JsonObject();registry.addProperty("trial_id",UUID.randomUUID().toString());}
        run=UUID.randomUUID().toString();world=currentWorld;deaths=0;wasDead=false;lastRespawn=-1;dragonDefeated=false;cancelled=false;
        registry.addProperty("protocol",1);registry.addProperty("world_id",world);registry.addProperty("world_name",name);
        registry.addProperty("run_id",run);registry.addProperty("goal","defeat_ender_dragon");registry.addProperty("enabled",true);
        registry.addProperty("allow_death_respawn",true);registry.addProperty("kit_version",KitConfig.class.getPackage().getImplementationVersion()==null?"2026.10.7.3":KitConfig.class.getPackage().getImplementationVersion());
        try{
            write(folder(c).resolve("registry.json"),registry);control(c,"start");disabledModules.keySet().forEach(dev.twob2tkit.MeteorModules::disable);
            LocalDecisionRuntime.configure(c,"local_model","clef-flash");LocalDecisionRuntime.configure(c,"keep_loaded",true);LocalDecisionRuntime.enable(c,true);
            c.setScreen(null);
            process=new ProcessBuilder(python.toString(),script.toString(),"--game",c.gameDirectory.toString(),"--parent-pid",Long.toString(ProcessHandle.current().pid()))
                .redirectErrorStream(true).redirectOutput(ProcessBuilder.Redirect.appendTo(folder(c).resolve("trial-service.log").toFile())).start();
            notice="单人打龙目标已启动；先核对出生地和开局能力";
        }catch(Exception e){run="";throw new IllegalStateException("无法启动单人试验："+e.getClass().getSimpleName(),e);}
    }
    public static void control(Minecraft c,String command){
        if(!java.util.Set.of("start","pause","resume","cancel").contains(command))throw new IllegalArgumentException("Invalid trial control");
        if(!command.equals("start")&&!activeHere(c))throw new IllegalStateException("当前没有此存档的单人试验");
        try{
            if(command.equals("pause")||command.equals("cancel"))dev.twob2tkit.automation.AutomationBridge.stopTrialInputs(c,text(registry,"trial_id"),run);
            var j=new JsonObject();j.addProperty("id",UUID.randomUUID().toString());j.addProperty("command",command);
            j.addProperty("trial_id",text(registry,"trial_id"));j.addProperty("run_id",run);write(folder(c).resolve("control.json"),j);
            if(command.equals("resume"))c.setScreen(null);notice=command.equals("pause")?"等待当前动作停止后暂停":command.equals("cancel")?"正在停止此试验，保留记录":notice;
            if(command.equals("cancel")){cancelled=true;restoreModules();var child=process;if(child!=null)java.util.concurrent.CompletableFuture.delayedExecutor(2,java.util.concurrent.TimeUnit.SECONDS).execute(()->{if(child.isAlive())child.destroy();});}
        }catch(Exception e){throw new IllegalStateException("无法保存单人试验操作",e);}
    }
    public static void require(Minecraft c,JsonObject request){
        if(!activeHere(c)||!SingleplayerTrialPolicy.owner(text(request,"trial_id"),text(request,"run_id"),text(registry,"trial_id"),run)
            ||!worldId(c).equals(text(request,"world_id")))throw new IllegalStateException("Trial save or run changed; server actions refused");
        if(KitKeys.manualMovementDown(c))throw new IllegalStateException("Player took control of trial");
    }
    public static void respawn(Minecraft c,JsonObject request){
        require(c,request);int epoch=request.has("death_epoch")?request.get("death_epoch").getAsInt():-1;
        if(!SingleplayerTrialPolicy.respawn(true,c.player!=null&&c.player.isDeadOrDying(),c.screen instanceof DeathScreen,deaths,epoch,lastRespawn,System.currentTimeMillis()-deadAt))
            throw new IllegalStateException("Trial death is not ready or respawn was already requested");
        lastRespawn=epoch;c.player.respawn();c.setScreen(null);
    }
    public static JsonObject snapshot(Minecraft c){
        load(c);var j=new JsonObject();j.addProperty("registered",registeredHere(c));j.addProperty("trial_id",text(registry,"trial_id"));
        j.addProperty("world_id",text(registry,"world_id"));j.addProperty("world_name",text(registry,"world_name"));j.addProperty("run_id",run);
        j.addProperty("process_alive",process!=null&&process.isAlive());j.addProperty("deaths",deaths);j.addProperty("death_epoch",deaths);j.addProperty("dragon_defeated",registeredHere(c)&&dragonDefeated);
        j.addProperty("goal",goal());j.addProperty("detail",notice);return j;
    }
    public static String status(Minecraft c){
        try{var p=folder(c).resolve("worker/status.json");if(Files.isRegularFile(p)){
            var j=JsonParser.parseString(Files.readString(p)).getAsJsonObject();if(run.equals(text(j,"run_id"))){
                String phase=j.has("state")?text(j,"state"):text(j,"phase");
                String label=switch(phase){case "thinking"->"模型选择中";case "running"->"正在试验";case "paused"->"已暂停";
                    case "waiting_model"->"等待模型";case "waiting_capability"->"等待新能力";case "death_wait"->"死亡恢复中";
                    case "completed"->"击败末影龙已确认";case "cancelled","stopped"->"已停止";default->"正在观察";};
                return label+" · "+(j.has("detail")?text(j,"detail"):text(j,"reason"));}}}
        catch(Exception ignored){}return notice;
    }
    public static void stop(Minecraft c,String reason){
        dev.twob2tkit.automation.AutomationBridge.stopTrialInputs(c,text(registry,"trial_id"),run);
        if(process!=null&&process.isAlive()){try{control(c,"cancel");}catch(Exception ignored){}process.destroy();}
        process=null;run="";cancelled=true;restoreModules();notice=reason;
    }
    private static void restoreModules(){disabledModules.forEach((module,on)->{if(on&&!dev.twob2tkit.MeteorModules.isActive(module))dev.twob2tkit.MeteorModules.enable(module);});disabledModules.clear();}
    public static void tick(Minecraft c){
        SingleplayerTrialApi.tick(c);
        if(process==null)return;
        if(!process.isAlive()){dev.twob2tkit.automation.AutomationBridge.stopTrialInputs(c,text(registry,"trial_id"),run);notice="试验后台已停止，进度和经验保留";process=null;run="";restoreModules();return;}
        if(!registeredHere(c)){stop(c,"试验存档已离开，服务器操作保持关闭");return;}
        if(!cancelled)disabledModules.keySet().forEach(dev.twob2tkit.MeteorModules::disable);
        boolean dead=c.player!=null&&c.player.isDeadOrDying();if(dead&&!wasDead){deaths++;deadAt=System.currentTimeMillis();}wasDead=dead;
        long now=System.currentTimeMillis();if(!advancementPending&&now>=nextAdvancementPoll&&c.player!=null&&!dead){
            nextAdvancementPoll=now+5000;var server=c.getSingleplayerServer();var uuid=c.player.getUUID();String expectedRun=run;advancementPending=true;
            server.execute(()->{boolean done=false;try{var player=server.getPlayerList().getPlayer(uuid);var holder=server.getAdvancements().get(Identifier.parse("minecraft:end/kill_dragon"));
                done=player!=null&&holder!=null&&player.getAdvancements().getOrStartProgress(holder).isDone();}catch(Exception ignored){}
                boolean result=done;c.execute(()->{if(server==c.getSingleplayerServer()&&expectedRun.equals(run)&&registeredHere(c))dragonDefeated=result;advancementPending=false;});});
        }
    }
}
