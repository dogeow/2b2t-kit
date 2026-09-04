package dev.twob2tkit.recipe;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.core.registries.Registries;
import net.minecraft.resources.Identifier;
import net.minecraft.tags.TagKey;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Stream;
import dev.twob2tkit.KitClient;

/** 本地原版配方缓存，供指南与配方书增强。 */
public final class LocalRecipes {
	private static List<Entry> entries;
	private static Set<String> craftableOutputs = Set.of();

	/** 本地原版配方缓存（不伪造服务器编号）。 */
	private LocalRecipes() {
	}

	/** 全部已加载配方。 */
	public static synchronized List<Entry> entries() {
		if (entries == null) entries = loadVanillaRecipes();
		return entries;
	}

	/** 是否已有该结果配方。 */
	public static boolean hasRecipe(Item item) {
		if (item == null) return false;
		entries();
		return craftableOutputs.contains(BuiltInRegistries.ITEM.getKey(item).toString());
	}

	/** 加载后整理分类。 */
	private static List<Entry> finalizeEntries(List<Entry> loaded) {
		Set<String> outputs = new HashSet<>();
		for (Entry entry : loaded) {
			outputs.add(BuiltInRegistries.ITEM.getKey(entry.output().getItem()).toString());
		}
		craftableOutputs = Set.copyOf(outputs);
		return List.copyOf(loaded);
	}

	/** 从数据包/内置读原版配方。 */
	private static List<Entry> loadVanillaRecipes() {
		try {
			Path recipeRoot = FabricLoader.getInstance().getModContainer("minecraft")
				.flatMap(container -> container.findPath("data/minecraft/recipe"))
				.orElseThrow();
			Path tagRoot = FabricLoader.getInstance().getModContainer("minecraft")
				.flatMap(container -> container.findPath("data/minecraft/tags/item"))
				.orElse(null);
			List<Entry> loaded = new ArrayList<>();
			try (Stream<Path> files = Files.walk(recipeRoot)) {
				files.filter(path -> path.toString().endsWith(".json"))
					.forEach(path -> loadRecipe(path, recipeRoot, tagRoot, loaded));
			}
			loaded.sort(Comparator.comparing(entry -> entry.output().getHoverName().getString(), String.CASE_INSENSITIVE_ORDER));
			if (!loaded.isEmpty()) {
				KitClient.LOGGER.info("Loaded {} local vanilla crafting recipes", loaded.size());
				return finalizeEntries(loaded);
			}
		} catch (Exception exception) {
			KitClient.LOGGER.warn("Could not load bundled vanilla recipes; using common fallback recipes", exception);
		}
		return fallbackRecipes();
	}

	/** 解析单条配方 JSON。 */
	private static void loadRecipe(Path path, Path recipeRoot, Path tagRoot, List<Entry> destination) {
		try (Reader reader = Files.newBufferedReader(path)) {
			JsonObject json = JsonParser.parseReader(reader).getAsJsonObject();
			String type = json.get("type").getAsString();
			boolean shaped = type.equals("minecraft:crafting_shaped");
			boolean shapeless = type.equals("minecraft:crafting_shapeless");
			if (!shaped && !shapeless) return;

			ItemStack output = parseResult(json.get("result"));
			if (output.isEmpty()) return;
			ItemStack[] grid = emptyGrid();
			if (shaped) fillShapedGrid(json, tagRoot, grid);
			else fillShapelessGrid(json, tagRoot, grid);

			String relative = recipeRoot.relativize(path).toString().replace('\\', '/');
			String id = "minecraft:" + relative.substring(0, relative.length() - ".json".length());
			String name = output.getHoverName().getString() + (output.getCount() > 1 ? " ×" + output.getCount() : "");
			String description = shaped ? "原版有序合成：按图摆放" : "原版无序合成：材料位置不限";
			String category = json.has("category") ? json.get("category").getAsString() : "misc";
			destination.add(new Entry(id, name, output, grid, description, category));
		} catch (Exception exception) {
			KitClient.LOGGER.debug("Skipping unsupported local recipe {}", path, exception);
		}
	}

