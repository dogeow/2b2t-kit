package dev.twob2tkit.mixin;

import dev.twob2tkit.recipe.LocalRecipeBookInjector;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.recipebook.CraftingRecipeBookComponent;
import net.minecraft.client.gui.screens.recipebook.GhostSlots;
import net.minecraft.network.chat.Component;
import net.minecraft.util.context.ContextMap;
import net.minecraft.world.item.crafting.display.RecipeDisplay;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 注入目标：{@link CraftingRecipeBookComponent}（合成配方书组件）。
 * <p>
 * 注入点：
 * <ul>
 *   <li>{@code canDisplay} — {@code HEAD}（可取消）：增强开启时一律允许显示本地大配方</li>
 *   <li>{@code fillGhostRecipe} — {@code TAIL}：填完幽灵配方后提示需工作台</li>
 * </ul>
 * 为何在此时机：{@code canDisplay} 要在原版按容器尺寸过滤之前放行；
 * 提示放在填幽灵槽之后，玩家已看到布局再提示去开工作台。不向服务器伪造配方编号。
 */
@Mixin(CraftingRecipeBookComponent.class)
public abstract class CraftingRecipeDisplayMixin {
	/** 配方书增强开启时，跳过原版「背包装不下就不显示」的限制。 */
	@Inject(method = "canDisplay", at = @At("HEAD"), cancellable = true)
	private void kit$showLargeRecipesInInventoryBook(RecipeDisplay display, CallbackInfoReturnable<Boolean> info) {
		if (!LocalRecipeBookInjector.isEnhancementEnabled()) return;
		info.setReturnValue(true);
	}

	/** 若配方需要 3×3，在屏幕下方叠一句去工作台的提示。 */
	@Inject(method = "fillGhostRecipe", at = @At("TAIL"))
	private void kit$hintCraftingTable(GhostSlots slots, RecipeDisplay display, ContextMap context, CallbackInfo info) {
		if (!LocalRecipeBookInjector.needsCraftingTable(display)) return;
		Minecraft minecraft = Minecraft.getInstance();
		if (minecraft.player != null) {
			minecraft.gui.setOverlayMessage(Component.literal("这个配方是 3×3，请打开工作台再合成").withColor(0xFFFF55), false);
		}
	}
}
