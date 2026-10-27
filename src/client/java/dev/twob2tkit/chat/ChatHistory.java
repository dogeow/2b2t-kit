package dev.twob2tkit.chat;

import net.minecraft.client.multiplayer.chat.GuiMessage;
import net.minecraft.network.chat.Component;

/** All calls belong on Minecraft's client thread. */
public interface ChatHistory {
    boolean mcbilingual$replace(GuiMessage original, Component content);
    GuiMessage mcbilingual$replaceTracked(GuiMessage original, Component content);
    boolean mcbilingual$contains(GuiMessage original);
}
