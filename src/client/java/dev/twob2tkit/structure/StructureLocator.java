package dev.twob2tkit.structure;

import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.RegistryAccess;
import net.minecraft.core.Vec3i;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.ResourceKey;
import net.minecraft.tags.BiomeTags;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.biome.Biomes;
import net.minecraft.world.level.biome.Climate;
import net.minecraft.world.level.biome.MultiNoiseBiomeSource;
import net.minecraft.world.level.biome.MultiNoiseBiomeSourceParameterList;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.DensityFunction;
import net.minecraft.world.level.levelgen.DensityFunctions;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.LegacyRandomSource;
import net.minecraft.world.level.levelgen.NoiseGeneratorSettings;
import net.minecraft.world.level.levelgen.RandomState;
import net.minecraft.world.level.levelgen.WorldgenRandom;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadStructurePlacement;
import net.minecraft.world.level.levelgen.structure.placement.RandomSpreadType;
import net.minecraft.world.level.levelgen.structure.placement.StructurePlacement;
import net.minecraft.world.phys.AABB;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import dev.twob2tkit.nether.NetherBiomePolicy;

/**
 * 用世界种子按原版随机散布规则，估算附近结构候选区块。
 * <p>
 * 不保证服务器一定生成；已加载区块会再过滤明显对不上的结果。
 */
public final class StructureLocator {
	/** 搜寻维度。 */
	public enum Dimension {
		OVERWORLD, NETHER, END
	}

