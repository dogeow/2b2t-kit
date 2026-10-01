package dev.twob2tkit.material;

import com.google.gson.JsonObject;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitKeys;
import dev.twob2tkit.automation.AutomationBridge;
import dev.twob2tkit.combat.EmergencyExit;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import net.minecraft.client.Minecraft;

/** One explicitly started local caretaker process, using the existing deterministic Python coordinator. */
public final class CaretakerJobs {
    private static final MaterialWorkerProcess worker=new MaterialWorkerProcess();
    private static final MaterialWorkerProcess probe=new MaterialWorkerProcess();
    private static boolean probeStarted,externalAlive;
    private static long externalObservedAt;
    private static CaretakerProtocol.Installation installed;
    private static JsonObject journal;
    private static String world="",note="";
    private static long lastPoll;
    private record Pending(String action,JsonObject context,long requestedAt,boolean resumeExisting) {}
    private static Pending pending;
    private CaretakerJobs() {}
    public static boolean running(){return worker.current()!=null&&worker.current().isAlive();}
    public static boolean occupied(){return pending!=null||worker.occupied()||externalAlive&&System.currentTimeMillis()-externalObservedAt<2500;}
    public static String status(){return CaretakerProtocol.status(journal,running())+(note.isBlank()?"":" · "+note);}
    public static String scope(){return installed==null?"请先安装已授权的本地农场配置；不会自动登记新区域。":CaretakerProtocol.summary(installed.profile());}
    public static Path directory(){return installed==null?null:installed.directory();}
    public static void inspect(Minecraft client){
        try{installed=CaretakerProtocol.installed(client.gameDirectory.toPath());refresh();note="";}
        catch(IOException|RuntimeException failure){if(!running()){installed=null;journal=null;}note=message(failure);}
    }
    public static void refresh(){
        if(installed==null)return;
        try{journal=CaretakerProtocol.journal(installed);}
        catch(IOException|RuntimeException failure){journal=null;note="原周期记录暂不可读："+message(failure);}
    }
    public static void start(Minecraft client){prepare(client,"run");}
    public static void resume(Minecraft client){prepare(client,"resume");}
    private static void prepare(Minecraft client,String action){
        if(pending!=null||probe.occupied()||worker.occupied()&&!(action.equals("resume")&&running()))throw new IllegalStateException("农场后台或启动请求仍在处理，请先停止或等待");
        if(MaterialJobs.running())throw new IllegalStateException("材料作业仍在运行，农场不会抢控制");
        try{
            var installation=CaretakerProtocol.installed(client.gameDirectory.toPath());var book=CaretakerProtocol.journal(installation);
            JsonObject state=live(installation),context=AutomationBridge.materialJobContext(client);
            CaretakerProtocol.requireUnlocked(automation(installation),state);
            CaretakerProtocol.requireReady(installation,state,book,System.currentTimeMillis(),true);
            if(EmergencyExit.held(client)||client.player.getHealth()!=20||client.player.getFoodData().getFoodLevel()<18||client.player.isUsingItem()||KitKeys.manualMovementDown(client))throw new IllegalStateException("角色或安全状态尚未就绪");
            if(action.equals("resume")&&book==null)throw new IllegalStateException("尚无可恢复的农场周期");
            installed=installation;journal=book;
            // Closing the normal Kit page happens once. Reopening any page cancels this pending launch.
            client.setScreen(null);
            probeStarted=false;pending=new Pending(action,context,System.currentTimeMillis(),running());note="等待关屏后的新鲜状态，再核对并启动";
        }catch(IOException failure){throw new IllegalStateException("农场启动文件无法读取",failure);}
    }
    public static void pause(Minecraft client){control(client,"pause");}
    public static void stopSchedule(Minecraft client){control(client,"stop");}
    private static void control(Minecraft client,String action){
        if(installed==null)throw new IllegalStateException("农场配置未安装或记录尚不可读");
        if(pending!=null){pending=null;probe.stop();probeStarted=false;note="尚未开始的启动请求已取消";return;}
        if(!running()&&!(externalAlive&&System.currentTimeMillis()-externalObservedAt<2500))
            throw new IllegalStateException("未确认有存活的周期后台；原记录保留，请先查看状态");
        try{CaretakerProtocol.control(installed,action);note="已提交"+(action.equals("pause")?"暂停":"停止")+"，等待当前动作安全收尾和真实记录确认";client.setScreen(null);}
        catch(IOException failure){throw new IllegalStateException("农场操作未能保存，状态未改变",failure);}
    }
    /** Exact handle shutdown only. The caller's existing host emergency cleanup stops native input. */
    public static void stopImmediately(String reason){
        boolean launchPending=pending!=null;pending=null;probe.stop();probeStarted=false;
        if(!worker.occupied()){if(launchPending)note=reason+"；启动请求已取消";return;}
        if(installed!=null)try{CaretakerProtocol.control(installed,"stop");}catch(IOException|RuntimeException ignored){}
        worker.stop();note=reason+"；后台已请求退出，原未确认记录保留";
    }
    public static void tick(Minecraft client){
        if(pending!=null){
            Pending request=pending;
            try{
                if(client.screen!=null)throw new IllegalStateException("启动前重新打开了界面，请手动再次开始");
                if(client.player==null||client.level==null||EmergencyExit.held(client)||KitKeys.manualMovementDown(client))throw new IllegalStateException("角色、输入或安全锁已改变，启动取消");
                if(System.currentTimeMillis()-request.requestedAt()>10000)throw new IllegalStateException("关屏后未取得新鲜状态，请手动再次开始");
                if(!request.context().get("world_session").getAsString().equals(AutomationBridge.materialJobWorldSession(client)))throw new IllegalStateException("启动前世界已改变");
                if(probeStarted&&probe.current()!=null&&probe.current().isAlive())return;
                JsonObject state=live(installed);if(state.get("time").getAsLong()<request.requestedAt())return;
                JsonObject context=AutomationBridge.materialJobContext(client);
                for(String key:new String[]{"world_session","expected_revision","server","dimension"})if(!context.get(key).equals(request.context().get(key)))throw new IllegalStateException("启动前世界或控制已改变");
                if(MaterialJobs.running())throw new IllegalStateException("材料任务已开始，农场不会接管");
                var checked=CaretakerProtocol.installed(client.gameDirectory.toPath());
                if(!checked.profile().equals(installed.profile()))throw new IllegalStateException("启动前农场登记配置已改变");
                var book=CaretakerProtocol.journal(checked);
                CaretakerProtocol.requireUnlocked(automation(checked),state);CaretakerProtocol.requireReady(checked,state,book,System.currentTimeMillis(),false);
                if(client.player.getHealth()!=20||client.player.getFoodData().getFoodLevel()<18||client.player.isUsingItem())throw new IllegalStateException("启动前生命或食物已改变");
                // This CLI action only reads the real worker flock; it cannot acquire a game lease.
                Path probeLog=checked.directory().resolve("ui-status-probe.log");
                if(!probeStarted){
                    Files.createDirectories(checked.directory());
                    probe.start(checked.command("status"),checked.script().getParent(),probeLog);probeStarted=true;return;
                }
                if(probe.current()==null)throw new IllegalStateException("本地周期后台核验已取消");
                if(probe.current().isAlive())return;
                int probeExit=probe.releaseExited();
                JsonObject probeReply=CaretakerProtocol.read(probeLog);
                if(probeExit!=0)throw new IllegalStateException("农场后台记录核验失败："+CaretakerProtocol.text(probeReply,"detail"));
                boolean locked=CaretakerProtocol.workerRunning(probeReply);
                externalAlive=locked&&!running();externalObservedAt=System.currentTimeMillis();
                if(locked&&!request.resumeExisting())throw new IllegalStateException("已有本地周期后台持有工作锁，原停车和周期保留");
                if(request.resumeExisting()){
                    if(!running())throw new IllegalStateException("原后台已退出，请查看真实记录后手动恢复");
                    CaretakerProtocol.control(checked,"resume");note="已提交恢复，等待真实记录确认";
                }else{
                    Files.createDirectories(checked.directory());
                    worker.start(checked.command(request.action()),checked.script().getParent(),checked.directory().resolve("ui-worker.log"));
                    world=context.get("world_session").getAsString();note="本地进程已启动，等待周期记录确认";
                }
                installed=checked;pending=null;lastPoll=0;
            }catch(IOException|RuntimeException failure){pending=null;probe.stop();probeStarted=false;note="未启动："+message(failure);}
        }
        if(running()&&(client.player==null||client.level==null||!world.equals(AutomationBridge.materialJobWorldSession(client))||EmergencyExit.held(client))){stopImmediately("世界或安全锁已改变，需要玩家重新确认");return;}
        long now=System.currentTimeMillis();if(installed==null||now-lastPoll<500)return;lastPoll=now;refresh();
        Process process=worker.current();if(process!=null&&!process.isAlive()){
            int exit=worker.releaseExited();note="本地后台已退出（"+exit+"），以原周期记录为准";refresh();
        }
    }
    private static JsonObject live(CaretakerProtocol.Installation installation)throws IOException{return CaretakerProtocol.read(automation(installation).resolve("status.json"));}
    private static Path automation(CaretakerProtocol.Installation installation){return installation.game().resolve("config/twob2tkit/automation");}
    private static String message(Exception failure){return failure.getMessage()==null?failure.getClass().getSimpleName():failure.getMessage();}
}
