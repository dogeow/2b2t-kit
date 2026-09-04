package dev.twob2tkit.villager;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.gizmos.TextGizmo;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.monster.zombie.ZombieVillager;
import net.minecraft.world.entity.npc.villager.Villager;
import net.minecraft.world.entity.npc.villager.VillagerProfession;
import net.minecraft.world.entity.npc.wanderingtrader.WanderingTrader;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitUi;

/** 已加载范围内给村民标职业，并列出还缺的职业和工作方块。 */
public final class VillagerScanner {
	private static final Job[] JOBS = {
		new Job(VillagerProfession.LIBRARIAN, "图书管理员", Blocks.LECTERN, "讲台", true, 0xFF55FF55),
		new Job(VillagerProfession.CLERIC, "牧师", Blocks.BREWING_STAND, "酿造台", true, 0xFFAA66FF),
		new Job(VillagerProfession.ARMORER, "盔甲匠", Blocks.BLAST_FURNACE, "高炉", true, 0xFFFFAA00),
		new Job(VillagerProfession.WEAPONSMITH, "武器匠", Blocks.GRINDSTONE, "砂轮", true, 0xFFFF5555),
		new Job(VillagerProfession.TOOLSMITH, "工具匠", Blocks.SMITHING_TABLE, "锻造台", true, 0xFF55FFFF),
		new Job(VillagerProfession.BUTCHER, "屠夫", Blocks.SMOKER, "烟熏炉", true, 0xFFFF8855),
		new Job(VillagerProfession.CARTOGRAPHER, "制图师", Blocks.CARTOGRAPHY_TABLE, "制图台", true, 0xFF55AAAA),
		new Job(VillagerProfession.SHEPHERD, "牧羊人", Blocks.LOOM, "织布机", true, 0xFFFF55FF),
		new Job(VillagerProfession.MASON, "石匠", Blocks.STONECUTTER, "切石机", true, 0xFFAAAAAA),
		new Job(VillagerProfession.FLETCHER, "箭匠", Blocks.FLETCHING_TABLE, "制箭台", true, 0xFFAAFF55),
		new Job(VillagerProfession.FARMER, "农民", Blocks.COMPOSTER, "堆肥桶", true, 0xFF88AA44),
		new Job(VillagerProfession.FISHERMAN, "渔夫", Blocks.BARREL, "木桶", false, 0xFF6688AA),
		new Job(VillagerProfession.LEATHERWORKER, "皮匠", Blocks.CAULDRON, "炼药锅", false, 0xFFAA8866)
	};

	private final KitConfig config;
	private final List<BlockPos> lecterns = new ArrayList<>();
	private final List<MarkedSite> sites = new ArrayList<>();
	private final Set<Block> foundBlocks = new LinkedHashSet<>();
	private int scanTicks;
	private String summary = "";
	private String missingPairs = "";
	private String unemployedHint = "";

	/** 按配置构造村民职业扫描。 */
	public VillagerScanner(KitConfig config) {
		this.config = config;
	}

	/** 是否开着扫描。 */
	public boolean isEnabled() {
		return config.villagerScanEnabled;
	}

	/** 开关扫描。 */
	public void toggle(Minecraft client) {
		config.villagerScanEnabled = !config.villagerScanEnabled;
		config.save();
		if (client.player != null) {
			client.player.sendSystemMessage(Component.literal(
				config.villagerScanEnabled
					? "[助手] 村庄职业扫描已开。头顶是现有职业，屏幕上方列出还缺的「职业（方块）」"
					: "[助手] 村庄职业扫描已关"));
		}
		if (!config.villagerScanEnabled) {
			lecterns.clear();
			sites.clear();
			foundBlocks.clear();
			summary = "";
			missingPairs = "";
			unemployedHint = "";
		}
	}

	/** 扫描附近村民与工作站。 */
	public void tick(Minecraft client) {
		if (!config.villagerScanEnabled) return;
		if (client.player == null || client.level == null) return;
		scanTicks++;
		if (scanTicks % 20 == 0) scanJobSites(client);
		try {
			emit(client);
		} catch (IllegalStateException ignored) {
		}
	}

	/** 职业配对摘要。 */
	public String summary() {
		return summary.isBlank() ? "村庄职业关" : summary;
	}

	/** 缺职业说明行。 */
	public String missingLine() {
		return missingPairs.isBlank() ? "" : "还缺：" + missingPairs;
	}

