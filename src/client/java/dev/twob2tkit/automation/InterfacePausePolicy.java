package dev.twob2tkit.automation;

import java.util.Set;

/** Screens without container controls pause task input while existing PvE modules keep running. */
public final class InterfacePausePolicy {
    private InterfacePausePolicy() {}
    public static boolean pauses(boolean alive,boolean screenOpen,boolean containerScreen,
                                  boolean inventoryMenu,boolean emergencyAirReturn){
        return alive&&screenOpen&&!containerScreen&&inventoryMenu&&!emergencyAirReturn;
    }
    public static boolean readOrStop(String command){
        return Set.of("stop","safe_logout","material_job_pause","snapshot","scan","scan_snow_biomes",
            "snow_seed_candidates","scan_trees","projection_audit","projection_model","map_audit","gravel_stop").contains(command);
    }
}
