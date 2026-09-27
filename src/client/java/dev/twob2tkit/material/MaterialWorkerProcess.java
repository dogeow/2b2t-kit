package dev.twob2tkit.material;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

/** Owns exact process handles, never a global process-name search or another task's worker. */
final class MaterialWorkerProcess {
    private Process active;
    private Process stopping;
    Process current() { return active; }
    boolean alive() { return active != null && active.isAlive() || stopping != null && stopping.isAlive(); }
    boolean occupied() { return active != null || stopping != null && stopping.isAlive(); }
    Process start(List<String> command, Path workingDirectory, Path log) throws IOException {
        if (occupied()) throw new IllegalStateException("上一个材料后台仍在收尾，请稍后再开始");
        stopping = null;
        Process child = new ProcessBuilder(command).directory(workingDirectory.toFile()).redirectErrorStream(true)
            .redirectOutput(log.toFile()).start();
        active = child; return child;
    }
    int releaseExited() {
        if (active == null || active.isAlive()) throw new IllegalStateException("材料后台尚未退出");
        int result = active.exitValue(); active = null; return result;
    }
    void stop() {
        Process child = active;
        if (child == null) return;
        active = null; stopping = child;
        var descendants = child.descendants().toList();
        descendants.forEach(handle -> { if (handle.isAlive()) handle.destroy(); }); child.destroy();
        // Captured handles cannot accidentally target a later task that reused this manager.
        CompletableFuture.delayedExecutor(2, TimeUnit.SECONDS).execute(() -> {
            descendants.forEach(handle -> { if (handle.isAlive()) handle.destroyForcibly(); });
            if (child.isAlive()) child.destroyForcibly();
        });
    }
}
