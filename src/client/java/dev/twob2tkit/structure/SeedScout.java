package dev.twob2tkit.structure;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.CommonPlayerSpawnInfo;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.tags.BiomeTags;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.component.MapDecorations;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.biome.BiomeManager;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BannerBlockEntity;
import net.minecraft.world.level.block.entity.BellBlockEntity;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.entity.ChestBlockEntity;
import net.minecraft.world.level.block.entity.SpawnerBlockEntity;
import net.minecraft.world.level.block.entity.TrialSpawnerBlockEntity;
import net.minecraft.world.level.block.entity.vault.VaultBlockEntity;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.saveddata.maps.MapDecorationTypes;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;

import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.OptionalLong;
import java.util.Random;
import java.util.Set;
import dev.twob2tkit.KitClient;

/**
 * 种子侦察：收集结构/地图/群系线索，配合 Seedcracker 或手动试种子。
 * <p>
 * 状态落在 {@code config/2b2t-kit/seed-scout.json}；有世界种子后多数扫描会停。
 */
public final class SeedScout {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
	private static final Path STORE = FabricLoader.getInstance().getConfigDir().resolve("2b2t-kit/seed-scout.json");
	private static final Path REPORT = FabricLoader.getInstance().getConfigDir().resolve("2b2t-kit/seed-report.txt");

	private Store store = new Store();
	private int ticks;
	private String notice = "";
	private int noticeColor = 0xA0A0A0;
	private BlockPos lastBiomeSample = BlockPos.ZERO;

	/** 从 seed-scout.json 读入；丢掉已废弃的地牢/试炼密室记录。 */
	public void load() {
		if (!Files.exists(STORE)) return;
		try (Reader reader = Files.newBufferedReader(STORE)) {
			Store loaded = GSON.fromJson(reader, Store.class);
			if (loaded != null) {
				if (loaded.findings == null) loaded.findings = new ArrayList<>();
				int before = loaded.findings.size();
				loaded.findings.removeIf(finding -> Kind.DUNGEON.name().equals(finding.kind)
					|| Kind.TRIAL_CHAMBER.name().equals(finding.kind));
				store = loaded;
				if (store.findings.size() != before) save();
			}
		} catch (Exception exception) {
			KitClient.LOGGER.warn("Could not read seed scout store", exception);
		}
	}

	/** 写回 seed-scout.json。 */
	public void save() {
		try {
			Files.createDirectories(STORE.getParent());
			try (Writer writer = Files.newBufferedWriter(STORE)) {
				GSON.toJson(store, writer);
			}
		} catch (IOException exception) {
			KitClient.LOGGER.warn("Could not save seed scout store", exception);
		}
	}

	/** 登录包里的哈希种子与维度；单人可直接取真种子。 */
	public void captureSpawnInfo(CommonPlayerSpawnInfo info) {
		if (info == null) return;
		store.hashedSeed = info.seed();
		store.hasHashedSeed = true;
		store.flat = info.isFlat();
		store.debug = info.isDebug();
		if (info.dimension() != null) store.lastDimension = info.dimension().identifier().toString();
		trySingleplayerSeed(Minecraft.getInstance());
		if (store.crackedSeed != null && matchesHash(store.crackedSeed)) {
			notice("哈希种子与已保存结果一致", 0x55FF55);
		}
		save();
	}

	/** 周期性扫描实体/地表/地图/群系，并尝试导入 Seedcracker。 */
	public void tick(Minecraft client) {
		ticks++;
		if (client.player == null || client.level == null) return;
		trySingleplayerSeed(client);
		if (hasWorldSeed()) return;
		if (ticks % 40 == 0) importSeedcrackerIfReady();
		if (ticks % 10 == 0) scanNearby(client);
		if (ticks % 20 == 0) {
			scanChunkEntities(client);
			scanLoadedSurfaces(client);
		}
		if (ticks % 40 == 0) scanMaps(client);
		if (ticks % 30 == 0) sampleBiome(client);
		if (ticks % 10 == 0) {
			try {
				emitGizmos(client);
			} catch (IllegalStateException ignored) {
			}
		}
	}

	/** 是否已有破解出的世界种子。 */
	public boolean hasWorldSeed() {
		return store.crackedSeed != null;
	}

	/** 持久化状态对象。 */
	public Store store() {
		return store;
	}

	/** 最近一条界面提示。 */
	public String notice() {
		return notice;
	}

	/** 提示颜色。 */
	public int noticeColor() {
		return noticeColor;
	}

	/** 普通特征估算比特。 */
	public int regularBits() {
		return bits(false);
	}

	/** 可提升特征估算比特。 */
	public int liftBits() {
		return bits(true);
	}

	/** 哈希种子显示文案。 */
	public String hashedLabel() {
		return store.hasHashedSeed ? Long.toString(store.hashedSeed) : "还没进过世界";
	}

	/** 已破解种子显示文案。 */
	public String resultLabel() {
		if (store.crackedSeed != null) return String.valueOf(store.crackedSeed);
		if (store.singleplayerSeed != null) return store.singleplayerSeed + "（单人世界，服务器不会给这个）";
		return "还没有完整种子";
	}

