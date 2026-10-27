package dev.twob2tkit.chat.core;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

class LocalHelperServiceTest {
    @TempDir Path root;
    private Path app() throws Exception {
        Path app = root.resolve("Minecraft Bilingual Helper.app");
        Files.createDirectories(app.resolve("Contents/MacOS"));
        Files.writeString(app.resolve("Contents/Info.plist"), "fixture");
        Path executable = app.resolve("Contents/MacOS/MinecraftBilingualHelper");
        Files.writeString(executable, "fixture");
        assertTrue(executable.toFile().setExecutable(true));
        return app;
    }
    @Test void healthyServiceIsReusedWithoutLaunchingOrRequiringInstalledApp() throws Exception {
        LocalHelperService service = new LocalHelperService(arguments -> fail("No second helper"));
        service.start(root.resolve("not-installed"), "Mac OS X", 8765, () -> true).get(2, TimeUnit.SECONDS);
    }
    @Test void concurrentStartsLaunchOnlyOnceAndDoNotBlockCaller() throws Exception {
        Path app = app(); AtomicBoolean healthy = new AtomicBoolean(); AtomicInteger count = new AtomicInteger();
        CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        LocalHelperService service = new LocalHelperService(arguments -> {
            assertEquals(List.of("/usr/bin/open", "-g", app.toAbsolutePath().toString()), arguments);
            count.incrementAndGet(); entered.countDown(); assertTrue(release.await(2, TimeUnit.SECONDS)); healthy.set(true);
        });
        var first = service.start(app, "Mac OS X", 8765, healthy::get);
        assertTrue(entered.await(2, TimeUnit.SECONDS));
        var second = service.start(app, "Mac OS X", 8765, healthy::get);
        assertFalse(second.isDone()); release.countDown();
        first.get(2, TimeUnit.SECONDS); second.get(2, TimeUnit.SECONDS); assertEquals(1, count.get());
    }
    @Test void unsafeOrMissingInstallCannotLaunchAnything() throws Exception {
        Path app = app();
        assertThrows(java.io.IOException.class, () -> LocalHelperService.command(app, "Linux", 8765, true));
        assertThrows(java.io.IOException.class, () -> LocalHelperService.command(app, "Mac OS X", 9999, true));
        assertThrows(java.io.IOException.class, () -> LocalHelperService.command(root.resolve("missing"), "Mac OS X", 8765, true));
    }
    @Test void failedLaunchIsNotRetriedByRepeatedClicks() throws Exception {
        Path app = app(); AtomicInteger count = new AtomicInteger();
        LocalHelperService service = new LocalHelperService(arguments -> { count.incrementAndGet(); throw new java.io.IOException("fixture failure"); });
        assertThrows(Exception.class, () -> service.start(app, "Mac OS X", 8765, () -> false).get(2, TimeUnit.SECONDS));
        assertThrows(Exception.class, () -> service.start(app, "Mac OS X", 8765, () -> false).get(2, TimeUnit.SECONDS));
        assertEquals(1, count.get());
    }
}
