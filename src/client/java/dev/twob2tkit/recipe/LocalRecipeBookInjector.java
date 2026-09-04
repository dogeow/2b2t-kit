package dev.twob2tkit.recipe;

import com.google.gson.JsonElement;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.serialization.DataResult;
import com.mojang.serialization.JsonOps;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.ClientRecipeBook;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractRecipeBookScreen;
import net.minecraft.client.gui.screens.recipebook.RecipeCollection;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.RegistryOps;
import net.minecraft.tags.TagKey;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.Ingredient;
import net.minecraft.world.item.crafting.Recipe;
import net.minecraft.world.item.crafting.ShapedRecipe;
import net.minecraft.world.item.crafting.ShapelessRecipe;
import net.minecraft.world.item.crafting.display.RecipeDisplay;
import net.minecraft.world.item.crafting.display.RecipeDisplayEntry;
import net.minecraft.world.item.crafting.display.RecipeDisplayId;
import net.minecraft.world.item.crafting.display.SlotDisplayContext;

import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Set;
import java.util.stream.Stream;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;

/** 把本地配方注入原版配方书显示（不伪造服务器编号）。 */
public final class LocalRecipeBookInjector {
	private static final int LOCAL_ID_BASE = -2_000_000_000;
	private static final Map<RecipeDisplayId, RecipeDisplay> LOCAL_DISPLAYS = new HashMap<>();
	private static List<LocalEntry> cachedEntries;
	private static Object cachedRegistryAccess;
	private static KitConfig config;

	/** 把本地配方注入原版配方书显示。 */
	private LocalRecipeBookInjector() {
	}

	/** 初始化注入器。 */
	public static synchronized void initialize(KitConfig loadedConfig) {
		config = loadedConfig;
	}

	/** 向配方书塞本地显示。 */
	public static synchronized boolean inject(Minecraft minecraft) {
		if (!isEnhancementEnabled() || minecraft.player == null || minecraft.level == null) return false;

		Object registryAccess = minecraft.level.registryAccess();
		if (cachedEntries == null || cachedRegistryAccess != registryAccess) {
			cachedEntries = loadEntries(minecraft);
			cachedRegistryAccess = registryAccess;
		}
		if (cachedEntries.isEmpty()) return false;
		return applyVisibleEntries(minecraft);
	}

	/** 当前显示模式相关。 */
	public static synchronized RecipeDisplay display(RecipeDisplayId id) {
		return LOCAL_DISPLAYS.get(id);
	}

	/** 是否开了配方书增强。 */
	public static synchronized boolean isEnhancementEnabled() {
		return config != null && config.recipeBookEnhancementEnabled;
	}

	/** 是否需要工作台。 */
	public static boolean needsCraftingTable(RecipeDisplay display) {
		if (display instanceof net.minecraft.world.item.crafting.display.ShapedCraftingRecipeDisplay shaped) {
			return shaped.width() > 2 || shaped.height() > 2;
		}
		if (display instanceof net.minecraft.world.item.crafting.display.ShapelessCraftingRecipeDisplay shapeless) {
			return shapeless.ingredients().size() > 4;
		}
		return false;
	}

	/** 当前注入模式。 */
	public static synchronized RecipeMode mode() {
		if (config == null) return RecipeMode.RELATED;
		return RecipeMode.fromConfig(config.recipeBookMode);
	}

	/** 切换注入模式。 */
	public static synchronized void setMode(Minecraft minecraft, RecipeMode mode) {
		if (config == null) return;
		if (!mode.name().equals(config.recipeBookMode)) {
			config.recipeBookMode = mode.name();
			config.save();
		}
		refresh(minecraft);
	}

	/** 开关配方书增强并刷新。 */
	public static synchronized void setEnhancementEnabled(Minecraft minecraft, boolean enabled) {
		if (config == null) return;
		boolean changed = config.recipeBookEnhancementEnabled != enabled;
		config.recipeBookEnhancementEnabled = enabled;
		if (changed) config.save();
		if (enabled) inject(minecraft);
		else removeInjectedEntries(minecraft);
		if (minecraft.screen instanceof AbstractRecipeBookScreen<?> screen) screen.recipesUpdated();
	}

