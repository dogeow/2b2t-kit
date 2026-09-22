package dev.twob2tkit.automation;

import com.google.gson.JsonObject;

/** Optional IPN integration is verified before unattended inventory changes. */
public final class CraftingCompatibility {
    private static boolean tickHookSeen;
    private CraftingCompatibility(){}
    public static void tickHookSeen(){tickHookSeen=true;}
    private static boolean ipnPresent(){
        try{Class.forName("org.anti_ad.mc.ipnext.event.ContinuousCraftingHandler",false,CraftingCompatibility.class.getClassLoader());return true;}
        catch(ClassNotFoundException absent){return false;}
        catch(LinkageError incompatible){return true;}
    }
    public static void requireReady(){
        if(ipnPresent()&&!tickHookSeen)throw new IllegalStateException("Inventory Profiles Next crafting isolation is not verified; restart with a compatible Kit before automatic crafting");
    }
    public static JsonObject snapshot(){var j=new JsonObject();j.addProperty("ipn_present",ipnPresent());j.addProperty("ipn_tick_hook_seen",tickHookSeen);j.addProperty("supported",!ipnPresent()||tickHookSeen);j.addProperty("active",AutomationBridge.ownsMaterialInventory());return j;}
}
