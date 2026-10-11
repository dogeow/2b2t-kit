package xaero.map.gui.dropdown.rightclick;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import xaero.map.gui.IRightClickableElement;
/** Handwritten compile-only signatures, not a replacement or copy of Xaero code. */
public abstract class RightClickOption {
    protected RightClickOption(String name,int index,IRightClickableElement target) {}
    public abstract void onAction(Screen screen);
    public Component getDisplayName(){throw new UnsupportedOperationException("compile-only API");}
    public RightClickOption setActive(boolean active){throw new UnsupportedOperationException("compile-only API");}
}
