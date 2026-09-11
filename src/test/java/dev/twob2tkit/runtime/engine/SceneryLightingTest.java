package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.SectionPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LightChunk;
import net.minecraft.world.level.chunk.LightChunkGetter;
import net.minecraft.world.level.lighting.LevelLightEngine;
import net.minecraft.world.level.material.FluidState;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/** Exercise Minecraft's actual light-column registration and lookup, not a boolean stand-in. */
class SceneryLightingTest {
	@org.junit.jupiter.api.BeforeAll static void bootstrapMinecraftRegistries() {
		net.minecraft.SharedConstants.tryDetectVersion();
		net.minecraft.server.Bootstrap.bootStrap();
	}
	private static LevelLightEngine lights() {
		BlockGetter height = new BlockGetter() {
			public BlockEntity getBlockEntity(BlockPos pos) { return null; }
			public BlockState getBlockState(BlockPos pos) { throw new AssertionError("No block sampling is needed for column flags"); }
			public FluidState getFluidState(BlockPos pos) { throw new AssertionError("No fluid sampling is needed for column flags"); }
			public int getMinY() { return -64; } public int getHeight() { return 384; }
		};
		return new LevelLightEngine(new LightChunkGetter() {
			public LightChunk getChunkForLighting(int x, int z) { return null; }
			public BlockGetter getLevel() { return height; }
		}, true, true);
	}
	@Test void screenshotCoordinatesAreLitWithSectionColumnKeyButNotTheOldChunkKey() {
		LevelLightEngine lights = lights();
		ChunkPos chunk = new ChunkPos(760873 >> 4, 797799 >> 4);
		lights.setLightEnabled(chunk, true);
		assertFalse(lights.lightOnInColumn(chunk.pack()), "Reproduces the 1.7.17 false-negative at the real screenshot location");
		assertTrue(lights.lightOnInColumn(SceneryCapturePolicy.lightColumnKey(chunk.x(), chunk.z())));
	}
	@Test void matchingKeysWorkAcrossPositiveNegativeAndOriginChunks() {
		LevelLightEngine lights = lights();
		for (ChunkPos chunk : new ChunkPos[]{ChunkPos.ZERO, new ChunkPos(1, 0), new ChunkPos(0, 1),
			new ChunkPos(-1, -1), new ChunkPos(-47554, 49862), new ChunkPos(47554, -49862)}) {
			long key = SceneryCapturePolicy.lightColumnKey(chunk.x(), chunk.z());
			assertEquals(chunk.x(), SectionPos.x(key)); assertEquals(chunk.z(), SectionPos.z(key)); assertEquals(0, SectionPos.y(key));
			assertFalse(lights.lightOnInColumn(key));
			lights.setLightEnabled(chunk, true); assertTrue(lights.lightOnInColumn(key));
			lights.setLightEnabled(chunk, false); assertFalse(lights.lightOnInColumn(key));
		}
	}
	@Test void enabledNeighbourDoesNotMakeMissingTargetLightLookReady() {
		LevelLightEngine lights = lights(); ChunkPos here = new ChunkPos(47554, 49862);
		lights.setLightEnabled(here, true);
		assertFalse(lights.lightOnInColumn(SceneryCapturePolicy.lightColumnKey(here.x() + 1, here.z())));
		assertFalse(SceneryCapturePolicy.ready(true, false, true, 10000));
		assertTrue(SceneryCapturePolicy.ready(true, lights.lightOnInColumn(SceneryCapturePolicy.lightColumnKey(here.x(), here.z())), true, 10));
	}
}
