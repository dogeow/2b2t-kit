package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;

/** Game-window event metadata only: never stores keys, button values, characters or input text. */
public final class GameInteractionClock {
    private static final State state=new State();
    private GameInteractionClock(){}
    static final class State {
        private long serial,lastInteraction,lastUiMotion;
        synchronized void interaction(long now){serial++;lastInteraction=Math.max(lastInteraction,now);}
        synchronized void uiMotion(long now){lastUiMotion=Math.max(lastUiMotion,now);}
        synchronized long serial(){return serial;}
        synchronized long idle(long now){long last=Math.max(lastInteraction,lastUiMotion);return now<last?0:now-last;}
        synchronized JsonObject snapshot(long now){var j=new JsonObject();j.addProperty("interaction_serial",serial);j.addProperty("last_interaction_at",lastInteraction);j.addProperty("last_ui_motion_at",lastUiMotion);j.addProperty("idle_ms",idle(now));return j;}
    }
    private static boolean gameWindow(Minecraft c,long window){return c!=null&&c.player!=null&&c.level!=null&&c.isWindowActive()&&c.getWindow().handle()==window;}
    public static void interaction(Minecraft c,long window){if(gameWindow(c,window))state.interaction(System.currentTimeMillis());}
    public static void guiMotion(Minecraft c,long window){if(gameWindow(c,window)&&c.gui.screen()!=null)state.uiMotion(System.currentTimeMillis());}
    public static long serial(){return state.serial();}
    public static long idleMillis(long now){return state.idle(now);}
    static JsonObject snapshot(){return state.snapshot(System.currentTimeMillis());}
}
