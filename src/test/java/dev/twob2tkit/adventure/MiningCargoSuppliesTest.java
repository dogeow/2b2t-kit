package dev.twob2tkit.adventure;

import net.minecraft.core.component.DataComponents;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class MiningCargoSuppliesTest {
	@BeforeAll static void bootstrap() {
		net.minecraft.SharedConstants.tryDetectVersion(); net.minecraft.server.Bootstrap.bootStrap();
		// 26.1 initializes item components during resource loading, after registry bootstrap.
		var lookup = net.minecraft.data.registries.VanillaRegistries.createLookup();
		net.minecraft.core.registries.BuiltInRegistries.DATA_COMPONENT_INITIALIZERS.build(lookup)
			.forEach(net.minecraft.core.component.DataComponentInitializers.PendingComponents::apply);
	}
	private ItemStack stack(Item item, int count) { return new ItemStack(item, count); }
	private ActivityRequirements.Requirement need(String match, int count) {
		return ActivityRequirements.requirement(ActivityRequirements.need(match, match, count));
	}
	@Test void pumpkinsAndOtherOrdinaryDropsAreNotMistakenForSupplies() {
		for (var item : List.of(Items.PUMPKIN, Items.WHEAT_SEEDS, Items.POPPY, Items.OAK_SAPLING, Items.OAK_LOG,
			Items.SANDSTONE, Items.FLINT, Items.GUNPOWDER, Items.DIAMOND, Items.RAW_COPPER))
			assertFalse(MiningCargoSupplies.alwaysKeep(stack(item, 8)), item.toString());
	}
	@Test void foodLightingEquipmentAndEmergencyItemsSurviveUnloading() {
		for (var item : List.of(Items.BREAD, Items.COOKED_BEEF, Items.ENCHANTED_GOLDEN_APPLE, Items.MELON_SLICE,
			Items.TORCH, Items.SOUL_TORCH, Items.REDSTONE_TORCH, Items.DIAMOND_PICKAXE, Items.IRON_SHOVEL,
			Items.IRON_AXE, Items.BOW, Items.CROSSBOW, Items.SHIELD, Items.DIAMOND_HELMET, Items.ELYTRA,
			Items.ARROW, Items.SPECTRAL_ARROW, Items.TIPPED_ARROW, Items.WATER_BUCKET, Items.BUCKET,
			Items.POTION, Items.SPLASH_POTION, Items.TOTEM_OF_UNDYING, Items.ENDER_PEARL, Items.FIREWORK_ROCKET))
			assertTrue(MiningCargoSupplies.alwaysKeep(stack(item, 1)), item.toString());
	}
	@Test void carriedContainersAndSpecialItemsAreProtected() {
		for (var item : List.of(Items.CHEST, Items.TRAPPED_CHEST, Items.ENDER_CHEST, Items.SHULKER_BOX, Items.BUNDLE,
			Items.ENCHANTED_BOOK, Items.CARVED_PUMPKIN)) assertTrue(MiningCargoSupplies.alwaysKeep(stack(item, 1)), item.toString());
		var named = stack(Items.PUMPKIN, 8); named.set(DataComponents.CUSTOM_NAME, Component.literal("纪念品"));
		assertTrue(MiningCargoSupplies.alwaysKeep(named));
	}
	@Test void checklistBuildingReserveIs128AndSurplusStillGoesToChest() {
		var bag = List.of(stack(Items.STONE, 64), stack(Items.DIRT, 64), stack(Items.DIRT, 64), stack(Items.COBBLESTONE, 64));
		assertArrayEquals(new boolean[]{false,true,true,false}, MiningCargoSupplies.reserve(bag, List.of(),
			List.of(need("building_blocks", 128), need("building_blocks", 64))));
	}
	@Test void editableChecklistQuantityAndSplitStacksAreRespected() {
		var bag = List.of(stack(Items.DIRT, 32), stack(Items.DIRT, 48), stack(Items.STONE, 64), stack(Items.STONE, 64));
		assertArrayEquals(new boolean[]{true,true,true,false}, MiningCargoSupplies.reserve(bag, List.of(), List.of(need("building_blocks", 128))));
		assertArrayEquals(new boolean[]{true,true,true,true}, MiningCargoSupplies.reserve(bag, List.of(), List.of(need("building_blocks", 192))));
	}
	@Test void logsAndCraftingTableKeepOnlyTheWholeStacksNeededByTheChecklist() {
		var bag = List.of(stack(Items.OAK_LOG, 32), stack(Items.OAK_LOG, 64), stack(Items.CRAFTING_TABLE, 1), stack(Items.CRAFTING_TABLE, 1), stack(Items.PUMPKIN, 8));
		assertArrayEquals(new boolean[]{false,true,true,false,false}, MiningCargoSupplies.reserve(bag, List.of(),
			List.of(need("item:minecraft:oak_log", 16), need("item:minecraft:crafting_table", 1))));
	}
	@Test void coalAndSticksReserveDoNotGrowEveryTimeTheInventoryIsRescanned() {
		var bag = new java.util.ArrayList<>(List.of(stack(Items.COAL, 16), stack(Items.COAL, 64), stack(Items.STICK, 16), stack(Items.STICK, 8)));
		var needs = List.of(need("item:minecraft:coal",16), need("item:minecraft:stick",16));
		assertArrayEquals(new boolean[]{false,true,true,false}, MiningCargoSupplies.reserve(bag,List.of(),needs));
		bag.set(0,ItemStack.EMPTY); bag.set(3,ItemStack.EMPTY);
		assertArrayEquals(new boolean[]{false,true,true,false}, MiningCargoSupplies.reserve(bag,List.of(),needs));
	}
	@Test void equippedAndAlreadyProtectedStacksFulfillRequirementsWithoutExtraReservations() {
		var bag = List.of(stack(Items.DIRT,64), stack(Items.DIRT,64), stack(Items.BREAD,32), stack(Items.BREAD,32));
		assertArrayEquals(new boolean[]{true,false,true,true}, MiningCargoSupplies.reserve(bag,List.of(stack(Items.DIRT,64)),
			List.of(need("building_blocks",128), need("food",32))));
	}
	@Test void customNonstandardRequirementIsReservedAndUnrelatedDropsRemainCargo() {
		var bag = List.of(stack(Items.PUMPKIN,8), stack(Items.PUMPKIN,32), stack(Items.POPPY,5));
		assertArrayEquals(new boolean[]{false,true,false}, MiningCargoSupplies.reserve(bag,List.of(),List.of(need("item:minecraft:pumpkin",16))));
	}
}
