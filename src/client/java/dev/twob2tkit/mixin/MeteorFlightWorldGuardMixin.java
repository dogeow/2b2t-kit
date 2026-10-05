package dev.twob2tkit.mixin;

import dev.twob2tkit.compat.ClientWorldGuard;
import net.minecraft.client.player.LocalPlayer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/** Configuration-start GameLeft can arrive after Minecraft has cleared its player. */
@Pseudo
@Mixin(targets = "meteordevelopment.meteorclient.systems.modules.movement.Flight", remap = false)
public abstract class MeteorFlightWorldGuardMixin {
	@Redirect(method = "onDeactivate()V", at = @At(value = "INVOKE",
		target = "Lnet/minecraft/client/player/LocalPlayer;isSpectator()Z", remap = false), require = 0, remap = false)
	private boolean kit$skipMissingPlayerAbilities(LocalPlayer player) {
		// A lazy lambda must not dereference a null receiver before the policy runs.
		return ClientWorldGuard.spectatorOrMissingPlayer(player, () -> player.isSpectator());
	}
}
