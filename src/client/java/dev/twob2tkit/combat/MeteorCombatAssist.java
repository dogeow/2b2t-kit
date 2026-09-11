package dev.twob2tkit.combat;

import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;
import dev.twob2tkit.MeteorModules;

/** 反射打开 Meteor KillAura / AutoLog，盾构遇怪与挨打共用。 */
public final class MeteorCombatAssist {
	private MeteorCombatAssist() {
	}

	/** 打开 Meteor 杀戮光环与自动断开，并提示聊天。 */
	public static void arm(Minecraft client) {
		boolean bowOwned = dev.twob2tkit.KitClient.borerCombatLook(client) != null
			&& client.player != null && client.player.getMainHandItem().is(net.minecraft.world.item.Items.BOW);
		boolean ka = !bowOwned && MeteorModules.enable(MeteorModules.KILL_AURA);
		boolean log = MeteorModules.enable(MeteorModules.AUTO_LOG);
		if (!ka && !log) return;
		StringBuilder text = new StringBuilder("[twob2tkit] 自动保护：已打开 Meteor");
		if (ka) text.append(" 杀戮光环");
		if (log) text.append(" 自动断开");
		if (client.player != null) {
			client.player.sendSystemMessage(Component.literal(text.toString()).withColor(0x55FF55));
		}
	}
}
