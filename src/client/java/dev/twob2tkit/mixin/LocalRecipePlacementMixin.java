package dev.twob2tkit.mixin;

import dev.twob2tkit.recipe.LocalRecipeBookInjector;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractRecipeBookScreen;
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.crafting.display.RecipeDisplay;
import net.minecraft.world.item.crafting.display.RecipeDisplayId;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 注入目标：{@link MultiPlayerGameMode#handlePlaceRecipe}。
 * <p>
 * 注入点：{@code HEAD}（可取消）。
 * 为何在此时机：本地配方没有服务器认可的 {@link RecipeDisplayId}；
 * 必须在发包摆放到合成格之前拦截，改为只填客户端幽灵配方并取消原调用，
 * 避免向服务器发送伪造配方编号。
 */
@Mixin(MultiPlayerGameMode.class)
public abstract class LocalRecipePlacementMixin {
	/** 点击本地配方时只显示幽灵布局，不向服务器请求放置。 */
	@Inject(method = "handlePlaceRecipe", at = @At("HEAD"), cancellable = true)
	private void kit$showLocalGhostRecipe(int containerId, RecipeDisplayId id, boolean shift, CallbackInfo info) {
		RecipeDisplay display = LocalRecipeBookInjector.display(id);
		if (display == null) return;

		Minecraft minecraft = Minecraft.getInstance();
		if (minecraft.screen instanceof AbstractRecipeBookScreen<?> recipeScreen) {
			recipeScreen.fillGhostRecipe(display);
		}
		if (minecraft.player != null && LocalRecipeBookInjector.needsCraftingTable(display)) {
			minecraft.gui.setOverlayMessage(Component.literal("这个配方是 3×3，请打开工作台再合成").withColor(0xFFFF55), false);
		}
		info.cancel();
	}
}
