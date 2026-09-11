package dev.twob2tkit.borer;

import com.google.gson.Gson;
import dev.twob2tkit.KitConfig;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.game.GameProvider;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class AreaDraftsTest {
    @TempDir static Path gameDir;
    private static final String WORLD = "test-server|minecraft:overworld";

    @BeforeAll static void isolatedConfigDirectory() {
        // Configure only the unit-test loader; all real save/load calls below use JUnit's temporary directory.
        var provider = (GameProvider) Proxy.newProxyInstance(GameProvider.class.getClassLoader(), new Class<?>[]{GameProvider.class},
            (proxy, method, args) -> {
                if (method.getName().equals("getLaunchDirectory")) return gameDir;
                throw new AssertionError("Unexpected loader call: " + method.getName());
            });
        FabricLoaderImpl.INSTANCE.setGameProvider(provider);
        net.minecraft.SharedConstants.tryDetectVersion(); net.minecraft.server.Bootstrap.bootStrap();
    }

    @Test void aSurvivesRealConfigSaveReloadAndCanBeCompletedLaterAtB() {
        var config = new KitConfig();
        var draft = AreaDrafts.open(config, WORLD);
        var aOnly = draft.edit("新区", "760981 76 797823", "", "30", "30", "30");
        assertTrue(AreaDrafts.store(config, draft, aOnly)); config.save();
        var loaded = KitConfig.load();
        var reopened = AreaDrafts.open(loaded, WORLD);
        assertEquals(aOnly, reopened);
        assertFalse(loaded.borerAreaASet); assertFalse(loaded.borerAreaBSet);
        var both = reopened.edit(reopened.name(), reopened.a(), "761010 47 797852", "30", "30", "30");
        assertTrue(AreaDrafts.store(loaded, reopened, both));
        var bounds = AreaForm.parse(both.a(), both.b(), -64, 320);
        assertEquals(new BlockPos(760981, 76, 797823), bounds.a());
        assertEquals(new BlockPos(761010, 47, 797852), bounds.b());
        assertFalse(loaded.borerAreaASet, "Completing a draft still must not apply it automatically");
    }

    @Test void bFirstAndUnfinishedManualInputSurviveJsonRoundTrip() {
        var config = new KitConfig(); var draft = AreaDrafts.open(config, WORLD);
        var edited = draft.edit("", "760981 76", "761010 47 797852", "", "16", "40");
        assertTrue(AreaDrafts.store(config, draft, edited));
        var gson = new Gson(); var restored = gson.fromJson(gson.toJson(config), KitConfig.class);
        assertEquals(edited, AreaDrafts.open(restored, WORLD));
        assertThrows(IllegalArgumentException.class, () -> AreaForm.parseDraft(edited.a(), edited.b(), -64, 320));
        assertFalse(restored.borerAreaASet); assertTrue(restored.areaProjects.isEmpty());
    }

    @Test void rebuildKeepsDraftButStaleInstanceCannotOverwriteANewerEdit() {
        var config = new KitConfig(); var first = AreaDrafts.open(config, WORLD);
        assertSame(first, AreaDrafts.open(config, WORLD));
        var second = first.edit("名字", "1 64 2", "", "16", "16", "40");
        assertTrue(AreaDrafts.store(config, first, second));
        assertSame(second, AreaDrafts.open(config, WORLD));
        assertFalse(AreaDrafts.store(config, first, first)); assertSame(second, config.borerAreaDraft);
    }

    @Test void draftDoesNotMutateCommittedAreaProjectOrOtherSettings() {
        var config = new KitConfig(); var project = project(); config.areaProjects.add(project);
        BorerAreaProjects.apply(config, project);
        config.targetX = 12345; config.borerLastMode = "ORE";
        var original = AreaDrafts.signature(config); var draft = AreaDrafts.open(config, WORLD);
        assertTrue(AreaDrafts.store(config, draft, draft.edit("新工地", "8 70 9", "", "30", "30", "30")));
        assertEquals(original, AreaDrafts.signature(config)); assertEquals("ORE", config.borerLastMode);
        assertEquals(12345, config.targetX); assertEquals(1, config.areaProjects.size());
        assertEquals("old", project.id); assertEquals("旧工程", project.name); assertEquals(10, project.ax);
        assertTrue(AreaDrafts.hasUnappliedCorners(config), "Project manager must not save the old bounds as the new draft");
    }

    @Test void explicitlyReloadingEvenTheSameProjectWinsOverTheOldScreenDraft() {
        var config = new KitConfig(); var project = project(); config.areaProjects.add(project);
        BorerAreaProjects.apply(config, project);
        var first = AreaDrafts.open(config, WORLD);
        var edited = first.edit("未保存", "9 65 7", "", "16", "16", "40");
        assertTrue(AreaDrafts.store(config, first, edited));
        config.loadAreaProject("old");
        assertNull(config.borerAreaDraft);
        assertFalse(AreaDrafts.store(config, edited, edited));
        var opened = AreaDrafts.open(config, WORLD);
        assertEquals("旧工程", opened.name()); assertEquals("10 64 20", opened.a()); assertEquals("25 0 35", opened.b());
        assertFalse(AreaDrafts.hasUnappliedCorners(config));
    }

    @Test void commandsAndDifferentCommittedBoundsInvalidateTheOldDraft() {
        var config = new KitConfig(); var first = AreaDrafts.open(config, WORLD);
        BorerAreaMarks.setA(config, new BlockPos(4, 70, 5));
        assertNull(config.borerAreaDraft); assertFalse(AreaDrafts.store(config, first, first));
        var next = AreaDrafts.open(config, WORLD); assertEquals("4 70 5", next.a());
        config.borerAreaAx = 6;
        assertFalse(AreaDrafts.store(config, next, next));
        assertEquals("6 70 5", AreaDrafts.open(config, WORLD).a());
    }

    @Test void rebaseAfterValidatedApplyKeepsDraftAcrossReopen() {
        var config = new KitConfig(); var first = AreaDrafts.open(config, WORLD);
        var edited = first.edit("完整", "1 64 2", "16 0 17", "16", "16", "65");
        var bounds = AreaForm.parse(edited.a(), edited.b(), -64, 320);
        config.borerAreaASet = config.borerAreaBSet = true;
        config.borerAreaAx = bounds.a().getX(); config.borerAreaAy = bounds.a().getY(); config.borerAreaAz = bounds.a().getZ();
        config.borerAreaBx = bounds.b().getX(); config.borerAreaBy = bounds.b().getY(); config.borerAreaBz = bounds.b().getZ();
        config.upsertAreaProject("完整", KitConfig.DIM_OVERWORLD);
        config.borerAreaDraft = edited.rebase(config);
        assertEquals(config.borerAreaDraft, AreaDrafts.open(config, WORLD));
        assertEquals("完整", config.areaProjects.getFirst().name);
    }

    @Test void differentServerOrDimensionCannotMixCornerDrafts() {
        for (String context : new String[]{"other-server|minecraft:overworld", "test-server|minecraft:the_nether"}) {
            var config = new KitConfig(); var first = AreaDrafts.open(config, WORLD);
            assertTrue(AreaDrafts.store(config, first, first.edit("旧世界草稿", "1 64 2", "", "30", "30", "30")));
            assertEquals("", AreaDrafts.open(config, context).a());
        }
    }

    @Test void legacyConfigsAndMissingDraftFieldsHaveSafeDefaults() {
        var gson = new Gson();
        var config = gson.fromJson("{\"borerAreaASet\":true,\"borerAreaAx\":10,\"borerAreaAy\":64,\"borerAreaAz\":20}", KitConfig.class);
        var draft = AreaDrafts.open(config, WORLD);
        assertEquals("10 64 20", draft.a()); assertEquals("", draft.b()); assertEquals("30", draft.length());
        var partial = gson.fromJson("{\"a\":\"1 64 2\"}", AreaDrafts.Draft.class);
        assertEquals("", partial.b()); assertEquals("", partial.source()); assertEquals("30", partial.height());
    }

    private static KitConfig.AreaProject project() {
        var project = new KitConfig.AreaProject(); project.id = "old"; project.name = "旧工程";
        project.ax = 10; project.ay = 64; project.az = 20; project.bx = 25; project.by = 0; project.bz = 35;
        return project;
    }
}
