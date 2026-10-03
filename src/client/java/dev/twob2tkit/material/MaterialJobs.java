package dev.twob2tkit.material;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.automation.AutomationBridge;
import dev.twob2tkit.builder.LitematicaAccess;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.UUID;
import net.minecraft.client.Minecraft;

/** Owns one local deterministic worker. An old process is never silently resumed after a world change. */
public final class MaterialJobs {
    private static final com.google.gson.Gson JSON = new GsonBuilder().setPrettyPrinting().create();
    private static final MaterialWorkerProcess workerProcess = new MaterialWorkerProcess();
    private static Path directory;
    private static String id = "", world = "", nativeSession = "", state = "idle", detail = "选择物品和数量，或使用已锁定投影";
    private static String reportedState = "queued", reportedDetail = "";
    private static String hudTitle = "材料任务";
    private static long createdAt, lastPoll, done, total, cancellationAt, lastControlAt, pid;
    private static String mode="",projectionKey="";
    private static boolean cancelling;
    private MaterialJobs() {}
    public static boolean running() { return workerProcess.current() != null; }
    public static boolean paused() { return state.equals("paused"); }
    public static String status() { return MaterialJobProtocol.label(state) + (total > 0 ? " · " + done + "/" + total : "") + (detail.isBlank() ? "" : " · " + detail); }
    public static String state() { return state; }
    public static Path directory() { return directory; }

