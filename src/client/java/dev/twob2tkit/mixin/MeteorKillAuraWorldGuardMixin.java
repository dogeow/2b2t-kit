package dev.twob2tkit.mixin;

import dev.twob2tkit.compat.ClientWorldGuard;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Pseudo;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Optional Meteor compatibility: late tick delivery after auto-logout must not dereference a cleared player. */
@Pseudo
@Mixin(targets = "meteordevelopment.meteorclient.systems.modules.combat.KillAura", remap = false)
public abstract class MeteorKillAuraWorldGuardMixin {
	@Inject(method = "onTick(Lmeteordevelopment/meteorclient/events/world/TickEvent$Pre;)V", at = @At("HEAD"), cancellable = true, remap = false)
	private void kit$skipTickWithoutWorld(CallbackInfo ci) {
		Minecraft client = Minecraft.getInstance();
		if (client == null || !ClientWorldGuard.ready(client.player, client.level, client.gameMode)) ci.cancel();
	}
}