	/** 手动试完整世界种子是否匹配哈希。 */
	public String tryFullSeed(String raw) {
		Long seed = parseSeed(raw);
		if (seed == null) return "不是有效种子（数字或任意字符串）";
		if (!store.hasHashedSeed) {
			store.crackedSeed = seed;
			save();
			return "当前没有哈希种子，已记下候选：" + seed + "。进服后再点一次可核对。";
		}
		if (matchesHash(seed)) {
			store.crackedSeed = seed;
			save();
			return "哈希对上了，这就是世界种子：" + seed;
		}
		return "哈希对不上。这个数不是当前维度的世界种子。";
	}

	/** Seedcracker 进度一行字。 */
	public String seedcrackerProgress() {
		return SeedcrackerBridge.snapshot().line();
	}

	/** Pulls a finished world seed from SeedcrackerX when that mod has one. */
	public String importSeedcrackerIfReady() {
		String poked = SeedcrackerBridge.pokeIfReady();
		Long seed = SeedcrackerBridge.worldSeed();
		if (seed == null) {
			if (!SeedcrackerBridge.installed()) return "还没装 SeedcrackerX。算 48 位结构种子要用这个模组，不需要网页 API。";
			return poked;
		}
		if (!store.hasHashedSeed) {
			store.crackedSeed = seed;
			save();
			return "已从 SeedcrackerX 读到种子：" + seed;
		}
		if (matchesHash(seed)) {
			store.crackedSeed = seed;
			save();
			notice("已从 SeedcrackerX 读到完整种子：" + seed, 0x55FF55);
			return "已从 SeedcrackerX 读到完整种子：" + seed;
		}
		return "SeedcrackerX 的种子和进服哈希对不上：" + seed;
	}

	/** 用结构种子 lifting 凑世界种子。 */
	public String tryStructureSeed(String raw) {
		Long value = parseLong(raw);
		if (value == null) return "请填 48 位结构种子（SeedcrackerX 中间结果，或别人给的 structure seed）";
		if (!store.hasHashedSeed) return "还没有哈希种子，先正常进一次服";
		Long world = liftFromStructureSeed(store.hashedSeed, value);
		if (world == null) return "这 65536 个组合都对不上哈希。结构种子可能不对，或不是这个世界。";
		store.structureSeed = value & ((1L << 48) - 1);
		store.crackedSeed = world;
		save();
		return "已用哈希解开完整种子：" + world;
	}

	/** 把准星/脚下标成指定结构线索。 */
	public String markLookedStructure(Minecraft client, Kind kind) {
		if (hasWorldSeed()) return "已经有完整种子，不再记地牢和结构点";
		if (client.player == null || client.level == null) return "不在世界里";
		BlockPos pos = lookedOrFeet(client);
		addFinding(kind, client.level.dimension(), pos, "手动标记");
		save();
		return "已标记 " + kind.label + " @ " + format(pos);
	}

	/** 把当前区块标成史莱姆线索。 */
	public String markSlime(Minecraft client) {
		if (hasWorldSeed()) return "已经有完整种子，不再记地牢和结构点";
		if (client.player == null || client.level == null) return "不在世界里";
		BlockPos pos = client.player.blockPosition();
		addFinding(Kind.SLIME_CHUNK, client.level.dimension(), pos, "玩家确认这里刷过史莱姆");
		save();
		return "已记下史莱姆区块 " + (pos.getX() >> 4) + "," + (pos.getZ() >> 4);
	}

	/** 清空线索与种子结果。 */
	public String clearData() {
		Long hashed = store.hasHashedSeed ? store.hashedSeed : null;
		store = new Store();
		if (hashed != null) {
			store.hasHashedSeed = true;
			store.hashedSeed = hashed;
		}
		save();
		return "已清空采集数据（哈希种子还留着）";
	}

	/** 导出文本报告到 seed-report.txt。 */
	public String exportReport(Minecraft client) {
		String text = buildReport();
		try {
			Files.createDirectories(REPORT.getParent());
			Files.writeString(REPORT, text);
		} catch (IOException exception) {
			return "写文件失败：" + exception.getMessage();
		}
		if (client.keyboardHandler != null) client.keyboardHandler.setClipboard(text);
		return "已复制到剪贴板，并保存到 config/2b2t-kit/seed-report.txt";
	}

	/** 复制已破解种子到剪贴板。 */
	public String copyResult(Minecraft client) {
		String value = store.crackedSeed != null ? String.valueOf(store.crackedSeed)
			: store.hasHashedSeed ? "hashed:" + store.hashedSeed : "";
		if (value.isEmpty()) return "还没有可复制的结果";
		if (client.keyboardHandler != null) client.keyboardHandler.setClipboard(value);
		return "已复制：" + value;
	}

	/** 史莱姆线索是否与候选种子一致。 */
	public boolean slimeMatches(long seed, Finding finding) {
		return isSlimeChunk(seed, finding.x >> 4, finding.z >> 4);
	}

	/** 集成服务器取世界种子。 */
	private void trySingleplayerSeed(Minecraft client) {
		if (client == null || !client.hasSingleplayerServer() || client.getSingleplayerServer() == null) return;
		long seed = client.getSingleplayerServer().overworld().getSeed();
		store.singleplayerSeed = seed;
		if (store.crackedSeed == null) store.crackedSeed = seed;
	}

