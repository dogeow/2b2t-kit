package dev.twob2tkit;

import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.game.GameProvider;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class KitConfigSaveSoonTest {
    @TempDir static Path directory;
    @BeforeAll static void isolatedLoader() {
        var provider = (GameProvider) Proxy.newProxyInstance(GameProvider.class.getClassLoader(), new Class<?>[]{GameProvider.class}, (p, m, a) -> {
            if (m.getName().equals("getLaunchDirectory")) return directory; throw new AssertionError(m.getName()); });
        FabricLoaderImpl.INSTANCE.setGameProvider(provider);
    }

    @Test void deferredSaveWaitsForTheWindowAndNothingPendingNeverSaves() {
        assertFalse(KitConfig.saveDue(0, 1_000_000));
        assertFalse(KitConfig.saveDue(10_000, 10_000 + KitConfig.SAVE_SOON_MILLIS - 1));
        assertTrue(KitConfig.saveDue(10_000, 10_000 + KitConfig.SAVE_SOON_MILLIS));
    }

    @Test void hurtBookkeepingIsDeferredWhileDisconnectAndExitFlushIt() throws Exception {
        var combat = calls("dev/twob2tkit/combat/CombatWatch", "noteHurt");
        assertTrue(combat.contains("saveSoon"));
        assertFalse(combat.contains("save"), "a poison tick every second must not rewrite the whole config");
        assertTrue(calls("dev/twob2tkit/KitClient", "onEndTick").contains("flushSoon"));
        var lambdas = new java.util.ArrayList<String>();
        var node = node("dev/twob2tkit/KitClient");
        for (var m : node.methods) if (m.name.startsWith("lambda$")) lambdas.addAll(names(m));
        assertTrue(lambdas.contains("flushPending"), "disconnect and exit both flush");
        assertTrue(lambdas.contains("isSameThread") && lambdas.contains("execute"), "a network-thread disconnect hands the flush to the client thread");
    }

    private static org.objectweb.asm.tree.ClassNode node(String cls) throws Exception {
        var node = new org.objectweb.asm.tree.ClassNode();
        try (var in = KitConfigSaveSoonTest.class.getResourceAsStream("/" + cls + ".class")) { assertNotNull(in); new org.objectweb.asm.ClassReader(in).accept(node, 0); }
        return node;
    }
    private static java.util.List<String> names(org.objectweb.asm.tree.MethodNode m) {
        var out = new java.util.ArrayList<String>();
        for (var i : m.instructions) if (i instanceof org.objectweb.asm.tree.MethodInsnNode c) out.add(c.name);
        return out;
    }
    private static java.util.List<String> calls(String cls, String method) throws Exception {
        return names(node(cls).methods.stream().filter(m -> m.name.equals(method)).findFirst().orElseThrow());
    }
    @Test void configIsSavedCompactlyAndPrettyFilesStillLoad() {
        var config = new KitConfig();
        String saved = KitConfig.GSON.toJson(config);
        assertFalse(saved.contains("\n"), "the multi-megabyte config should not be pretty printed");
        String pretty = new com.google.gson.GsonBuilder().setPrettyPrinting().create().toJson(config);
        assertEquals(saved, KitConfig.GSON.toJson(KitConfig.GSON.fromJson(pretty, KitConfig.class)));
    }
    @Test void aFailedSaveKeepsTheChangePendingForARetry() throws Exception {
        var save = node("dev/twob2tkit/KitConfig").methods.stream().filter(m -> m.name.equals("save") && m.desc.equals("()V")).findFirst().orElseThrow();
        var writes = new java.util.ArrayList<Integer>(); int index = 0; int written = -1;
        for (var i : save.instructions) {
            if (i instanceof org.objectweb.asm.tree.MethodInsnNode c && c.name.equals("write")) written = index;
            if (i instanceof org.objectweb.asm.tree.FieldInsnNode f && f.name.equals("saveRequestedAt") && f.getOpcode() == org.objectweb.asm.Opcodes.PUTFIELD) writes.add(index);
            index++;
        }
        assertTrue(written >= 0 && writes.size() >= 2, "cleared on success and re-armed on failure");
        assertTrue(writes.get(0) > written, "the pending flag is only cleared after the file was written");
    }
}