	/** 发现新物品时回调刷新。 */
	public static synchronized void onDiscoveredItemsChanged(Minecraft minecraft) {
		refresh(minecraft);
	}

	/** 发现物品变化后刷新。 */
	private static void refresh(Minecraft minecraft) {
		if (minecraft.player == null || minecraft.level == null || cachedEntries == null) return;
		if (cachedRegistryAccess != minecraft.level.registryAccess()) return;
		if (!applyVisibleEntries(minecraft)) return;
		if (minecraft.screen instanceof AbstractRecipeBookScreen<?> screen) screen.recipesUpdated();
	}

	/** 按发现把可见条写进书。 */
	private static boolean applyVisibleEntries(Minecraft minecraft) {
		ClientRecipeBook book = minecraft.player.getRecipeBook();
		Set<String> serverResults = serverResultItems(minecraft, book);
		for (RecipeDisplayId id : LOCAL_DISPLAYS.keySet()) book.remove(id);

		int visible = 0;
		for (LocalEntry local : cachedEntries) {
			if (!shouldShow(local)) continue;
			if (!local.primaryResultId().isEmpty() && serverResults.contains(local.primaryResultId())) continue;
			book.add(local.entry());
			visible++;
		}
		book.rebuildCollections();
		if (minecraft.getConnection() != null) {
			minecraft.getConnection().searchTrees().updateRecipes(book, minecraft.level);
		}
		KitClient.LOGGER.debug("Showing {} discovered local crafting recipes", visible);
		return true;
	}

	/** 服务器配方书已有产物集合。 */
	private static Set<String> serverResultItems(Minecraft minecraft, ClientRecipeBook book) {
		Set<String> results = new LinkedHashSet<>();
		var context = SlotDisplayContext.fromLevel(minecraft.level);
		for (RecipeCollection collection : book.getCollections()) {
			for (RecipeDisplayEntry entry : collection.getRecipes()) {
				if (LOCAL_DISPLAYS.containsKey(entry.id())) continue;
				for (ItemStack stack : entry.resultItems(context)) {
					if (!stack.isEmpty()) results.add(BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());
				}
			}
		}
		return results;
	}

	/** 去掉本 Mod 注入条目。 */
	private static void removeInjectedEntries(Minecraft minecraft) {
		if (minecraft.player == null || minecraft.level == null || LOCAL_DISPLAYS.isEmpty()) return;
		ClientRecipeBook book = minecraft.player.getRecipeBook();
		for (RecipeDisplayId id : LOCAL_DISPLAYS.keySet()) book.remove(id);
		book.rebuildCollections();
		if (minecraft.getConnection() != null) {
			minecraft.getConnection().searchTrees().updateRecipes(book, minecraft.level);
		}
	}

	/** 该本地条是否该显示。 */
	private static boolean shouldShow(LocalEntry local) {
		RecipeMode mode = mode();
		if (mode == RecipeMode.ALL) return true;
		Set<String> discovered = config.discoveredRecipeItems;
		if (discovered.isEmpty()) return false;

		if (mode == RecipeMode.READY) {
			return !local.ingredients().isEmpty()
				&& local.ingredients().stream().allMatch(ingredient -> ingredientWasDiscovered(ingredient, discovered));
		}

		if (local.unlockRule() != null && local.unlockRule().matches(discovered)) return true;
		return local.ingredients().stream().anyMatch(ingredient -> ingredientWasDiscovered(ingredient, discovered))
			|| local.resultItems().stream().anyMatch(discovered::contains);
	}

	/** 材料是否已发现。 */
	private static boolean ingredientWasDiscovered(Ingredient ingredient, Set<String> discovered) {
		return ingredient.items()
			.map(holder -> BuiltInRegistries.ITEM.getKey(holder.value()).toString())
			.anyMatch(discovered::contains);
	}

