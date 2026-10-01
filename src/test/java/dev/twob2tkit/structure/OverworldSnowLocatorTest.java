package dev.twob2tkit.structure;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeAll;

import java.util.HashSet;

import static org.junit.jupiter.api.Assertions.*;

class OverworldSnowLocatorTest {
	@BeforeAll static void bootstrapVanillaRegistries(){
		net.minecraft.SharedConstants.tryDetectVersion();
		net.minecraft.server.Bootstrap.bootStrap();
	}
	@Test void ringCursorIsUniqueNearFirstAndBounded() {
		var seen = new HashSet<String>();
		for (int cursor = 0; cursor < 81; cursor++) {
			int[] point = OverworldSnowLocator.ringOffset(cursor);
			assertTrue(seen.add(point[0] + ":" + point[1]));
			int ring = Math.max(Math.abs(point[0]), Math.abs(point[1]));
			assertEquals((int)Math.ceil((Math.sqrt(cursor + 1.0) - 1.0) / 2.0), ring);
		}
		assertArrayEquals(new int[]{0, 0}, OverworldSnowLocator.ringOffset(0));
		assertArrayEquals(new int[]{-1, -1}, OverworldSnowLocator.ringOffset(1));
		assertArrayEquals(new int[]{1, 1}, OverworldSnowLocator.ringOffset(5));
		assertThrows(IllegalArgumentException.class,
			() -> OverworldSnowLocator.ringOffset(-1));
	}

	@Test void onlyExplicitSnowBiomesBecomeTravelHints() {
		assertTrue(OverworldSnowLocator.snowyBiome("minecraft:snowy_plains"));
		assertTrue(OverworldSnowLocator.snowyBiome("minecraft:frozen_peaks"));
		assertTrue(OverworldSnowLocator.snowyBiome("minecraft:deep_frozen_ocean"));
		assertFalse(OverworldSnowLocator.snowyBiome("minecraft:plains"));
		assertFalse(OverworldSnowLocator.snowyBiome("unknown"));
	}

	@Test void realVanillaProviderIsDeterministicAndFindsASnowHint() {
		int buildsBefore=OverworldSnowLocator.vanillaLookupBuilds();
		long coldStart=System.nanoTime();
		assertTrue(OverworldSnowLocator.vanillaLookupComplete(),
			"vanilla BIOME/NOISE/DENSITY_FUNCTION/NOISE_SETTINGS must all exist");
		OverworldSnowLocator.Candidate found=null;int cursor=0;
		while(found==null){
			var batch=OverworldSnowLocator.batch(0L,0,0,32768,cursor,128);
			if(!batch.candidates().isEmpty())found=batch.candidates().getFirst();
			if(batch.done())break;cursor=batch.nextCursor();
		}
		assertNotNull(found,"vanilla provider should identify at least one snowy candidate");
		System.out.println("OverworldSnowLocator vanilla cold start/sample ms="
			+(System.nanoTime()-coldStart)/1_000_000L);
		assertTrue(OverworldSnowLocator.snowyBiome(found.biome()));
		String original=OverworldSnowLocator.biomeAt(0L,found.x(),found.sampleY(),found.z());
		OverworldSnowLocator.biomeAt(1L,found.x(),found.sampleY(),found.z());
		assertEquals(original,
			OverworldSnowLocator.biomeAt(0L,found.x(),found.sampleY(),found.z()),
			"alternating seeds must not contaminate the cached sampler");
		long hotStart=System.nanoTime();
		var repeat=OverworldSnowLocator.batch(0L,0,0,32768,found.cursor(),1);
		System.out.println("OverworldSnowLocator cached single-sample us="
			+(System.nanoTime()-hotStart)/1_000L);
		assertFalse(repeat.candidates().isEmpty());
		assertEquals(found,repeat.candidates().getFirst());
		int buildsAfter=OverworldSnowLocator.vanillaLookupBuilds();
		assertTrue(buildsAfter==buildsBefore||buildsAfter==buildsBefore+1);
		OverworldSnowLocator.biomeAt(2L,0,64,0);
		assertEquals(buildsAfter,OverworldSnowLocator.vanillaLookupBuilds(),
			"the vanilla lookup provider is built once and reused across seeds");
	}
}
