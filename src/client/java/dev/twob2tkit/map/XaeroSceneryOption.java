package dev.twob2tkit.map;

import dev.twob2tkit.KitClient;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.Level;
import xaero.map.gui.IRightClickableElement;
import xaero.map.gui.dropdown.rightclick.RightClickOption;

/** Configure scenery capture centred on this map click. */
public final class XaeroSceneryOption extends RightClickOption {
    private final int x, z;
    private final ResourceKey<Level> dimension;
    private final ClientLevel openedLevel;

    public XaeroSceneryOption(Object target, int index, int x, int z, ResourceKey<Level> dimension) {
        super("twob2tkit.scenery_here",index,(IRightClickableElement)target);
        this.x=x;
        this.z=z;
        this.dimension=dimension;
        openedLevel=Minecraft.getInstance().level;
        setActive(available(Minecraft.getInstance()));
    }

    private boolean available(Minecraft client) {
        return client.player!=null && !client.player.isDeadOrDying() && client.level!=null
            && client.level==openedLevel && dimension!=null
            && MapCruiseTarget.allowed(client.level.dimension().identifier().toString(),
                dimension.identifier().toString(),x,z);
    }

    @Override public Component getDisplayName() {
        return Component.literal("Kit 以这里为圆心预加载风景");
    }

    @Override public void onAction(Screen screen) {
        var client=Minecraft.getInstance();
        if (available(client)) KitClient.openMapScenery(client,screen,x,z);
    }
}