	/** 从数据包加载本地条。 */
	private static List<LocalEntry> loadEntries(Minecraft minecraft) {
		try {
			var minecraftContainer = FabricLoader.getInstance().getModContainer("minecraft").orElseThrow();
			Path recipeRoot = minecraftContainer.findPath("data/minecraft/recipe")
				.orElseThrow();
			Path advancementRoot = minecraftContainer.findPath("data/minecraft/advancement/recipes").orElse(null);
			Path itemTagRoot = minecraftContainer.findPath("data/minecraft/tags/item").orElse(null);
			RegistryOps<JsonElement> ops = RegistryOps.create(JsonOps.INSTANCE, minecraft.level.registryAccess());
			List<DecodedRecipe> recipes = new ArrayList<>();
			try (Stream<Path> files = Files.walk(recipeRoot)) {
				files.filter(path -> path.toString().endsWith(".json"))
					.sorted()
					.forEach(path -> decodeRecipe(path, recipeRoot, ops, recipes));
			}
			Map<String, UnlockRule> unlockRules = loadUnlockRules(advancementRoot, itemTagRoot);

			Map<String, Integer> groups = new LinkedHashMap<>();
			List<LocalEntry> entries = new ArrayList<>();
			var displayContext = SlotDisplayContext.fromLevel(minecraft.level);
			LOCAL_DISPLAYS.clear();
			int sequence = 0;
			for (DecodedRecipe decoded : recipes) {
				Recipe<?> recipe = decoded.recipe();
				if (!(recipe instanceof ShapedRecipe) && !(recipe instanceof ShapelessRecipe)) continue;
				List<Ingredient> ingredients = List.copyOf(recipe.placementInfo().ingredients());
				OptionalInt group = recipe.group().isEmpty()
					? OptionalInt.empty()
					: OptionalInt.of(groups.computeIfAbsent(recipe.group(), ignored -> LOCAL_ID_BASE + groups.size()));
				var requirements = recipe.isSpecial()
					? Optional.<List<Ingredient>>empty()
					: Optional.of(ingredients);
				for (RecipeDisplay display : recipe.display()) {
					if (!display.isEnabled(minecraft.level.enabledFeatures())) continue;
					RecipeDisplayId id = new RecipeDisplayId(LOCAL_ID_BASE + sequence++);
					RecipeDisplayEntry entry = new RecipeDisplayEntry(id, display, group, recipe.recipeBookCategory(), requirements);
					Set<String> resultItems = new LinkedHashSet<>();
					for (ItemStack stack : entry.resultItems(displayContext)) {
						if (!stack.isEmpty()) resultItems.add(BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());
					}
					String primaryResult = resultItems.isEmpty() ? "" : resultItems.iterator().next();
					entries.add(new LocalEntry(entry, ingredients, Set.copyOf(resultItems), unlockRules.get(decoded.id()), primaryResult));
					LOCAL_DISPLAYS.put(id, display);
				}
			}

			KitClient.LOGGER.info("Loaded {} bundled vanilla crafting recipes for discovery filtering", entries.size());
			return List.copyOf(entries);
		} catch (Exception exception) {
			KitClient.LOGGER.warn("Could not prepare the bundled vanilla recipe book", exception);
			return List.of();
		}
	}

	/** 加载解锁规则。 */
	private static Map<String, UnlockRule> loadUnlockRules(Path advancementRoot, Path itemTagRoot) {
		if (advancementRoot == null) return Map.of();
		Map<String, UnlockRule> rules = new HashMap<>();
		try (Stream<Path> files = Files.walk(advancementRoot)) {
			files.filter(path -> path.toString().endsWith(".json"))
				.forEach(path -> loadUnlockRule(path, itemTagRoot, rules));
		} catch (Exception exception) {
			KitClient.LOGGER.warn("Could not load vanilla recipe discovery rules", exception);
		}
		return rules;
	}

