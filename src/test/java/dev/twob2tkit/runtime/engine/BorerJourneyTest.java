package dev.twob2tkit.runtime.engine;

import java.nio.file.*;
import java.io.IOException;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerJourneyTest {
	@TempDir Path root;
	private static final String OVERWORLD = "server:example.test|minecraft:overworld";
	private static final String NETHER = "server:example.test|minecraft:the_nether";
	private BorerTrail create(String scope) throws Exception {
		var t = new BorerTrail(new BorerTrailStore(root)); t.useScope(scope); return t;
	}

	@Test void hmclQuickPlayDefaultPortKeepsTheSameSavedJourney() throws Exception {
		String base="server:"+BorerTrail.canonicalServer("simpcraft.com")+"|minecraft:the_nether";
		var journey=create(base); journey.append(new BlockPos(95102,34,99719));journey.save(null);
		String quick="server:"+BorerTrail.canonicalServer("simpcraft.com:25565")+"|minecraft:the_nether";
		assertEquals(base,quick);assertEquals(journey.first(),create(quick).first());
		assertNotEquals(BorerTrail.canonicalServer("simpcraft.com:25566"),BorerTrail.canonicalServer("simpcraft.com"));
	}

	@Test void repeatedPauseSaveReloadAndFarRestartKeepTheFirstOriginAndAllPoints() throws Exception {
		BlockPos origin = new BlockPos(10, 70, 10);
		var t = create(OVERWORLD); t.append(origin);
		for (int run = 1; run <= 5; run++) {
			t.append(new BlockPos(10 + run * 40, 70, 10)); t.save(null);
			t = create(OVERWORLD);
			assertEquals(origin, t.first()); assertEquals(run + 1, t.size());
		}
		assertTrue(t.snapshot().contains("gap 1\n"));
	}

	@Test void continuousPausedWalkingExtendsTheRouteWithoutAGap() throws Exception {
		var t = create(OVERWORLD);
		for (int x = 0; x <= 60; x += 3) t.append(new BlockPos(x, 64, 0));
		t.save(null); var restarted = create(OVERWORLD);
		assertEquals(new BlockPos(0, 64, 0), restarted.first());
		assertEquals(21, restarted.size()); assertFalse(restarted.snapshot().contains("gap "));
	}

	@Test void dimensionAndServerChangesRestoreTheirOwnJourneys() throws Exception {
		var t = create(OVERWORLD); t.append(new BlockPos(100, 64, 100));
		t.useScope(NETHER); assertEquals(0, t.size()); t.append(new BlockPos(12, 70, 12));
		t.useScope("server:another.test|minecraft:overworld"); assertEquals(0, t.size()); t.append(new BlockPos(-5, 80, 8));
		t.useScope(OVERWORLD); assertEquals(new BlockPos(100, 64, 100), t.first());
		t.useScope(NETHER); assertEquals(new BlockPos(12, 70, 12), t.first());
	}

	@Test void newJourneyArchivesTheExactOldRouteBeforeSettingANewOrigin() throws Exception {
		var t = create(OVERWORLD); t.append(new BlockPos(1, 64, 1)); t.append(new BlockPos(4, 64, 1));
		String before = t.snapshot(); Path backup = t.startNewJourney(new BlockPos(90, 70, 90));
		assertEquals(before, Files.readString(backup));
		assertEquals(new BlockPos(90, 70, 90), create(OVERWORLD).first());
		assertEquals(1, create(OVERWORLD).size());
	}

	@Test void failedArchiveDoesNotChangeTheCurrentRouteOrDisk() throws Exception {
		var t = create(OVERWORLD); t.append(new BlockPos(1, 64, 1)); t.save(null);
		String before = t.snapshot(); Files.writeString(root.resolve("journeys/archive"), "block directory creation");
		assertThrows(IOException.class, () -> t.startNewJourney(new BlockPos(90, 70, 90)));
		assertEquals(before, t.snapshot()); assertEquals(before, new BorerTrailStore(root).read(OVERWORLD));
	}

	@Test void longRouteAndHotReloadDoNotDeleteTheEarlyReturnSegments() throws Exception {
		var t = create(OVERWORLD);
		for (int i = 0; i < 5100; i++) t.append(new BlockPos(i * 3, 64, 0));
		t.save(null); var loaded = create(OVERWORLD);
		assertEquals(5100, loaded.size()); assertEquals(new BlockPos(0, 64, 0), loaded.first());
		var hot = new BorerTrail(new BorerTrailStore(root)); hot.restore(loaded.snapshot()); hot.useScope(OVERWORLD);
		assertEquals(loaded.snapshot(), hot.snapshot());
		assertTrue(hot.snapshot().contains("3 64 0\n6 64 0\n"));
	}

	@Test void legacyMigrationIsClaimedOnlyOnceAndKeepsTheOriginalFile() throws Exception {
		String legacy = "portal 20 40 30\n100 64 100\n103 64 100\n";
		Files.writeString(root.resolve("borer-trail.txt"), legacy);
		var t = create(OVERWORLD); assertEquals(2, t.size()); assertNull(t.portal()); t.save(null);
		assertEquals(legacy, Files.readString(root.resolve("borer-trail.txt")));
		assertEquals(0, create(NETHER).size());
		try (var files = Files.list(root.resolve("journeys/archive"))) {
			assertEquals(legacy, Files.readString(files.findFirst().orElseThrow()));
		}
	}

	@Test void emptySavedJourneyDoesNotReloadTheLegacyRoute() throws Exception {
		Files.writeString(root.resolve("borer-trail.txt"), "10 64 10\n");
		var store = new BorerTrailStore(root); store.write(OVERWORLD, BorerTrailStore.header(OVERWORLD));
		assertEquals(0, create(OVERWORLD).size());
	}

	@Test void routeWorldMismatchIsRejectedAndCannotOverwriteTheStoredFile() throws Exception {
		var store = new BorerTrailStore(root);
		String first = BorerTrailStore.header(OVERWORLD) + "1 64 1\n";
		store.write(OVERWORLD, first);
		assertThrows(IOException.class, () -> store.write(OVERWORLD, BorerTrailStore.header(NETHER)));
		assertEquals(first, store.read(OVERWORLD));
	}

	@Test void returnStopsAtAnUnrecordedJumpRatherThanSkippingIt() {
		var points = List.of(new BlockPos(0, 64, 0), new BlockPos(80, 64, 0), new BlockPos(83, 64, 0));
		int index = BorerTrailPolicy.advanceReturnIndex(points, 2, Vec3.atBottomCenterOf(points.get(2)), Set.of(1));
		assertEquals(1, index);
		assertEquals(1, BorerTrailPolicy.advanceReturnIndex(points, index, Vec3.atBottomCenterOf(points.get(1)), Set.of(1)));
	}

	@Test void findingALaterPortalCannotReplaceTheLockedOrigin() throws Exception {
		var t = create(NETHER); t.append(new BlockPos(10, 64, 10));
		t.ensureFirst(new BlockPos(100, 70, 100));
		assertEquals(new BlockPos(10, 64, 10), t.first());
	}

	@Test void productionStartRestoresThenAppendsWithoutDistanceBasedClearing() throws Exception {
		var node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/BorerTrail.class")) {
			new ClassReader(in).accept(node, 0);
		}
		var method = node.methods.stream().filter(m -> m.name.equals("beginMiningSession")).findFirst().orElseThrow();
		var calls = new ArrayList<String>();
		for (var insn : method.instructions) if (insn instanceof MethodInsnNode call) calls.add(call.name);
		assertTrue(calls.indexOf("loadIfEmpty") < calls.indexOf("append"));
		assertFalse(calls.contains("clear")); assertFalse(calls.contains("resumeExistingTrail"));
	}
}