	/** 扫已加载区块方块实体。 */
	private void scanChunkEntities(Minecraft client) {
		LocalPlayer player = client.player;
		ClientLevel level = client.level;
		int cx = player.chunkPosition().x();
		int cz = player.chunkPosition().z();
		for (int dx = -6; dx <= 6; dx++) {
			for (int dz = -6; dz <= 6; dz++) {
				if (!level.hasChunk(cx + dx, cz + dz)) continue;
				LevelChunk chunk = level.getChunk(cx + dx, cz + dz);
				for (BlockEntity entity : chunk.getBlockEntities().values()) {
					inspectBlockEntity(level, entity);
				}
			}
		}
	}

	/** 根据箱子/刷怪笼等记线索。 */
	private void inspectBlockEntity(ClientLevel level, BlockEntity entity) {
		BlockPos pos = entity.getBlockPos();
		if (entity instanceof SpawnerBlockEntity spawner) {
			String mob = displayName(spawner.getSpawner().getOrCreateDisplayEntity(level, pos));
			Kind kind = classifySpawner(level, pos, mob);
			if (kind == Kind.DUNGEON) return;
			addFinding(kind, level.dimension(), pos, mob);
			return;
		}
		if (entity instanceof TrialSpawnerBlockEntity || entity instanceof VaultBlockEntity) {
			return;
		}
		if (entity instanceof BellBlockEntity) {
			addFinding(Kind.VILLAGE, level.dimension(), pos, "铃铛");
			return;
		}
		if (entity instanceof BannerBlockEntity banner && looksLikeIllagerBanner(banner)) {
			addFinding(Kind.OUTPOST, level.dimension(), pos, "不祥旗帜");
			return;
		}
		if (entity instanceof ChestBlockEntity) {
			classifyChest(level, pos);
		}
	}

	/** 扫玩家附近方块证据。 */
	private void scanNearby(Minecraft client) {
		LocalPlayer player = client.player;
		ClientLevel level = client.level;
		BlockPos origin = player.blockPosition();
		for (int dx = -16; dx <= 16; dx++) {
			for (int dz = -16; dz <= 16; dz++) {
				for (int dy = -8; dy <= 10; dy++) {
					inspectStructureBlock(level, origin.offset(dx, dy, dz));
				}
			}
		}
	}

	/** Scans the ground of loaded chunks so flying at Y=333 still sees temples and huts. */
	private void scanLoadedSurfaces(Minecraft client) {
		LocalPlayer player = client.player;
		ClientLevel level = client.level;
		int cx = player.chunkPosition().x();
		int cz = player.chunkPosition().z();
		for (int dx = -6; dx <= 6; dx++) {
			for (int dz = -6; dz <= 6; dz++) {
				if (!level.hasChunk(cx + dx, cz + dz)) continue;
				scanChunkSurface(level, level.getChunk(cx + dx, cz + dz));
			}
		}
	}

	/** 扫一个区块地表结构迹象。 */
	private void scanChunkSurface(ClientLevel level, LevelChunk chunk) {
		var heightmap = chunk.getOrCreateHeightmapUnprimed(Heightmap.Types.WORLD_SURFACE);
		int minX = chunk.getPos().getMinBlockX();
		int minZ = chunk.getPos().getMinBlockZ();
		int minY = level.getMinY();
		int maxY = level.getMaxY();
		for (int lx = 2; lx < 16; lx += 4) {
			for (int lz = 2; lz < 16; lz += 4) {
				int surface = heightmap.getFirstAvailable(lx, lz) - 1;
				if (surface < minY || surface > maxY) continue;
				for (int dy = -20; dy <= 3; dy++) {
					int y = surface + dy;
					if (y < minY || y > maxY) continue;
					inspectStructureBlock(level, new BlockPos(minX + lx, y, minZ + lz));
				}
			}
		}
	}

	/** 根据方块形态分类结构。 */
	private void inspectStructureBlock(ClientLevel level, BlockPos pos) {
		if (!level.hasChunkAt(pos)) return;
		BlockState state = level.getBlockState(pos);
		if (state.isAir()) return;
		if (state.is(Blocks.BLUE_TERRACOTTA) && sandstoneAround(level, pos)) {
			addFinding(Kind.DESERT_PYRAMID, level.dimension(), pos, "蓝色陶瓦");
		} else if (state.is(Blocks.GOLD_BLOCK) && prismarineAround(level, pos)) {
			addFinding(Kind.MONUMENT, level.dimension(), pos, "海晶灯+金块");
		} else if (state.is(Blocks.CRYING_OBSIDIAN)) {
			addFinding(Kind.RUINED_PORTAL, level.dimension(), pos, "哭泣的黑曜石");
		} else if (state.is(Blocks.PURPUR_PILLAR)) {
			addFinding(Kind.END_CITY, level.dimension(), pos, "紫珀柱");
		} else if (state.is(Blocks.PACKED_ICE) && looksLikeIgloo(level, pos)) {
			addFinding(Kind.IGLOO, level.dimension(), pos, "雪屋特征");
		} else if (state.is(Blocks.CAULDRON) && swampy(level, pos)) {
			addFinding(Kind.SWAMP_HUT, level.dimension(), pos, "沼泽炼药锅");
		} else if (state.is(Blocks.DISPENSER) && looksLikeJungleTemple(level, pos)) {
			addFinding(Kind.JUNGLE_TEMPLE, level.dimension(), pos, "神庙发射器");
		} else if (state.is(Blocks.OBSIDIAN) && endPillar(level, pos)) {
			addFinding(Kind.END_PILLAR, level.dimension(), pillarTop(level, pos), "末地柱顶");
		} else if (isShipwreckPlank(state) && looksLikeShipwreck(level, pos)) {
			addFinding(Kind.SHIPWRECK, level.dimension(), pos, "水边船木");
		}
	}

