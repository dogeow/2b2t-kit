package dev.twob2tkit.adventure;

import net.minecraft.advancements.Advancement;
import net.minecraft.advancements.AdvancementHolder;
import net.minecraft.advancements.AdvancementProgress;
import net.minecraft.advancements.AdvancementRequirements;
import net.minecraft.advancements.AdvancementRewards;
import net.minecraft.advancements.AdvancementType;
import net.minecraft.advancements.CriteriaTriggers;
import net.minecraft.advancements.Criterion;
import net.minecraft.advancements.DisplayInfo;
import net.minecraft.advancements.criterion.ImpossibleTrigger;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientAdvancements;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.core.ClientAsset;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ClientboundUpdateAdvancementsPacket;
import net.minecraft.resources.Identifier;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStackTemplate;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import dev.twob2tkit.KitConfig;

/** 本机进度：不向服务器伪造，只写本地配置。 */
public final class LocalAdvancementManager {
	private static final String NAMESPACE = "2b2t-kit";
	private static final String PATH_PREFIX = "survival/";
	private static final String CRITERION = "done";
	private static final Identifier ROOT_ID = id("root");
	private static final List<NodeSpec> SPECS = List.of(
		node("root", null, "本地生存进度", "独立于服务器，记录你在本机完成的生存里程碑", Items.COMPASS, AdvancementType.TASK, 0, 0),
		node("wood", "root", "获得木头", "获得任意原木、菌柄或木头", Items.OAK_LOG, AdvancementType.TASK, 1, 0),
		node("crafting_table", "wood", "动手制作", "获得工作台", Items.CRAFTING_TABLE, AdvancementType.TASK, 2, 0),
		node("stone", "crafting_table", "石器时代", "获得圆石、黑石或深板岩圆石", Items.COBBLESTONE, AdvancementType.TASK, 3, 0),
		node("iron", "stone", "来硬的", "获得铁锭或粗铁", Items.IRON_INGOT, AdvancementType.GOAL, 4, 0),
		node("diamond", "iron", "钻石！", "获得一颗钻石", Items.DIAMOND, AdvancementType.GOAL, 5, 0),
		node("diamond_pickaxe", "diamond", "钻石镐", "获得钻石镐", Items.DIAMOND_PICKAXE, AdvancementType.TASK, 6, -1),
		node("enchanting_table", "diamond_pickaxe", "附魔师", "获得附魔台", Items.ENCHANTING_TABLE, AdvancementType.GOAL, 7, -1),
		node("diamond_armor", "diamond", "钻石护体", "曾经集齐钻石头盔、胸甲、护腿和靴子", Items.DIAMOND_CHESTPLATE, AdvancementType.CHALLENGE, 7, 0),
		node("netherite_ingot", "diamond", "下界合金", "获得下界合金锭", Items.NETHERITE_INGOT, AdvancementType.GOAL, 6, 1),
		node("netherite_armor", "netherite_ingot", "顶级防护", "曾经集齐全套下界合金护甲", Items.NETHERITE_CHESTPLATE, AdvancementType.CHALLENGE, 7, 1),
		node("shield", "iron", "举盾防御", "获得盾牌", Items.SHIELD, AdvancementType.TASK, 5, -2),
		node("totem", "shield", "不死护符", "获得不死图腾", Items.TOTEM_OF_UNDYING, AdvancementType.CHALLENGE, 6, -2),
		node("golden_apple", "iron", "保命口粮", "获得金苹果或附魔金苹果", Items.GOLDEN_APPLE, AdvancementType.GOAL, 5, -3),
		node("bucket", "iron", "桶装世界", "获得空桶", Items.BUCKET, AdvancementType.TASK, 5, 2),
		node("water", "bucket", "获得水", "装满一桶水", Items.WATER_BUCKET, AdvancementType.TASK, 6, 2),
		node("lava", "bucket", "获得岩浆", "装满一桶岩浆", Items.LAVA_BUCKET, AdvancementType.TASK, 6, 3),
		node("obsidian", "lava", "黑曜石", "获得黑曜石", Items.OBSIDIAN, AdvancementType.TASK, 7, 3),
		node("nether", "obsidian", "深入下界", "进入下界维度", Items.FLINT_AND_STEEL, AdvancementType.GOAL, 8, 3),
		node("blaze_rod", "nether", "烈焰之心", "获得烈焰棒", Items.BLAZE_ROD, AdvancementType.TASK, 9, 2),
		node("ender_pearl", "diamond", "末影珍珠", "获得末影珍珠", Items.ENDER_PEARL, AdvancementType.TASK, 8, 1),
		node("ender_eye", "blaze_rod", "末影之眼", "获得末影之眼", Items.ENDER_EYE, AdvancementType.GOAL, 10, 2),
		node("ender_chest", "obsidian", "随身仓库", "获得末影箱", Items.ENDER_CHEST, AdvancementType.GOAL, 8, 2),
		node("the_end", "ender_eye", "进入末地", "进入末地维度", Items.END_PORTAL_FRAME, AdvancementType.GOAL, 11, 2),
		node("dragon_egg", "the_end", "龙之传承", "获得龙蛋", Items.DRAGON_EGG, AdvancementType.CHALLENGE, 12, 1),
		node("elytra", "the_end", "飞向远方", "获得鞘翅", Items.ELYTRA, AdvancementType.CHALLENGE, 12, 3)
	);
	private static final Map<String, NodeSpec> SPEC_BY_KEY = indexSpecs();
	private static final List<AdvancementHolder> HOLDERS = buildHolders();
	private static KitConfig config;
	private static ClientPacketListener lastConnection;
	private static int ticks;

