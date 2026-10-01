package dev.twob2tkit.structure;

import net.minecraft.core.Holder;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.registries.Registries;
import net.minecraft.data.registries.VanillaRegistries;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.biome.Climate;
import net.minecraft.world.level.biome.MultiNoiseBiomeSource;
import net.minecraft.world.level.biome.MultiNoiseBiomeSourceParameterList;
import net.minecraft.world.level.levelgen.NoiseGeneratorSettings;
import net.minecraft.world.level.levelgen.RandomState;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * Bounded seed-side hints for likely snowy Overworld terrain.
 *
 * <p>The world seed never appears in a result.  Every coordinate remains only
 * a hint until the multiplayer client has loaded it and the ordinary snow
 * survey confirms the server biome and natural snow blocks.</p>
 */
public final class OverworldSnowLocator {
	public static final int PROTOCOL = 1;
	public static final int STRIDE = 256;
	public static final int MAX_BATCH = 128;
	public static final int MIN_RADIUS = 256;
	public static final int MAX_RADIUS = 32768;
	private static final int[] SAMPLE_Y = {64, 128, 192, 256};
	private static final Set<String> SNOWY = Set.of(
		"minecraft:snowy_plains", "minecraft:ice_spikes", "minecraft:snowy_taiga",
		"minecraft:grove", "minecraft:snowy_slopes", "minecraft:jagged_peaks",
		"minecraft:frozen_peaks", "minecraft:frozen_river",
		"minecraft:frozen_ocean", "minecraft:deep_frozen_ocean"
	);

	private static HolderLookup.Provider vanillaLookup;
	private static int vanillaLookupBuilds;
	private static long cachedSeed = Long.MIN_VALUE;
	private static Climate.Sampler cachedSampler;
	private static MultiNoiseBiomeSource cachedBiomes;

	public record Candidate(int cursor, int x, int z, int sampleY, String biome, int distance) {}
	public record Batch(int cursor, int nextCursor, int processed, int total,
		boolean done, List<Candidate> candidates) {}
	public static final class SamplerUnavailable extends IllegalStateException {
		public SamplerUnavailable(String message,Throwable cause){super(message,cause);}
	}

	private OverworldSnowLocator() {}

	/** Ring-ordered batch: close hints are produced before distant hints. */
	public static synchronized Batch batch(long seed,
		int originX, int originZ, int radius, int cursor, int budget) {
		if (radius < MIN_RADIUS || radius > MAX_RADIUS)
			throw new IllegalArgumentException("Snow seed radius must be 256..32768");
		if (budget < 1 || budget > MAX_BATCH)
			throw new IllegalArgumentException("Snow seed batch must be 1..128 samples");
		int rings = (radius + STRIDE - 1) / STRIDE;
		int width = rings * 2 + 1;
		int total = Math.multiplyExact(width, width);
		if (cursor < 0 || cursor > total)
			throw new IllegalArgumentException("Snow seed cursor is outside the bounded grid");
		prepare(seed);
		int next = cursor, processed = 0;
		List<Candidate> found = new ArrayList<>();
		while (next < total && processed < budget) {
			int sampleCursor = next;
			int[] offset = ringOffset(next++);
			long dx = (long)offset[0] * STRIDE;
			long dz = (long)offset[1] * STRIDE;
			if (dx * dx + dz * dz > (long)radius * radius) continue;
			processed++;
			long rawX = (long)originX + dx, rawZ = (long)originZ + dz;
			if (rawX < Integer.MIN_VALUE || rawX > Integer.MAX_VALUE
				|| rawZ < Integer.MIN_VALUE || rawZ > Integer.MAX_VALUE) continue;
			int x = (int)rawX, z = (int)rawZ;
			Candidate candidate = snowyAt(sampleCursor, x, z,
				(int)Math.round(Math.hypot(dx, dz)));
			if (candidate != null) found.add(candidate);
		}
		return new Batch(cursor, next, processed, total, next >= total, List.copyOf(found));
	}

	/** Deterministic square-ring coordinate for a non-negative cursor. */
	static int[] ringOffset(int cursor) {
		if (cursor < 0) throw new IllegalArgumentException("Ring cursor must be non-negative");
		if (cursor == 0) return new int[]{0, 0};
		int ring = (int)Math.ceil((Math.sqrt(cursor + 1.0) - 1.0) / 2.0);
		int start = (2 * ring - 1) * (2 * ring - 1);
		int offset = cursor - start;
		int top = 2 * ring + 1;
		if (offset < top) return new int[]{-ring + offset, -ring};
		offset -= top;
		if (offset < 2 * ring) return new int[]{ring, -ring + 1 + offset};
		offset -= 2 * ring;
		if (offset < 2 * ring) return new int[]{ring - 1 - offset, ring};
		offset -= 2 * ring;
		return new int[]{-ring, ring - 1 - offset};
	}

	static boolean snowyBiome(String id) { return SNOWY.contains(id); }
	static int vanillaLookupBuilds(){return vanillaLookupBuilds;}
	static boolean vanillaLookupComplete(){
		HolderLookup.Provider provider=vanillaProvider();
		return provider.lookup(Registries.BIOME).isPresent()
			&&provider.lookup(Registries.NOISE).isPresent()
			&&provider.lookup(Registries.DENSITY_FUNCTION).isPresent()
			&&provider.lookup(Registries.NOISE_SETTINGS).isPresent()
			&&provider.lookupOrThrow(Registries.NOISE_SETTINGS)
				.get(NoiseGeneratorSettings.OVERWORLD).isPresent();
	}
	static String biomeAt(long seed,int x,int y,int z){
		prepare(seed);
		return cachedBiomes.getNoiseBiome(Math.floorDiv(x,4),Math.floorDiv(y,4),
			Math.floorDiv(z,4),cachedSampler).unwrapKey()
			.map(key->key.identifier().toString()).orElse("unknown");
	}

	private static Candidate snowyAt(int cursor, int x, int z, int distance) {
		for (int y : SAMPLE_Y) {
			Holder<Biome> holder = cachedBiomes.getNoiseBiome(
				Math.floorDiv(x, 4), Math.floorDiv(y, 4), Math.floorDiv(z, 4), cachedSampler);
			String biome = holder.unwrapKey()
				.map(key -> key.identifier().toString()).orElse("unknown");
			if (snowyBiome(biome)) return new Candidate(cursor, x, z, y, biome, distance);
		}
		return null;
	}

	private static void prepare(long seed) {
		if (cachedSeed == seed && cachedSampler != null && cachedBiomes != null) return;
		try {
			HolderLookup.Provider provider=vanillaProvider();
			RandomState state = RandomState.create(provider, NoiseGeneratorSettings.OVERWORLD, seed);
			MultiNoiseBiomeSourceParameterList list = new MultiNoiseBiomeSourceParameterList(
				MultiNoiseBiomeSourceParameterList.Preset.OVERWORLD,
				provider.lookupOrThrow(Registries.BIOME));
			cachedSeed = seed;
			cachedSampler = state.sampler();
			cachedBiomes = MultiNoiseBiomeSource.createFromList(list.parameters());
		} catch (RuntimeException error) {
			cachedSeed = Long.MIN_VALUE;
			cachedSampler = null;
			cachedBiomes = null;
			throw new SamplerUnavailable("Overworld seed biome sampler is unavailable", error);
		}
	}

	private static HolderLookup.Provider vanillaProvider(){
		if(vanillaLookup==null){vanillaLookup=VanillaRegistries.createLookup();vanillaLookupBuilds++;}
		return vanillaLookup;
	}
}
