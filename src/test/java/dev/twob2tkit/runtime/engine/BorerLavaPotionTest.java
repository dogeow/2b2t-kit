package dev.twob2tkit.runtime.engine;

import net.minecraft.world.item.Items;
import net.minecraft.world.item.alchemy.PotionContents;
import net.minecraft.world.item.alchemy.Potions;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerLavaPotionTest {
	@BeforeAll static void bootstrap() {
		net.minecraft.SharedConstants.tryDetectVersion();
		net.minecraft.server.Bootstrap.bootStrap();
	}
	@Test void picksOnlyDrinkableFireResistanceAndAcceptsExtendedDuration() {
		assertTrue(BorerLavaPotion.drinkable(PotionContents.createItemStack(Items.POTION,Potions.FIRE_RESISTANCE)));
		assertTrue(BorerLavaPotion.drinkable(PotionContents.createItemStack(Items.POTION,Potions.LONG_FIRE_RESISTANCE)));
		assertFalse(BorerLavaPotion.drinkable(PotionContents.createItemStack(Items.POTION,Potions.WATER)));
		assertFalse(BorerLavaPotion.drinkable(PotionContents.createItemStack(Items.SPLASH_POTION,Potions.FIRE_RESISTANCE)));
		assertFalse(BorerLavaPotion.drinkable(PotionContents.createItemStack(Items.LINGERING_POTION,Potions.FIRE_RESISTANCE)));
	}
}