	/** 按配置构造本地进度管理。 */
	private LocalAdvancementManager() {
	}

	/** 首次注入本地进度树。 */
	public static void initialize(KitConfig value) {
		config = value;
	}

	/** 按条件更新本地进度。 */
	public static void tick(Minecraft minecraft) {
		if (config == null || minecraft.player == null || minecraft.level == null || minecraft.getConnection() == null) {
			lastConnection = null;
			return;
		}

		ClientPacketListener connection = minecraft.getConnection();
		boolean newConnection = connection != lastConnection;
		lastConnection = connection;
		Set<String> before = new HashSet<>(config.completedLocalAdvancements);
		Set<String> direct = completedNow(minecraft);
		config.completedLocalAdvancements.addAll(direct);
		propagateParents(config.completedLocalAdvancements);
		Set<String> changed = new HashSet<>(config.completedLocalAdvancements);
		changed.removeAll(before);
		if (!changed.isEmpty()) config.save();

		ClientAdvancements advancements = connection.getAdvancements();
		boolean missing = hasMissingNodes(advancements);
		if (newConnection || missing || ++ticks % 20 == 0 && advancements.get(ROOT_ID) == null) {
			injectAll(advancements);
		}
		if (!newConnection && !changed.isEmpty()) {
			updateProgress(advancements, changed, false);
			Set<String> toast = new HashSet<>(direct);
			toast.retainAll(changed);
			toast.remove("root");
			if (!toast.isEmpty()) updateProgress(advancements, toast, true);
		}
	}

	/** 确保已注入。 */
	public static void ensureInjected(ClientAdvancements advancements) {
		if (config != null && advancements != null && hasMissingNodes(advancements)) injectAll(advancements);
	}

	/** 是否本 Mod 注入的进度。 */
	public static boolean isLocal(AdvancementHolder holder) {
		return holder != null && NAMESPACE.equals(holder.id().getNamespace()) && holder.id().getPath().startsWith(PATH_PREFIX);
	}

