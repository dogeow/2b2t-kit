package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.ArrayList;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoPolicyTest {
	private BorerCargoPolicy.Stack stack(String id, int count) { return new BorerCargoPolicy.Stack("minecraft:" + id, count, false); }
	@Test void currentHostStoresEveryOrdinaryDropWithoutExpandingDiscardRules() {
		for (String id : List.of("minecraft:pumpkin", "minecraft:wheat_seeds", "minecraft:poppy", "minecraft:oak_log", "minecraft:gunpowder", "example:raw_ore")) {
			var drops = List.of(new BorerCargoPolicy.Stack(id,8,false,false,true));
			assertEquals(0,BorerCargoPolicy.next(drops,false),id);
			assertEquals(-1,BorerCargoPolicy.next(drops,true),id);
		}
	}
	@Test void checklistMaskProtectsSuppliesFromBothDepositAndDiscard() {
		var bag = List.of(new BorerCargoPolicy.Stack("minecraft:dirt",64,false,true,true),
			new BorerCargoPolicy.Stack("minecraft:cobblestone",64,false,true,true),
			new BorerCargoPolicy.Stack("minecraft:pumpkin",8,false,false,true),
			new BorerCargoPolicy.Stack("minecraft:stone",64,false,false,true));
		assertArrayEquals(new boolean[]{true,true,false,false},BorerCargoPolicy.reservedForStore(bag));
		assertEquals(2,BorerCargoPolicy.next(bag,false));assertEquals(3,BorerCargoPolicy.next(bag,true));
		assertEquals(-1,BorerCargoPolicy.next(bag,false,i->i<2));
	}
	@Test void specialItemsRemainProtectedEvenWhenNoChecklistRuleMatches() {
		var bag = List.of(new BorerCargoPolicy.Stack("minecraft:pumpkin",8,true,false,true));
		assertEquals(-1,BorerCargoPolicy.next(bag,false));assertEquals(-1,BorerCargoPolicy.next(bag,true));
	}
	@Test void olderHostWithoutSupplyMaskRemainsOnTheSafeMaterialOnlyPolicy() {
		assertEquals(-1,BorerCargoPolicy.next(List.of(stack("pumpkin",8),stack("chest",2),stack("bread",64)),false));
	}
	@Test void sandstoneIsDepositedButTheDiscardWhitelistIsNotExpanded(){
		for(String id:List.of("sandstone","red_sandstone")){
			assertTrue(BorerCargoPolicy.material("minecraft:"+id));assertFalse(BorerCargoPolicy.stone("minecraft:"+id));
			assertEquals(0,BorerCargoPolicy.next(List.of(stack(id,64)),false));assertEquals(-1,BorerCargoPolicy.next(List.of(stack(id,64)),true));
		}
	}
	@Test void dirtReserveLetsAllPlainStoneAndSandstoneEnterTheChest(){
		var bag=List.of(stack("stone",64),stack("sandstone",64),stack("dirt",64),stack("cobblestone",64));
		assertArrayEquals(new boolean[]{false,false,true,false},BorerCargoPolicy.reservedForStore(bag));
		assertEquals(0,BorerCargoPolicy.next(bag,false));
		assertEquals(1,BorerCargoPolicy.next(bag,false,i->i!=0));
		assertEquals(-1,BorerCargoPolicy.next(bag,false,i->i==2));
	}
	@Test void preferOneFullReserveStackOverSeveralPartiallyFilledSlots(){
		assertArrayEquals(new boolean[]{false,true,false},BorerCargoPolicy.reservedForStore(List.of(stack("dirt",10),stack("cobblestone",64),stack("stone",64))));
		assertArrayEquals(new boolean[]{true,false},BorerCargoPolicy.reservedForStore(List.of(stack("stone",64),stack("stone",32))));
	}
	@Test void ordinaryStonesAreExplicitlyRecognisedButEveryOreAndToolIsSafeFromDiscard() {
		for (String id : BorerCargoPolicy.STONE) assertTrue(BorerCargoPolicy.stone("minecraft:" + id));
		for (String id : List.of("lapis_lazuli", "lapis_block", "gold_ore", "raw_gold", "gold_ingot", "diamond", "deepslate_diamond_ore",
			"redstone", "emerald", "coal", "quartz", "ancient_debris", "diamond_pickaxe", "bow", "arrow", "water_bucket", "chest")) {
			assertFalse(BorerCargoPolicy.stone("minecraft:" + id), id);
		}
		assertFalse(BorerCargoPolicy.stone("custom:stone"));
	}
	@Test void dropsOnlySurplusStoneAndKeepsOneStackOfBuildingMaterial() {
		var stacks = List.of(stack("cobblestone", 64), stack("lapis_lazuli", 64), stack("deepslate", 64), stack("gold_ingot", 64));
		assertEquals(2, BorerCargoPolicy.next(stacks, true));
		assertEquals(1, BorerCargoPolicy.next(stacks, false));
	}
	@Test void reserveWorksAcrossSplitStacksAndDifferentStoneTypes() {
		var stacks = List.of(stack("stone", 32), stack("tuff", 32), stack("granite", 64));
		assertArrayEquals(new boolean[]{true, true, false}, BorerCargoPolicy.reserved(stacks));
		assertEquals(2, BorerCargoPolicy.next(stacks, true));
	}
	@Test void storageKeepsEquipmentSuppliesChestsAndCoalReserve() {
		var stacks = new ArrayList<BorerCargoPolicy.Stack>();
		for (String id : List.of("diamond_pickaxe", "bow", "arrow", "torch", "bread", "water_bucket", "chest", "coal", "cobblestone")) stacks.add(stack(id, 64));
		assertEquals(-1, BorerCargoPolicy.next(stacks, false));
		stacks.add(stack("coal", 64));
		assertEquals(9, BorerCargoPolicy.next(stacks, false));
	}
	@Test void namedOrModifiedResourcesAreNeverAutomaticallyTransferred() {
		var stacks = List.of(new BorerCargoPolicy.Stack("minecraft:stone", 64, true), new BorerCargoPolicy.Stack("minecraft:diamond", 64, true));
		assertEquals(-1, BorerCargoPolicy.next(stacks, true));
		assertEquals(-1, BorerCargoPolicy.next(stacks, false));
	}
	@Test void onlyNearFullBagsTriggerAndStationIsOutsideEvenAtNegativeCoordinates() {
		assertFalse(BorerCargoPolicy.nearFull(4)); assertTrue(BorerCargoPolicy.nearFull(3)); assertTrue(BorerCargoPolicy.nearFull(0));
		assertFalse(BorerCargoPolicy.outside(-5, -5, -10, -10, 0, 0));
		assertFalse(BorerCargoPolicy.outside(-13, -5, -10, -10, 0, 0));
		assertTrue(BorerCargoPolicy.outside(-14, -5, -10, -10, 0, 0));
		assertTrue(BorerCargoPolicy.outside(-5, 4, -10, -10, 0, 0));
	}
}
