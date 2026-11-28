package dev.twob2tkit.runtime.engine;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaThinkStoreWriteTest {
    @TempDir Path directory;

    @Test void writesWholeFileThroughATemporaryAndLeavesNothingBehind() throws Exception {
        Path target = directory.resolve("twob2tkit/area-think.json");
        BorerAreaThinkStore.write(target, "{\"scenes\":{}}");
        BorerAreaThinkStore.write(target, "{\"scenes\":{\"a\":1}}");
        assertEquals("{\"scenes\":{\"a\":1}}", Files.readString(target));
        assertFalse(Files.exists(target.resolveSibling("area-think.json.tmp")));
    }

    @Test void seedScoutSavesThroughTheAtomicHelper() throws Exception {
        var node = new org.objectweb.asm.tree.ClassNode();
        try (var in = getClass().getResourceAsStream("/dev/twob2tkit/structure/SeedScout.class")) {
            assertNotNull(in); new org.objectweb.asm.ClassReader(in).accept(node, 0);
        }
        var save = node.methods.stream().filter(m -> m.name.equals("save") && m.desc.equals("()V")).findFirst().orElseThrow();
        boolean atomic = false, direct = false;
        for (var i : save.instructions) if (i instanceof org.objectweb.asm.tree.MethodInsnNode c) {
            atomic |= c.owner.equals("dev/twob2tkit/AtomicFiles") && c.name.equals("write");
            direct |= c.name.equals("newBufferedWriter");
        }
        assertTrue(atomic); assertFalse(direct);
    }
}
