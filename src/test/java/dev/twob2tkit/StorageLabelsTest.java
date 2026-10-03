package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import dev.twob2tkit.storage.StorageLabels;

final class StorageLabelsTest {
	private static KitConfig.StorageSnapshot snapshot(KitConfig.StoredItem... items) {
		var result = new KitConfig.StorageSnapshot();
		result.items = new java.util.ArrayList<>(java.util.Arrays.asList(items));
		return result;
	}
	private static KitConfig.StoredItem item(String id, String name, int count) {
		return new KitConfig.StoredItem("minecraft:" + id, name, count);
	}

	@Test
	void ironSearchShowsEachMatchedTypeWithoutCountingPickaxesAsIngots() {
		var data = snapshot(item("iron_ingot", "铁锭", 20), item("raw_iron", "粗铁", 6),
			item("iron_pickaxe", "铁镐", 1), item("iron_ingot", "铁锭", 8), item("stone", "石头", 64));
		assertEquals("开箱缓存：铁锭×28 · 粗铁×6 · 铁镐×1", StorageLabels.quantitySummary(data, "铁"));
		assertEquals("开箱缓存：铁锭×28", StorageLabels.quantitySummary(data, "铁锭"));
		assertEquals(5, data.items.size());
		assertEquals(20, data.items.getFirst().count);
	}

	@Test
	void idSearchIsCaseInsensitiveAndUsesAllTerms() {
		var data = snapshot(item("iron_ingot", "铁锭", 28), item("raw_iron", "粗铁", 6));
		assertEquals("开箱缓存：铁锭×28", StorageLabels.quantitySummary(data, "  IRON  INGOT "));
		assertEquals("开箱缓存：粗铁×6", StorageLabels.quantitySummary(data, "minecraft:raw_iron"));
	}

	@Test
	void emptyQueryOrLocationOnlyMatchShowsTotalCachedQuantityAndDistinctTypes() {
		var data = snapshot(item("iron_ingot", "铁锭", 20), item("iron_ingot", "铁锭", 8), item("raw_iron", "粗铁", 6));
		assertEquals("开箱缓存：2 类 · 共 34 件", StorageLabels.quantitySummary(data, ""));
		assertEquals("开箱缓存：2 类 · 共 34 件", StorageLabels.quantitySummary(data, "761019"));
		assertEquals("开箱缓存：2 类 · 共 34 件", StorageLabels.quantitySummary(data, null));
	}

	@Test
	void shortSummaryRetainsQuantitiesAndSignalsAdditionalMatchedTypes() {
		var data = snapshot(item("iron_ingot", "铁锭", 28), item("raw_iron", "粗铁", 6),
			item("iron_pickaxe", "铁镐", 1), item("iron_axe", "铁斧", 2), item("iron_sword", "铁剑", 1));
		assertEquals("开箱缓存：铁锭×28 · 粗铁×6 · 铁镐×1 · 另 2 类", StorageLabels.quantitySummary(data, "铁"));
	}

	@Test
	void missingLabelsEmptyRowsAndLargeTotalsRemainAccurate() {
		var data = snapshot(item("iron_ingot", "", 28), null, item("stone", "石头", 0), item("dirt", "泥土", -1));
		assertEquals("开箱缓存：minecraft:iron_ingot×28", StorageLabels.quantitySummary(data, "iron"));
		assertEquals("开箱缓存：空箱", StorageLabels.quantitySummary(snapshot(), "铁"));
		assertEquals("开箱缓存：空箱", StorageLabels.quantitySummary(null, ""));
		data = snapshot(item("iron_ingot", "铁锭", Integer.MAX_VALUE), item("iron_ingot", "铁锭", 1));
		assertEquals("开箱缓存：铁锭×2147483648", StorageLabels.quantitySummary(data, "铁锭"));
	}
	@Test
	void signLinesAreJoinedWithoutEmptyRows() {
		assertEquals("小麦 种子", StorageLabels.joinSignLines("小麦", "", "种子", "  "));
		assertEquals("", StorageLabels.joinSignLines("", " ", null));
	}

	@Test
	void dyeIdsHaveChineseLabels() {
		assertEquals("红", StorageLabels.colorLabel("red"));
		assertEquals("浅蓝", StorageLabels.colorLabel("light_blue"));
		assertEquals("铜", StorageLabels.colorLabel("copper"));
		assertEquals("", StorageLabels.colorLabel(""));
	}
    @Test void queryShowsCachedCountAndItsContentTimeInsteadOfStructuralVerificationTime() {
        var data=snapshot(item("coal","煤炭",192));data.server="example.com";data.status="active";
        data.lastSeenEpochMillis=1_700_000_000_000L;data.lastStructureObservedAt=1_900_000_000_000L;
        var summary=StorageLabels.cacheSummary(data,"煤炭");
        org.junit.jupiter.api.Assertions.assertTrue(summary.startsWith("开箱缓存：煤炭×192 · 内容 "));
        org.junit.jupiter.api.Assertions.assertTrue(summary.endsWith(StorageLabels.contentTime(data)));
        data.contentsDirty=true;data.contentsDirtyReason="Withdrawal not confirmed";
        org.junit.jupiter.api.Assertions.assertTrue(StorageLabels.cacheSummary(data,"coal").endsWith(" · 待确认"));
        org.junit.jupiter.api.Assertions.assertTrue(StorageLabels.evidenceSummary(data).contains("Withdrawal not confirmed"));
        org.junit.jupiter.api.Assertions.assertTrue(StorageLabels.evidenceSummary(data).contains("实际取料以服务器槽位为准"));
        assertEquals(192,data.items.getFirst().count);
    }
}