	/** 箱子周边推断结构类型。 */
	private void classifyChest(ClientLevel level, BlockPos pos) {
		if (sandstoneAround(level, pos)) {
			addFinding(Kind.DESERT_PYRAMID, level.dimension(), pos, "沙石房间箱子");
			return;
		}
		if (looksLikeJungleTemple(level, pos)) {
			addFinding(Kind.JUNGLE_TEMPLE, level.dimension(), pos, "神庙箱子");
			return;
		}
		if (looksLikeShipwreck(level, pos)) {
			addFinding(Kind.SHIPWRECK, level.dimension(), pos, "沉船箱子");
		}
	}

	/** 附近是否有水。 */
	private boolean waterNear(ClientLevel level, BlockPos pos) {
		for (int dx = -2; dx <= 2; dx++) {
			for (int dy = -2; dy <= 2; dy++) {
				for (int dz = -2; dz <= 2; dz++) {
					if (!level.getBlockState(pos.offset(dx, dy, dz)).getFluidState().isEmpty()) return true;
				}
			}
		}
		return false;
	}

	/** 附近是否有木板。 */
	private boolean planksNear(ClientLevel level, BlockPos pos) {
		int n = 0;
		for (int dx = -3; dx <= 3; dx++) {
			for (int dy = -2; dy <= 2; dy++) {
				for (int dz = -3; dz <= 3; dz++) {
					if (isShipwreckPlank(level.getBlockState(pos.offset(dx, dy, dz))) && ++n >= 6) return true;
				}
			}
		}
		return false;
	}

	/** 是否沉船用木板。 */
	private static boolean isShipwreckPlank(BlockState state) {
		return state.is(Blocks.OAK_PLANKS) || state.is(Blocks.SPRUCE_PLANKS) || state.is(Blocks.DARK_OAK_PLANKS)
			|| state.is(Blocks.JUNGLE_PLANKS) || state.is(Blocks.OAK_STAIRS) || state.is(Blocks.SPRUCE_STAIRS)
			|| state.is(Blocks.DARK_OAK_STAIRS) || state.is(Blocks.JUNGLE_STAIRS);
	}

