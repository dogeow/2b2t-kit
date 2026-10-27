package dev.twob2tkit.chat.mixin;

import dev.twob2tkit.chat.BilingualClient;
import dev.twob2tkit.chat.ChatHistory;
import net.minecraft.client.gui.components.ChatComponent;
import net.minecraft.client.multiplayer.chat.GuiMessage;
import net.minecraft.network.chat.Component;
import org.spongepowered.asm.mixin.Final;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.util.List;

@Mixin(ChatComponent.class)
public abstract class ChatComponentMixin implements ChatHistory {
    @Shadow @Final private List<GuiMessage> allMessages;
    @Shadow private int chatScrollbarPos;
    @Shadow private boolean newMessageSinceScroll;
    @Shadow protected abstract void refreshTrimmedMessages();
    @Shadow public abstract void scrollChat(int amount);

    @Inject(method = "addMessageToQueue", at = @At("TAIL"))
    private void mcbilingual$received(GuiMessage message, CallbackInfo ci) {
        BilingualClient.onDisplayedMessage(message);
    }

    @Override
    public boolean mcbilingual$replace(GuiMessage original, Component content) {
        return mcbilingual$replaceTracked(original, content) != null;
    }

    @Override public boolean mcbilingual$contains(GuiMessage original) {
        return allMessages.stream().anyMatch(message -> message == original);
    }

    @Override
    public GuiMessage mcbilingual$replaceTracked(GuiMessage original, Component content) {
        for (int i = 0; i < allMessages.size(); i++) {
            // Identity prevents duplicate text, deletion markers, and old sessions from matching.
            if (allMessages.get(i) != original) continue;
            GuiMessage replacement = new GuiMessage(original.addedTime(), content,
                    original.signature(), original.source(), original.tag());
            allMessages.set(i, replacement);
            int scroll = chatScrollbarPos;
            boolean unread = newMessageSinceScroll;
            refreshTrimmedMessages();
            chatScrollbarPos = scroll;
            scrollChat(0); // Clamp after translation-only mode shortens the history.
            newMessageSinceScroll = unread;
            return replacement;
        }
        return null; // Cleared, deleted, or aged out: do not resurrect it.
    }
}
