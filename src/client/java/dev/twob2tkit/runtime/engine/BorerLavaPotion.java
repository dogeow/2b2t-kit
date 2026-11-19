package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.component.DataComponents;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.alchemy.PotionContents;
import net.minecraft.world.item.alchemy.Potions;

/** One ordinary drink per lava contact, then yield immediately to the retreat handler. */
final class BorerLavaPotion {
	private LocalPlayer owner;
	private boolean attempted, holding;
	private int source = -1, selected = -1, previous = -1, started;
	private ItemStack displaced = ItemStack.EMPTY, original = ItemStack.EMPTY;
	private InteractionHand hand;

	static boolean drinkable(ItemStack stack) {
		if (!stack.is(Items.POTION)) return false;
		PotionContents contents = stack.get(DataComponents.POTION_CONTENTS);
		return contents != null && (contents.is(Potions.FIRE_RESISTANCE) || contents.is(Potions.LONG_FIRE_RESISTANCE));
	}

	boolean tick(Minecraft c, LocalPlayer p, DefaultTunnelBorerEngine engine) {
		if (p != owner || !p.isInLava()) reset(c);
		if (!p.isInLava()) return false;
		owner = p;
		if (p.hasEffect(MobEffects.FIRE_RESISTANCE)) { finish(c,p); return false; }
		if (attempted) {
			if (!holding) return false;
			if (p.tickCount-started >= 45 || !p.isUsingItem() || p.getUsedItemHand()!=hand
					|| !drinkable(p.getUseItem())) {
				finish(c,p);
				return false;
			}
		} else {
			attempted = true;
			if (p.containerMenu!=p.inventoryMenu || c.gui.screen()!=null) return false;
			var inv=p.getInventory();
			previous=inv.getSelectedSlot();
			if (drinkable(p.getMainHandItem())) hand=InteractionHand.MAIN_HAND;
			else if (drinkable(p.getOffhandItem())) hand=InteractionHand.OFF_HAND;
			else {
				int slot=0;
				while (slot<36 && !drinkable(inv.getItem(slot))) slot++;
				if (slot==36) return false;
				hand=InteractionHand.MAIN_HAND;
				selected=slot<9 ? slot : previous;
				if (slot>=9) {
					source=slot;
					displaced=inv.getItem(selected).copy();
					original=inv.getItem(slot).copy();
					c.gameMode.handleContainerInput(p.inventoryMenu.containerId,slot,selected,ContainerInput.SWAP,p);
				}
				inv.setSelectedSlot(selected);
			}
			if (!drinkable(p.getItemInHand(hand))) { finish(c,p); return false; }
			if (p.isUsingItem() && (p.getUsedItemHand()!=hand || !drinkable(p.getUseItem())))
				c.gameMode.releaseUsingItem(p);
			if (!p.isUsingItem() && !c.gameMode.useItem(p,hand).consumesAction()) { finish(c,p); return false; }
			holding=true;
			started=p.tickCount;
		}
		engine.releaseMine(c);
		c.options.keyShift.setDown(false);
		c.options.keyUse.setDown(true);
		engine.overlay(c,"落入岩浆，正在喝抗火药水",0xFFFF55);
		return true;
	}

	private void finish(Minecraft c,LocalPlayer p) {
		if (holding) c.options.keyUse.setDown(false);
		holding=false;
		var inv=p.getInventory();
		if (selected>=0 && inv.getSelectedSlot()==selected) {
			if (source>=9 && c.gameMode!=null && p.containerMenu==p.inventoryMenu
					&& c.gui.screen()==null && ItemStack.matches(inv.getItem(source),displaced)
					&& (ItemStack.matches(inv.getItem(selected),original) || inv.getItem(selected).is(Items.GLASS_BOTTLE))) {
				c.gameMode.handleContainerInput(p.inventoryMenu.containerId,source,selected,ContainerInput.SWAP,p);
			}
			inv.setSelectedSlot(previous);
		}
		selected=source=previous=-1;
		displaced=original=ItemStack.EMPTY;
	}

	void reset(Minecraft c) {
		if (owner!=null && c.player==owner) finish(c,owner);
		else {
			if (holding) c.options.keyUse.setDown(false);
			holding=false;
			selected=source=previous=-1;
			displaced=original=ItemStack.EMPTY;
		}
		attempted=false;
		owner=null;
	}
}