	/** 把本地进度塞进进度屏。 */
	private static void injectAll(ClientAdvancements advancements) {
		List<AdvancementHolder> missing = new ArrayList<>();
		for (AdvancementHolder holder : HOLDERS) {
			if (advancements.get(holder.id()) == null) missing.add(holder);
		}
		Map<Identifier, AdvancementProgress> progress = progressFor(keysOf(SPECS));
		advancements.update(new ClientboundUpdateAdvancementsPacket(false, missing, Set.of(), progress, false));
	}

	/** 按背包/位置刷新完成度。 */
	private static void updateProgress(ClientAdvancements advancements, Collection<String> keys, boolean showToasts) {
		advancements.update(new ClientboundUpdateAdvancementsPacket(false, List.of(), Set.of(), progressFor(keys), showToasts));
	}

	/** 取某进度进度对象。 */
	private static Map<Identifier, AdvancementProgress> progressFor(Collection<String> keys) {
		Map<Identifier, AdvancementProgress> result = new LinkedHashMap<>();
		for (String key : keys) {
			NodeSpec spec = SPEC_BY_KEY.get(key);
			if (spec == null) continue;
			AdvancementHolder holder = holder(key);
			AdvancementProgress progress = new AdvancementProgress();
			progress.update(holder.value().requirements());
			if (config.completedLocalAdvancements.contains(key)) progress.grantProgress(CRITERION);
			result.put(holder.id(), progress);
		}
		return result;
	}

	/** 进度树是否还有未注入节点。 */
	private static boolean hasMissingNodes(ClientAdvancements advancements) {
		for (AdvancementHolder holder : HOLDERS) if (advancements.get(holder.id()) == null) return true;
		return false;
	}

	/** 本拍是否刚完成该进度。 */
	private static Set<String> completedNow(Minecraft minecraft) {
		Set<String> completed = new HashSet<>();
		for (NodeSpec spec : SPECS) if (conditionMet(spec.key(), minecraft)) completed.add(spec.key());
		return completed;
	}

	/** 本地条件是否已满足。 */
	private static boolean conditionMet(String key, Minecraft minecraft) {
		return switch (key) {
			case "root" -> true;
			case "wood" -> hasWood();
			case "crafting_table" -> has("minecraft:crafting_table");
			case "stone" -> has("minecraft:cobblestone", "minecraft:cobbled_deepslate", "minecraft:blackstone", "minecraft:stone");
			case "iron" -> has("minecraft:iron_ingot", "minecraft:raw_iron", "minecraft:iron_ore", "minecraft:deepslate_iron_ore");
			case "diamond" -> has("minecraft:diamond");
			case "diamond_pickaxe" -> has("minecraft:diamond_pickaxe");
			case "enchanting_table" -> has("minecraft:enchanting_table");
			case "diamond_armor" -> hasAll("minecraft:diamond_helmet", "minecraft:diamond_chestplate", "minecraft:diamond_leggings", "minecraft:diamond_boots");
			case "netherite_ingot" -> has("minecraft:netherite_ingot");
			case "netherite_armor" -> hasAll("minecraft:netherite_helmet", "minecraft:netherite_chestplate", "minecraft:netherite_leggings", "minecraft:netherite_boots");
			case "shield" -> has("minecraft:shield");
			case "totem" -> has("minecraft:totem_of_undying");
			case "golden_apple" -> has("minecraft:golden_apple", "minecraft:enchanted_golden_apple");
			case "bucket" -> has("minecraft:bucket");
			case "water" -> has("minecraft:water_bucket");
			case "lava" -> has("minecraft:lava_bucket");
			case "obsidian" -> has("minecraft:obsidian");
			case "nether" -> minecraft.level.dimension().equals(Level.NETHER);
			case "blaze_rod" -> has("minecraft:blaze_rod");
			case "ender_pearl" -> has("minecraft:ender_pearl");
			case "ender_eye" -> has("minecraft:ender_eye");
			case "ender_chest" -> has("minecraft:ender_chest");
			case "the_end" -> minecraft.level.dimension().equals(Level.END);
			case "dragon_egg" -> has("minecraft:dragon_egg");
			case "elytra" -> has("minecraft:elytra");
			default -> false;
		};
	}

