package dev.twob2tkit.automation;

import com.google.gson.JsonObject;

/** Observe optional IPN cooperation without changing its saved preferences. */
public final class AutoRefillCompatibility {
    public static final int PROTOCOL=1;
    private static final Observation observation=new Observation();
    private AutoRefillCompatibility() {}
    public static boolean tick(boolean owned){return observation.tick(owned,System.currentTimeMillis());}
    private static boolean present(){
        try{Class.forName("org.anti_ad.mc.ipnext.event.autorefill.AutoRefillHandler",false,AutoRefillCompatibility.class.getClassLoader());return true;}
        catch(ClassNotFoundException absent){return false;}
        catch(LinkageError incompatible){return true;}
    }
    public static JsonObject snapshot(){return observation.snapshot(present(),AutomationBridge.ownsMaterialInventory(),System.currentTimeMillis());}
    static final class Observation {
        private boolean seen,lastOwned;
        private long lastHook,lastSuppressed,suppressedTicks;
        synchronized boolean tick(boolean owned,long now){
            seen=true;lastOwned=owned;lastHook=now;
            if(owned){lastSuppressed=now;suppressedTicks++;}
            return owned;
        }
        synchronized JsonObject snapshot(boolean present,boolean owned,long now){
            var out=new JsonObject();out.addProperty("protocol",PROTOCOL);out.addProperty("ipn_present",present);
            out.addProperty("hook_seen",seen);out.addProperty("supported",!present||seen);out.addProperty("active",owned);
            out.addProperty("suppressed",present&&owned&&seen&&lastOwned&&now>=lastHook&&now-lastHook<=1000);
            out.addProperty("suppressed_ticks",suppressedTicks);out.addProperty("last_hook_at",lastHook);out.addProperty("last_suppressed_at",lastSuppressed);
            return out;
        }
    }
}