	/** 加载单条解锁规则。 */
	private static void loadUnlockRule(Path path, Path itemTagRoot, Map<String, UnlockRule> destination) {
		try (Reader reader = Files.newBufferedReader(path)) {
			JsonObject json = JsonParser.parseReader(reader).getAsJsonObject();
			JsonObject criteriaJson = json.getAsJsonObject("criteria");
			if (criteriaJson == null) return;

			Map<String, UnlockCriterion> criteria = new HashMap<>();
			for (Map.Entry<String, JsonElement> criterionEntry : criteriaJson.entrySet()) {
				criteria.put(criterionEntry.getKey(), parseUnlockCriterion(criterionEntry.getValue().getAsJsonObject(), itemTagRoot));
			}

			List<List<UnlockCriterion>> requirements = new ArrayList<>();
			JsonArray requirementsJson = json.getAsJsonArray("requirements");
			if (requirementsJson == null) {
				for (UnlockCriterion criterion : criteria.values()) requirements.add(List.of(criterion));
			} else {
				for (JsonElement groupElement : requirementsJson) {
					List<UnlockCriterion> group = new ArrayList<>();
					for (JsonElement nameElement : groupElement.getAsJsonArray()) {
						group.add(criteria.getOrDefault(nameElement.getAsString(), UnlockCriterion.NEVER));
					}
					requirements.add(List.copyOf(group));
				}
			}

			JsonObject rewards = json.getAsJsonObject("rewards");
			JsonArray recipes = rewards == null ? null : rewards.getAsJsonArray("recipes");
			if (recipes == null) return;
			UnlockRule rule = new UnlockRule(List.copyOf(requirements));
			for (JsonElement recipe : recipes) destination.put(recipe.getAsString(), rule);
		} catch (Exception exception) {
			KitClient.LOGGER.debug("Skipping unsupported local recipe discovery rule {}", path, exception);
		}
	}

	/** 解析解锁条件 JSON。 */
	private static UnlockCriterion parseUnlockCriterion(JsonObject criterion, Path itemTagRoot) {
		String trigger = criterion.has("trigger") ? criterion.get("trigger").getAsString() : "";
		if (trigger.equals("minecraft:tick")) return UnlockCriterion.ALWAYS;
		if (!trigger.equals("minecraft:inventory_changed")) return UnlockCriterion.NEVER;

		JsonObject conditions = criterion.getAsJsonObject("conditions");
		JsonArray predicates = conditions == null ? null : conditions.getAsJsonArray("items");
		if (predicates == null || predicates.isEmpty()) return UnlockCriterion.ANY_DISCOVERED_ITEM;

		List<Set<String>> requiredItems = new ArrayList<>();
		for (JsonElement predicateElement : predicates) {
			JsonObject predicate = predicateElement.getAsJsonObject();
			Set<String> accepted = resolveItemReferences(predicate.get("items"), itemTagRoot);
			if (!accepted.isEmpty()) requiredItems.add(accepted);
		}
		return requiredItems.isEmpty() ? UnlockCriterion.NEVER : new UnlockCriterion(false, false, List.copyOf(requiredItems));
	}

	/** 展开物品/标签引用。 */
	private static Set<String> resolveItemReferences(JsonElement items, Path itemTagRoot) {
		if (items == null) return Set.of();
		Set<String> resolved = new LinkedHashSet<>();
		if (items.isJsonArray()) {
			for (JsonElement item : items.getAsJsonArray()) resolveItemReference(item.getAsString(), itemTagRoot, resolved, new LinkedHashSet<>());
		} else {
			resolveItemReference(items.getAsString(), itemTagRoot, resolved, new LinkedHashSet<>());
		}
		return Set.copyOf(resolved);
	}