	/** 解析产物。 */
	private static ItemStack parseResult(JsonElement resultElement) {
		if (resultElement == null) return ItemStack.EMPTY;
		String id;
		int count = 1;
		if (resultElement.isJsonPrimitive()) {
			id = resultElement.getAsString();
		} else {
			JsonObject result = resultElement.getAsJsonObject();
			JsonElement idElement = result.has("id") ? result.get("id") : result.get("item");
			if (idElement == null) return ItemStack.EMPTY;
			id = idElement.getAsString();
			if (result.has("count")) count = result.get("count").getAsInt();
		}
		Identifier identifier = Identifier.tryParse(id);
		if (identifier == null || !BuiltInRegistries.ITEM.containsKey(identifier)) return ItemStack.EMPTY;
		return new ItemStack(BuiltInRegistries.ITEM.getValue(identifier), Math.max(1, count));
	}

	/** 填有序合成格。 */
	private static void fillShapedGrid(JsonObject json, Path tagRoot, ItemStack[] grid) {
		JsonObject keys = json.getAsJsonObject("key");
		JsonArray pattern = json.getAsJsonArray("pattern");
		for (int row = 0; row < Math.min(3, pattern.size()); row++) {
			String line = pattern.get(row).getAsString();
			for (int column = 0; column < Math.min(3, line.length()); column++) {
				char symbol = line.charAt(column);
				if (symbol == ' ' || !keys.has(Character.toString(symbol))) continue;
				grid[row * 3 + column] = parseIngredient(keys.get(Character.toString(symbol)), tagRoot);
			}
		}
	}

	/** 无序配方材料填进 3×3 预览。 */
	private static void fillShapelessGrid(JsonObject json, Path tagRoot, ItemStack[] grid) {
		JsonArray ingredients = json.getAsJsonArray("ingredients");
		for (int index = 0; index < Math.min(9, ingredients.size()); index++) {
			grid[index] = parseIngredient(ingredients.get(index), tagRoot);
		}
	}

	/** 解析材料 JSON 或字符串。 */
	private static ItemStack parseIngredient(JsonElement element, Path tagRoot) {
		if (element == null) return ItemStack.EMPTY;
		if (element.isJsonArray()) {
			for (JsonElement choice : element.getAsJsonArray()) {
				ItemStack stack = parseIngredient(choice, tagRoot);
				if (!stack.isEmpty()) return stack;
			}
			return ItemStack.EMPTY;
		}
		if (element.isJsonObject()) {
			JsonObject object = element.getAsJsonObject();
			if (object.has("item")) return parseIngredient(object.get("item"), tagRoot);
			if (object.has("tag")) return parseIngredient("#" + object.get("tag").getAsString(), tagRoot);
			return ItemStack.EMPTY;
		}
		return parseIngredient(element.getAsString(), tagRoot);
	}

	/** 解析材料 JSON 或字符串。 */
	private static ItemStack parseIngredient(String value, Path tagRoot) {
		if (!value.startsWith("#")) {
			Identifier id = Identifier.tryParse(value);
			return id != null && BuiltInRegistries.ITEM.containsKey(id)
				? new ItemStack(BuiltInRegistries.ITEM.getValue(id))
				: ItemStack.EMPTY;
		}
		String tagName = value.substring(1);
		Identifier tagId = Identifier.tryParse(tagName);
		if (tagId == null) return ItemStack.EMPTY;
		TagKey<Item> key = TagKey.create(Registries.ITEM, tagId);
		for (Holder<Item> holder : BuiltInRegistries.ITEM.getTagOrEmpty(key)) return new ItemStack(holder.value());
		return resolveLocalTag(tagName, tagRoot, new HashSet<>());
	}

	/** 解析本地物品标签。 */
	private static ItemStack resolveLocalTag(String tagName, Path tagRoot, Set<String> visited) {
		if (tagRoot == null || !visited.add(tagName)) return ItemStack.EMPTY;
		Identifier id = Identifier.tryParse(tagName);
		if (id == null || !id.getNamespace().equals("minecraft")) return ItemStack.EMPTY;
		Path file = tagRoot.resolve(id.getPath() + ".json");
		if (!Files.exists(file)) return ItemStack.EMPTY;
		try (Reader reader = Files.newBufferedReader(file)) {
			JsonArray values = JsonParser.parseReader(reader).getAsJsonObject().getAsJsonArray("values");
			for (JsonElement element : values) {
				String value = element.isJsonObject() ? element.getAsJsonObject().get("id").getAsString() : element.getAsString();
				if (value.startsWith("#")) {
					ItemStack nested = resolveLocalTag(value.substring(1), tagRoot, visited);
					if (!nested.isEmpty()) return nested;
				} else {
					ItemStack item = parseIngredient(value, null);
					if (!item.isEmpty()) return item;
				}
			}
		} catch (Exception ignored) {
		}
		return ItemStack.EMPTY;
	}

