package dev.twob2tkit.adventure;

import dev.twob2tkit.KitConfig;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import static org.junit.jupiter.api.Assertions.*;

class ActivityRequirementsTest {
	@Test
	void miningDefaultsIncludeToolsWaterFireProtectionRangedAndLighting() {
		var list = ActivityRequirements.copyDefault(ActivityRequirements.Profile.MINING);
		for (String id : new String[]{"tag:minecraft:pickaxes", "item:minecraft:water_bucket", "fire_resistance",
			"ranged_weapon", "tag:minecraft:arrows", "item:minecraft:torch", "building_blocks", "food", "item:minecraft:shield"}) {
			assertTrue(list.needs.stream().anyMatch(n -> n.match.equals(id)), id);
		}
		assertEquals(2, list.needs.stream().filter(n -> n.match.equals("tag:minecraft:pickaxes")).findFirst().orElseThrow().target);
	}
	@Test
	void migrationPreservesEditedCountsAndDoesNotReinsertLaterRemovedEntries() {
		var mining = new KitConfig.ActivityList();
		mining.id = "MINING"; mining.label = "我的挖矿准备";
		mining.needs = new ArrayList<>();
		mining.needs.add(ActivityRequirements.need("item:minecraft:torch", "火把", 12));
		mining.needs.add(ActivityRequirements.need("fire_resistance", "自定义抗火", 8));
		int version = ActivityRequirements.migrateMining(mining, 0);
		assertEquals(12, mining.needs.stream().filter(n -> n.match.equals("item:minecraft:torch")).findFirst().orElseThrow().target);
		assertEquals(8, mining.needs.stream().filter(n -> n.match.equals("fire_resistance")).findFirst().orElseThrow().target);
		assertEquals(1, mining.needs.stream().filter(n -> n.match.equals("fire_resistance")).count());
		mining.needs.removeIf(n -> n.match.equals("ranged_weapon"));
		ActivityRequirements.migrateMining(mining, version);
		assertFalse(mining.needs.stream().anyMatch(n -> n.match.equals("ranged_weapon")));
		assertEquals("我的挖矿准备", mining.label);
	}
}
