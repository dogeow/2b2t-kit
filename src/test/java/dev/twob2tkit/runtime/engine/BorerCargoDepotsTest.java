package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.List;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoDepotsTest {
	@TempDir Path temp;
	@Test void onlyRecordedProjectChestsSurviveReloadAndFullStatusIsUpdated() throws Exception {
		Path p = temp.resolve("depots.json");
		var depots = new BorerCargoDepots(p, "server|dim|area-a");
		BlockPos chest = new BlockPos(-4, 65, 0);
		depots.remember(chest, false);
		depots = new BorerCargoDepots(p, "server|dim|area-a");
		assertEquals(chest, depots.sites().getFirst().pos());
		assertFalse(depots.sites().getFirst().full());
		depots.remember(chest, true);
		assertEquals(1, depots.sites().size()); assertTrue(depots.sites().getFirst().full());
	}
	@Test void differentServerDimensionOrAreaCannotTakeAnExistingChest() throws Exception {
		Path p = temp.resolve("depots.json");
		new BorerCargoDepots(p, "server-a|overworld|area-a").remember(BlockPos.ZERO, false);
		for (String key : new String[]{"server-b|overworld|area-a", "server-a|nether|area-a", "server-a|overworld|area-b"}) {
			assertTrue(new BorerCargoDepots(p, key).sites().isEmpty());
		}
		new BorerCargoDepots(p, "server-a|overworld|area-b").remember(new BlockPos(1, 2, 3), false);
		assertEquals(1, new BorerCargoDepots(p, "server-a|overworld|area-a").sites().size());
	}
	@Test void corruptFileIsNotOverwritten() throws Exception {
		Path p = temp.resolve("depots.json"); Files.writeString(p, "broken[");
		assertThrows(java.io.IOException.class, () -> new BorerCargoDepots(p, "a"));
		assertEquals("broken[", Files.readString(p));
	}
	@Test void deeperSliceFindsOldSurfaceChestsAndPreservesTheirFullStatus() throws Exception {
		Path file = temp.resolve("depots.json");
		BlockPos oldMin = new BlockPos(760864, -50, 797792), oldMax = new BlockPos(760879, 0, 797807);
		BlockPos full = new BlockPos(760872, 1, 797792), available = new BlockPos(760878, 1, 797792);
		var old = new BorerCargoDepots(file, "server|minecraft:overworld|" + oldMin + "|" + oldMax);
		old.remember(full, true); old.remember(available, false);
		var deep = new BorerCargoDepots(file, "server|minecraft:overworld", oldMin.below(9), oldMax.below(50));
		assertEquals(2, deep.sites().size());
		assertFalse(deep.sites().stream().filter(s -> s.pos().equals(full)).findFirst().orElseThrow().acceptsAny(Set.of("minecraft:diamond")));
		assertTrue(deep.sites().stream().filter(s -> s.pos().equals(available)).findFirst().orElseThrow().acceptsAny(Set.of("minecraft:diamond")));
	}
	@Test void canonicalCapacitySurvivesNewYBoundsAndDoesNotCrossServersOrFootprints() throws Exception {
		Path file = temp.resolve("depots.json"); BlockPos min = BlockPos.ZERO, max = new BlockPos(15, 60, 15), chest = new BlockPos(1, 61, 1);
		var original = new BorerCargoDepots(file, "server|overworld", min, max);
		original.remember(chest, true);
		assertTrue(new BorerCargoDepots(file, "server|overworld", min.below(64), max.below(110)).sites().getFirst().full());
		assertTrue(new BorerCargoDepots(file, "other|overworld", min, max).sites().isEmpty());
		assertTrue(new BorerCargoDepots(file, "server|nether", min, max).sites().isEmpty());
		assertTrue(new BorerCargoDepots(file, "server|overworld", min.east(), max.east()).sites().isEmpty());
	}
	@Test void confirmedCapacityOverridesLegacyFlagWithoutDeletingLegacyOrOtherProjects() throws Exception {
		Path file = temp.resolve("depots.json"); BlockPos min = BlockPos.ZERO, max = new BlockPos(15, 60, 15), chest = new BlockPos(1, 61, 1);
		String legacyKey = "server|overworld|" + min + "|" + max;
		new BorerCargoDepots(file, legacyKey).remember(chest, true);
		var current = new BorerCargoDepots(file, "server|overworld", min, max);
		current.remember(chest, false, List.of("minecraft:diamond"));
		var refreshed = new BorerCargoDepots(file, "server|overworld", min, max).sites().getFirst();
		assertTrue(refreshed.acceptsAny(Set.of("minecraft:diamond")));
		assertFalse(refreshed.acceptsAny(Set.of("minecraft:cobblestone")));
		assertTrue(new BorerCargoDepots(file, legacyKey).sites().getFirst().full());
	}
	@Test void bothHalvesOfAFullChestRemainExcludedAfterReloadAndChangingDepth() throws Exception {
		Path file = temp.resolve("depots.json"); BlockPos min = BlockPos.ZERO, max = new BlockPos(15, 20, 15);
		var depots = new BorerCargoDepots(file, "server|world", min, max);
		depots.remember(new BlockPos(1, 21, 1), true, List.of()); depots.remember(new BlockPos(2, 21, 1), true, List.of());
		var next = new BorerCargoDepots(file, "server|world", min.below(64), max.below(64));
		assertEquals(2, next.sites().size());
		assertTrue(next.sites().stream().noneMatch(s -> s.acceptsAny(Set.of("minecraft:diamond"))));
	}
}