    public static void startItem(Minecraft client, KitConfig config, String item, int amount) {
        if(amount<1||amount>1_000_000)throw new IllegalArgumentException("物品数量无效（1–1000000）");
        validateItem(item);start(client, config, "item", Map.of(item, amount), "");
    }
    private static void validateItem(String item){
        try{var key=net.minecraft.resources.Identifier.parse(item);
            if(!key.getNamespace().equals("minecraft")||!net.minecraft.core.registries.BuiltInRegistries.ITEM.containsKey(key)
                ||net.minecraft.core.registries.BuiltInRegistries.ITEM.getValue(key)==net.minecraft.world.item.Items.AIR)throw new IllegalArgumentException();
        }catch(RuntimeException invalid){throw new IllegalArgumentException("请选择游戏中有效的目标物品");}
    }
    public static void startProjection(Minecraft client, KitConfig config) {
        var selection = LitematicaAccess.lockedBuildSelection();
        start(client, config, "projection", Map.of(), selection.key());
    }
    private static void start(Minecraft client, KitConfig config, String mode, Map<String, Integer> targets, String projectionKey) {
        if (workerProcess.occupied()) throw new IllegalStateException("已有材料任务或后台仍在收尾，请先完成取消");
        if (CaretakerJobs.occupied()) throw new IllegalStateException("农场周期后台仍在运行或收尾，请先停止并核对记录");
        Path root = root(client), worker = worker(client, config);
        Path python = MaterialJobProtocol.resolvePython(config.materialJobsPython, worker, System.getenv("HOME"), System.getProperty("user.home"));
        String nextId = "material-job-" + UUID.randomUUID();
        Path nextDir = root.resolve("material-jobs").resolve(nextId), requestPath = nextDir.resolve("request.json");
        var command = MaterialJobProtocol.command(python, worker, root, requestPath, nextDir);
        // Read and validate before closing the page, so missing workers never look like a successful start.
        AutomationBridge.preemptIdleForPlayer(client,"FORMAL_MATERIAL_START");
        JsonObject context = AutomationBridge.materialJobContext(client);
        long now = System.currentTimeMillis();
        JsonObject request = MaterialJobProtocol.request(nextId, mode, targets, projectionKey, context, now);
        var stackSizes = new JsonObject();
        net.minecraft.core.registries.BuiltInRegistries.ITEM.forEach(item -> stackSizes.addProperty(
            net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(item).toString(), new net.minecraft.world.item.ItemStack(item).getMaxStackSize()));
        request.add("target_stack_sizes", stackSizes);
        try {
            Files.createDirectories(nextDir); write(nextDir.resolve("request.json"), request);
            client.setScreen(null);
            // Closing a screen may flush a config/draft; check ownership once more before spawning.
            JsonObject fresh = AutomationBridge.materialJobContext(client);
            if (!context.equals(fresh)) throw new IllegalStateException("启动前角色或控制状态已变化，请重新开始");
            if(mode.equals("projection")&&!projectionKey.equals(LitematicaAccess.lockedBuildSelection().key()))throw new IllegalStateException("启动前选定投影已改变");
            pid=workerProcess.start(command, worker.getParent(), nextDir.resolve("worker.log")).pid();
            MaterialJobs.mode=mode;MaterialJobs.projectionKey=projectionKey;
            directory = nextDir; id = nextId; world = context.get("world_session").getAsString();
            createdAt = now; lastPoll = 0; nativeSession = ""; state = "queued"; detail = "正在准备材料计划";
            reportedState = "queued"; reportedDetail = "";
            hudTitle = mode.equals("projection") ? "投影材料与施工" : "获取 " + new net.minecraft.world.item.ItemStack(
                net.minecraft.core.registries.BuiltInRegistries.ITEM.getValue(net.minecraft.resources.Identifier.parse(targets.keySet().iterator().next()))).getHoverName().getString();
            done = total = cancellationAt = 0; cancelling = false;
            KitClient.LOGGER.info("[Materials] worker started job={} mode={}", id, mode);
        } catch (IOException failure) { throw new IllegalStateException("材料任务未能启动：" + failure.getClass().getSimpleName(), failure); }
    }
    public static void pause(Minecraft client) {
        if (!running() || cancelling || paused()) throw new IllegalStateException("当前没有可暂停的材料任务");
        control("pause"); detail = "正在安全暂停，等待当前动作收尾";
    }
    public static void resume(Minecraft client) {
        if (!running() || cancelling || !paused()) throw new IllegalStateException("只有已暂停的任务才能继续");
        if (dev.twob2tkit.combat.EmergencyExit.held(client)) throw new IllegalStateException("低血量安全锁仍开启，请先自行处理");
        if (!world.equals(AutomationBridge.materialJobWorldSession(client))) throw new IllegalStateException("世界已改变，请创建新的材料任务");
        AutomationBridge.preemptIdleForPlayer(client,"FORMAL_MATERIAL_RESUME");
        JsonObject context = AutomationBridge.materialJobContext(client);
        if(mode.equals("projection")&&!projectionKey.equals(LitematicaAccess.lockedBuildSelection().key()))throw new IllegalStateException("已暂停任务的投影已改变，请新建材料任务");
        client.setScreen(null);
        if (!context.equals(AutomationBridge.materialJobContext(client))) throw new IllegalStateException("继续前角色或控制状态已变化，请重新确认");
        control("resume", context); state = "queued"; detail = "正在重新核对任务与安全状态";
    }
    public static void cancel(Minecraft client) {
        if (!running()) throw new IllegalStateException("没有正在运行的材料任务");
        control("cancel"); cancelling = true; cancellationAt = System.currentTimeMillis(); detail = "正在停止，保留已取得的材料";
        if (!nativeSession.isBlank()) AutomationBridge.materialJobCancel(client, nativeSession, "材料任务已取消");
    }
    private static void control(String action) {
        control(action, null);
    }
    private static void control(String action, JsonObject context) {
        long stamp = Math.max(System.currentTimeMillis(), lastControlAt + 1);
        JsonObject message = action.equals("resume") ? MaterialJobProtocol.resume(id, stamp, context) : MaterialJobProtocol.control(id, action, stamp);
        try { write(directory.resolve("control.json"), message); lastControlAt = stamp; }
        catch (IOException error) { throw new IllegalStateException("无法保存任务操作，任务状态未改变", error); }
    }
    /** Called by emergency stop and disconnect; only this worker is terminated, no new task is started. */
    public static void stop(String reason) {
        if (!running()) return;
        try { control("cancel"); } catch (RuntimeException e) { KitClient.LOGGER.warn("[Materials] could not save cancellation job={}", id); }
        workerProcess.stop();
        state = "cancelled"; detail = reason; cancelling = false;
        KitClient.LOGGER.info("[Materials] worker stopped job={} reason={}", id, reason);
    }
    public static void tick(Minecraft client) {
        if (!running()) return;
        Process process = workerProcess.current();
        if (client.player == null || client.level == null || !world.equals(AutomationBridge.materialJobWorldSession(client))) { stop("世界已变化，请手动重新开始"); return; }
        long now = System.currentTimeMillis(); if (now - lastPoll < 500) return; lastPoll = now;
        try {
            Path file = directory.resolve("status.json");
            if (Files.exists(file)) {
                if (Files.size(file) > 65536) throw new IllegalArgumentException("材料任务回执过大");
                var progress = MaterialJobProtocol.progress(JsonParser.parseString(Files.readString(file)).getAsJsonObject(), id, createdAt, now);
                state = progress.state(); detail = progress.detail().isBlank() ? progress.phase() : progress.detail();
                reportedState = state; reportedDetail = detail;
                if (!progress.taskSession().isBlank()) nativeSession = progress.taskSession();
                done = progress.done(); total = progress.total();
                if (state.equals("completed") && process.isAlive()) { state = "finishing"; detail = "数量已核对，正在安全收尾"; }
            }
        } catch (Exception failure) {
            detail = "任务回执暂不可读，等待后台确认";
        }
        if (!process.isAlive()) {
            int exit = workerProcess.releaseExited();
            var outcome = MaterialJobProtocol.exited(exit, cancelling, reportedState, reportedDetail);
            state = outcome.state(); detail = outcome.detail();
            cancelling = false;
            KitClient.LOGGER.info("[Materials] worker exited job={} code={} state={}", id, exit, state);
        } else if (cancelling && now - cancellationAt > 60000) { stop("后台停止超时，任务已中断；请检查背包与容器"); }
    }
    /** Read-only handle shared by the UI and local command API; never claims an alive worker has finished. */
    public static JsonObject snapshot(){
        var value=new JsonObject();value.addProperty("id",id);value.addProperty("state",state);value.addProperty("detail",detail);
        value.addProperty("done",done);value.addProperty("total",total);value.addProperty("world_session",world);
        value.addProperty("process_alive",workerProcess.alive());value.addProperty("pid",pid);
        value.addProperty("occupied",workerProcess.occupied());value.addProperty("cancelling",cancelling);
        value.addProperty("created_at",createdAt);value.addProperty("updated_at",lastPoll);value.addProperty("mode",mode);
        if(!projectionKey.isBlank())value.addProperty("placement_key",projectionKey);
        if(!nativeSession.isBlank())value.addProperty("native_task_session",nativeSession);
        return value;
    }
    public static JsonObject snapshot(String expectedId){
        if(expectedId!=null&&!expectedId.isBlank()&&!expectedId.equals(id))throw new IllegalStateException("Material task job_id is not the current worker");
        return snapshot();
    }
    /** Exact handle control delegates to the existing UI lifecycle; no second controller is created. */
    public static void control(Minecraft client,String expectedId,String action){
        MaterialTaskProtocol.requireJob(expectedId,id,world,AutomationBridge.materialJobWorldSession(client));
        switch(action){case "pause"->pause(client);case "resume"->resume(client);case "cancel"->cancel(client);default->throw new IllegalArgumentException("Unsupported material task action");}
    }
    /** Reuses the central HUD selection and Jade avoidance; this does not render a second overlay. */
    public static JsonObject hud() {
        var value = new JsonObject(); value.addProperty("active", running()); value.addProperty("world_session", world);
        value.addProperty("title", hudTitle); value.addProperty("done", done); value.addProperty("total", total);
        value.addProperty("phase", MaterialJobProtocol.label(state)); return value;
    }
    private static Path root(Minecraft client) { return client.gameDirectory.toPath().resolve("config/twob2tkit/automation"); }
    private static Path worker(Minecraft client, KitConfig config) {
        return config.materialJobsWorker == null || config.materialJobsWorker.isBlank()
            ? client.gameDirectory.toPath().resolve("config/twob2tkit/material-worker/material_jobs_cli.py") : Path.of(config.materialJobsWorker);
    }
    private static void write(Path path, JsonObject value) throws IOException {
        Path temporary = path.resolveSibling(path.getFileName() + ".tmp"); Files.writeString(temporary, JSON.toJson(value));
        try { Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
        catch (java.nio.file.AtomicMoveNotSupportedException e) { Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING); }
    }
}
