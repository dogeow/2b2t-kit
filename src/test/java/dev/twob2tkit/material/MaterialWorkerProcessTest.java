package dev.twob2tkit.material;

import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class MaterialWorkerProcessTest {
    @TempDir Path directory;
    private Process start(MaterialWorkerProcess worker, String name) throws Exception {
        return worker.start(List.of("/bin/sleep", "60"), directory, directory.resolve(name));
    }
    @Test void stoppingOwnedWorkerCannotKillAnUnrelatedProcess() throws Exception {
        var owner = new MaterialWorkerProcess();
        Process other = new ProcessBuilder("/bin/sleep", "60").start();
        Process child = start(owner,"owned.log");
        try {
            owner.stop();
            assertTrue(child.waitFor(5,TimeUnit.SECONDS));
            assertTrue(other.isAlive()); assertNull(owner.current());
            owner.stop(); assertTrue(other.isAlive());
        } finally { child.destroyForcibly(); other.destroyForcibly(); }
    }
    @Test void liveWorkerReservesSlotAndCannotBeOverwrittenByNewLaunch() throws Exception {
        var owner = new MaterialWorkerProcess(); Process child = start(owner,"first.log");
        try {
            assertTrue(owner.occupied());
            assertThrows(IllegalStateException.class,()->start(owner,"second.log"));
            assertSame(child,owner.current()); assertTrue(child.isAlive());
            assertThrows(IllegalStateException.class,owner::releaseExited);
        } finally { owner.stop(); child.waitFor(5,TimeUnit.SECONDS); }
    }
    @Test void confirmedExitFreesSlotAndPreservesExitCode() throws Exception {
        var owner = new MaterialWorkerProcess();
        Process child = owner.start(List.of("/usr/bin/true"),directory,directory.resolve("done.log"));
        assertTrue(child.waitFor(5,TimeUnit.SECONDS)); assertEquals(0,owner.releaseExited());
        assertFalse(owner.occupied()); assertNull(owner.current());
        Process next = start(owner,"next.log");
        try { assertTrue(next.isAlive()); assertSame(next,owner.current()); }
        finally { owner.stop(); next.waitFor(5,TimeUnit.SECONDS); }
    }
    @Test void launchFailureDoesNotReserveControllerSlot() {
        var owner = new MaterialWorkerProcess();
        assertThrows(java.io.IOException.class,()->owner.start(List.of(directory.resolve("missing").toString()),directory,directory.resolve("failed.log")));
        assertFalse(owner.occupied()); assertNull(owner.current());
    }
}