	/** 缺配对文案。 */
	public String missingPairsText() {
		return missingPairs;
	}

	/** 无业村民提示。 */
	public String unemployedHintText() {
		return unemployedHint;
	}

	/** 画出扫描结果 gizmo/标签。 */
	private void emit(Minecraft client) {
		LocalPlayer player = client.player;
		double range = range();
		AABB box = player.getBoundingBox().inflate(range, 16.0, range);
		Set<ResourceKey<VillagerProfession>> presentJobs = new LinkedHashSet<>();
		int unemployed = 0;
		int librarians = 0;
		int villagers = 0;
		for (Entity entity : client.level.getEntities(player, box)) {
			if (entity instanceof WanderingTrader trader) {
				label(trader, "流浪商人", 0xFFFFAA55, false);
				continue;
			}
			if (entity instanceof ZombieVillager zombie) {
				label(zombie, "僵尸·" + professionLabel(zombie.getVillagerData().profession(), zombie.isBaby()), 0xFF88FF55, false);
				continue;
			}
			if (!(entity instanceof Villager villager)) continue;
			villagers++;
			Holder<VillagerProfession> profession = villager.getVillagerData().profession();
			boolean librarian = profession.is(VillagerProfession.LIBRARIAN);
			if (librarian) librarians++;
			if (profession.is(VillagerProfession.NONE) && !villager.isBaby()) unemployed++;
			profession.unwrapKey().ifPresent(presentJobs::add);
			String text = professionLabel(profession, villager.isBaby()) + levelSuffix(villager) + " " + Math.round(player.distanceTo(villager)) + "格";
			label(villager, text, librarian ? 0xFF55FF55 : colorFor(profession), librarian);
		}
		for (MarkedSite site : sites) {
			boolean lectern = site.job.highlight;
			if (!site.job.highlight && countSites(site.job.block) > 4) continue;
			Gizmos.cuboid(site.pos, GizmoStyle.strokeAndFill(site.job.color, lectern ? 3.2F : 1.6F, lectern ? 0x4455FF55 : 0x22000000 | (site.job.color & 0xFFFFFF)));
			Gizmos.billboardText(site.job.blockLabel, Vec3.atCenterOf(site.pos.above()),
				TextGizmo.Style.forColorAndCentered(site.job.color).withScale(lectern ? 0.32F : 0.22F)).setAlwaysOnTop();
		}
		if (!lecterns.isEmpty()) {
			lecterns.sort((a, b) -> Double.compare(player.distanceToSqr(Vec3.atCenterOf(a)), player.distanceToSqr(Vec3.atCenterOf(b))));
			Gizmos.arrow(player.getEyePosition(), Vec3.atCenterOf(lecterns.getFirst()), 0xFF55FF55, 2.4F);
		}

		List<String> missingEntries = new ArrayList<>();
		for (Job job : JOBS) {
			if (!presentJobs.contains(job.profession)) {
				missingEntries.add(job.professionLabel + "（" + job.blockLabel + "）");
			}
		}
		boolean emptyArea = villagers == 0 && foundBlocks.isEmpty();
		if (emptyArea) {
			missingPairs = "";
			summary = "附近没有村民和工作方块";
			unemployedHint = "";
		} else {
			missingPairs = missingEntries.isEmpty() ? "" : String.join("、", missingEntries);
			summary = "村民" + villagers
				+ " 图书管理员" + librarians
				+ " 失业" + unemployed
				+ " 讲台" + lecterns.size()
				+ (missingEntries.isEmpty() ? "  13职业齐" : "");
			unemployedHint = unemployed > 0 && !missingPairs.isBlank()
				? "有" + unemployed + "个失业村民，放上方块后他们会认职业"
				: "";
		}
	}

	/** 画在屏幕正中偏上，不跟视角抖。还缺项为「职业（方块）」并自动换行。 */
	public void renderHud(Minecraft client, GuiGraphicsExtractor graphics) {
		if (!config.villagerScanEnabled || client.options.hideGui) return;
		if (client.screen != null && !client.screen.isInGameUi()) return;
		int center = graphics.guiWidth() / 2;
		int maxW = Math.max(160, graphics.guiWidth() - 48);
		int y = Math.max(12, graphics.guiHeight() / 2 - 90);
		graphics.nextStratum();
		y = KitUi.centeredWrapped(graphics, client.font,
			KitUi.fit(client.font, summary, maxW), center, y, 0xAAFFAA, maxW);
		y += 2;
		if (!missingPairs.isBlank()) {
			y = KitUi.centeredWrapped(graphics, client.font,
				"还缺：" + missingPairs, center, y, 0xFFFF55, maxW);
			y += 2;
		}
		if (!unemployedHint.isBlank()) {
			KitUi.centeredWrapped(graphics, client.font, unemployedHint, center, y, 0xFFCC66, maxW);
		}
	}

