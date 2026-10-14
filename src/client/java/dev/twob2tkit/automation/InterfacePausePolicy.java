package dev.twob2tkit.automation;

import java.util.Set;

/** Passive screens and a player's inventory pause task input without taking over container controls. */
public final class InterfacePausePolicy {
    private InterfacePausePolicy() {}
    public static final class InventoryState {
        private boolean held;
        public boolean observe(boolean alive,boolean playerInventoryScreen,boolean inventoryMenu,boolean cursorEmpty) {
            if(!alive||!inventoryMenu)held=false;
            else if(playerInventoryScreen)held=true;
            else if(cursorEmpty)held=false;
            return held;
        }
        public boolean held(){return held;}
        public void clear(){held=false;}
    }
    public static boolean pauses(boolean alive,boolean screenOpen,boolean containerScreen,
                                  boolean inventoryMenu,boolean emergencyAirReturn){
        return alive&&screenOpen&&!containerScreen&&inventoryMenu&&!emergencyAirReturn;
    }
    public static boolean readOrStop(String command){
        return Set.of("stop","safe_logout","material_job_pause","snapshot","scan","scan_snow_biomes",
            "snow_seed_candidates","scan_trees","projection_audit","projection_model","map_audit","gravel_stop").contains(command);
    }
}