	/** 扫背包探险家地图。 */
	private void scanMaps(Minecraft client) {
		LocalPlayer player = client.player;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			readMap(client.level, stack);
		}
		readMap(client.level, player.getOffhandItem());
	}

	/** 从地图装饰读结构线索。 */
	private void readMap(ClientLevel level, ItemStack stack) {
		MapDecorations decorations = stack.get(DataComponents.MAP_DECORATIONS);
		if (decorations == null) return;
		for (MapDecorations.Entry entry : decorations.decorations().values()) {
			Kind kind = mapKind(entry.type());
			if (kind == null) continue;
			BlockPos pos = BlockPos.containing(entry.x(), level.getSeaLevel(), entry.z());
			addFinding(kind, level.dimension(), pos, "探险家地图 " + String.format(Locale.ROOT, "%.0f, %.0f", entry.x(), entry.z()));
		}
	}

	/** 采样当前位置群系。 */
	private void sampleBiome(Minecraft client) {
		BlockPos pos = client.player.blockPosition();
		if (pos.distSqr(lastBiomeSample) < 96 * 96) return;
		lastBiomeSample = pos.immutable();
		Holder<Biome> biome = client.level.getBiome(pos);
		addFinding(Kind.BIOME, client.level.dimension(), pos, biome.getRegisteredName());
		save();
	}

	/** 刷怪笼类型推断结构。 */
	private Kind classifySpawner(ClientLevel level, BlockPos pos, String mob) {
		String id = mob.toLowerCase(Locale.ROOT);
		if (id.contains("cave_spider") || id.contains("洞穴蜘蛛")) return Kind.MINESHAFT;
		if (id.contains("blaze") || id.contains("烈焰")) return Kind.FORTRESS;
		if (id.contains("silverfish") || id.contains("蠹虫")) return Kind.STRONGHOLD;
		if (dungeonFloor(level, pos).chars().filter(ch -> ch == 'C' || ch == 'M').count() >= 20) return Kind.DUNGEON;
		return Kind.DUNGEON;
	}

	/** 地牢地板材质提示。 */
	private String dungeonFloor(ClientLevel level, BlockPos spawner) {
		StringBuilder builder = new StringBuilder(81);
		int y = spawner.getY() - 1;
		for (int dz = -4; dz <= 4; dz++) {
			for (int dx = -4; dx <= 4; dx++) {
				BlockState state = level.getBlockState(new BlockPos(spawner.getX() + dx, y, spawner.getZ() + dz));
				if (state.is(Blocks.MOSSY_COBBLESTONE)) builder.append('M');
				else if (state.is(Blocks.COBBLESTONE)) builder.append('C');
				else builder.append('.');
			}
		}
		return builder.toString();
	}

	/** 附近是否砂岩。 */
	private boolean sandstoneAround(ClientLevel level, BlockPos pos) {
		int n = 0;
		for (int dx = -3; dx <= 3; dx++) {
			for (int dz = -3; dz <= 3; dz++) {
				if (level.getBlockState(pos.offset(dx, 0, dz)).is(Blocks.SANDSTONE) && ++n >= 8) return true;
			}
		}
		return false;
	}

	/** 附近是否海晶。 */
	private boolean prismarineAround(ClientLevel level, BlockPos pos) {
		int lanterns = 0;
		int prism = 0;
		for (int dx = -4; dx <= 4; dx++) {
			for (int dy = -2; dy <= 4; dy++) {
				for (int dz = -4; dz <= 4; dz++) {
					BlockState state = level.getBlockState(pos.offset(dx, dy, dz));
					if (state.is(Blocks.SEA_LANTERN)) lanterns++;
					if (state.is(Blocks.PRISMARINE) || state.is(Blocks.DARK_PRISMARINE) || state.is(Blocks.PRISMARINE_BRICKS)) {
						prism++;
					}
				}
			}
		}
		return lanterns >= 2 && prism >= 12;
	}

	/** 附近是否雪。 */
	private boolean snowAround(ClientLevel level, BlockPos pos) {
		int snow = 0;
		for (int dx = -3; dx <= 3; dx++) {
			for (int dz = -3; dz <= 3; dz++) {
				if (level.getBlockState(pos.offset(dx, 0, dz)).is(Blocks.SNOW_BLOCK) && ++snow >= 6) return true;
			}
		}
		return false;
	}

	/** 是否像沼泽小屋环境。 */
	private boolean swampy(ClientLevel level, BlockPos pos) {
		Holder<Biome> biome = level.getBiome(pos);
		return biome.is(BiomeTags.HAS_SWAMP_HUT) || biome.getRegisteredName().contains("swamp");
	}

	/** 是否像丛林神庙。 */
	private boolean looksLikeJungleTemple(ClientLevel level, BlockPos pos) {
		return mossyAround(level, pos) && cobbleAround(level, pos) && dispenserNear(level, pos);
	}

	/** 是否像雪屋。 */
	private boolean looksLikeIgloo(ClientLevel level, BlockPos pos) {
		return snowAround(level, pos) && (countBlock(level, pos, Blocks.SNOW_BLOCK, 4) >= 8
			|| countBlock(level, pos, Blocks.WHITE_CARPET, 3) >= 1
			|| countBlock(level, pos, Blocks.OAK_TRAPDOOR, 3) >= 1);
	}

	/** 是否像沉船。 */
	private boolean looksLikeShipwreck(ClientLevel level, BlockPos pos) {
		return waterNear(level, pos) && planksNear(level, pos) && countBlock(level, pos, Blocks.OAK_FENCE, 4)
			+ countBlock(level, pos, Blocks.DARK_OAK_FENCE, 4) + countBlock(level, pos, Blocks.SPRUCE_FENCE, 4) >= 2;
	}

	/** 附近是否圆石。 */
	private boolean cobbleAround(ClientLevel level, BlockPos pos) {
		return countBlock(level, pos, Blocks.COBBLESTONE, 4) >= 10
			|| countBlock(level, pos, Blocks.MOSSY_COBBLESTONE, 4) >= 8;
	}

	/** 附近是否发射器。 */
	private boolean dispenserNear(ClientLevel level, BlockPos pos) {
		return countBlock(level, pos, Blocks.DISPENSER, 4) >= 1;
	}

	/** 半径内某种方块计数。 */
	private int countBlock(ClientLevel level, BlockPos pos, net.minecraft.world.level.block.Block block, int radius) {
		int n = 0;
		for (int dx = -radius; dx <= radius; dx++) {
			for (int dy = -2; dy <= 3; dy++) {
				for (int dz = -radius; dz <= radius; dz++) {
					if (level.getBlockState(pos.offset(dx, dy, dz)).is(block)) n++;
				}
			}
		}
		return n;
	}

	/** 附近是否苔石。 */
	private boolean mossyAround(ClientLevel level, BlockPos pos) {
		int mossy = 0;
		for (int dx = -4; dx <= 4; dx++) {
			for (int dy = -1; dy <= 3; dy++) {
				for (int dz = -4; dz <= 4; dz++) {
					if (level.getBlockState(pos.offset(dx, dy, dz)).is(Blocks.MOSSY_COBBLESTONE) && ++mossy >= 8) return true;
				}
			}
		}
		return false;
	}

	/** 是否末地柱。 */
	private boolean endPillar(ClientLevel level, BlockPos pos) {
		if (!level.dimension().identifier().getPath().contains("end")) return false;
		return level.getBlockState(pos.above()).is(Blocks.OBSIDIAN) || level.getBlockState(pos.below()).is(Blocks.OBSIDIAN);
	}

	/** 末地柱顶坐标。 */
	private BlockPos pillarTop(ClientLevel level, BlockPos pos) {
		BlockPos top = pos;
		while (level.getBlockState(top.above()).is(Blocks.OBSIDIAN) && top.getY() < pos.getY() + 50) {
			top = top.above();
		}
		return top;
	}

	/** 是否灾厄村民旗帜。 */
	private boolean looksLikeIllagerBanner(BannerBlockEntity banner) {
		ItemStack item = banner.getItem();
		String name = item.getHoverName().getString();
		return name.contains("不祥") || name.contains("Ominous") || name.contains("Illager");
	}

	/** 地图装饰类型对应线索。 */
	private Kind mapKind(Holder<net.minecraft.world.level.saveddata.maps.MapDecorationType> type) {
		if (type.equals(MapDecorationTypes.RED_X) || sameHolder(type, MapDecorationTypes.RED_X)) return Kind.BURIED_TREASURE;
		if (type.equals(MapDecorationTypes.OCEAN_MONUMENT) || sameHolder(type, MapDecorationTypes.OCEAN_MONUMENT)) return Kind.MAP_MONUMENT;
		if (type.equals(MapDecorationTypes.WOODLAND_MANSION) || sameHolder(type, MapDecorationTypes.WOODLAND_MANSION)) return Kind.MAP_MANSION;
		if (type.equals(MapDecorationTypes.TRIAL_CHAMBERS) || sameHolder(type, MapDecorationTypes.TRIAL_CHAMBERS)) return Kind.MAP_TRIAL;
		return null;
	}

	/** 两个 Holder 是否同一注册项。 */
	private static boolean sameHolder(Holder<?> left, Holder<?> right) {
		return left.unwrapKey().isPresent() && left.unwrapKey().equals(right.unwrapKey())
			|| left.value() == right.value();
	}

	/** 追加一条线索（去重、裁剪）。 */
	private void addFinding(Kind kind, ResourceKey<net.minecraft.world.level.Level> dimension, BlockPos pos, String extra) {
		if (hasWorldSeed()) return;
		String dim = dimension.identifier().toString();
		String key = kind.name() + "|" + dim + "|" + keyPos(kind, pos);
		for (Finding finding : store.findings) {
			Kind existing = Kind.fromName(finding.kind);
			if (existing == null) continue;
			String existingKey = existing.name() + "|" + finding.dimension + "|"
				+ keyPos(existing, new BlockPos(finding.x, finding.y, finding.z));
			if (key.equals(existingKey)) return;
		}
		Finding finding = new Finding();
		finding.kind = kind.name();
		finding.label = kind.label;
		finding.dimension = dim;
		finding.x = pos.getX();
		finding.y = pos.getY();
		finding.z = pos.getZ();
		finding.extra = extra == null ? "" : extra;
		finding.regularBits = kind.regularBits;
		finding.liftBits = kind.liftBits;
		finding.time = System.currentTimeMillis();
		store.findings.add(finding);
		pruneFindings();
		save();
		if (kind != Kind.BIOME) {
			notice("记到 " + kind.label + "  " + format(pos), 0x55FFFF);
		}
	}

	/** Drops old biomes/dungeons first so they cannot push out temples and shipwrecks. */
	private void pruneFindings() {
		trimKind(Kind.BIOME, 80);
		int zeroBit = 0;
		for (Finding finding : store.findings) {
			Kind kind = Kind.fromName(finding.kind);
			if (kind != null && kind.regularBits + kind.liftBits == 0 && kind != Kind.BIOME) zeroBit++;
		}
		if (zeroBit <= 200) return;
		int[] extra = {zeroBit - 200};
		store.findings.removeIf(finding -> {
			if (extra[0] <= 0) return false;
			Kind kind = Kind.fromName(finding.kind);
			if (kind == null || kind == Kind.BIOME || kind.regularBits + kind.liftBits > 0) return false;
			extra[0]--;
			return true;
		});
	}

	/** 保留某类型最近若干条。 */
	private void trimKind(Kind kind, int keep) {
		int count = 0;
		for (Finding finding : store.findings) {
			if (kind.name().equals(finding.kind)) count++;
		}
		if (count <= keep) return;
		int[] extra = {count - keep};
		store.findings.removeIf(finding -> {
			if (extra[0] <= 0) return false;
			if (!kind.name().equals(finding.kind)) return false;
			extra[0]--;
			return true;
		});
	}

	/** 线索类型计数摘要。 */
	public String findingsSummary() {
		int useful = 0;
		int dungeon = 0;
		int biome = 0;
		int other = 0;
		for (Finding finding : store.findings) {
			Kind kind = Kind.fromName(finding.kind);
			if (kind == null) {
				other++;
				continue;
			}
			if (kind.regularBits + kind.liftBits > 0) useful++;
			else if (kind == Kind.BIOME) biome++;
			else if (kind == Kind.DUNGEON || kind == Kind.MINESHAFT || kind == Kind.TRIAL_CHAMBER) dungeon++;
			else other++;
		}
		return "已记 " + store.findings.size() + " 条（有用结构 " + useful
			+ "，地牢/矿井/试炼 " + dungeon + "，群系 " + biome + "，其它 " + other + "）";
	}

	/** 线索去重键。 */
	private String keyPos(Kind kind, BlockPos pos) {
		if (kind == Kind.BIOME) return (pos.getX() >> 5) + ":" + (pos.getZ() >> 5);
		if (kind == Kind.SLIME_CHUNK) return (pos.getX() >> 4) + ":" + (pos.getZ() >> 4);
		if (kind.regularBits + kind.liftBits > 0) return (pos.getX() >> 9) + ":" + (pos.getZ() >> 9);
		return pos.getX() + ":" + pos.getY() + ":" + pos.getZ();
	}

	/** 按线索估算信息量。 */
	private int bits(boolean lift) {
		int total = 0;
		Set<String> seen = new LinkedHashSet<>();
		for (Finding finding : store.findings) {
			Kind kind = Kind.fromName(finding.kind);
			if (kind == null) continue;
			int value = lift ? kind.liftBits : kind.regularBits;
			if (value <= 0) continue;
			String key = kind.name() + "|" + finding.dimension + "|" + (finding.x >> 9) + ":" + (finding.z >> 9);
			if (!seen.add(key)) continue;
			total += value;
		}
		return total;
	}

	/** 世界里标出线索位置。 */
	private void emitGizmos(Minecraft client) {
		BlockPos player = client.player.blockPosition();
		for (Finding finding : store.findings) {
			if (Kind.BIOME.name().equals(finding.kind)) continue;
			BlockPos pos = new BlockPos(finding.x, finding.y, finding.z);
			if (pos.distSqr(player) > 96 * 96) continue;
			Gizmos.cuboid(pos, GizmoStyle.strokeAndFill(0xFF55FFFF, 2.0F, 0x2255FFFF));
		}
	}

	/** 拼文本报告。 */
	private String buildReport() {
		StringBuilder out = new StringBuilder();
		out.append("2b2t-kit 世界种子探测报告\n");
		out.append("Minecraft 26.1.2\n\n");
		out.append("原理：服务器不把 /seed 发给普通玩家，但进服时会发一份 SHA-256 哈希种子。");
		out.append("1.18 以后用地牢地板反推已经失效，现在要靠沙漠神殿、丛林神庙、沼泽小屋、雪屋、沉船、前哨站、海底神殿的位置，");
		out.append("凑够大约 40 个可提升结构位 + 32 个普通结构位，才能把 48 位结构种子搜出来，再用哈希解开完整 64 位种子。\n\n");
		out.append("哈希种子：").append(store.hasHashedSeed ? store.hashedSeed : "无").append('\n');
		out.append("完整种子：").append(store.crackedSeed != null ? store.crackedSeed : "尚未得到").append('\n');
		if (store.singleplayerSeed != null) out.append("单人世界种子：").append(store.singleplayerSeed).append('\n');
		out.append("结构位：普通 ").append(regularBits()).append("/32，可提升 ").append(liftBits()).append("/40\n\n");
		out.append("还缺什么：").append(nextHint()).append("\n\n");
		out.append("采集到的点：\n");
		List<Finding> copy = new ArrayList<>(store.findings);
		copy.sort(Comparator.comparing((Finding finding) -> finding.kind).thenComparingInt(finding -> finding.x));
		for (Finding finding : copy) {
			if (Kind.BIOME.name().equals(finding.kind)) continue;
			out.append("- ").append(finding.label)
				.append("  ").append(finding.x).append(' ').append(finding.y).append(' ').append(finding.z)
				.append("  ").append(finding.dimension);
			if (finding.extra != null && !finding.extra.isEmpty()) out.append("  ").append(finding.extra);
			out.append('\n');
		}
		out.append("\n生物群系样本：\n");
		for (Finding finding : copy) {
			if (!Kind.BIOME.name().equals(finding.kind)) continue;
			out.append("- ").append(finding.x).append(' ').append(finding.z).append("  ").append(finding.extra).append('\n');
		}
		out.append("\n下一步：\n");
		out.append("1. 自己继续找上面列出的结构（走过去让本模组自动记，或准星对准后手动标记）。\n");
		out.append("2. 位够了仍解不开时，把这份报告配合 SeedcrackerX 2.16.0（支持 26.1.2）再跑一遍。\n");
		out.append("3. 若别人或 SeedcrackerX 给出了 48 位结构种子，回到本界面「试结构种子」，用哈希在 1 秒内解开完整种子。\n");
		out.append("4. 得到完整种子后，可在 Chunkbase 查村庄、神殿、宝藏。\n");
		return out.toString();
	}

	/** 下一步该采什么线索的提示。 */
	public String nextHint() {
		int lift = liftBits();
		int regular = regularBits();
		if (store.crackedSeed != null && store.hasHashedSeed && matchesHash(store.crackedSeed)) {
			return "已经解开。可以复制种子去 Chunkbase。";
		}
		if (lift >= 40 && regular >= 32) {
			if (SeedcrackerBridge.installed()) {
				return "结构位已够。请让 SeedcrackerX 开始计算，算出后本页会自动填入完整种子。";
			}
			return "结构位已够，但本模组不算 48 位结构种子。请装 SeedcrackerX，或把结构种子填进下面。不需要网页 API。";
		}
		List<String> missing = new ArrayList<>();
		if (count(Kind.DESERT_PYRAMID) == 0) missing.add("沙漠神殿");
		if (count(Kind.SWAMP_HUT) == 0) missing.add("沼泽小屋");
		if (count(Kind.SHIPWRECK) == 0) missing.add("沉船");
		if (count(Kind.IGLOO) == 0) missing.add("雪屋");
		if (count(Kind.JUNGLE_TEMPLE) == 0) missing.add("丛林神庙");
		if (count(Kind.OUTPOST) == 0) missing.add("掠夺者前哨");
		if (count(Kind.MONUMENT) == 0) missing.add("海底神殿");
		String more = missing.isEmpty()
			? "再找几座不同类型的神殿/小屋/沉船"
			: "去找：" + String.join("、", missing.subList(0, Math.min(3, missing.size())));
		return more + "。看上面黄字才是 SeedcrackerX 进度。";
	}

	/** 某类型线索条数。 */
	private int count(Kind kind) {
		int n = 0;
		for (Finding finding : store.findings) {
			if (kind.name().equals(finding.kind)) n++;
		}
		return n;
	}

	/** 种子是否匹配登录哈希。 */
	private boolean matchesHash(long seed) {
		return store.hasHashedSeed && BiomeManager.obfuscateSeed(seed) == store.hashedSeed;
	}

	/** 用哈希+结构种子 lifting 出世界种子。 */
	public static Long liftFromStructureSeed(long hashed, long structureSeed) {
		long lower = structureSeed & ((1L << 48) - 1);
		for (int upper = 0; upper < 65536; upper++) {
			long world = ((long)upper << 48) | lower;
			if (BiomeManager.obfuscateSeed(world) == hashed) return world;
		}
		return null;
	}

	/** 原版史莱姆区块判定。 */
	public static boolean isSlimeChunk(long seed, int chunkX, int chunkZ) {
		Random random = new Random(seed +
			(long)(chunkX * chunkX * 0x4c1906) +
			(long)(chunkX * 0x5ac0db) +
			(long)(chunkZ * chunkZ) * 0x4307a7L +
			(long)(chunkZ * 0x5f24f) ^ 0x3ad8025fL);
		return random.nextInt(10) == 0;
	}

	/** 解析种子字符串（数字或字符串种子）。 */
	public static Long parseSeed(String raw) {
		if (raw == null) return null;
		String text = raw.trim();
		if (text.isEmpty()) return null;
		OptionalLong parsed = net.minecraft.world.level.levelgen.WorldOptions.parseSeed(text);
		return parsed.isPresent() ? parsed.getAsLong() : null;
	}

	/** 解析长整型；失败 null。 */
	private static Long parseLong(String raw) {
		if (raw == null) return null;
		try {
			return Long.parseLong(raw.trim());
		} catch (NumberFormatException exception) {
			return null;
		}
	}

	/** 准星方块或脚底。 */
	private static BlockPos lookedOrFeet(Minecraft client) {
		if (client.hitResult instanceof BlockHitResult hit && hit.getType() == HitResult.Type.BLOCK) {
			return hit.getBlockPos();
		}
		return client.player.blockPosition();
	}

	/** 实体显示名。 */
	private static String displayName(Entity entity) {
		if (entity == null) return "未知";
		EntityType<?> type = entity.getType();
		Identifier id = BuiltInRegistries.ENTITY_TYPE.getKey(type);
		return type.getDescription().getString() + (id == null ? "" : " (" + id.getPath() + ")");
	}

	/** 坐标短串。 */
	private static String format(BlockPos pos) {
		return pos.getX() + " " + pos.getY() + " " + pos.getZ();
	}

	/** 更新提示文案，并往聊天打一条。 */
	private void notice(String text, int color) {
		notice = text;
		noticeColor = color;
		Minecraft client = Minecraft.getInstance();
		if (client.player != null) {
			client.player.sendSystemMessage(Component.literal("[种子] " + text));
		}
	}

	/** 侦察线索类型及其估算比特。 */
	public enum Kind {
		DUNGEON("地牢刷怪笼", 0, 0),
		MINESHAFT("矿井刷怪笼", 0, 0),
		FORTRESS("下界要塞刷怪笼", 0, 0),
		STRONGHOLD("要塞刷怪笼", 0, 0),
		DESERT_PYRAMID("沙漠神殿", 9, 9),
		JUNGLE_TEMPLE("丛林神庙", 9, 9),
		SWAMP_HUT("沼泽小屋", 9, 9),
		IGLOO("雪屋", 9, 9),
		SHIPWRECK("沉船", 8, 8),
		OUTPOST("掠夺者前哨", 0, 9),
		MONUMENT("海底神殿", 9, 0),
		VILLAGE("村庄", 0, 0),
		RUINED_PORTAL("废弃传送门", 0, 0),
		END_CITY("末地城", 9, 0),
		END_PILLAR("末地黑曜石柱", 0, 0),
		BURIED_TREASURE("埋藏的宝藏", 0, 0),
		TRIAL_CHAMBER("试炼密室", 0, 0),
		BIOME("生物群系", 0, 0),
		SLIME_CHUNK("史莱姆区块", 0, 0),
		MAP_MONUMENT("地图·海底神殿", 9, 0),
		MAP_MANSION("地图·林地府邸", 0, 0),
		MAP_TRIAL("地图·试炼密室", 0, 0);

		final String label;
		final int regularBits;
		final int liftBits;

		Kind(String label, int regularBits, int liftBits) {
			this.label = label;
			this.regularBits = regularBits;
			this.liftBits = liftBits;
		}

		/** 从枚举名还原；非法返回 null。 */
		static Kind fromName(String name) {
			try {
				return valueOf(name);
			} catch (Exception ignored) {
				return null;
			}
		}
	}

	/** 持久化状态：哈希种子、已破解种子与线索列表。 */
	public static final class Store {
		boolean hasHashedSeed;
		long hashedSeed;
		Long crackedSeed;
		Long structureSeed;
		Long singleplayerSeed;
		boolean flat;
		boolean debug;
		String lastDimension = "";
		List<Finding> findings = new ArrayList<>();
	}

	/** 一条结构/地图/群系线索。 */
	public static final class Finding {
		String kind = "";
		String label = "";
		String dimension = "";
		int x;
		int y;
		int z;
		String extra = "";
		int regularBits;
		int liftBits;
		long time;

		/** 去重键：类型+维度+坐标。 */
		String key() {
			return kind + "|" + dimension + "|" + x + ":" + y + ":" + z;
		}
	}
}