	/** 扫描工作站方块。 */
	private void scanJobSites(Minecraft client) {
		sites.clear();
		lecterns.clear();
		foundBlocks.clear();
		LocalPlayer player = client.player;
		int radius = Math.min(32, (int)Math.ceil(range()));
		BlockPos feet = player.blockPosition();
		int minY = feet.getY() - 8;
		int maxY = feet.getY() + 12;
		for (int dx = -radius; dx <= radius; dx++) {
			for (int dz = -radius; dz <= radius; dz++) {
				if (dx * dx + dz * dz > radius * radius) continue;
				for (int y = minY; y <= maxY; y++) {
					BlockPos pos = new BlockPos(feet.getX() + dx, y, feet.getZ() + dz);
					if (!client.level.hasChunkAt(pos)) continue;
					Block block = client.level.getBlockState(pos).getBlock();
					Job job = jobOf(block);
					if (job == null) continue;
					foundBlocks.add(block);
					if (job.highlight || countSites(block) < 4) {
						sites.add(new MarkedSite(pos.immutable(), job));
					}
					if (block == Blocks.LECTERN) lecterns.add(pos.immutable());
				}
			}
		}
	}

	/** 某工作站方块数量。 */
	private int countSites(Block block) {
		int count = 0;
		for (MarkedSite site : sites) {
			if (site.job.block == block) count++;
		}
		return count;
	}

	/** 在实体上画文字。 */
	private static void label(Entity entity, String text, int color, boolean important) {
		Gizmos.cuboid(entity.getBoundingBox().inflate(0.04), GizmoStyle.strokeAndFill(color, important ? 2.4F : 1.1F, important ? 0x3355FF55 : 0x22000000));
		Gizmos.billboardTextOverMob(entity, 0, text, color, important ? 0.38F : 0.28F);
	}

	/** 职业显示名（含幼年）。 */
	private static String professionLabel(Holder<VillagerProfession> profession, boolean baby) {
		String name = chineseProfession(profession);
		if (baby && profession.is(VillagerProfession.NONE)) return "幼年";
		return baby ? "幼年·" + name : name;
	}

	/** 职业中文名。 */
	private static String chineseProfession(Holder<VillagerProfession> profession) {
		for (Job job : JOBS) {
			if (profession.is(job.profession)) return job.professionLabel;
		}
		if (profession.is(VillagerProfession.NONE)) return "失业";
		if (profession.is(VillagerProfession.NITWIT)) return "傻子";
		return profession.value().name().getString();
	}

	/** 交易等级后缀。 */
	private static String levelSuffix(Villager villager) {
		Holder<VillagerProfession> profession = villager.getVillagerData().profession();
		if (profession.is(VillagerProfession.NONE) || profession.is(VillagerProfession.NITWIT)) return "";
		int level = villager.getVillagerData().level();
		return level <= 1 ? "" : "·" + level + "级";
	}

	/** 职业对应颜色。 */
	private static int colorFor(Holder<VillagerProfession> profession) {
		for (Job job : JOBS) {
			if (profession.is(job.profession)) return job.color;
		}
		if (profession.is(VillagerProfession.NONE)) return 0xFFAAAAAA;
		if (profession.is(VillagerProfession.NITWIT)) return 0xFFAA7744;
		return 0xFF55FFFF;
	}

	/** 扫描半径。 */
	private double range() {
		return Math.max(16.0, Math.min(96.0, config.villagerScanRange));
	}

	/** 方块对应职业。 */
	private static Job jobOf(Block block) {
		for (Job job : JOBS) {
			if (job.block == block) return job;
		}
		return null;
	}

	/** 村民职业与工作方块对照。 */
	private record Job(
		ResourceKey<VillagerProfession> profession,
		String professionLabel,
		Block block,
		String blockLabel,
		boolean highlight,
		int color
	) {
	}

	/** 已标记的工作站点。 */
	private record MarkedSite(BlockPos pos, Job job) {
	}
}
