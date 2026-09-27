package dev.twob2tkit.material;

import com.google.gson.JsonObject;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** File protocol shared with the deterministic material worker. No Minecraft or process side effects. */
public final class MaterialJobProtocol {
    private MaterialJobProtocol() {}
    public static final Set<String> STATES = Set.of("queued", "planning", "fetching", "gathering", "crafting", "smelting", "hardening", "building", "paused", "completed", "blocked", "failed", "cancelled");
    public static boolean terminal(String state) { return Set.of("completed", "blocked", "failed", "cancelled").contains(state); }
    public static JsonObject request(String id, String mode, Map<String, Integer> targets, String projectionKey, JsonObject context, long now) {
        if (id == null || !id.matches("[a-zA-Z0-9_-]{1,96}")) throw new IllegalArgumentException("任务标识无效");
        if (!Set.of("item", "projection").contains(mode)) throw new IllegalArgumentException("材料任务类型无效");
        if (targets == null || targets.size() > 256 || mode.equals("item") && targets.isEmpty()) throw new IllegalArgumentException("请选择目标物品");
        JsonObject items = new JsonObject();
        targets.forEach((item, amount) -> {
            if (item == null || !item.matches("[a-z0-9_.-]+:[a-z0-9_./-]+") || amount == null || amount < 1 || amount > 1_000_000)
                throw new IllegalArgumentException("物品或数量无效（1–1000000）");
            items.addProperty(item, amount);
        });
        if (mode.equals("projection") && (projectionKey == null || projectionKey.isBlank())) throw new IllegalArgumentException("请先选择并锁定投影");
        requireContext(context);
        JsonObject request = new JsonObject(); request.addProperty("schema", 1); request.addProperty("id", id);
        request.addProperty("mode", mode); request.add("targets", items); request.add("context", context.deepCopy());
        if (mode.equals("projection")) request.addProperty("projection_key", projectionKey);
        request.addProperty("created_at", now); return request;
    }
    private static void requireContext(JsonObject context) {
        if (context == null || text(context, "world_session").isBlank() || text(context, "server").isBlank()
                || text(context, "dimension").isBlank() || !context.has("expected_revision") || !context.has("start_pos"))
            throw new IllegalArgumentException("当前世界状态尚未就绪");
        try {
            var position = context.getAsJsonArray("start_pos");
            if (number(context, "expected_revision") < 0 || position.size() != 3) throw new IllegalArgumentException();
            for (var coordinate : position) if (!Double.isFinite(coordinate.getAsDouble())) throw new IllegalArgumentException();
        } catch (RuntimeException error) { throw new IllegalArgumentException("当前世界坐标或控制状态无效"); }
    }
    public static JsonObject control(String id, String action, long now) {
        if (id == null || !id.matches("[a-zA-Z0-9_-]{1,96}")) throw new IllegalArgumentException("任务标识无效");
        if (!Set.of("pause", "resume", "cancel").contains(action)) throw new IllegalArgumentException("任务操作无效");
        JsonObject result = new JsonObject(); result.addProperty("schema", 1); result.addProperty("id", id);
        result.addProperty("action", action); result.addProperty("created_at", now); return result;
    }
    public static JsonObject resume(String id, long now, JsonObject context) {
        requireContext(context);
        JsonObject result = control(id, "resume", now); result.add("context", context.deepCopy()); return result;
    }
    public record Progress(String state, String phase, String detail, long done, long total, long updatedAt, String taskSession) {}
    public record Outcome(String state, String detail) {}
    public static Outcome exited(int exitCode, boolean cancelled, String reportedState, String reportedDetail) {
        if (cancelled) return new Outcome("cancelled", "已取消，已取得的材料保留");
        if (terminal(reportedState) && (!reportedState.equals("completed") || exitCode == 0)) return new Outcome(reportedState, reportedDetail);
        return new Outcome("failed", "材料后台已停止，请查看任务日志后重试");
    }
    public static Progress progress(JsonObject data, String id, long createdAt, long now) {
        if (data == null || !id.equals(text(data, "id")) || number(data, "schema") != 1) throw new IllegalArgumentException("材料任务回执不匹配");
        String state = text(data, "state");
        long updated = number(data, "updated_at"), done = number(data, "done"), total = number(data, "total");
        if (!STATES.contains(state) || updated < createdAt || updated > now + 5000 || done < 0 || total < 0)
            throw new IllegalArgumentException("材料任务回执无效");
        return new Progress(state, clean(text(data, "phase")), clean(text(data, "detail")), done, total, updated, text(data, "native_task_session"));
    }
    public static List<String> command(Path python, Path worker, Path automation, Path request, Path out) {
        if (!Files.isRegularFile(python) || !Files.isExecutable(python)) throw new IllegalStateException("材料任务运行环境未安装，请更新 Kit");
        if (!Files.isRegularFile(worker)) throw new IllegalStateException("材料任务后台未安装，请更新 Kit");
        return List.of(python.toString(), "-u", worker.toString(), "--automation", automation.toString(), "--request", request.toString(), "--out", out.toString());
    }
    /** HMCL may override user.home; use the installer-recorded local runtime before home fallbacks. */
    public static Path resolvePython(String configured, Path worker, String environmentHome, String propertyHome) {
        if (configured != null && !configured.isBlank()) return runtimePath(configured);
        Path marker = worker.resolveSibling("runtime-python.txt");
        if (Files.exists(marker)) {
            try {
                if (!Files.isRegularFile(marker) || Files.size(marker) > 4096) throw new IllegalStateException("材料运行环境配置无效，请重新安装后台");
                String value = Files.readString(marker);
                if (value.endsWith("\r\n")) value = value.substring(0, value.length() - 2);
                else if (value.endsWith("\n")) value = value.substring(0, value.length() - 1);
                return runtimePath(value);
            } catch (java.io.IOException error) { throw new IllegalStateException("材料运行环境配置无法读取，请重新安装后台", error); }
        }
        String home = environmentHome != null && !environmentHome.isBlank() ? environmentHome : propertyHome;
        Path root = runtimePath(home);
        return root.resolve("Library/Application Support/MinecraftDecisions/venv/bin/python");
    }
    private static Path runtimePath(String raw) {
        if (raw == null || raw.isBlank() || raw.length() > 4096 || raw.chars().anyMatch(Character::isISOControl))
            throw new IllegalStateException("材料运行环境路径无效，请重新安装后台");
        try {
            Path path = Path.of(raw);
            if (!path.isAbsolute()) throw new IllegalStateException("材料运行环境路径必须是完整路径");
            // Do not resolve symlinks: resolving a venv/bin/python link loses its virtual environment.
            return path;
        } catch (java.nio.file.InvalidPathException error) { throw new IllegalStateException("材料运行环境路径无效", error); }
    }
    public static String label(String state) {
        return switch (state) {
            case "queued" -> "准备启动"; case "planning" -> "核对材料"; case "fetching" -> "仓库取料";
            case "gathering" -> "采集材料"; case "crafting" -> "合成中"; case "smelting" -> "熔炼中";
            case "hardening" -> "硬化混凝土"; case "building" -> "投影施工"; case "paused" -> "已暂停";
            case "completed" -> "已完成"; case "finishing" -> "安全收尾"; case "blocked" -> "需要处理"; case "failed" -> "已停止";
            case "cancelled" -> "已取消"; default -> "尚未启动";
        };
    }
    private static String clean(String value) { String result = value.replaceAll("[\\p{Cntrl}]", " ").replaceAll("§.", ""); return result.length() > 300 ? result.substring(0, 299) + "…" : result; }
    private static String text(JsonObject data, String key) { try { return data.get(key).getAsString(); } catch (RuntimeException e) { return ""; } }
    private static long number(JsonObject data, String key) { try { return data.get(key).getAsLong(); } catch (RuntimeException e) { throw new IllegalArgumentException("任务回执字段缺失：" + key); } }
}
