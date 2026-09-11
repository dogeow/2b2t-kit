package dev.twob2tkit.mixin;

import dev.twob2tkit.KitClient;
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.phys.BlockHitResult;

/**
 * 注入目标：{@link MultiPlayerGameMode}。
 * <p>
 * 注入点：
 * <ul>
 *   <li>{@code continueDestroyBlock} — {@code HEAD}：盾构连续挖时清掉原版挖完空挥延迟</li>
 *   <li>{@code useItemOn} — {@code HEAD}：记录玩家点击的容器坐标供开箱助手用</li>
 * </ul>
 * 为何在此时机：延迟要在原版读到 {@code destroyDelay} 之前清零，否则仍会空挥数拍；
 * 容器点击要在交互真正发出前记下坐标。
 */
@Mixin(MultiPlayerGameMode.class)
public abstract class MultiPlayerGameModeMixin {
	@Shadow
	private int destroyDelay;
	/** Revalidate only the toolkit-owned bow release; manual use and other item types remain vanilla. */
	@Inject(method = "releaseUsingItem", at = @At("HEAD"), cancellable = true)
	private void kit$visibleBowRelease(net.minecraft.world.entity.player.Player player, CallbackInfo info) {
		if (!KitClient.prepareBowRelease(net.minecraft.client.Minecraft.getInstance(), player)) info.cancel();
	}

	/** 盾构正在破坏时，去掉原版挖完一块后的空挥延迟，避免动画停在同一格。 */
	@Inject(method = "continueDestroyBlock", at = @At("HEAD"))
	private void kit$skipBreakDelay(BlockPos pos, Direction direction, CallbackInfoReturnable<Boolean> info) {
		if (this.destroyDelay > 0 && KitClient.borerIsBreaking()) this.destroyDelay = 0;
	}

	/** 对手持物品右键方块时，记下命中方块坐标（存储/开箱补货）。 */
	@Inject(method = "useItemOn", at = @At("HEAD"))
	private void kit$rememberStorageClick(
		LocalPlayer player, InteractionHand hand, BlockHitResult hit, CallbackInfoReturnable<InteractionResult> info
	) {
		if (player == null || hit == null) return;
		dev.twob2tkit.automation.ProfessionalPrinter.noteInteraction(player,hand,hit);
		KitClient.noteStorageClick(hit.getBlockPos());
	}
}
