package dev.twob2tkit.mixin;

import dev.twob2tkit.recipe.LocalRecipeBookInjector;
import net.minecraft.client.ClientRecipeBook;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.CycleButton;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.recipebook.CraftingRecipeBookComponent;
import net.minecraft.client.gui.screens.recipebook.RecipeBookComponent;
import net.minecraft.client.input.MouseButtonEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.world.inventory.RecipeBookMenu;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.util.List;

/**
 * 注入目标：{@link RecipeBookComponent}（配方书 UI）。
 * <p>
 * 注入点：
 * <ul>
 *   <li>{@code initVisuals} — {@code TAIL}：原版过滤按钮建好后替换为本 Mod 显示模式按钮</li>
 *   <li>{@code extractRenderState} — {@code TAIL}：绘制自定义模式按钮</li>
 *   <li>{@code mouseClicked} — {@code HEAD}（可取消）：优先把点击交给模式按钮</li>
 * </ul>
 * 为何在这些时机：TAIL 才能复用原版过滤按钮的坐标尺寸；绘制与点击必须单独挂上，
 * 否则自定义按钮不可见/点不到。仅对合成配方书组件生效。
 */
@Mixin(RecipeBookComponent.class)
public abstract class RecipeBookFilterButtonMixin {
	@Shadow protected CycleButton<Boolean> filterButton;
	@Shadow protected Minecraft minecraft;
	@Shadow @Final protected RecipeBookMenu menu;
	@Shadow private ClientRecipeBook book;
	@Unique private CycleButton<LocalRecipeBookInjector.RecipeMode> kit$modeButton;

	/** 增强开启时隐藏原版过滤键，装上「相关 / 齐料 / 全部」模式切换，并注入本地配方。 */
	@Inject(method = "initVisuals", at = @At("TAIL"))
	private void kit$installDiscoveryFilter(CallbackInfo info) {
		if (!((Object) this instanceof CraftingRecipeBookComponent)) return;
		if (!LocalRecipeBookInjector.isEnhancementEnabled()) {
			kit$modeButton = null;
			return;
		}

		int x = filterButton.getX();
		int y = filterButton.getY();
		int width = filterButton.getWidth();
		int height = filterButton.getHeight();
		filterButton.visible = false;
		book.setFiltering(menu.getRecipeBookType(), false);

		kit$modeButton = CycleButton.builder(
			mode -> Component.literal(mode.label()),
			LocalRecipeBookInjector.mode()
		).withValues(List.of(
			LocalRecipeBookInjector.RecipeMode.RELATED,
			LocalRecipeBookInjector.RecipeMode.READY,
			LocalRecipeBookInjector.RecipeMode.ALL
		)).withTooltip(mode -> Tooltip.create(Component.literal(switch (mode) {
			case RELATED -> "相关：按照原版生存解锁条件显示";
			case READY -> "齐料：每一种必要材料都曾经获得过才显示";
			case ALL -> "全部：显示客户端自带的全部原版配方。背包是 2×2，末影箱等 3×3 配方仍会列出，实际要去工作台做";
		}))).displayState(CycleButton.DisplayState.VALUE).create(
			x, y, width, height, Component.literal("配方显示范围"),
			(button, mode) -> LocalRecipeBookInjector.setMode(minecraft, mode)
		);

		if (LocalRecipeBookInjector.inject(minecraft)) {
			((RecipeBookComponent<?>) (Object) this).recipesUpdated();
		}
	}

	/** 在原版配方书抽取之后绘制模式切换按钮。 */
	@Inject(method = "extractRenderState", at = @At("TAIL"))
	private void kit$renderModeButton(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta, CallbackInfo info) {
		if (kit$modeButton != null) kit$modeButton.extractRenderState(graphics, mouseX, mouseY, delta);
	}

	/** 优先把鼠标点击交给模式按钮；点中则取消后续原版处理。 */
	@Inject(method = "mouseClicked", at = @At("HEAD"), cancellable = true)
	private void kit$clickModeButton(MouseButtonEvent event, boolean doubleClick, CallbackInfoReturnable<Boolean> info) {
		if (kit$modeButton != null && kit$modeButton.mouseClicked(event, doubleClick)) info.setReturnValue(true);
	}
}
