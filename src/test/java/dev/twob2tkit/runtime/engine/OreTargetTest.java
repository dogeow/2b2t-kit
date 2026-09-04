package dev.twob2tkit.runtime.engine;

import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.server.Bootstrap;
import net.minecraft.SharedConstants;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** 锁住勾选矿种：只选煤时不能把铁矿或粗铁当目标、掉落物。 */
final class OreTargetTest {
	@BeforeAll
	static void bootstrapMinecraftRegistries() {
		SharedConstants.tryDetectVersion();
		Bootstrap.bootStrap();
	}

	@Test
	void coalOnlyDoesNotMatchIronBlocks() {
		assertTrue(OreTarget.selectedMatches("COAL", Blocks.COAL_ORE.defaultBlockState()));
		assertTrue(OreTarget.selectedMatches("COAL", Blocks.DEEPSLATE_COAL_ORE.defaultBlockState()));
		assertFalse(OreTarget.selectedMatches("COAL", Blocks.IRON_ORE.defaultBlockState()));
		assertFalse(OreTarget.selectedMatches("COAL", Blocks.DEEPSLATE_IRON_ORE.defaultBlockState()));
	}

	@Test
	void coalOnlyDoesNotMatchIronDrops() {
		assertTrue(OreTarget.selectedMatchesDropItem("COAL", Items.COAL));
		assertFalse(OreTarget.selectedMatchesDropItem("COAL", Items.RAW_IRON));
		assertFalse(OreTarget.selectedMatchesDropItem("COAL", Items.IRON_ORE));
	}

	@Test
	void anyResolvesToTheConcreteOreThatWasActuallyMined() {
		assertTrue(OreTarget.firstMatching("ANY", Blocks.DIAMOND_ORE.defaultBlockState()) == OreTarget.DIAMOND);
		assertTrue(OreTarget.firstMatching("ANY", Blocks.COAL_ORE.defaultBlockState()) == OreTarget.COAL);
	}

	@Test
	void multiSelectionKeepsAdjacentOreTypesDistinct() {
		assertTrue(OreTarget.firstMatching("COAL,DIAMOND", Blocks.COAL_ORE.defaultBlockState()) == OreTarget.COAL);
		assertTrue(OreTarget.firstMatching("COAL,DIAMOND", Blocks.DIAMOND_ORE.defaultBlockState()) == OreTarget.DIAMOND);
	}
}