	/** 空的 3×3 预览格。 */
	private static ItemStack[] emptyGrid() {
		ItemStack[] stacks = new ItemStack[9];
		for (int i = 0; i < stacks.length; i++) stacks[i] = ItemStack.EMPTY;
		return stacks;
	}

	/** 内置兜底配方列表。 */
	private static List<Entry> fallbackRecipes() {
		return finalizeEntries(List.of(
			fallback("minecraft:oak_planks", "木板 ×4", new ItemStack(Items.OAK_PLANKS, 4), grid(null, null, null, null, Items.OAK_LOG, null, null, null, null), "任意原木均可", "building"),
			fallback("minecraft:crafting_table", "工作台", new ItemStack(Items.CRAFTING_TABLE), grid(Items.OAK_PLANKS, Items.OAK_PLANKS, null, Items.OAK_PLANKS, Items.OAK_PLANKS, null, null, null, null), "4 个木板摆成 2×2", "misc"),
			fallback("minecraft:furnace", "熔炉", new ItemStack(Items.FURNACE), grid(Items.COBBLESTONE, Items.COBBLESTONE, Items.COBBLESTONE, Items.COBBLESTONE, null, Items.COBBLESTONE, Items.COBBLESTONE, Items.COBBLESTONE, Items.COBBLESTONE), "8 个圆石围一圈", "misc"),
			fallback("minecraft:smoker", "烟熏炉", new ItemStack(Items.SMOKER), grid(null, Items.OAK_LOG, null, Items.OAK_LOG, Items.FURNACE, Items.OAK_LOG, null, Items.OAK_LOG, null), "熔炉居中，上下左右各 1 个原木", "food")
		));
	}

	/** 构造一条兜底配方。 */
	private static Entry fallback(String id, String name, ItemStack output, ItemStack[] grid, String description, String category) {
		return new Entry(id, name, output, grid, description, category);
	}

	/** 可变参数物品排成网格。 */
	private static ItemStack[] grid(net.minecraft.world.level.ItemLike... items) {
		ItemStack[] stacks = new ItemStack[9];
		for (int i = 0; i < stacks.length; i++) stacks[i] = items[i] == null ? ItemStack.EMPTY : new ItemStack(items[i]);
		return stacks;
	}

	/** 一条本地配方。 */
	public record Entry(String id, String name, ItemStack output, ItemStack[] grid, String description, String category) {
		/** 指南 tab 分类。 */
		public String tabCategory() {
			return RecipeCategoryPolicy.displayCategory(category, isBlockOutput(), isFoodOutput());
		}

		/** 是否匹配分类筛选。 */
		public boolean matchesCategory(String filter) {
			return RecipeCategoryPolicy.matches(filter, category, isBlockOutput(), isFoodOutput());
		}

		/** 产物是否方块。 */
		private boolean isBlockOutput() {
			return output.getItem() instanceof BlockItem;
		}

		/** 产物是否食物。 */
		private boolean isFoodOutput() {
			return output.has(DataComponents.FOOD);
		}

		/** 是否匹配搜索关键字。 */
		public boolean matches(String query) {
			String normalized = query.trim().toLowerCase(Locale.ROOT);
			if (normalized.isEmpty()) return false;
			if (name.toLowerCase(Locale.ROOT).contains(normalized) || id.toLowerCase(Locale.ROOT).contains(normalized)) {
				return true;
			}
			if (output.getHoverName().getString().toLowerCase(Locale.ROOT).contains(normalized)) return true;
			for (ItemStack stack : grid) {
				if (stack == null || stack.isEmpty()) continue;
				if (stack.getHoverName().getString().toLowerCase(Locale.ROOT).contains(normalized)) return true;
			}
			return false;
		}
	}
}
