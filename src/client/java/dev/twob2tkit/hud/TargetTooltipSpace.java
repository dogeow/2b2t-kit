package dev.twob2tkit.hud;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import net.fabricmc.loader.api.FabricLoader;

/** Optional Jade integration: only read public geometry, never change the user's tooltip settings. */
public final class TargetTooltipSpace {
    private static boolean initialized,unavailable;
    private static Object animation;
    private static Field rect,expected;
    private static Method x,y,width,height;
    private TargetTooltipSpace() {}
    private static void initialize() {
        if(initialized)return;
        initialized=true;
        if(!FabricLoader.getInstance().isModLoaded("jade")) {
            unavailable=FabricLoader.getInstance().isModLoaded("wthit");return;
        }
        try {
            Class<?> overlay=Class.forName("snownee.jade.overlay.OverlayRenderer");
            animation=overlay.getField("animation").get(null);
            rect=animation.getClass().getField("rect");expected=animation.getClass().getField("expectedRect");
            Class<?> type=rect.getType();x=type.getMethod("getX");y=type.getMethod("getY");width=type.getMethod("getWidth");height=type.getMethod("getHeight");
        }catch(ReflectiveOperationException|LinkageError e){unavailable=true;}
    }
    private static HudPlacement.Rect read(Field field)throws ReflectiveOperationException {
        Object r=field.get(animation);
        return new HudPlacement.Rect(((Number)x.invoke(r)).doubleValue(),((Number)y.invoke(r)).doubleValue(),((Number)width.invoke(r)).doubleValue(),((Number)height.invoke(r)).doubleValue());
    }
    public static int top(int panelX,int panelWidth,int panelHeight,int screenHeight) {
        initialize();
        // Unknown tooltip layout: omit our optional line rather than cover the block information.
        if(unavailable)return -1;
        try{return animation==null?HudPlacement.below(panelX,panelWidth,panelHeight,screenHeight):HudPlacement.below(panelX,panelWidth,panelHeight,screenHeight,read(rect),read(expected));}
        catch(ReflectiveOperationException|RuntimeException e){return -1;}
    }
}