	/** 结构/下界群系种类及原版散布参数。 */
	public enum Kind {
		VILLAGE("村庄", Dimension.OVERWORLD, NetherRole.NONE, 34, 8, RandomSpreadType.LINEAR, 10387312, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		STRONGHOLD("要塞", Dimension.OVERWORLD, NetherRole.NONE, 1, 0, RandomSpreadType.LINEAR, 0, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		DESERT_TEMPLE("沙漠神殿", Dimension.OVERWORLD, NetherRole.NONE, 32, 8, RandomSpreadType.LINEAR, 14357617, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		JUNGLE_TEMPLE("丛林神庙", Dimension.OVERWORLD, NetherRole.NONE, 32, 8, RandomSpreadType.LINEAR, 14357619, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		WITCH_HUT("沼泽小屋", Dimension.OVERWORLD, NetherRole.NONE, 32, 8, RandomSpreadType.LINEAR, 14357620, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		IGLOO("雪屋", Dimension.OVERWORLD, NetherRole.NONE, 32, 8, RandomSpreadType.LINEAR, 14357618, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		OUTPOST("掠夺者前哨", Dimension.OVERWORLD, NetherRole.NONE, 32, 8, RandomSpreadType.LINEAR, 165745296, 0.2F, StructurePlacement.FrequencyReductionMethod.LEGACY_TYPE_1),
		MONUMENT("海底神殿", Dimension.OVERWORLD, NetherRole.NONE, 32, 5, RandomSpreadType.TRIANGULAR, 10387313, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		SHIPWRECK("沉船", Dimension.OVERWORLD, NetherRole.NONE, 24, 4, RandomSpreadType.LINEAR, 165745295, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		TRIAL_CHAMBER("试炼密室", Dimension.OVERWORLD, NetherRole.NONE, 34, 12, RandomSpreadType.LINEAR, 94251327, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		ANCIENT_CITY("远古城市", Dimension.OVERWORLD, NetherRole.NONE, 24, 8, RandomSpreadType.LINEAR, 20083232, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		TRAIL_RUINS("踪迹废墟", Dimension.OVERWORLD, NetherRole.NONE, 34, 8, RandomSpreadType.LINEAR, 83469867, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		OCEAN_RUIN("海底废墟", Dimension.OVERWORLD, NetherRole.NONE, 20, 8, RandomSpreadType.LINEAR, 14357621, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		FORTRESS("下界要塞", Dimension.NETHER, NetherRole.FORTRESS, 27, 4, RandomSpreadType.LINEAR, 30084232, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		BASTION("堡垒遗迹", Dimension.NETHER, NetherRole.BASTION, 27, 4, RandomSpreadType.LINEAR, 30084232, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		TREASURE_BASTION("藏宝室堡垒", Dimension.NETHER, NetherRole.TREASURE, 27, 4, RandomSpreadType.LINEAR, 30084232, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		NETHER_FOSSIL("下界化石", Dimension.NETHER, NetherRole.NONE, 2, 1, RandomSpreadType.LINEAR, 14357921, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		RUINED_PORTAL("传送门残骸", Dimension.NETHER, NetherRole.NONE, 40, 15, RandomSpreadType.LINEAR, 34222645, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		WARPED_FOREST("诡异森林", Biomes.WARPED_FOREST),
		CRIMSON_FOREST("绯红森林", Biomes.CRIMSON_FOREST),
		SOUL_SAND_VALLEY("灵魂沙谷", Biomes.SOUL_SAND_VALLEY),
		BASALT_DELTAS("玄武岩洲", Biomes.BASALT_DELTAS),
		END_CITY("末地城", Dimension.END, NetherRole.NONE, 20, 11, RandomSpreadType.TRIANGULAR, 10387313, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT),
		END_CITY_SHIP("带船末地城", Dimension.END, NetherRole.NONE, 20, 11, RandomSpreadType.TRIANGULAR, 10387313, 1.0F, StructurePlacement.FrequencyReductionMethod.DEFAULT);

		final String label;
		public final Dimension dimension;
		final NetherRole netherRole;
		final RandomSpreadStructurePlacement placement;
		final ResourceKey<Biome> netherBiome;

		Kind(String label, ResourceKey<Biome> netherBiome) {
			this.label = label;
			this.dimension = Dimension.NETHER;
			this.netherRole = NetherRole.NONE;
			this.netherBiome = netherBiome;
			this.placement = new RandomSpreadStructurePlacement(
				Vec3i.ZERO, StructurePlacement.FrequencyReductionMethod.DEFAULT, 1.0F, 0, Optional.empty(),
				1, 0, RandomSpreadType.LINEAR
			);
		}

		Kind(
			String label,
			Dimension dimension,
			NetherRole netherRole,
			int spacing,
			int separation,
			RandomSpreadType spread,
			int salt,
			float frequency,
			StructurePlacement.FrequencyReductionMethod reduction
		) {
			this.label = label;
			this.dimension = dimension;
			this.netherRole = netherRole;
			this.netherBiome = null;
			this.placement = new RandomSpreadStructurePlacement(
				Vec3i.ZERO, reduction, frequency, salt, Optional.empty(), spacing, separation, spread
			);
		}

		boolean isNetherBiome() {
			return netherBiome != null;
		}

		/**
		 * 持久化用的稳定 id，和枚举名解耦：将来重命名枚举不会让配置里的老标记静默失效。
		 * 用 switch 而不是构造器参数，新增 Kind 时编译器会直接报缺分支。
		 */
		public String stableId() {
			return switch (this) {
				case VILLAGE -> "village";
				case STRONGHOLD -> "stronghold";
				case DESERT_TEMPLE -> "desert_temple";
				case JUNGLE_TEMPLE -> "jungle_temple";
				case WITCH_HUT -> "witch_hut";
				case IGLOO -> "igloo";
				case OUTPOST -> "outpost";
				case MONUMENT -> "monument";
				case SHIPWRECK -> "shipwreck";
				case TRIAL_CHAMBER -> "trial_chamber";
				case ANCIENT_CITY -> "ancient_city";
				case TRAIL_RUINS -> "trail_ruins";
				case OCEAN_RUIN -> "ocean_ruin";
				case FORTRESS -> "fortress";
				case BASTION -> "bastion";
				case TREASURE_BASTION -> "treasure_bastion";
				case NETHER_FOSSIL -> "nether_fossil";
				case RUINED_PORTAL -> "ruined_portal";
				case WARPED_FOREST -> "warped_forest";
				case CRIMSON_FOREST -> "crimson_forest";
				case SOUL_SAND_VALLEY -> "soul_sand_valley";
				case BASALT_DELTAS -> "basalt_deltas";
				case END_CITY, END_CITY_SHIP -> "end_city";
			};
		}

		/** 该维度可选的结构类型。 */
		static Kind[] forDimension(Dimension dimension) {
			List<Kind> kinds = new ArrayList<>();
			for (Kind kind : values()) {
				if (kind.dimension == dimension) kinds.add(kind);
			}
			return kinds.toArray(Kind[]::new);
		}

		/** 维度默认结构类型。 */
		public static Kind defaultFor(Dimension dimension) {
			return switch (dimension) {
				case NETHER -> FORTRESS;
				case END -> END_CITY;
				case OVERWORLD -> VILLAGE;
			};
		}
	}

	/** 下界要塞/堡垒同 salt 时的角色。 */
	public enum NetherRole {
		NONE, FORTRESS, BASTION, TREASURE
	}

	/** 下界复合体细分类（要塞或各类堡垒）。 */
	public enum NetherPick {
		FORTRESS("下界要塞"),
		HOUSING("住房型堡垒"),
		HOGLIN("猪堡"),
		TREASURE("藏宝室型堡垒"),
		BRIDGE("桥型堡垒");

		final String label;

		NetherPick(String label) {
			this.label = label;
		}

		boolean isFortress() {
			return this == FORTRESS;
		}

		boolean isBastion() {
			return this != FORTRESS;
		}

		boolean isTreasure() {
			return this == TREASURE;
		}
	}

	/** 一次结构命中：类型、坐标、距离与显示名。 */
	public record Hit(Kind kind, int x, int z, int distance, String label) {
	}

	/** 标记管理页用：把配置里存的稳定 id 还原成中文名，认不出来就原样显示。 */
	public static String labelForId(String id) {
		if (id == null || id.isBlank()) return "未知结构";
		for (Kind kind : Kind.values()) {
			if (kind.stableId().equals(id)) return kind.label;
		}
		return id;
	}

	private static long cachedEndSeed = Long.MIN_VALUE;
	private static DensityFunction cachedEndIslands;
	private static long cachedNetherSeed = Long.MIN_VALUE;
	private static Climate.Sampler cachedNetherSampler;
	private static MultiNoiseBiomeSource cachedNetherBiomes;

	private StructureLocator() {
	}

	@FunctionalInterface
	public interface XzFilter {
		boolean test(int x, int z);
	}

	/** 按种子与随机散布规则搜附近候选结构。 */
	public static List<Hit> nearby(long seed, int originX, int originZ, Kind kind, int radiusBlocks, int limit) {
		return nearby(seed, originX, originZ, kind, radiusBlocks, limit, null);
	}

	/** 按种子与随机散布规则搜附近候选结构。 */
	public static List<Hit> nearby(
		long seed,
		ClientLevel level,
		int originX,
		int originY,
		int originZ,
		Kind kind,
		int radiusBlocks,
		int limit,
		XzFilter filter
	) {
		if (kind.isNetherBiome()) {
			return nearbyNetherBiome(seed, level, originX, originY, originZ, kind, radiusBlocks, limit, filter);
		}
		return nearby(seed, originX, originZ, kind, radiusBlocks, limit, filter);
	}

	/** 按种子与随机散布规则搜附近候选结构。 */
	public static List<Hit> nearby(long seed, int originX, int originZ, Kind kind, int radiusBlocks, int limit, XzFilter filter) {
		if (kind.isNetherBiome()) return List.of();
		if (kind == Kind.STRONGHOLD) return nearbyStrongholds(seed, originX, originZ, radiusBlocks, limit, filter);
		int originChunkX = originX >> 4;
		int originChunkZ = originZ >> 4;
		int spacing = Math.max(1, kind.placement.spacing());
		int regionRadius = Math.max(1, (radiusBlocks >> 4) / spacing + 2);
		int originRegionX = Math.floorDiv(originChunkX, spacing);
		int originRegionZ = Math.floorDiv(originChunkZ, spacing);
		List<Hit> hits = new ArrayList<>();
		for (int rx = originRegionX - regionRadius; rx <= originRegionX + regionRadius; rx++) {
			for (int rz = originRegionZ - regionRadius; rz <= originRegionZ + regionRadius; rz++) {
				ChunkPos chunk = kind.placement.getPotentialStructureChunk(seed, rx * spacing, rz * spacing);
				if (!kind.placement.applyAdditionalChunkRestrictions(chunk.x(), chunk.z(), seed)) continue;
				if (kind == Kind.END_CITY || kind == Kind.END_CITY_SHIP) {
					if (!canPlaceEndCity(seed, chunk.x(), chunk.z())) continue;
					boolean ship = EndCityLayout.hasShip(seed, chunk.x(), chunk.z());
					if (kind == Kind.END_CITY_SHIP && !ship) continue;
					int cityX = (chunk.x() << 4) + 7;
					int cityZ = (chunk.z() << 4) + 7;
					int cityDx = cityX - originX;
					int cityDz = cityZ - originZ;
					int cityDist = (int)Math.round(Math.hypot(cityDx, cityDz));
					if (cityDist > radiusBlocks) continue;
					if (filter != null && !filter.test(cityX, cityZ)) continue;
					hits.add(new Hit(kind, cityX, cityZ, cityDist, ship ? "带船末地城" : "末地城"));
					continue;
				}
				BlockPos pos = kind.placement.getLocatePos(chunk);
				int dx = pos.getX() - originX;
				int dz = pos.getZ() - originZ;
				int distance = (int)Math.round(Math.hypot(dx, dz));
				if (distance > radiusBlocks) continue;
				if (filter != null && !filter.test(pos.getX(), pos.getZ())) continue;
				String label = kind.label;
				if (kind.netherRole != NetherRole.NONE) {
					NetherPick pick = classifyNetherComplex(seed, chunk.x(), chunk.z());
					if (kind.netherRole == NetherRole.FORTRESS && !pick.isFortress()) continue;
					if (kind.netherRole == NetherRole.BASTION && !pick.isBastion()) continue;
					if (kind.netherRole == NetherRole.TREASURE && !pick.isTreasure()) continue;
					label = pick.label;
				}
				hits.add(new Hit(kind, pos.getX(), pos.getZ(), distance, label));
			}
		}
		hits.sort(Comparator.comparingInt(Hit::distance));
		if (hits.size() > limit) return new ArrayList<>(hits.subList(0, limit));
		return hits;
	}

	/**
	 * 下界群系按种子采噪声。步长 32 格，192 格内算同一片，列出离人最近的几片。
	 */
	public static List<Hit> nearbyNetherBiome(
		long seed,
		ClientLevel level,
		int originX,
		int originY,
		int originZ,
		Kind kind,
		int radiusBlocks,
		int limit,
		XzFilter filter
	) {
		if (level == null || kind.netherBiome == null) return List.of();
		if (!prepareNetherNoise(level.registryAccess(), seed)) return List.of();
		int y = NetherBiomePolicy.sampleY(originY);
		int step = NetherBiomePolicy.SAMPLE_STEP;
		int radius = Math.max(step, radiusBlocks);
		List<int[]> matches = new ArrayList<>();
		for (int x = originX - radius; x <= originX + radius; x += step) {
			for (int z = originZ - radius; z <= originZ + radius; z += step) {
				int dx = x - originX;
				int dz = z - originZ;
				if ((long) dx * dx + (long) dz * dz > (long) radius * radius) continue;
				if (filter != null && !filter.test(x, z)) continue;
				if (!netherBiomeAt(x, y, z, kind.netherBiome)) continue;
				matches.add(new int[]{x, z, (int) Math.round(Math.hypot(dx, dz))});
			}
		}
		matches.sort(Comparator.comparingInt(a -> a[2]));
		List<Hit> hits = new ArrayList<>();
		for (int[] sample : matches) {
			boolean fresh = true;
			for (Hit kept : hits) {
				if (!NetherBiomePolicy.newPatch(sample[0] - kept.x(), sample[1] - kept.z())) {
					fresh = false;
					break;
				}
			}
			if (!fresh) continue;
			hits.add(new Hit(kind, sample[0], sample[1], sample[2], kind.label));
			if (hits.size() >= limit) break;
		}
		return hits;
	}

	/** 准备下界 MultiNoise 与 RandomState。 */
	private static boolean prepareNetherNoise(RegistryAccess access, long seed) {
		if (cachedNetherSampler != null && cachedNetherBiomes != null && cachedNetherSeed == seed) return true;
		try {
			RandomState state = RandomState.create(access, NoiseGeneratorSettings.NETHER, seed);
			MultiNoiseBiomeSourceParameterList list = new MultiNoiseBiomeSourceParameterList(
				MultiNoiseBiomeSourceParameterList.Preset.NETHER,
				access.lookupOrThrow(Registries.BIOME));
			cachedNetherSeed = seed;
			cachedNetherSampler = state.sampler();
			cachedNetherBiomes = MultiNoiseBiomeSource.createFromList(list.parameters());
			return true;
		} catch (RuntimeException ignored) {
			cachedNetherSeed = Long.MIN_VALUE;
			cachedNetherSampler = null;
			cachedNetherBiomes = null;
			return false;
		}
	}

	/** 坐标处是否为目标下界群系。 */
	private static boolean netherBiomeAt(int x, int y, int z, ResourceKey<Biome> want) {
		Holder<Biome> holder = cachedNetherBiomes.getNoiseBiome(
			NetherBiomePolicy.quart(x),
			NetherBiomePolicy.quart(y),
			NetherBiomePolicy.quart(z),
			cachedNetherSampler);
		return holder.is(want);
	}

	/**
	 * 原版要塞是 concentric_rings（distance=32, spread=3, count=128），不是随机网格。
	 * 这里算出环上的候选区块；真正位置还会因群系最多偏约 112 格。
	 */
	public static List<Hit> nearbyStrongholds(long seed, int originX, int originZ, int radiusBlocks, int limit, XzFilter filter) {
		RandomSource random = RandomSource.create();
		random.setSeed(seed);
		double angle = random.nextDouble() * Math.PI * 2.0;
		int distance = 32;
		int count = 128;
		int ringCount = 3;
		int placedOnRing = 0;
		int ring = 0;
		List<Hit> hits = new ArrayList<>();
		for (int n = 0; n < count; n++) {
			double dist = 4.0 * distance + distance * ring * 6.0 + (random.nextDouble() - 0.5) * distance * 2.5;
			int chunkX = (int)Math.round(Math.cos(angle) * dist);
			int chunkZ = (int)Math.round(Math.sin(angle) * dist);
			random.fork();
			int x = (chunkX << 4) + 8;
			int z = (chunkZ << 4) + 8;
			int range = (int)Math.round(Math.hypot(x - originX, z - originZ));
			if (range <= radiusBlocks && (filter == null || filter.test(x, z))) {
				hits.add(new Hit(Kind.STRONGHOLD, x, z, range, Kind.STRONGHOLD.label));
			}
			angle += Math.PI * 2.0 / ringCount;
			placedOnRing++;
			if (placedOnRing == ringCount) {
				ring++;
				placedOnRing = 0;
				ringCount += 2 * ringCount / (ring + 1);
				ringCount = Math.min(ringCount, count - n);
				angle += random.nextDouble() * Math.PI * 2.0;
			}
		}
		hits.sort(Comparator.comparingInt(Hit::distance));
		if (hits.size() > limit) return new ArrayList<>(hits.subList(0, limit));
		return hits;
	}

	/**
	 * 已加载区块再核对：群系不对，或周围都在视野里却没有塔/旗帜/掠夺者，就丢掉空点。
	 * 26.1 的 {@code ClientLevel.hasChunkAt} 恒为 true，必须问 chunk source。
	 */
	public static List<Hit> rejectLoadedMisses(ClientLevel level, List<Hit> hits) {
		if (level == null || hits.isEmpty()) return hits;
		List<Hit> kept = new ArrayList<>();
		for (Hit hit : hits) {
			if (keepLoadedHit(level, hit)) kept.add(hit);
		}
		return kept;
	}

	/** 已加载区块是否仍像该结构。 */
	private static boolean keepLoadedHit(ClientLevel level, Hit hit) {
		if (hit.kind() != Kind.OUTPOST) return true;
		if (!chunkReallyLoaded(level, hit.x(), hit.z())) return true;
		int surface = level.getHeight(Heightmap.Types.WORLD_SURFACE, hit.x(), hit.z());
		Holder<Biome> biome = level.getBiome(new BlockPos(hit.x(), Math.max(64, surface), hit.z()));
		if (!outpostBiome(biome)) return false;
		if (!outpostAreaLoaded(level, hit.x(), hit.z())) return true;
		return hasOutpostEvidence(level, hit.x(), hit.z(), surface);
	}

	/** 客户端 {@code hasChunk}/{@code hasChunkAt} 在 26.1 里永远 true，不能用来判断视野。 */
	private static boolean chunkReallyLoaded(ClientLevel level, int x, int z) {
		return level.getChunkSource().hasChunk(x >> 4, z >> 4);
	}

	/** 前哨周边是否已加载够。 */
	private static boolean outpostAreaLoaded(ClientLevel level, int x, int z) {
		for (int dx = -24; dx <= 24; dx += 16) {
			for (int dz = -24; dz <= 24; dz += 16) {
				if (!chunkReallyLoaded(level, x + dx, z + dz)) return false;
			}
		}
		return true;
	}

	/** 是否适合掠夺者前哨的群系。 */
	private static boolean outpostBiome(Holder<Biome> biome) {
		if (biome.is(BiomeTags.HAS_PILLAGER_OUTPOST)) return true;
		String name = biome.getRegisteredName();
		int colon = name.indexOf(':');
		String path = colon >= 0 ? name.substring(colon + 1) : name;
		if (path.equals("forest") || path.equals("flower_forest") || path.equals("birch_forest")
			|| path.contains("jungle") || path.contains("swamp") || path.contains("ocean")
			|| path.contains("river") || path.contains("beach") || path.contains("dark_forest")) {
			return false;
		}
		return path.contains("plains") || path.contains("desert") || path.contains("savanna")
			|| path.contains("taiga") || path.equals("meadow") || path.equals("grove")
			|| path.contains("snowy") || path.contains("ice") || path.contains("peaks")
			|| path.contains("windswept") || path.contains("cherry");
	}

	/** 地表是否有前哨证据。 */
	private static boolean hasOutpostEvidence(ClientLevel level, int x, int z, int surface) {
		AABB box = new AABB(x - 32, surface - 16, z - 32, x + 32, surface + 40, z + 32);
		if (!level.getEntities(EntityType.PILLAGER, box, entity -> entity.isAlive()).isEmpty()) return true;
		int darkOak = 0;
		int banners = 0;
		BlockPos.MutableBlockPos cursor = new BlockPos.MutableBlockPos();
		int minY = Math.max(level.getMinY(), surface - 8);
		int maxY = Math.min(level.getMaxY(), surface + 28);
		for (int dx = -20; dx <= 20; dx += 2) {
			for (int dz = -20; dz <= 20; dz += 2) {
				int wx = x + dx;
				int wz = z + dz;
				if (!chunkReallyLoaded(level, wx, wz)) continue;
				for (int y = minY; y <= maxY; y += 2) {
					BlockState state = level.getBlockState(cursor.set(wx, y, wz));
					if (state.is(Blocks.WHITE_BANNER) || state.is(Blocks.WHITE_WALL_BANNER)
						|| state.is(Blocks.GRAY_BANNER) || state.is(Blocks.GRAY_WALL_BANNER)) {
						banners++;
					}
					if (state.is(Blocks.DARK_OAK_LOG) || state.is(Blocks.STRIPPED_DARK_OAK_LOG)
						|| state.is(Blocks.DARK_OAK_PLANKS) || state.is(Blocks.DARK_OAK_FENCE)
						|| state.is(Blocks.DARK_OAK_STAIRS)) {
						darkOak++;
					}
					if (banners > 0 || darkOak >= 10) return true;
				}
			}
		}
		return false;
	}

	/**
	 * 原版末地城：外岛高地（岛噪声 &gt; 0.25）且 5×5 角落最低地面 ≥ 60。
	 * 只判高地会把矮岛列出来，飞过去没有城。
	 */
	public static boolean canPlaceEndCity(long seed, int chunkX, int chunkZ) {
		if (!isEndHighlands(seed, chunkX, chunkZ)) return false;
		WorldgenRandom random = new WorldgenRandom(new LegacyRandomSource(0L));
		random.setLargeFeatureSeed(seed, chunkX, chunkZ);
		int rot = random.nextInt(4);
		int ox = 5;
		int oz = 5;
		if (rot == 1) ox = -5;
		else if (rot == 2) {
			ox = -5;
			oz = -5;
		} else if (rot == 3) oz = -5;
		int x = (chunkX << 4) + 7;
		int z = (chunkZ << 4) + 7;
		int min = endIslandSurfaceY(seed, x, z);
		min = Math.min(min, endIslandSurfaceY(seed, x, z + oz));
		min = Math.min(min, endIslandSurfaceY(seed, x + ox, z));
		min = Math.min(min, endIslandSurfaceY(seed, x + ox, z + oz));
		return min >= 60;
	}

	/**
	 * 原版末地城只生成在高地：主岛 1024 格内是末地群系，小岛噪声太低。
	 * 高地判定和 {@code TheEndBiomeSource} 一样，岛噪声大于 0.25。
	 */
	public static boolean isEndHighlands(long seed, int chunkX, int chunkZ) {
		if ((long)chunkX * chunkX + (long)chunkZ * chunkZ <= 4096L) return false;
		int x = (chunkX << 4) + 8;
		int z = (chunkZ << 4) + 8;
		return endIslandDensity(seed, x, z) > 0.25;
	}

	/** 岛噪声换算成大约的地面 Y。3D 噪声还会上下晃几格，60 是原版硬门槛。 */
	private static int endIslandSurfaceY(long seed, int blockX, int blockZ) {
		return (int)Math.floor(endIslandDensity(seed, blockX, blockZ) * 128.0 + 8.0);
	}

	/** 末地外岛密度噪声。 */
	private static double endIslandDensity(long seed, int blockX, int blockZ) {
		if (cachedEndIslands == null || cachedEndSeed != seed) {
			cachedEndSeed = seed;
			cachedEndIslands = DensityFunctions.endIslands(seed);
		}
		return cachedEndIslands.compute(new DensityFunction.SinglePointContext(blockX, 0, blockZ));
	}

	/**
	 * 要塞和堡垒共用 nether_complexes（盐 30084232，权重 2:3）。
	 * 堡垒起点池再按旋转后 nextInt(4) 分成住房/猪堡/藏宝室/桥。
	 */
	public static NetherPick classifyNetherComplex(long seed, int chunkX, int chunkZ) {
		WorldgenRandom pickRandom = new WorldgenRandom(new LegacyRandomSource(0L));
		pickRandom.setLargeFeatureSeed(seed, chunkX, chunkZ);
		if (pickRandom.nextInt(5) < 2) return NetherPick.FORTRESS;
		WorldgenRandom jigsaw = new WorldgenRandom(new LegacyRandomSource(0L));
		jigsaw.setLargeFeatureSeed(seed, chunkX, chunkZ);
		jigsaw.nextInt(4);
		return switch (jigsaw.nextInt(4)) {
			case 0 -> NetherPick.HOUSING;
			case 1 -> NetherPick.HOGLIN;
			case 2 -> NetherPick.TREASURE;
			default -> NetherPick.BRIDGE;
		};
	}
}
