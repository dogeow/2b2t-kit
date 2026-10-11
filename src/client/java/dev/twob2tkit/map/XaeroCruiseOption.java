package dev.twob2tkit.map;

import dev.twob2tkit.KitClient;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceKey;
import net.minecraft.world.level.Level;
import xaero.map.gui.IRightClickableElement;
import xaero.map.gui.dropdown.rightclick.RightClickOption;

/** Loaded only by the optional Xaero context-menu hook. */
public final class XaeroCruiseOption extends RightClickOption {
    private final int x,z;
    private final ResourceKey<Level> dimension;
    private final ClientLevel openedLevel;
    public XaeroCruiseOption(Object target,int index,int x,int z,ResourceKey<Level> dimension){
        super("twob2tkit.cruise_here",index,(IRightClickableElement)target);
        this.x=x;this.z=z;this.dimension=dimension;openedLevel=Minecraft.getInstance().level;
        setActive(available());
    }
    private boolean available(){
        var c=Minecraft.getInstance();
        return c.player!=null&&!c.player.isDeadOrDying()&&c.level!=null&&c.level==openedLevel
            &&dimension!=null&&MapCruiseTarget.allowed(c.level.dimension().identifier().toString(),
                dimension.identifier().toString(),x,z);
    }
    @Override public Component getDisplayName(){return Component.literal("Kit 巡航到这里");}
    @Override public void onAction(Screen screen){
        var c=Minecraft.getInstance();
        if(!available())return;
        // User selection takes over through the same path as Kit's saved-place navigation.
        KitClient.controller().start(c,x+.5,z+.5,KitClient.config().cruiseY);
        KitClient.controller().keepConnectedOnArrival();
        if(KitClient.controller().isActive())c.setScreen(null);
    }
}