	/** 背包是否有该物品。 */
	private static boolean has(String... ids) {
		for (String id : ids) if (config.discoveredRecipeItems.contains(id)) return true;
		return false;
	}

	/** 是否凑齐全部物品。 */
	private static boolean hasAll(String... ids) {
		for (String id : ids) if (!config.discoveredRecipeItems.contains(id)) return false;
		return true;
	}

	/** 是否有任意原木/木板。 */
	private static boolean hasWood() {
		for (String raw : config.discoveredRecipeItems) {
			int separator = raw.indexOf(':');
			String path = separator >= 0 ? raw.substring(separator + 1) : raw;
			if (path.endsWith("_log") || path.endsWith("_wood") || path.endsWith("_stem") || path.endsWith("_hyphae")) return true;
		}
		return false;
	}

	/** 子完成时向上标记父进度。 */
	private static void propagateParents(Set<String> completed) {
		boolean changed;
		do {
			changed = false;
			for (String key : new HashSet<>(completed)) {
				NodeSpec spec = SPEC_BY_KEY.get(key);
				if (spec != null && spec.parent() != null) changed |= completed.add(spec.parent());
			}
		} while (changed);
	}

	/** 构建可注入的进度 Holder。 */
	private static List<AdvancementHolder> buildHolders() {
		List<AdvancementHolder> result = new ArrayList<>();
		Map<String, Criterion<?>> criteria = Map.of(CRITERION,
			new Criterion<>(CriteriaTriggers.IMPOSSIBLE, new ImpossibleTrigger.TriggerInstance()));
		AdvancementRequirements requirements = AdvancementRequirements.allOf(criteria.keySet());
		for (NodeSpec spec : SPECS) {
			Optional<ClientAsset.ResourceTexture> background = spec.parent() == null
				? Optional.of(new ClientAsset.ResourceTexture(Identifier.withDefaultNamespace("block/stone")))
				: Optional.empty();
			DisplayInfo display = new DisplayInfo(
				new ItemStackTemplate(spec.icon()), Component.literal(spec.title()), Component.literal(spec.description()),
				background, spec.type(), true, false, false
			);
			display.setLocation(spec.x(), spec.y());
			Advancement advancement = new Advancement(
				Optional.ofNullable(spec.parent()).map(LocalAdvancementManager::id), Optional.of(display),
				AdvancementRewards.EMPTY, criteria, requirements, false
			);
			result.add(new AdvancementHolder(id(spec.key()), advancement));
		}
		return List.copyOf(result);
	}

	/** 按 id 索引节点规格。 */
	private static Map<String, NodeSpec> indexSpecs() {
		Map<String, NodeSpec> result = new LinkedHashMap<>();
		for (NodeSpec spec : SPECS) result.put(spec.key(), spec);
		return Map.copyOf(result);
	}

	/** 取某进度 Holder。 */
	private static AdvancementHolder holder(String key) {
		for (AdvancementHolder holder : HOLDERS) if (holder.id().equals(id(key))) return holder;
		throw new IllegalArgumentException("Unknown local advancement " + key);
	}

	/** 全部本地进度键。 */
	private static List<String> keysOf(List<NodeSpec> specs) {
		return specs.stream().map(NodeSpec::key).toList();
	}

	/** 进度 ResourceLocation/id。 */
	private static Identifier id(String key) {
		return Identifier.fromNamespaceAndPath(NAMESPACE, PATH_PREFIX + key);
	}

	/** 取节点规格。 */
	private static NodeSpec node(String key, String parent, String title, String description, Item icon, AdvancementType type, float x, float y) {
		return new NodeSpec(key, parent, title, description, icon, type, x, y);
	}

	/** 本地进度树节点规格。 */
	private record NodeSpec(String key, String parent, String title, String description, Item icon, AdvancementType type, float x, float y) {
	}
}