	/** 解析单个引用（防环）。 */
	private static void resolveItemReference(String reference, Path itemTagRoot, Set<String> destination, Set<String> visitedTags) {
		if (!reference.startsWith("#")) {
			destination.add(reference);
			return;
		}

		String tagName = reference.substring(1);
		if (!visitedTags.add(tagName)) return;
		Identifier tagId = Identifier.tryParse(tagName);
		if (tagId == null) return;
		int previousSize = destination.size();
		TagKey<Item> tagKey = TagKey.create(Registries.ITEM, tagId);
		for (Holder<Item> holder : BuiltInRegistries.ITEM.getTagOrEmpty(tagKey)) {
			destination.add(BuiltInRegistries.ITEM.getKey(holder.value()).toString());
		}
		if (destination.size() > previousSize || itemTagRoot == null || !tagId.getNamespace().equals("minecraft")) return;

		Path tagFile = itemTagRoot.resolve(tagId.getPath() + ".json");
		if (!Files.exists(tagFile)) return;
		try (Reader reader = Files.newBufferedReader(tagFile)) {
			JsonArray values = JsonParser.parseReader(reader).getAsJsonObject().getAsJsonArray("values");
			for (JsonElement valueElement : values) {
				String value = valueElement.isJsonObject()
					? valueElement.getAsJsonObject().get("id").getAsString()
					: valueElement.getAsString();
				resolveItemReference(value, itemTagRoot, destination, visitedTags);
			}
		} catch (Exception exception) {
			KitClient.LOGGER.debug("Could not resolve local item tag {}", tagName, exception);
		}
	}

	/** 解码一条配方文件。 */
	private static void decodeRecipe(Path path, Path recipeRoot, RegistryOps<JsonElement> ops, List<DecodedRecipe> destination) {
		try (Reader reader = Files.newBufferedReader(path)) {
			JsonElement json = JsonParser.parseReader(reader);
			DataResult<Recipe<?>> result = Recipe.CODEC.parse(ops, json);
			result.resultOrPartial(message -> KitClient.LOGGER.debug("Skipping local recipe {}: {}", path, message))
				.ifPresent(recipe -> {
					String relative = recipeRoot.relativize(path).toString().replace('\\', '/');
					String id = "minecraft:" + relative.substring(0, relative.length() - ".json".length());
					destination.add(new DecodedRecipe(id, recipe));
				});
		} catch (Exception exception) {
			KitClient.LOGGER.debug("Skipping unsupported local recipe {}", path, exception);
		}
	}

	/** 解码后的配方 id 与对象。 */
	private record DecodedRecipe(String id, Recipe<?> recipe) {
	}

	/** 注入用的本地显示条。 */
	private record LocalEntry(RecipeDisplayEntry entry, List<Ingredient> ingredients, Set<String> resultItems, UnlockRule unlockRule, String primaryResultId) {
	}

	/** 解锁规则：条件组。 */
	private record UnlockRule(List<List<UnlockCriterion>> requirements) {
		boolean matches(Set<String> discovered) {
			return !requirements.isEmpty() && requirements.stream()
				.allMatch(group -> group.stream().anyMatch(criterion -> criterion.matches(discovered)));
		}
	}

	/** 单条解锁条件。 */
	private record UnlockCriterion(boolean always, boolean anyDiscoveredItem, List<Set<String>> requiredItems) {
		private static final UnlockCriterion ALWAYS = new UnlockCriterion(true, false, List.of());
		private static final UnlockCriterion NEVER = new UnlockCriterion(false, false, List.of());
		private static final UnlockCriterion ANY_DISCOVERED_ITEM = new UnlockCriterion(false, true, List.of());

		boolean matches(Set<String> discovered) {
			if (always) return true;
			if (anyDiscoveredItem) return !discovered.isEmpty();
			return !requiredItems.isEmpty() && requiredItems.stream()
				.allMatch(accepted -> accepted.stream().anyMatch(discovered::contains));
		}
	}

	public enum RecipeMode {
		RELATED("相关"),
		READY("齐料"),
		ALL("全部");

		private final String label;

		RecipeMode(String label) {
			this.label = label;
		}

		/** 条件/规则显示标签。 */
		public String label() {
			return label;
		}

		static RecipeMode fromConfig(String value) {
			try {
				return RecipeMode.valueOf(value);
			} catch (Exception ignored) {
				return RELATED;
			}
		}
	}
}
