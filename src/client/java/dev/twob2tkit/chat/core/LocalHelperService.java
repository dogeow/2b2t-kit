package dev.twob2tkit.chat.core;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

/** Starts the installed local app once; never launches a shell or another game. */
public final class LocalHelperService {
    @FunctionalInterface public interface Launcher { void launch(List<String> arguments) throws Exception; }
    private final Launcher launcher;
    private CompletableFuture<Void> starting;
    private long lastLaunch;

    public LocalHelperService() {
        this(arguments -> {
            Process process = new ProcessBuilder(arguments).redirectOutput(ProcessBuilder.Redirect.DISCARD)
                    .redirectError(ProcessBuilder.Redirect.DISCARD).start();
            if (!process.waitFor(5, TimeUnit.SECONDS) || process.exitValue() != 0)
                throw new IOException("无法启动助手，请检查安装位置");
        });
    }
    public LocalHelperService(Launcher launcher) { this.launcher = launcher; }

    public synchronized CompletableFuture<Void> start(Path app, String os, int port, BooleanSupplier healthy) {
        if (starting != null && !starting.isDone()) return starting.copy();
        starting = CompletableFuture.runAsync(() -> {
            if (healthy.getAsBoolean()) return;
            try {
                List<String> arguments;
                synchronized (this) {
                    if (System.nanoTime() - lastLaunch < TimeUnit.SECONDS.toNanos(20) && lastLaunch != 0)
                        throw new IOException("助手仍在启动或上次启动失败，请稍后重试");
                    arguments = command(app, os, port, true);
                    lastLaunch = System.nanoTime();
                }
                launcher.launch(arguments);
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
                do {
                    if (healthy.getAsBoolean()) return;
                    Thread.sleep(200);
                } while (System.nanoTime() < deadline);
                throw new IOException("助手已打开，但服务尚未就绪，请查看助手窗口");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new java.util.concurrent.CompletionException(error);
            } catch (Exception error) {
                throw new java.util.concurrent.CompletionException(error);
            }
        });
        return starting.copy();
    }

    public CompletableFuture<Void> open(Path app, String os, int port) {
        return CompletableFuture.runAsync(() -> {
            try { launcher.launch(command(app, os, port, false)); }
            catch (Exception error) { throw new java.util.concurrent.CompletionException(error); }
        });
    }

    public static List<String> command(Path app, String os, int port, boolean background) throws IOException {
        if (!os.toLowerCase(Locale.ROOT).contains("mac")) throw new IOException("Apple 翻译助手仅支持 macOS");
        if (port != 8765) throw new IOException("内置助手使用端口 8765，请先恢复默认端口");
        if (!Files.isDirectory(app) || !Files.isRegularFile(app.resolve("Contents/Info.plist"))
                || !Files.isExecutable(app.resolve("Contents/MacOS/MinecraftBilingualHelper")))
            throw new IOException("翻译助手尚未安装，请安装 Kit 随附的 macOS 翻译助手");
        return background ? List.of("/usr/bin/open", "-g", app.toAbsolutePath().toString())
                : List.of("/usr/bin/open", app.toAbsolutePath().toString());
    }
}
